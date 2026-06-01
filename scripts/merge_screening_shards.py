#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
import sys

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from evotaxa.io import iter_jsonl, write_json, write_jsonl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge independent relevance-screening shard outputs.")
    parser.add_argument("--shards-root", type=Path, required=True, help="Directory containing shard_* output directories.")
    parser.add_argument("--output-root", type=Path, required=True, help="Merged output directory.")
    args = parser.parse_args()

    shards_root = args.shards_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    decisions = _read_rows(shards_root, "screening_decisions.jsonl")
    cleaning = _read_rows(shards_root, "cleaning_records.jsonl")
    screened = _read_rows(shards_root, "corpus.screened.jsonl")
    decisions.sort(key=lambda row: int(row.get("row_index") or 0))

    cleaning_by_doc = {str(row.get("doc_id") or ""): row for row in cleaning}
    cleaning_sorted = [cleaning_by_doc.get(str(row.get("doc_id") or ""), {}) for row in decisions]
    cleaning_sorted = [row for row in cleaning_sorted if row]
    screened.sort(key=lambda row: _screened_row_index(row, decisions))

    write_jsonl(output_root / "screening_decisions.jsonl", decisions)
    write_jsonl(output_root / "cleaning_records.jsonl", cleaning_sorted)
    write_jsonl(output_root / "corpus.screened.jsonl", screened)
    write_json(output_root / "screening_summary.json", build_summary(shards_root, output_root, decisions, cleaning_sorted, screened))
    return 0


def _read_rows(root: Path, filename: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob(f"shard_*/{filename}")):
        rows.extend(iter_jsonl(path))
    return rows


def _screened_row_index(row: dict[str, Any], decisions: list[dict[str, Any]]) -> int:
    doc_id = str(row.get("doc_id") or "")
    for decision in decisions:
        if str(decision.get("doc_id") or "") == doc_id:
            return int(decision.get("row_index") or 0)
    return 0


def build_summary(
    shards_root: Path,
    output_root: Path,
    decisions: list[dict[str, Any]],
    cleaning: list[dict[str, Any]],
    screened: list[dict[str, Any]],
) -> dict[str, Any]:
    decisions_by_label = Counter(str(row.get("screening_decision") or "unknown") for row in decisions)
    marker_counts: Counter[str] = Counter()
    for row in cleaning:
        marker_counts.update(str(item) for item in row.get("removed_markers") or [])
    return {
        "shards_root": str(shards_root),
        "output_root": str(output_root),
        "shard_count": len(list(shards_root.glob("shard_*"))),
        "input_count": len(decisions),
        "screened_count": len(screened),
        "decisions_by_label": dict(sorted(decisions_by_label.items())),
        "used_model_count": sum(1 for row in decisions if row.get("used_model")),
        "error_count": sum(1 for row in decisions if row.get("llm_error")),
        "json_repaired_count": sum(1 for row in decisions if row.get("json_repaired")),
        "retried_count": sum(1 for row in decisions if int(row.get("llm_attempts") or 0) > 1),
        "cleaned_count": sum(1 for row in cleaning if int(row.get("removed_abstract_length") or 0) > 0),
        "removed_abstract_chars": sum(int(row.get("removed_abstract_length") or 0) for row in cleaning),
        "cleaning_marker_counts": dict(sorted(marker_counts.items())),
        "decisions_path": str(output_root / "screening_decisions.jsonl"),
        "cleaning_path": str(output_root / "cleaning_records.jsonl"),
        "screened_path": str(output_root / "corpus.screened.jsonl"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
