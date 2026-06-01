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

from evotaxa.io import iter_jsonl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize relevance-screening shard progress.")
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    run_root = args.run_root.expanduser().resolve()
    totals = Counter()
    print("shard\tdecisions\tcore\tperipheral\texclude\tllm_error\trepaired\tretried")
    for shard_dir in sorted((run_root / "shards").glob("shard_*")):
        rows = list(iter_jsonl(shard_dir / "screening_decisions.jsonl")) if (shard_dir / "screening_decisions.jsonl").exists() else []
        counts = summarize(rows)
        totals.update(counts)
        print(
            f"{shard_dir.name}\t{counts['decisions']}\t{counts['core']}\t{counts['peripheral']}\t"
            f"{counts['exclude']}\t{counts['llm_error']}\t{counts['repaired']}\t{counts['retried']}"
        )
    print(
        f"TOTAL\t{totals['decisions']}\t{totals['core']}\t{totals['peripheral']}\t{totals['exclude']}\t"
        f"{totals['llm_error']}\t{totals['repaired']}\t{totals['retried']}"
    )
    return 0


def summarize(rows: list[dict[str, Any]]) -> Counter:
    counts: Counter[str] = Counter()
    counts["decisions"] = len(rows)
    for row in rows:
        counts[str(row.get("screening_decision") or "unknown")] += 1
        if row.get("json_repaired"):
            counts["repaired"] += 1
        if int(row.get("llm_attempts") or 0) > 1:
            counts["retried"] += 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
