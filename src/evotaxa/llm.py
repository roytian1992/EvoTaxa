from __future__ import annotations

import json
import os
import hashlib
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evotaxa.config import LLMConfig
from evotaxa.io import iter_jsonl, write_jsonl
from evotaxa.prompts import render_prompt

try:
    from json_repair import repair_json
except ImportError:  # pragma: no cover - exercised only when optional dependency is missing.
    repair_json = None


@dataclass
class LLMRecord:
    task: str
    provider: str
    model: str
    used_model: bool
    prompt: str
    output: dict[str, Any]
    error: str = ""
    cache_key: str = ""
    cache_hit: bool = False
    schema_valid: bool = True
    json_repaired: bool = False
    attempts: int = 1

    def to_record(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "provider": self.provider,
            "model": self.model,
            "used_model": self.used_model,
            "prompt": self.prompt,
            "output": self.output,
            "error": self.error,
            "cache_key": self.cache_key,
            "cache_hit": self.cache_hit,
            "schema_valid": self.schema_valid,
            "json_repaired": self.json_repaired,
            "attempts": self.attempts,
        }


class LLMClient:
    def complete_json(self, *, task: str, prompt: str, fallback: dict[str, Any]) -> LLMRecord:
        raise NotImplementedError


class DeterministicLLMClient(LLMClient):
    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def complete_json(self, *, task: str, prompt: str, fallback: dict[str, Any]) -> LLMRecord:
        return LLMRecord(
            task=task,
            provider="deterministic",
            model="fallback",
            used_model=False,
            prompt=prompt,
            output=fallback,
            cache_key=_cache_key("deterministic", "fallback", task, prompt),
        )


class OpenAICompatJSONClient(LLMClient):
    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.api_key = config.api_key or os.environ.get(config.api_key_env, "")
        self.cache: dict[str, LLMRecord] = {}
        self._lock = threading.RLock()
        self.system_prompt = render_prompt(config.system_prompt_id, prompt_dir=config.prompt_dir)
        if config.cache_path and config.cache_path.exists():
            for row in iter_jsonl(config.cache_path):
                key = str(row.get("cache_key") or "")
                if key:
                    self.cache[key] = _record_from_row(row)

    def complete_json(self, *, task: str, prompt: str, fallback: dict[str, Any]) -> LLMRecord:
        key = _cache_key(
            self.config.provider,
            self.config.model,
            task,
            prompt,
            request_options={
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
                "extra_body": self.config.extra_body,
                "system_prompt": self.system_prompt,
            },
        )
        with self._lock:
            cached = self.cache.get(key)
        if cached is not None:
            return _cache_hit_record(cached, prompt=prompt, cache_key=key)
        enabled_tasks = set(self.config.enabled_tasks)
        if not enabled_tasks:
            return LLMRecord(
                task=task,
                provider=self.config.provider,
                model=self.config.model,
                used_model=False,
                prompt=prompt,
                output=fallback,
                error="No LLM tasks enabled.",
                cache_key=key,
            )
        if "*" not in enabled_tasks and task not in enabled_tasks:
            return LLMRecord(
                task=task,
                provider=self.config.provider,
                model=self.config.model,
                used_model=False,
                prompt=prompt,
                output=fallback,
                error="Task not enabled for model calls.",
                cache_key=key,
            )
        if not self.api_key:
            return LLMRecord(
                task=task,
                provider=self.config.provider,
                model=self.config.model,
                used_model=False,
                prompt=prompt,
                output=fallback,
                error=f"Missing API key env: {self.config.api_key_env}",
                cache_key=key,
            )

        base_url = self.config.base_url.rstrip("/") or "https://api.openai.com/v1"
        url = f"{base_url}/chat/completions"
        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.config.extra_body:
            payload.update(self.config.extra_body)
        if self.config.max_tokens > 0:
            payload["max_tokens"] = self.config.max_tokens
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        last_error = ""
        max_attempts = max(1, self.config.max_retries)
        for attempt in range(1, max_attempts + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                    raw = json.loads(response.read().decode("utf-8"))
                choice = raw["choices"][0]
                content = choice["message"]["content"]
                finish_reason = str(choice.get("finish_reason") or "")
                try:
                    output, repaired = _loads_json_object(content)
                except ValueError as exc:
                    last_error = (
                        f"Failed to parse JSON content; finish_reason={finish_reason or 'unknown'}; "
                        f"{exc}; content_excerpt={_compact_excerpt(content)}"
                    )
                    continue
                schema_valid = _schema_valid(task, output)
                if not schema_valid:
                    last_error = (
                        f"LLM output failed schema validation; finish_reason={finish_reason or 'unknown'}; "
                        f"content_excerpt={_compact_excerpt(content)}"
                    )
                    continue
                record = LLMRecord(
                    task=task,
                    provider=self.config.provider,
                    model=self.config.model,
                    used_model=True,
                    prompt=prompt,
                    output=output,
                    error="",
                    cache_key=key,
                    schema_valid=schema_valid,
                    json_repaired=repaired,
                    attempts=attempt,
                )
                self._store(record)
                return record
            except (urllib.error.URLError, KeyError, json.JSONDecodeError, TimeoutError) as exc:
                last_error = str(exc)
        return LLMRecord(
                task=task,
                provider=self.config.provider,
                model=self.config.model,
                used_model=False,
                prompt=prompt,
                output=fallback,
                error=last_error,
                cache_key=key,
                schema_valid=False,
                attempts=max_attempts,
            )

    def _store(self, record: LLMRecord) -> None:
        with self._lock:
            existing = self.cache.get(record.cache_key)
            if existing is not None:
                return
            self.cache[record.cache_key] = record
            if not self.config.cache_path:
                return
            path = Path(self.config.cache_path)
            rows = [item.to_record() for item in self.cache.values()]
            write_jsonl(path, rows)


def _cache_hit_record(cached: LLMRecord, *, prompt: str, cache_key: str) -> LLMRecord:
    return LLMRecord(
        task=cached.task,
        provider=cached.provider,
        model=cached.model,
        used_model=cached.used_model,
        prompt=prompt,
        output=cached.output,
        error=cached.error,
        cache_key=cache_key,
        cache_hit=True,
        schema_valid=cached.schema_valid,
        json_repaired=cached.json_repaired,
        attempts=cached.attempts,
    )


def build_llm_client(config: LLMConfig) -> LLMClient:
    if config.provider in {"openai", "openai_compat", "openai-compatible"}:
        return OpenAICompatJSONClient(config)
    return DeterministicLLMClient(config)


def judge_taxonomy_candidate(
    client: LLMClient,
    *,
    candidate: dict[str, Any],
    context: str,
) -> LLMRecord:
    fallback = {
        "accept": bool(candidate.get("support_documents")),
        "confidence": min(0.9, float(candidate.get("trigger_score") or 0.0) + 0.2),
        "rationale": candidate.get("reason") or "Deterministic fallback based on trigger score and support.",
        "suggested_label": candidate.get("proposed_label") or "",
    }
    prompt = _render_llm_prompt(
        client,
        "llm/taxonomy_candidate_judge",
        {
            "candidate": candidate,
            "context": context[:4000],
        },
    )
    return client.complete_json(task="taxonomy_candidate_judge", prompt=prompt, fallback=fallback)


def judge_edge_evidence(
    client: LLMClient,
    *,
    edge: dict[str, Any],
    source_text: str,
    target_text: str,
    relation_schema: dict[str, Any] | None = None,
    evidence_schema: dict[str, Any] | None = None,
) -> LLMRecord:
    edge_type = str(edge.get("edge_type") or "")
    relation_spec = (relation_schema or {}).get(edge_type) if isinstance(relation_schema, dict) else {}
    evidence_slots = _edge_evidence_slots(edge=edge, relation_spec=relation_spec, evidence_schema=evidence_schema)
    fallback = {
        "edge_type": edge_type,
        "confidence": edge.get("confidence", 0.0),
        "evidence": {
            slot: (edge.get("evidence") or {}).get(slot) or {}
            for slot in evidence_slots
        },
        "rationale": "Deterministic fallback preserving cue-based extraction.",
    }
    for slot, value in fallback["evidence"].items():
        fallback[slot] = value
    prompt = _render_llm_prompt(
        client,
        "llm/edge_evidence_judge",
        {
            "relation_schema": relation_schema or {},
            "evidence_schema": evidence_schema or {},
            "evidence_slots": evidence_slots,
            "edge": edge,
            "source_text": source_text[:3000],
            "target_text": target_text[:3000],
        },
    )
    return client.complete_json(task="edge_evidence_judge", prompt=prompt, fallback=fallback)


def extract_relation_for_pair(
    client: LLMClient,
    *,
    pair: dict[str, Any],
    source_text: str,
    target_text: str,
    relation_schema: dict[str, Any],
    evidence_schema: dict[str, Any],
) -> LLMRecord:
    fallback = {
        "accept": False,
        "edge_type": "background",
        "confidence": 0.0,
        "evidence": {},
        "rationale": "Deterministic fallback: schema-guided relation extraction task was not run.",
        "negative_rationale": "No model evidence available.",
    }
    prompt = _render_llm_prompt(
        client,
        "llm/relation_extraction",
        {
            "pair": pair,
            "relation_schema": relation_schema,
            "evidence_schema": evidence_schema,
            "source_text": source_text[:3500],
            "target_text": target_text[:3500],
        },
    )
    return client.complete_json(task="relation_extraction", prompt=prompt, fallback=fallback)


def extract_relations_for_pairs(
    client: LLMClient,
    *,
    pairs: list[dict[str, Any]],
    document_texts: dict[str, str],
    relation_schema: dict[str, Any],
    evidence_schema: dict[str, Any],
) -> LLMRecord:
    fallback = {
        "relations": [
            {
                "pair_index": index,
                "accept": False,
                "edge_type": "background",
                "confidence": 0.0,
                "evidence": {},
                "rationale": "Deterministic fallback: schema-guided relation extraction task was not run.",
                "negative_rationale": "No model evidence available.",
                "rejection_reason": "model_not_run",
            }
            for index, _ in enumerate(pairs)
        ]
    }
    prompt_pairs = []
    for index, pair in enumerate(pairs):
        source_doc = str(pair.get("source_document") or "")
        target_doc = str(pair.get("target_document") or "")
        prompt_pairs.append(
            {
                "pair_index": index,
                "pair": pair,
                "source_text": document_texts.get(source_doc, "")[:2500],
                "target_text": document_texts.get(target_doc, "")[:2500],
            }
        )
    prompt = _render_llm_prompt(
        client,
        "llm/relation_extraction_batch",
        {
            "relation_schema": relation_schema,
            "evidence_schema": evidence_schema,
            "pairs": prompt_pairs,
        },
    )
    return client.complete_json(task="relation_extraction_batch", prompt=prompt, fallback=fallback)


def extract_successor_edges_for_pairs(
    client: LLMClient,
    *,
    pairs: list[dict[str, Any]],
    allowed_relation_types: list[str],
) -> LLMRecord:
    fallback = {
        "edges": [
            {
                "pair_index": index,
                "accept": False,
                "relation_type": "background",
                "confidence": 0.0,
                "evidence": {
                    "mechanism": {"description": "", "quote": "", "quote_source": "target"},
                    "methodological_problem": {"description": "", "quote": "", "quote_source": "target"},
                    "tradeoff": {"description": "", "quote": "", "quote_source": "target"},
                },
                "rationale": "Deterministic fallback: successor edge extraction task was not run.",
                "rejection_reason": "model_not_run",
            }
            for index, _ in enumerate(pairs)
        ]
    }
    prompt = _render_llm_prompt(
        client,
        "llm/successor_edge_batch",
        {
            "pairs": pairs,
            "allowed_relation_types": allowed_relation_types,
        },
    )
    return client.complete_json(task="successor_edge_batch", prompt=prompt, fallback=fallback)


def infer_relation_schema(
    client: LLMClient,
    *,
    domain_id: str,
    entity_types: list[str],
    strong_edge_types: list[str],
    sample_documents: list[dict[str, Any]],
    fixed_schema: dict[str, Any],
    max_relation_types: int,
) -> LLMRecord:
    fallback = {"relation_types": [{"edge_type": edge_type, **spec} for edge_type, spec in fixed_schema.items()]}
    prompt = _render_llm_prompt(
        client,
        "llm/relation_schema_inference",
        {
            "domain_id": domain_id,
            "entity_types": entity_types,
            "strong_edge_types": strong_edge_types,
            "max_relation_types": max_relation_types,
            "fixed_schema": fixed_schema,
            "sample_documents": json.dumps(sample_documents, ensure_ascii=False)[:5000],
        },
    )
    return client.complete_json(task="relation_schema_inference", prompt=prompt, fallback=fallback)


def infer_entity_evidence_schema(
    client: LLMClient,
    *,
    domain_id: str,
    taxonomy_dimensions: list[str],
    configured_entity_types: list[str],
    fixed_entity_schema: dict[str, Any],
    fixed_evidence_schema: dict[str, Any],
    sample_documents: list[dict[str, Any]],
) -> LLMRecord:
    fallback = {
        "entity_types": [{"entity_type": entity_type, **spec} for entity_type, spec in fixed_entity_schema.items()],
        "evidence_slots": [{"slot": slot, **spec} for slot, spec in fixed_evidence_schema.items()],
    }
    prompt = _render_llm_prompt(
        client,
        "llm/entity_evidence_schema_inference",
        {
            "domain_id": domain_id,
            "taxonomy_dimensions": taxonomy_dimensions,
            "configured_entity_types": configured_entity_types,
            "fixed_entity_schema": fixed_entity_schema,
            "fixed_evidence_schema": fixed_evidence_schema,
            "sample_documents": json.dumps(sample_documents, ensure_ascii=False)[:5000],
        },
    )
    return client.complete_json(task="entity_evidence_schema_inference", prompt=prompt, fallback=fallback)


def judge_schema_revision(
    client: LLMClient,
    *,
    candidate: dict[str, Any],
    current_schema: dict[str, Any],
) -> LLMRecord:
    fallback = {
        "decision": "promote",
        "confidence": candidate.get("confidence", 0.0),
        "rationale": "Deterministic fallback promotes threshold-generated schema revision.",
        "risk": "not_model_judged",
    }
    prompt = _render_llm_prompt(
        client,
        "llm/schema_revision_judge",
        {
            "current_schema": json.dumps(current_schema, ensure_ascii=False)[:5000],
            "candidate": candidate,
        },
    )
    return client.complete_json(task="schema_revision_judge", prompt=prompt, fallback=fallback)


def extract_document_entities(
    client: LLMClient,
    *,
    doc_id: str,
    title: str,
    text: str,
    entity_types: list[str],
    max_entities: int,
    entity_schema: dict[str, Any] | None = None,
) -> LLMRecord:
    fallback: dict[str, Any] = {"entities": []}
    schema = _entity_schema_for_prompt(entity_schema, entity_types)
    prompt = _render_llm_prompt(
        client,
        "llm/entity_extraction",
        {
            "entity_schema": schema,
            "max_entities": max_entities,
            "doc_id": doc_id,
            "title": title,
            "text": text[:6000],
        },
    )
    return client.complete_json(task="entity_extraction", prompt=prompt, fallback=fallback)


def summarize_macro_pattern(
    client: LLMClient,
    *,
    pattern_profile: dict[str, Any],
    evidence_records: list[dict[str, Any]],
) -> LLMRecord:
    fallback = {
        "summary": pattern_profile.get("explanation") or "",
        "caveats": ["Deterministic fallback: macro pattern summary task was not run."],
    }
    prompt = _render_llm_prompt(
        client,
        "llm/macro_pattern_summary",
        {
            "pattern_profile": pattern_profile,
            "evidence_records": json.dumps(evidence_records[:12], ensure_ascii=False)[:8000],
        },
    )
    return client.complete_json(task="macro_pattern_summary", prompt=prompt, fallback=fallback)


def _render_llm_prompt(client: LLMClient, prompt_id: str, values: dict[str, Any]) -> str:
    config = getattr(client, "config", None)
    prompt_dir = getattr(config, "prompt_dir", None)
    return render_prompt(prompt_id, values, prompt_dir=prompt_dir)


def _cache_key(provider: str, model: str, task: str, prompt: str, request_options: dict[str, Any] | None = None) -> str:
    payload = json.dumps(
        {
            "provider": provider,
            "model": model,
            "task": task,
            "prompt": prompt,
            "request_options": request_options or {},
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _compact_excerpt(text: str, max_len: int = 500) -> str:
    excerpt = " ".join(str(text or "").split())
    if len(excerpt) > max_len:
        return excerpt[:max_len] + "..."
    return excerpt


def _loads_json_object(content: str) -> tuple[dict[str, Any], bool]:
    try:
        output = json.loads(content)
        if not isinstance(output, dict):
            raise ValueError("JSON content is not an object.")
        return output, False
    except json.JSONDecodeError as original_error:
        if repair_json is None:
            raise ValueError(f"{original_error}; json_repair is not installed.") from original_error
        try:
            repaired = repair_json(content, return_objects=True)
        except Exception as repair_error:  # pragma: no cover - depends on malformed model output.
            raise ValueError(f"{original_error}; json_repair failed: {repair_error}") from repair_error
        if not isinstance(repaired, dict):
            raise ValueError(f"{original_error}; json_repair did not return a JSON object.")
        return repaired, True


def _schema_valid(task: str, output: dict[str, Any]) -> bool:
    if not isinstance(output, dict):
        return False
    if task == "taxonomy_candidate_judge":
        return "accept" in output and "confidence" in output
    if task == "edge_evidence_judge":
        return "edge_type" in output and "confidence" in output and (
            "evidence" in output or any(isinstance(output.get(key), dict) for key in ["bottleneck", "mechanism", "tradeoff"])
        )
    if task == "relation_extraction":
        return "accept" in output and "edge_type" in output and "confidence" in output and "evidence" in output
    if task == "relation_extraction_batch":
        rows = output.get("relations")
        if not isinstance(rows, list):
            return False
        return all(
            isinstance(row, dict)
            and "pair_index" in row
            and "accept" in row
            and "edge_type" in row
            and "confidence" in row
            and "evidence" in row
            for row in rows
        )
    if task == "successor_edge_batch":
        rows = output.get("edges")
        if not isinstance(rows, list):
            return False
        return all(
            isinstance(row, dict)
            and "pair_index" in row
            and "accept" in row
            and "relation_type" in row
            and "confidence" in row
            and "evidence" in row
            for row in rows
        )
    if task == "relation_schema_inference":
        relation_types = output.get("relation_types")
        if not isinstance(relation_types, list):
            return False
        return all(isinstance(row, dict) and row.get("edge_type") and row.get("definition") for row in relation_types)
    if task == "entity_evidence_schema_inference":
        entity_types = output.get("entity_types")
        evidence_slots = output.get("evidence_slots")
        if not isinstance(entity_types, list) or not isinstance(evidence_slots, list):
            return False
        valid_entities = all(isinstance(row, dict) and row.get("entity_type") and row.get("definition") for row in entity_types)
        valid_slots = all(isinstance(row, dict) and row.get("slot") and row.get("definition") for row in evidence_slots)
        return valid_entities and valid_slots
    if task == "schema_revision_judge":
        return output.get("decision") in {"promote", "reject", "needs_human_review"} and "confidence" in output
    if task == "entity_extraction":
        entities = output.get("entities")
        if not isinstance(entities, list):
            return False
        return all(
            isinstance(row, dict)
            and row.get("name")
            and row.get("quote")
            and isinstance(row.get("contextual_name", ""), str)
            and isinstance(row.get("domain_context", ""), str)
            and isinstance(row.get("method_role", ""), str)
            for row in entities
        )
    if task == "relevance_screening":
        if output.get("screening_decision") not in {"core", "peripheral", "exclude"}:
            return False
        required_scores = ["screening_score"]
        optional_scores = ["method_relevance", "social_science_relevance", "evolution_signal"]
        for key in required_scores:
            try:
                number = float(output.get(key))
            except (TypeError, ValueError):
                return False
            if number < 0.0 or number > 1.0:
                return False
        for key in optional_scores:
            if key not in output or output.get(key) in {None, ""}:
                continue
            try:
                number = float(output.get(key))
            except (TypeError, ValueError):
                return False
            if number < 0.0 or number > 1.0:
                return False
        return isinstance(output.get("screening_reason"), str)
    if task == "macro_pattern_summary":
        return isinstance(output.get("summary"), str)
    return True


def _edge_evidence_slots(
    *,
    edge: dict[str, Any],
    relation_spec: dict[str, Any] | None,
    evidence_schema: dict[str, Any] | None,
) -> list[str]:
    slots = []
    evidence = edge.get("evidence") if isinstance(edge.get("evidence"), dict) else {}
    for value in [
        (relation_spec or {}).get("evidence_slots"),
        evidence.get("schema_slots"),
        list((evidence_schema or {}).keys()) if evidence_schema else [],
    ]:
        if isinstance(value, list):
            slots.extend(str(item) for item in value if str(item).strip())
    if not slots:
        slots = ["bottleneck", "mechanism", "tradeoff"]
    deduped: list[str] = []
    for slot in slots:
        if slot not in deduped:
            deduped.append(slot)
    return deduped


def _entity_schema_for_prompt(entity_schema: dict[str, Any] | None, entity_types: list[str]) -> dict[str, Any]:
    if isinstance(entity_schema, dict) and entity_schema:
        allowed = set(entity_types)
        rows = {
            str(entity_type): _compact_entity_schema_spec(spec)
            for entity_type, spec in entity_schema.items()
            if (not allowed or str(entity_type) in allowed) and isinstance(spec, dict)
        }
        if rows:
            return rows
    return {str(entity_type): {"entity_type": str(entity_type)} for entity_type in entity_types}


def _compact_entity_schema_spec(spec: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "entity_type",
        "definition",
        "inclusion_criteria",
        "exclusion_criteria",
        "allowed_dimensions",
        "example_mentions",
        "negative_examples",
        "quality_rules",
    ]
    compact: dict[str, Any] = {}
    for key in keys:
        value = spec.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            compact[key] = value[:12]
        else:
            compact[key] = value
    return compact


def _record_from_row(row: dict[str, Any]) -> LLMRecord:
    return LLMRecord(
        task=str(row.get("task") or ""),
        provider=str(row.get("provider") or ""),
        model=str(row.get("model") or ""),
        used_model=bool(row.get("used_model")),
        prompt=str(row.get("prompt") or ""),
        output=row.get("output") if isinstance(row.get("output"), dict) else {},
        error=str(row.get("error") or ""),
        cache_key=str(row.get("cache_key") or ""),
        cache_hit=bool(row.get("cache_hit")),
        schema_valid=bool(row.get("schema_valid", True)),
        json_repaired=bool(row.get("json_repaired")),
        attempts=int(row.get("attempts") or 1),
    )
