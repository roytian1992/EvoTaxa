#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from evotaxa.config import LLMConfig  # noqa: E402
from evotaxa.content_cleaning import CleanedText, clean_title_abstract  # noqa: E402
from evotaxa.io import iter_jsonl, write_json, write_jsonl  # noqa: E402
from evotaxa.llm import LLMClient, build_llm_client  # noqa: E402
from evotaxa.prompts import render_prompt  # noqa: E402
from evotaxa import toml_compat  # noqa: E402


@dataclass
class ScreeningRubric:
    domain_id: str
    domain_definition: str
    core_criteria: list[str]
    peripheral_criteria: list[str]
    exclude_criteria: list[str]
    default_decision: str = "peripheral"


@dataclass
class PromptTemplate:
    template_id: str
    text: str
    prompt_id: str = ""
    prompt_dir: Path | None = None


def main() -> int:
    parser = argparse.ArgumentParser(description="Screen a corpus for domain relevance before EvoTaxa runs.")
    parser.add_argument("--input", type=Path, required=True, help="Input corpus JSONL.")
    parser.add_argument("--output-root", type=Path, required=True, help="Directory for screened corpus and audit files.")
    parser.add_argument("--rubric", type=Path, required=True, help="Domain screening rubric TOML.")
    parser.add_argument(
        "--prompt-template",
        type=Path,
        default=REPO_ROOT / "task_specs" / "prompts" / "screening" / "relevance_screening.yaml",
    )
    parser.add_argument("--llm-config", type=Path, required=True, help="LLM connection TOML.")
    parser.add_argument("--include-decisions", default="core", help="Comma-separated decisions to include in screened corpus.")
    parser.add_argument("--limit", type=int, default=0, help="Optional row limit for pilot runs.")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many input rows before screening.")
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--no-resume", action="store_false", dest="resume")
    parser.add_argument(
        "--cache-errors",
        action="store_true",
        help="Reuse cached llm_error rows instead of retrying them on resume.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Write decisions and summary, but no screened corpus.")
    args = parser.parse_args()

    rubric = load_rubric(args.rubric)
    prompt_template = load_prompt_template(args.prompt_template)
    llm_config = load_llm_config(args.llm_config)
    client = build_llm_client(llm_config)

    rows = list(iter_jsonl(args.input))
    if args.offset:
        rows = rows[args.offset :]
    if args.limit > 0:
        rows = rows[: args.limit]

    output_root = args.output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    decisions_path = output_root / "screening_decisions.jsonl"
    cleaning_path = output_root / "cleaning_records.jsonl"
    run_signature = build_run_signature(
        rubric_path=args.rubric,
        prompt_template_path=args.prompt_template,
        llm_config_path=args.llm_config,
        rubric=rubric,
        prompt_template=prompt_template,
        llm_config=llm_config,
    )
    cached_decisions = (
        load_cached_decisions(
            decisions_path,
            run_signature=run_signature,
            cache_errors=args.cache_errors,
        )
        if args.resume
        else {}
    )
    include_decisions = {item.strip() for item in args.include_decisions.split(",") if item.strip()}
    decisions = []
    screened = []
    for index, row in enumerate(rows, start=1 + max(0, args.offset)):
        doc_id = str(row.get("doc_id") or row.get("openalex_id") or row.get("id") or "")
        cached = cached_decisions.get(doc_id)
        cleaned = clean_row(row)
        if cached:
            decision = dict(cached)
            decision["cache_hit"] = True
        else:
            decision = screen_row(cleaned["row"], rubric=rubric, prompt_template=prompt_template, client=client)
            decision["cache_hit"] = False
            decision["run_signature"] = run_signature
        decision["row_index"] = index
        decision["doc_id"] = doc_id
        decision["run_signature"] = run_signature
        decision["cleaning"] = cleaned["record"]
        decisions.append(decision)
        if not cached:
            append_jsonl(decisions_path, decision)
            append_jsonl(cleaning_path, cleaned["record"])
        if decision["screening_decision"] in include_decisions:
            screened.append(
                {
                    **cleaned["row"],
                    "role": "core" if decision["screening_decision"] == "core" else str(decision["screening_decision"]),
                    "content_cleaning": cleaned["record"],
                    "screening": {
                        key: decision[key]
                        for key in [
                            "screening_decision",
                            "screening_score",
                            "screening_reason",
                            "method_relevance",
                            "social_science_relevance",
                            "evolution_signal",
                            "mode",
                            "used_model",
                            "llm_schema_valid",
                            "json_repaired",
                            "llm_attempts",
                        ]
                    },
                }
            )

    write_jsonl(decisions_path, decisions)
    write_jsonl(cleaning_path, [row["cleaning"] for row in decisions if isinstance(row.get("cleaning"), dict)])
    screened_path = output_root / "corpus.screened.jsonl"
    if not args.dry_run:
        write_jsonl(screened_path, screened)
    summary = build_summary(
        input_path=args.input,
        output_root=output_root,
        rubric_path=args.rubric,
        prompt_template_path=args.prompt_template,
        llm_config_path=args.llm_config,
        mode="llm",
        include_decisions=include_decisions,
        input_count=len(rows),
        decisions=decisions,
        screened_count=len(screened),
        decisions_path=decisions_path,
        cleaning_path=cleaning_path,
        screened_path=None if args.dry_run else screened_path,
        run_signature=run_signature,
    )
    write_json(output_root / "screening_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def load_cached_decisions(path: Path, *, run_signature: str, cache_errors: bool = False) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    cached: dict[str, dict[str, Any]] = {}
    for row in iter_jsonl(path):
        if row.get("run_signature") != run_signature:
            continue
        if not cache_errors and str(row.get("screening_decision") or "") == "llm_error":
            continue
        doc_id = str(row.get("doc_id") or "")
        if doc_id:
            cached[doc_id] = row
    return cached


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_rubric(path: Path) -> ScreeningRubric:
    with path.expanduser().resolve().open("rb") as handle:
        raw = toml_compat.load(handle)
    screening = raw.get("screening") or {}
    return ScreeningRubric(
        domain_id=str(screening.get("domain_id") or "domain"),
        domain_definition=str(screening.get("domain_definition") or ""),
        core_criteria=[str(item) for item in screening.get("core_criteria") or []],
        peripheral_criteria=[str(item) for item in screening.get("peripheral_criteria") or []],
        exclude_criteria=[str(item) for item in screening.get("exclude_criteria") or []],
        default_decision=str(screening.get("default_decision") or "peripheral"),
    )


def load_prompt_template(path: Path) -> PromptTemplate:
    resolved = path.expanduser().resolve()
    if resolved.suffix.lower() in {".yaml", ".yml"}:
        prompt_dir = REPO_ROOT / "task_specs" / "prompts"
        try:
            prompt_id = resolved.relative_to(prompt_dir).with_suffix("").as_posix()
            text = resolved.read_text(encoding="utf-8")
            return PromptTemplate(template_id=resolved.stem, text=text, prompt_id=prompt_id, prompt_dir=prompt_dir)
        except ValueError:
            text = resolved.read_text(encoding="utf-8")
            return PromptTemplate(template_id=resolved.stem, text=text, prompt_id=str(resolved), prompt_dir=None)
    text = resolved.read_text(encoding="utf-8")
    return PromptTemplate(template_id=resolved.stem, text=text)


def load_llm_config(path: Path | None) -> LLMConfig:
    if path is None:
        return LLMConfig(provider="deterministic")
    with path.expanduser().resolve().open("rb") as handle:
        raw = toml_compat.load(handle)
    llm = raw.get("llm") or {}
    return LLMConfig(
        provider=str(llm.get("provider") or "deterministic"),
        model=str(llm.get("model") or llm.get("model_name") or ""),
        api_key=str(llm.get("api_key") or ""),
        api_key_env=str(llm.get("api_key_env") or "OPENAI_API_KEY"),
        base_url=str(llm.get("base_url") or ""),
        enabled_tasks=[str(item) for item in llm.get("enabled_tasks") or []],
        max_retries=int(llm.get("max_retries") or 1),
        timeout_seconds=int(llm.get("timeout_seconds") or 90),
        temperature=float(llm.get("temperature") or 0.0),
        max_tokens=int(llm.get("max_tokens") or 0),
        max_workers=max(1, int(llm.get("max_workers") or 1)),
        extra_body=dict(llm.get("extra_body") or {}),
    )


def build_run_signature(
    *,
    rubric_path: Path,
    prompt_template_path: Path,
    llm_config_path: Path,
    rubric: ScreeningRubric,
    prompt_template: PromptTemplate,
    llm_config: LLMConfig,
) -> str:
    payload = {
        "script": "screen_relevance.py",
        "rubric_path": str(rubric_path),
        "prompt_template_path": str(prompt_template_path),
        "llm_config_path": str(llm_config_path),
        "rubric": {
            "domain_id": rubric.domain_id,
            "domain_definition": rubric.domain_definition,
            "core_criteria": rubric.core_criteria,
            "peripheral_criteria": rubric.peripheral_criteria,
            "exclude_criteria": rubric.exclude_criteria,
            "default_decision": rubric.default_decision,
        },
        "prompt_template": prompt_template.text,
        "content_cleaning": "clean_title_abstract:v1",
        "llm": {
            "provider": llm_config.provider,
            "model": llm_config.model,
            "base_url": llm_config.base_url,
            "enabled_tasks": llm_config.enabled_tasks,
            "temperature": llm_config.temperature,
            "max_tokens": llm_config.max_tokens,
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def clean_row(row: dict[str, Any]) -> dict[str, Any]:
    title = str(row.get("title") or "")
    original_abstract = str(row.get("abstract") or row.get("text") or "")
    cleaned = clean_title_abstract(title=title, abstract=original_abstract)
    cleaned_row = dict(row)
    cleaned_row["raw_abstract"] = original_abstract
    cleaned_row["abstract"] = cleaned.text
    cleaned_row["text"] = _replace_abstract_in_text(row=row, cleaned=cleaned)
    record = cleaning_record(row=row, cleaned=cleaned)
    return {"row": cleaned_row, "record": record}


def cleaning_record(row: dict[str, Any], cleaned: CleanedText) -> dict[str, Any]:
    doc_id = str(row.get("doc_id") or row.get("openalex_id") or row.get("id") or "")
    return {
        "doc_id": doc_id,
        "title": row.get("title") or "",
        "original_abstract_length": cleaned.original_length,
        "cleaned_abstract_length": cleaned.cleaned_length,
        "removed_abstract_length": cleaned.removed_length,
        "removed_markers": cleaned.removed_markers,
    }


def _replace_abstract_in_text(row: dict[str, Any], cleaned: CleanedText) -> str:
    title = str(row.get("title") or "").strip()
    if title:
        return f"{title}\n\n{cleaned.text}".strip()
    return cleaned.text


def screen_row(
    row: dict[str, Any],
    *,
    rubric: ScreeningRubric,
    prompt_template: PromptTemplate,
    client: LLMClient,
) -> dict[str, Any]:
    prompt = screening_prompt(row, rubric, prompt_template)
    fallback = llm_error_screening("LLM did not return a usable screening decision.")
    record = client.complete_json(task="relevance_screening", prompt=prompt, fallback=fallback)
    if record.error or not record.used_model or not record.schema_valid:
        output = llm_error_screening(record.error or "LLM screening failed.")
        output["mode"] = "llm"
        output["used_model"] = record.used_model
        output["llm_error"] = record.error or "LLM screening failed."
        output["llm_schema_valid"] = record.schema_valid
        output["json_repaired"] = record.json_repaired
        output["llm_attempts"] = record.attempts
        return output
    output = normalize_llm_screening(record.output, fallback=fallback, rubric=rubric)
    output["mode"] = "llm"
    output["used_model"] = record.used_model
    output["llm_error"] = record.error
    output["llm_schema_valid"] = record.schema_valid
    output["json_repaired"] = record.json_repaired
    output["llm_attempts"] = record.attempts
    return output


def screening_prompt(row: dict[str, Any], rubric: ScreeningRubric, prompt_template: PromptTemplate) -> str:
    payload = {
        "title": row.get("title") or "",
        "abstract": (row.get("abstract") or row.get("text") or "")[:5000],
        "publication_year": row.get("publication_year") or "",
        "query_buckets": row.get("query_buckets") or [],
        "concepts": (row.get("concepts") or [])[:12],
        "keywords": (row.get("keywords") or [])[:12],
    }
    replacements = {
        "domain_id": rubric.domain_id,
        "domain_definition": rubric.domain_definition,
        "core_criteria": rubric.core_criteria,
        "peripheral_criteria": rubric.peripheral_criteria,
        "exclude_criteria": rubric.exclude_criteria,
        "paper": payload,
    }
    if prompt_template.prompt_id:
        return render_prompt(prompt_template.prompt_id, replacements, prompt_dir=prompt_template.prompt_dir)
    replacements_legacy = {
        "domain_id": rubric.domain_id,
        "domain_definition": rubric.domain_definition,
        "core_criteria_json": json.dumps(rubric.core_criteria, ensure_ascii=False),
        "peripheral_criteria_json": json.dumps(rubric.peripheral_criteria, ensure_ascii=False),
        "exclude_criteria_json": json.dumps(rubric.exclude_criteria, ensure_ascii=False),
        "paper_json": json.dumps(payload, ensure_ascii=False),
    }
    prompt = prompt_template.text
    for key, value in replacements_legacy.items():
        prompt = prompt.replace("{{" + key + "}}", value)
    return prompt


def normalize_llm_screening(output: dict[str, Any], *, fallback: dict[str, Any], rubric: ScreeningRubric) -> dict[str, Any]:
    decision = str(output.get("screening_decision") or fallback.get("screening_decision") or rubric.default_decision).strip().lower()
    if decision not in {"core", "peripheral", "exclude"}:
        decision = str(fallback.get("screening_decision") or rubric.default_decision)
    score = _bounded_float(output.get("screening_score"), fallback=float(fallback.get("screening_score") or 0.0))
    method = _bounded_float(output.get("method_relevance"), fallback=float(fallback.get("method_relevance") or score))
    social = _bounded_float(output.get("social_science_relevance"), fallback=float(fallback.get("social_science_relevance") or score))
    evolution = _bounded_float(output.get("evolution_signal"), fallback=float(fallback.get("evolution_signal") or score))
    return {
        "screening_decision": decision,
        "screening_score": score,
        "screening_reason": str(output.get("screening_reason") or fallback.get("screening_reason") or ""),
        "method_relevance": method,
        "social_science_relevance": social,
        "evolution_signal": evolution,
    }


def llm_error_screening(reason: str) -> dict[str, Any]:
    return {
        "screening_decision": "llm_error",
        "screening_score": 0.0,
        "screening_reason": reason,
        "method_relevance": 0.0,
        "social_science_relevance": 0.0,
        "evolution_signal": 0.0,
        "mode": "llm",
        "used_model": False,
        "llm_error": reason,
        "llm_schema_valid": False,
        "json_repaired": False,
        "llm_attempts": 0,
    }


def build_summary(
    *,
    input_path: Path,
    output_root: Path,
    rubric_path: Path,
    prompt_template_path: Path,
    llm_config_path: Path | None,
    mode: str,
    include_decisions: set[str],
    input_count: int,
    decisions: list[dict[str, Any]],
    screened_count: int,
    decisions_path: Path,
    cleaning_path: Path,
    screened_path: Path | None,
    run_signature: str,
) -> dict[str, Any]:
    decisions_by_label = Counter(str(row.get("screening_decision") or "unknown") for row in decisions)
    used_model_count = sum(1 for row in decisions if row.get("used_model"))
    error_count = sum(1 for row in decisions if row.get("llm_error"))
    json_repaired_count = sum(1 for row in decisions if row.get("json_repaired"))
    retried_count = sum(1 for row in decisions if int(row.get("llm_attempts") or 0) > 1)
    cleaning_records = [row.get("cleaning") for row in decisions if isinstance(row.get("cleaning"), dict)]
    cleaned_count = sum(1 for row in cleaning_records if int(row.get("removed_abstract_length") or 0) > 0)
    removed_abstract_chars = sum(int(row.get("removed_abstract_length") or 0) for row in cleaning_records)
    marker_counts: Counter[str] = Counter()
    for row in cleaning_records:
        marker_counts.update(str(item) for item in row.get("removed_markers") or [])
    return {
        "input_path": str(input_path),
        "output_root": str(output_root),
        "rubric_path": str(rubric_path),
        "prompt_template_path": str(prompt_template_path),
        "llm_config_path": str(llm_config_path) if llm_config_path else None,
        "mode": mode,
        "input_count": input_count,
        "screened_count": screened_count,
        "include_decisions": sorted(include_decisions),
        "decisions_by_label": dict(sorted(decisions_by_label.items())),
        "used_model_count": used_model_count,
        "error_count": error_count,
        "json_repaired_count": json_repaired_count,
        "retried_count": retried_count,
        "cleaned_count": cleaned_count,
        "removed_abstract_chars": removed_abstract_chars,
        "cleaning_marker_counts": dict(sorted(marker_counts.items())),
        "run_signature": run_signature,
        "decisions_path": str(decisions_path),
        "cleaning_path": str(cleaning_path),
        "screened_path": str(screened_path) if screened_path else None,
    }


def _bounded_float(value: Any, *, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = fallback
    return round(min(1.0, max(0.0, number)), 3)


if __name__ == "__main__":
    raise SystemExit(main())
