#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from evotaxa.config import load_config  # noqa: E402
from evotaxa.graph import build_relation_extraction_pairs, edge_from_relation_extraction  # noqa: E402
from evotaxa.io import iter_jsonl, write_json, write_jsonl  # noqa: E402
from evotaxa.llm import build_llm_client, extract_relations_for_pairs  # noqa: E402
from evotaxa.loaders import infer_assignments_from_text, load_assignments, load_documents, load_taxonomy_nodes  # noqa: E402
from evotaxa.models import EntityMention, EvolutionEntity  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe EvoTaxa LLM relation candidates without running the full pipeline.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, default=None, help="Completed run output root to reuse entity artifacts.")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--run-llm", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    output_root = args.output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    if args.limit >= 0:
        config.graph.llm_relation_extraction_limit = args.limit
    if args.batch_size > 0:
        config.graph.llm_relation_batch_size = args.batch_size

    docs, corpus_manifest = load_documents(config)
    nodes, taxonomy_manifest = load_taxonomy_nodes(config)
    assignments, assignment_manifest = load_assignments(config)
    if not assignments:
        assignments = infer_assignments_from_text(docs, nodes)
        assignment_manifest["inferred_from_text"] = True
        assignment_manifest["loaded_assignments"] = len(assignments)

    run_root = args.run_root.expanduser().resolve() if args.run_root else None
    if run_root:
        entities = load_entities(run_root / "graph" / "method_registry.jsonl")
        mentions = load_mentions(run_root / "graph" / "paper_method_mentions.jsonl")
    else:
        raise ValueError("--run-root is currently required so the probe reuses the completed run's entity cards.")

    pairs = build_relation_extraction_pairs(
        docs,
        entities,
        mentions,
        config.graph,
        limit=max(0, config.graph.llm_relation_extraction_limit),
    )
    pair_rows = [pair_to_row(index, pair) for index, pair in enumerate(pairs)]
    write_jsonl(output_root / "candidate_pairs.jsonl", pair_rows)

    llm_records: list[dict[str, Any]] = []
    relation_rows: list[dict[str, Any]] = []
    extracted_edges = []
    if args.run_llm and pairs:
        client = build_llm_client(config.llm)
        relation_schema = json.loads((run_root / "schema" / "relation_schema.final.json").read_text(encoding="utf-8")) if run_root else {}
        evidence_schema = json.loads((run_root / "schema" / "evidence_schema.final.json").read_text(encoding="utf-8")) if run_root else {}
        document_texts = {doc.doc_id: doc.full_text for doc in docs}
        batch_size = max(1, config.graph.llm_relation_batch_size)
        for batch_start in range(0, len(pairs), batch_size):
            batch = pairs[batch_start : batch_start + batch_size]
            record = extract_relations_for_pairs(
                client,
                pairs=batch,
                document_texts=document_texts,
                relation_schema=relation_schema,
                evidence_schema=evidence_schema,
            )
            llm_records.append(record.to_record())
            outputs = relation_outputs_by_pair(record.output.get("relations") if isinstance(record.output, dict) else [])
            for local_index, pair in enumerate(batch):
                output = outputs.get(local_index) or {
                    "accept": False,
                    "edge_type": "background",
                    "confidence": 0.0,
                    "evidence": {},
                    "negative_rationale": "No output for pair.",
                    "rejection_reason": "missing_output",
                }
                edge = edge_from_relation_extraction(pair, output, relation_schema=relation_schema, evidence_schema=evidence_schema)
                row = pair_to_row(batch_start + local_index, pair)
                row.update(
                    {
                        "accepted": edge is not None,
                        "edge_type": output.get("edge_type"),
                        "confidence": output.get("confidence"),
                        "rationale": output.get("rationale") or output.get("negative_rationale") or "",
                        "rejection_reason": "" if edge is not None else str(output.get("rejection_reason") or "not_accepted"),
                        "llm_error": record.error,
                        "used_model": record.used_model,
                    }
                )
                relation_rows.append(row)
                if edge is not None:
                    extracted_edges.append(edge.to_record())
        write_jsonl(output_root / "llm_relation_records.jsonl", llm_records)
        write_jsonl(output_root / "llm_relation_report.jsonl", relation_rows)
        write_jsonl(output_root / "llm_relation_edges.jsonl", extracted_edges)

    summary = {
        "config_path": str(config.path),
        "run_root": str(run_root) if run_root else "",
        "output_root": str(output_root),
        "model": config.llm.model,
        "base_url": config.llm.base_url,
        "enabled_tasks": config.llm.enabled_tasks,
        "max_tokens": config.llm.max_tokens,
        "max_workers": config.llm.max_workers,
        "candidate_limit": config.graph.llm_relation_extraction_limit,
        "candidate_min_score": config.graph.llm_relation_candidate_min_score,
        "documents": len(docs),
        "entities": len(entities),
        "mentions": len(mentions),
        "candidate_pairs": len(pairs),
        "candidate_score": score_summary(pair_rows),
        "candidate_reason_counts": reason_counts(pair_rows),
        "candidate_type_pairs": dict(Counter(row["entity_type_pair"] for row in pair_rows)),
        "llm_run": bool(args.run_llm),
        "llm_records": len(llm_records),
        "llm_errors": dict(Counter(str(row.get("error") or "") for row in llm_records)),
        "accepted_relations": sum(1 for row in relation_rows if row.get("accepted")),
        "rejection_reasons": dict(Counter(str(row.get("rejection_reason") or "") for row in relation_rows if not row.get("accepted"))),
        "inputs": {
            "corpus": corpus_manifest,
            "taxonomy": taxonomy_manifest,
            "assignments": assignment_manifest,
        },
    }
    write_json(output_root / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def load_entities(path: Path) -> list[EvolutionEntity]:
    return [
        EvolutionEntity(
            entity_id=str(row.get("entity_id") or ""),
            canonical_name=str(row.get("canonical_name") or ""),
            aliases=[str(item) for item in row.get("aliases") or []],
            first_seen_date=str(row.get("first_seen_date") or ""),
            support_documents=[str(item) for item in row.get("support_documents") or []],
            taxonomy_nodes=[str(item) for item in row.get("taxonomy_nodes") or []],
            entity_type=str(row.get("entity_type") or ""),
        )
        for row in iter_jsonl(path)
    ]


def load_mentions(path: Path) -> list[EntityMention]:
    return [
        EntityMention(
            doc_id=str(row.get("doc_id") or ""),
            entity_id=str(row.get("entity_id") or ""),
            canonical_name=str(row.get("canonical_name") or ""),
            taxonomy_nodes=[str(item) for item in row.get("taxonomy_nodes") or []],
            evidence=str(row.get("evidence") or ""),
        )
        for row in iter_jsonl(path)
    ]


def pair_to_row(index: int, pair: dict[str, Any]) -> dict[str, Any]:
    source = pair.get("source_entity") if isinstance(pair.get("source_entity"), dict) else {}
    target = pair.get("target_entity") if isinstance(pair.get("target_entity"), dict) else {}
    return {
        "pair_index": index,
        "source_entity": source.get("entity_id"),
        "source_name": source.get("canonical_name"),
        "source_type": source.get("entity_type"),
        "target_entity": target.get("entity_id"),
        "target_name": target.get("canonical_name"),
        "target_type": target.get("entity_type"),
        "entity_type_pair": f"{source.get('entity_type')}->{target.get('entity_type')}",
        "source_document": pair.get("source_document"),
        "target_document": pair.get("target_document"),
        "time_delta_days": pair.get("time_delta_days"),
        "taxonomy_nodes": pair.get("taxonomy_nodes") or [],
        "candidate_score": pair.get("candidate_score"),
        "candidate_evidence": pair.get("candidate_evidence") or {},
    }


def relation_outputs_by_pair(rows: Any) -> dict[int, dict[str, Any]]:
    outputs: dict[int, dict[str, Any]] = {}
    if not isinstance(rows, list):
        return outputs
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            outputs[int(row.get("pair_index"))] = row
        except (TypeError, ValueError):
            continue
    return outputs


def score_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(row["candidate_score"]) for row in rows if row.get("candidate_score") is not None]
    if not values:
        return {"min": None, "max": None, "mean": None}
    return {"min": min(values), "max": max(values), "mean": round(sum(values) / len(values), 3)}


def reason_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        evidence = row.get("candidate_evidence") if isinstance(row.get("candidate_evidence"), dict) else {}
        counter.update(str(item) for item in evidence.get("score_reasons") or [])
    return dict(counter)


if __name__ == "__main__":
    raise SystemExit(main())
