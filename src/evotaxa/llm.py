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
) -> LLMRecord:
    fallback = {
        "edge_type": edge.get("edge_type"),
        "confidence": edge.get("confidence", 0.0),
        "bottleneck": (edge.get("evidence") or {}).get("bottleneck") or {},
        "mechanism": (edge.get("evidence") or {}).get("mechanism") or {},
        "tradeoff": (edge.get("evidence") or {}).get("tradeoff") or {},
        "rationale": "Deterministic fallback preserving cue-based extraction.",
    }
    prompt = (
        "Audit this evolution edge. Extract bottleneck, mechanism, and tradeoff evidence from the source/target text.\n"
        f"Edge JSON:\n{json.dumps(edge, ensure_ascii=False)}\n"
        f"Source text:\n{source_text[:3000]}\n"
        f"Target text:\n{target_text[:3000]}\n"
        "Return JSON with edge_type, confidence, bottleneck, mechanism, tradeoff, and rationale."
    )
    return client.complete_json(task="edge_evidence_judge", prompt=prompt, fallback=fallback)


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
        return "edge_type" in output and "confidence" in output
    if task == "entity_extraction":
        entities = output.get("entities")
        if not isinstance(entities, list):
            return False
        return all(isinstance(row, dict) and row.get("name") and row.get("quote") for row in entities)
    return True


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
