from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from evotaxa.config import LLMConfig


@dataclass
class LLMRecord:
    task: str
    provider: str
    model: str
    used_model: bool
    prompt: str
    output: dict[str, Any]
    error: str = ""

    def to_record(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "provider": self.provider,
            "model": self.model,
            "used_model": self.used_model,
            "prompt": self.prompt,
            "output": self.output,
            "error": self.error,
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
        )


class OpenAICompatJSONClient(LLMClient):
    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.api_key = config.api_key or os.environ.get(config.api_key_env, "")

    def complete_json(self, *, task: str, prompt: str, fallback: dict[str, Any]) -> LLMRecord:
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
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = json.loads(response.read().decode("utf-8"))
            content = raw["choices"][0]["message"]["content"]
            output = json.loads(content)
            return LLMRecord(
                task=task,
                provider=self.config.provider,
                model=self.config.model,
                used_model=True,
                prompt=prompt,
                output=output,
            )
        except (urllib.error.URLError, KeyError, json.JSONDecodeError, TimeoutError) as exc:
            return LLMRecord(
                task=task,
                provider=self.config.provider,
                model=self.config.model,
                used_model=False,
                prompt=prompt,
                output=fallback,
                error=str(exc),
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
