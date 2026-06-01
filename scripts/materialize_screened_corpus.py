#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from evotaxa.io import iter_jsonl, write_json, write_jsonl  # noqa: E402
from scripts.screen_relevance import clean_row  # noqa: E402


DEFAULT_SCREENING_KEYS = [
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize a screened corpus view from a raw corpus and completed relevance decisions."
    )
    parser.add_argument("--input", type=Path, required=True, help="Original corpus JSONL.")
    parser.add_argument("--decisions", type=Path, required=True, help="screening_decisions.jsonl.")
    parser.add_argument("--output", type=Path, required=True, help="Output corpus JSONL.")
    parser.add_argument(
        "--include-decisions",
        default="core",
        help="Comma-separated screening decisions to materialize.",
    )
    parser.add_argument(
        "--role-map",
        action="append",
        default=[],
        help="Decision-to-role mapping, e.g. --role-map peripheral=support. Can be repeated.",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=None,
        help="Optional summary JSON path. Defaults to output path with .summary.json suffix.",
    )
    args = parser.parse_args()

    include_decisions = {item.strip() for item in args.include_decisions.split(",") if item.strip()}
    role_map = parse_role_map(args.role_map)
    output = args.output.expanduser().resolve()
    summary_path = args.summary.expanduser().resolve() if args.summary else output.with_suffix(".summary.json")

    decisions, decision_stats = load_decisions(args.decisions)
    rows = []
    skipped: Counter[str] = Counter()
    included_by_decision: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    cleaning_marker_counts: Counter[str] = Counter()
    cleaned_count = 0
    removed_abstract_chars = 0

    for index, row in enumerate(iter_jsonl(args.input), start=1):
        doc_id = str(row.get("doc_id") or row.get("openalex_id") or row.get("id") or "")
        if not doc_id:
            skipped["missing_doc_id"] += 1
            continue
        decision = decisions.get(doc_id)
        if decision is None:
            skipped["missing_decision"] += 1
            continue
        screening_decision = str(decision.get("screening_decision") or "")
        if screening_decision not in include_decisions:
            skipped[f"decision_{screening_decision or 'unknown'}"] += 1
            continue

        cleaned = clean_row(row)
        cleaning_record = cleaned["record"]
        if int(cleaning_record.get("removed_abstract_length") or 0) > 0:
            cleaned_count += 1
        removed_abstract_chars += int(cleaning_record.get("removed_abstract_length") or 0)
        cleaning_marker_counts.update(str(item) for item in cleaning_record.get("removed_markers") or [])

        role = role_map.get(screening_decision, "core" if screening_decision == "core" else screening_decision)
        rows.append(
            {
                **cleaned["row"],
                "role": role,
                "content_cleaning": cleaning_record,
                "screening": {
                    key: decision[key]
                    for key in DEFAULT_SCREENING_KEYS
                    if key in decision
                },
                "screening_view": {
                    "source_input": str(args.input),
                    "source_decisions": str(args.decisions),
                    "source_row_index": decision.get("row_index", index),
                    "included_decisions": sorted(include_decisions),
                    "decision_role_map": role_map,
                },
            }
        )
        included_by_decision[screening_decision] += 1
        roles[role] += 1

    write_jsonl(output, rows)
    summary = {
        "script": "materialize_screened_corpus.py",
        "input_path": str(args.input),
        "decisions_path": str(args.decisions),
        "output_path": str(output),
        "include_decisions": sorted(include_decisions),
        "role_map": role_map,
        "raw_input_count": index if "index" in locals() else 0,
        "decision_count": len(decisions),
        "decision_duplicates": decision_stats["duplicates"],
        "materialized_count": len(rows),
        "included_by_decision": dict(sorted(included_by_decision.items())),
        "roles": dict(sorted(roles.items())),
        "skipped": dict(sorted(skipped.items())),
        "cleaned_count": cleaned_count,
        "removed_abstract_chars": removed_abstract_chars,
        "cleaning_marker_counts": dict(sorted(cleaning_marker_counts.items())),
    }
    write_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def parse_role_map(items: list[str]) -> dict[str, str]:
    role_map: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid role mapping, expected decision=role: {item}")
        decision, role = item.split("=", 1)
        decision = decision.strip()
        role = role.strip()
        if not decision or not role:
            raise ValueError(f"Invalid role mapping, expected decision=role: {item}")
        role_map[decision] = role
    return role_map


def load_decisions(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    by_doc: dict[str, dict[str, Any]] = {}
    duplicates: dict[str, int] = defaultdict(int)
    for row in iter_jsonl(path):
        doc_id = str(row.get("doc_id") or "")
        if not doc_id:
            continue
        if doc_id in by_doc:
            duplicates[doc_id] += 1
        by_doc[doc_id] = row
    return by_doc, {"duplicates": dict(sorted(duplicates.items()))}


if __name__ == "__main__":
    raise SystemExit(main())
