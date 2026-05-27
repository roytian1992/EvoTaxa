from __future__ import annotations

import json
import os
import hashlib
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evotaxa.config import LLMConfig
from evotaxa.io import iter_jsonl, write_jsonl


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
        if config.cache_path and config.cache_path.exists():
            for row in iter_jsonl(config.cache_path):
                key = str(row.get("cache_key") or "")
                if key:
                    self.cache[key] = _record_from_row(row)

    def complete_json(self, *, task: str, prompt: str, fallback: dict[str, Any]) -> LLMRecord:
        key = _cache_key(self.config.provider, self.config.model, task, prompt)
        if key in self.cache:
            cached = self.cache[key]
            return LLMRecord(
                task=cached.task,
                provider=cached.provider,
                model=cached.model,
                used_model=cached.used_model,
                prompt=prompt,
                output=cached.output,
                error=cached.error,
                cache_key=key,
                cache_hit=True,
                schema_valid=cached.schema_valid,
            )
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
                {"role": "system", "content": "Return only a valid JSON object."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
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
        for _ in range(max(1, self.config.max_retries)):
            try:
                with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                    raw = json.loads(response.read().decode("utf-8"))
                content = raw["choices"][0]["message"]["content"]
                output = json.loads(content)
                schema_valid = _schema_valid(task, output)
                record = LLMRecord(
                    task=task,
                    provider=self.config.provider,
                    model=self.config.model,
                    used_model=True,
                    prompt=prompt,
                    output=output if schema_valid else fallback,
                    error="" if schema_valid else "LLM output failed schema validation.",
                    cache_key=key,
                    schema_valid=schema_valid,
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
            )

    def _store(self, record: LLMRecord) -> None:
        self.cache[record.cache_key] = record
        if not self.config.cache_path:
            return
        path = Path(self.config.cache_path)
        rows = [item.to_record() for item in self.cache.values()]
        write_jsonl(path, rows)


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
    prompt = (
        "Judge whether the following taxonomy expansion candidate is valid.\n"
        f"Candidate JSON:\n{json.dumps(candidate, ensure_ascii=False)}\n"
        f"Context:\n{context[:4000]}\n"
        "Return JSON with accept, confidence, rationale, and suggested_label."
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
    prompt = (
        "Audit this evolution edge using the allowed relation and evidence schemas.\n"
        "Return only evidence slots requested below. Do not invent quotes.\n"
        "Every evidence quote must be an exact copied span from the source or target text; leave quote empty if unsupported.\n"
        f"Allowed relation schema:\n{json.dumps(relation_schema or {}, ensure_ascii=False)}\n"
        f"Evidence schema:\n{json.dumps(evidence_schema or {}, ensure_ascii=False)}\n"
        f"Required evidence slots for this edge:\n{json.dumps(evidence_slots, ensure_ascii=False)}\n"
        f"Edge JSON:\n{json.dumps(edge, ensure_ascii=False)}\n"
        f"Source text:\n{source_text[:3000]}\n"
        f"Target text:\n{target_text[:3000]}\n"
        "Return JSON with edge_type, confidence, evidence, and rationale. "
        "edge_type must be one of the allowed schema keys. evidence must be an object keyed by the required evidence slots; "
        "each slot object must include description and quote."
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
    prompt = (
        "Decide whether this source-target entity pair expresses a taxonomy-guided evolution relation.\n"
        "Use the relation schema as the closed set of allowed edge types. Prefer background or accept=false for weak co-mentions.\n"
        "If accepted, return quote-grounded evidence for the selected relation's evidence slots. Every quote must be copied exactly from source or target text.\n"
        f"Pair JSON:\n{json.dumps(pair, ensure_ascii=False)}\n"
        f"Allowed relation schema:\n{json.dumps(relation_schema, ensure_ascii=False)}\n"
        f"Evidence schema:\n{json.dumps(evidence_schema, ensure_ascii=False)}\n"
        f"Source text:\n{source_text[:3500]}\n"
        f"Target text:\n{target_text[:3500]}\n"
        "Return JSON with accept, edge_type, confidence, evidence, rationale, and negative_rationale. "
        "evidence must be an object keyed by evidence slot, each with description and quote."
    )
    return client.complete_json(task="relation_extraction", prompt=prompt, fallback=fallback)


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
    prompt = (
        "Infer a domain-appropriate relation extraction schema for taxonomy-guided evolution modeling.\n"
        "Keep the schema compact and compatible with quote-grounded evidence extraction.\n"
        f"Domain id: {domain_id}\n"
        f"Entity types: {entity_types}\n"
        f"Core strong edge types to preserve unless inappropriate: {strong_edge_types}\n"
        f"Maximum relation types: {max_relation_types}\n"
        f"Fixed fallback schema:\n{json.dumps(fixed_schema, ensure_ascii=False)}\n"
        f"Sample documents:\n{json.dumps(sample_documents, ensure_ascii=False)[:5000]}\n"
        "Return JSON: {\"relation_types\": [{\"edge_type\": \"\", \"label\": \"\", \"definition\": \"\", "
        "\"source_role\": \"\", \"target_role\": \"\", \"directionality\": \"directed\", "
        "\"temporal_constraint\": \"none\", \"evidence_slots\": [\"mechanism\"], "
        "\"positive_cues\": [], \"negative_cues\": [], \"counterexamples\": [], \"strong_edge\": false}]}."
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
    prompt = (
        "Infer a compact entity and evidence schema for taxonomy-guided evolution modeling.\n"
        "Entity types should describe domain objects worth tracking over time. Evidence slots should be quote-grounded fields needed to validate entities and relations.\n"
        f"Domain id: {domain_id}\n"
        f"Taxonomy dimensions: {taxonomy_dimensions}\n"
        f"Configured entity types: {configured_entity_types}\n"
        f"Fixed entity schema:\n{json.dumps(fixed_entity_schema, ensure_ascii=False)}\n"
        f"Fixed evidence schema:\n{json.dumps(fixed_evidence_schema, ensure_ascii=False)}\n"
        f"Sample documents:\n{json.dumps(sample_documents, ensure_ascii=False)[:5000]}\n"
        "Return JSON: {\"entity_types\": [{\"entity_type\": \"\", \"definition\": \"\", "
        "\"inclusion_criteria\": \"\", \"exclusion_criteria\": \"\", \"aliases\": [], "
        "\"allowed_dimensions\": [], \"example_mentions\": [], \"negative_examples\": [], \"quality_rules\": []}], "
        "\"evidence_slots\": [{\"slot\": \"\", \"definition\": \"\", \"required\": true, "
        "\"quote_required\": true, \"allowed_source\": \"either\", \"validation\": \"substring\"}]}."
    )
    return client.complete_json(task="entity_evidence_schema_inference", prompt=prompt, fallback=fallback)


def extract_document_entities(
    client: LLMClient,
    *,
    doc_id: str,
    title: str,
    text: str,
    entity_types: list[str],
    max_entities: int,
) -> LLMRecord:
    fallback: dict[str, Any] = {"entities": []}
    prompt = (
        "Extract evolution-relevant entities from this document.\n"
        "Each entity must be a method, mechanism, intervention, policy instrument, measurement strategy, "
        "evaluation protocol, public frame, or other configured type.\n"
        "Every entity must include an exact quote copied from the document text that supports the mention.\n"
        f"Allowed entity types: {entity_types}\n"
        f"Maximum entities: {max_entities}\n"
        f"Document id: {doc_id}\n"
        f"Title: {title}\n"
        f"Text:\n{text[:6000]}\n"
        "Return JSON: {\"entities\": [{\"name\": \"\", \"entity_type\": \"\", \"quote\": \"\", \"confidence\": 0.0, \"rationale\": \"\"}]}."
    )
    return client.complete_json(task="entity_extraction", prompt=prompt, fallback=fallback)


def _cache_key(provider: str, model: str, task: str, prompt: str) -> str:
    payload = json.dumps(
        {"provider": provider, "model": model, "task": task, "prompt": prompt},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
    if task == "entity_extraction":
        entities = output.get("entities")
        if not isinstance(entities, list):
            return False
        return all(isinstance(row, dict) and row.get("name") and row.get("quote") for row in entities)
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
    )
