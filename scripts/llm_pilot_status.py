#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize an EvoTaxa LLM pilot run from cache and output artifacts.")
    parser.add_argument("--run-root", type=Path, required=True, help="Pilot directory containing cache/config/output.")
    parser.add_argument("--cache", type=Path, default=None, help="Optional explicit LLM cache JSONL path.")
    parser.add_argument("--output-root", type=Path, default=None, help="Optional explicit run output root.")
    args = parser.parse_args()

    run_root = args.run_root.expanduser().resolve()
    cache_path = args.cache.expanduser().resolve() if args.cache else run_root / "llm_pilot_200_no_thinking_cache.jsonl"
    output_root = args.output_root.expanduser().resolve() if args.output_root else run_root / "run_output_no_thinking"
    summary = {
        "run_root": str(run_root),
        "cache": summarize_cache(cache_path),
        "output": summarize_output(output_root),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def summarize_cache(path: Path) -> dict[str, Any]:
    tasks: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    attempts: Counter[str] = Counter()
    repaired = 0
    used_model = 0
    rows = 0
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                rows += 1
                row = json.loads(line)
                tasks[str(row.get("task") or "")] += 1
                errors[str(row.get("error") or "")] += 1
                attempts[str(row.get("attempts") or "")] += 1
                repaired += bool(row.get("json_repaired"))
                used_model += bool(row.get("used_model"))
    return {
        "path": str(path),
        "exists": path.exists(),
        "records": rows,
        "tasks": dict(sorted(tasks.items())),
        "errors": dict(sorted(errors.items())),
        "attempts": dict(sorted(attempts.items())),
        "json_repaired": repaired,
        "used_model": used_model,
    }


def summarize_output(path: Path) -> dict[str, Any]:
    manifest_path = path / "manifest.json"
    quality_path = path / "evaluation" / "quality_report.json"
    output: dict[str, Any] = {
        "path": str(path),
        "manifest_exists": manifest_path.exists(),
        "quality_report_exists": quality_path.exists(),
    }
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        output["counts"] = manifest.get("counts", {})
        output["generated_at"] = manifest.get("generated_at", "")
    if quality_path.exists():
        quality = json.loads(quality_path.read_text(encoding="utf-8"))
        output["overall_quality_score"] = quality.get("overall_quality_score")
        output["dimension_scores"] = quality.get("dimension_scores", {})
        output["llm_reliability"] = quality.get("llm_reliability", {})
    return output


if __name__ == "__main__":
    raise SystemExit(main())
