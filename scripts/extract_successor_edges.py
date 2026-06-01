#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from evotaxa.config import load_config  # noqa: E402
from evotaxa.io import iter_jsonl, normalize_space, parse_date, slugify, write_json, write_jsonl  # noqa: E402
from evotaxa.llm import build_llm_client, extract_successor_edges_for_pairs  # noqa: E402
from schema_groups import schema_group_for_type  # noqa: E402


ALLOWED_RELATION_TYPES = ["extends", "improves", "replaces", "adapts", "specializes", "generalizes"]
GENERIC_NAMES = {
    "analysis",
    "analyses",
    "approach",
    "approaches",
    "data",
    "dataset",
    "evaluation",
    "experiment",
    "experiments",
    "feature",
    "framework",
    "hand",
    "method",
    "methods",
    "model",
    "models",
    "performance",
    "reason",
    "research",
    "simulation",
    "study",
    "studies",
    "system",
}
LABEL_STRUCTURE_TOKENS = {
    "algorithm",
    "algorithms",
    "analysis",
    "analyses",
    "approach",
    "approaches",
    "classifier",
    "classifiers",
    "data",
    "dataset",
    "datasets",
    "evaluation",
    "experiment",
    "experiments",
    "framework",
    "frameworks",
    "method",
    "methods",
    "model",
    "models",
    "modeling",
    "modelling",
    "pipeline",
    "pipelines",
    "protocol",
    "protocols",
    "result",
    "results",
    "system",
    "systems",
    "technique",
    "techniques",
    "tool",
    "tools",
}
LABEL_VARIANT_EXTRA_TOKENS = {
    "applied",
    "classic",
    "classical",
    "common",
    "comparative",
    "conventional",
    "empirical",
    "enhanced",
    "extended",
    "general",
    "improved",
    "large",
    "new",
    "novel",
    "prior",
    "public",
    "previous",
    "robust",
    "scalable",
    "small",
    "standard",
    "supervised",
    "superior",
    "traditional",
    "unsupervised",
}
LABEL_CONTEXT_EXTRA_TOKENS = {
    "application",
    "applications",
    "based",
    "classification",
    "detection",
    "estimation",
    "prediction",
    "recognition",
    "task",
    "tasks",
    "topic",
    "visualization",
    "visualisation",
}
GENERIC_ML_MODIFIERS = {
    "semi",
    "supervised",
    "unsupervised",
    "self",
    "weakly",
    "traditional",
    "classical",
    "standard",
    "generic",
}
BROAD_PREDECESSOR_HEAD_TOKENS = {
    "algorithm",
    "algorithms",
    "approach",
    "approaches",
    "framework",
    "frameworks",
    "method",
    "methods",
    "pipeline",
    "pipelines",
    "technique",
    "techniques",
}
BROAD_PREDECESSOR_ENTITY_TERMS = {
    "accuracy",
    "behavior",
    "behaviour",
    "challenge",
    "challenges",
    "collection",
    "consideration",
    "considerations",
    "data",
    "dataset",
    "datasets",
    "performance",
    "posts",
    "practice",
    "practices",
    "recommendation",
    "recommendations",
    "result",
    "results",
    "science",
    "structure",
    "task",
    "tasks",
}
BROAD_PREDECESSOR_CORE_PHRASES = {
    "computational framework",
    "computational modeling",
    "computational modelling",
    "data collection",
    "data science",
    "deep learning",
    "deep learning models",
    "digital methods",
    "learning methods",
    "machine learning",
    "machine learning models",
    "supervised machine learning",
    "traditional machine learning",
    "unsupervised machine learning",
    "network approach",
    "network methods",
    "public sentiment",
    "real networks",
    "social network",
    "user engagement",
}
SPECIFIC_METHOD_ANCHOR_TOKENS = {
    "agent",
    "bayesian",
    "bert",
    "causal",
    "carlo",
    "dirichlet",
    "embedding",
    "embeddings",
    "forest",
    "gpt",
    "lda",
    "lexicon",
    "markov",
    "monte",
    "privacy",
    "regression",
    "simulation",
    "svm",
    "topic",
    "transformer",
    "vector",
}
NAME_STOP_SUBSTRINGS = [
    " it ",
    " this ",
    " that ",
    " of an ",
    " of a ",
    " of the ",
    " explains how ",
    " shows that ",
    "in this ",
    "to this ",
]
ACTION_GERUND_PREFIXES = {
    "adopting",
    "assessing",
    "building",
    "classifying",
    "detecting",
    "estimating",
    "explaining",
    "harvesting",
    "identifying",
    "measuring",
    "modeling",
    "predicting",
    "simulating",
    "studying",
    "visualizing",
}
METHOD_HEAD_NOUNS = {
    "algorithm",
    "analysis",
    "approach",
    "architecture",
    "classification",
    "clustering",
    "estimation",
    "framework",
    "inference",
    "learning",
    "method",
    "model",
    "modeling",
    "pipeline",
    "protocol",
    "regression",
    "simulation",
    "system",
    "technique",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract explicit successor/evolution edges from an existing EvoTaxa run.")
    parser.add_argument("--config", type=Path, required=True, help="Config with LLM connection settings.")
    parser.add_argument("--run-root", type=Path, required=True, help="Completed EvoTaxa run root.")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--candidate-limit", type=int, default=240)
    parser.add_argument("--llm-limit", type=int, default=48)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--workers", type=int, default=1, help="Concurrent LLM batch workers.")
    parser.add_argument("--max-sources-per-target", type=int, default=120, help="Pre-filtered older sources considered per target.")
    parser.add_argument("--per-target-candidates", type=int, default=6, help="Candidate pairs retained per target entity.")
    parser.add_argument("--max-source-age-years", type=float, default=18.0)
    parser.add_argument("--min-candidate-score", type=float, default=0.25)
    parser.add_argument("--include-label-variants", action="store_true", help="Keep near-duplicate label variants in the candidate pool.")
    parser.add_argument(
        "--candidate-scope",
        choices=["schema_group", "entity_type"],
        default="schema_group",
        help="Entity grouping axis used for successor candidate generation.",
    )
    parser.add_argument("--run-llm", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Resume from existing JSONL outputs in output-root.")
    parser.add_argument("--retry-failed-decisions", action="store_true", help="With --resume, remove failed LLM decisions and retry those pairs.")
    parser.add_argument("--install", action="store_true", help="Copy accepted successor edges into <run-root>/graph/successor_edges.accepted.jsonl.")
    args = parser.parse_args()

    run_root = args.run_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    config = load_config(args.config)
    config.llm.enabled_tasks = sorted(set(config.llm.enabled_tasks) | {"successor_edge_batch"})

    docs = load_documents(run_root)
    entities = load_entities(run_root)
    mentions = load_mentions(run_root)
    candidates, candidate_filter_counts = build_successor_candidates(
        entities=entities,
        docs=docs,
        mentions=mentions,
        max_source_age_years=args.max_source_age_years,
        min_candidate_score=args.min_candidate_score,
        max_sources_per_target=args.max_sources_per_target,
        per_target_candidates=args.per_target_candidates,
        limit=args.candidate_limit,
        skip_label_variants=not args.include_label_variants,
        candidate_scope=args.candidate_scope,
    )
    write_jsonl(output_root / "successor_candidates.jsonl", candidates)

    llm_records_path = output_root / "successor_llm_records.jsonl"
    decisions_path = output_root / "successor_decisions.jsonl"
    accepted_edges_path = output_root / "successor_edges.accepted.jsonl"
    summary_path = output_root / "summary.json"
    if args.resume:
        llm_records: list[dict[str, Any]] = read_jsonl(llm_records_path)
        decisions: list[dict[str, Any]] = read_jsonl(decisions_path)
        accepted_edges: list[dict[str, Any]] = read_jsonl(accepted_edges_path)
        if args.retry_failed_decisions:
            retry_pair_ids = {str(row.get("pair_id") or "") for row in decisions if decision_needs_retry(row)}
            retry_pair_ids.discard("")
            if retry_pair_ids:
                decisions = [row for row in decisions if str(row.get("pair_id") or "") not in retry_pair_ids]
                accepted_edges = [edge_from_decision(row) for row in decisions if row.get("accepted")]
                truncate_jsonl(decisions_path)
                truncate_jsonl(accepted_edges_path)
                append_jsonl(decisions_path, decisions)
                append_jsonl(accepted_edges_path, accepted_edges)
    else:
        llm_records = []
        decisions = []
        accepted_edges = []
        truncate_jsonl(llm_records_path)
        truncate_jsonl(decisions_path)
        truncate_jsonl(accepted_edges_path)

    if args.run_llm and candidates:
        client = build_llm_client(config.llm)
        llm_candidates = candidates[: max(0, args.llm_limit)]
        processed_pair_ids = {
            str(row.get("pair_id") or "")
            for row in decisions
            if row.get("pair_id")
        }
        pending_items = [
            (global_index, candidate)
            for global_index, candidate in enumerate(llm_candidates)
            if str(candidate.get("pair_id") or "") not in processed_pair_ids
        ]
        batches = [
            pending_items[index : index + max(1, args.batch_size)]
            for index in range(0, len(pending_items), max(1, args.batch_size))
        ]
        print(
            json.dumps(
                {
                    "event": "successor_llm_start",
                    "candidate_count": len(candidates),
                    "llm_candidate_count": len(llm_candidates),
                    "already_decided": len(processed_pair_ids),
                    "pending_candidates": len(pending_items),
                    "batches": len(batches),
                    "batch_size": max(1, args.batch_size),
                    "workers": max(1, args.workers),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

        def run_batch(batch_items: list[tuple[int, dict[str, Any]]]) -> tuple[list[int], Any]:
            prompt_pairs = [candidate_for_prompt(index=global_index, row=row) for global_index, row in batch_items]
            record = extract_successor_edges_for_pairs(
                client,
                pairs=prompt_pairs,
                allowed_relation_types=ALLOWED_RELATION_TYPES,
            )
            return [global_index for global_index, _row in batch_items], record

        completed_batches = 0
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = {executor.submit(run_batch, batch): batch for batch in batches}
            for future in as_completed(futures):
                batch = futures[future]
                batch_indexes = [global_index for global_index, _row in batch]
                try:
                    _returned_indexes, record = future.result()
                except Exception as exc:  # pragma: no cover - defensive guard for long-running jobs.
                    record = failed_record(config, exc=exc, batch_indexes=batch_indexes)
                record_row = record.to_record()
                llm_records.append(record_row)
                append_jsonl(llm_records_path, [record_row])

                outputs = outputs_by_pair(record.output.get("edges") if isinstance(record.output, dict) else [])
                new_decisions = []
                new_edges = []
                for local_index, (global_index, candidate) in enumerate(batch):
                    output = outputs.get(global_index) or outputs.get(local_index) or rejection(global_index, "missing_output")
                    decision = decision_row(global_index, candidate, output, record)
                    new_decisions.append(decision)
                    if decision["accepted"]:
                        new_edges.append(edge_from_decision(decision))
                decisions.extend(new_decisions)
                accepted_edges.extend(new_edges)
                append_jsonl(decisions_path, new_decisions)
                append_jsonl(accepted_edges_path, new_edges)
                completed_batches += 1
                summary = build_summary(
                    args=args,
                    run_root=run_root,
                    output_root=output_root,
                    config=config,
                    docs=docs,
                    entities=entities,
                    mentions=mentions,
                    candidates=candidates,
                    candidate_filter_counts=candidate_filter_counts,
                    decisions=decisions,
                    accepted_edges=accepted_edges,
                    llm_records=llm_records,
                    installed=False,
                )
                write_json(summary_path, summary)
                print(
                    json.dumps(
                        {
                            "event": "successor_llm_progress",
                            "completed_batches": completed_batches,
                            "total_batches": len(batches),
                            "completed_decisions": len(decisions),
                            "accepted_edges": len(accepted_edges),
                            "last_batch_indexes": batch_indexes,
                            "last_batch_error": record_row.get("error", ""),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

    if args.install:
        target = run_root / "graph" / "successor_edges.accepted.jsonl"
        shutil.copyfile(accepted_edges_path, target)

    summary = build_summary(
        args=args,
        run_root=run_root,
        output_root=output_root,
        config=config,
        docs=docs,
        entities=entities,
        mentions=mentions,
        candidates=candidates,
        candidate_filter_counts=candidate_filter_counts,
        decisions=decisions,
        accepted_edges=accepted_edges,
        llm_records=llm_records,
        installed=bool(args.install),
    )
    write_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return list(iter_jsonl(path))


def truncate_jsonl(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


class FailedBatchRecord:
    def __init__(self, *, config: Any, exc: Exception, batch_indexes: list[int]) -> None:
        self.output = {"edges": []}
        self.config = config
        self.exc = exc
        self.batch_indexes = batch_indexes
        self.used_model = False
        self.error = f"batch_exception: {exc}"
        self.json_repaired = False
        self.attempts = 0

    def to_record(self) -> dict[str, Any]:
        return {
            "task": "successor_edge_batch",
            "provider": self.config.llm.provider,
            "model": self.config.llm.model,
            "used_model": False,
            "prompt": "",
            "output": self.output,
            "error": self.error,
            "cache_key": "",
            "cache_hit": False,
            "schema_valid": False,
            "json_repaired": False,
            "attempts": 0,
            "batch_indexes": self.batch_indexes,
        }


def failed_record(config: Any, *, exc: Exception, batch_indexes: list[int]) -> FailedBatchRecord:
    return FailedBatchRecord(config=config, exc=exc, batch_indexes=batch_indexes)


def build_summary(
    *,
    args: argparse.Namespace,
    run_root: Path,
    output_root: Path,
    config: Any,
    docs: dict[str, dict[str, Any]],
    entities: list[dict[str, Any]],
    mentions: dict[str, list[dict[str, Any]]],
    candidates: list[dict[str, Any]],
    candidate_filter_counts: Counter[str],
    decisions: list[dict[str, Any]],
    accepted_edges: list[dict[str, Any]],
    llm_records: list[dict[str, Any]],
    installed: bool,
) -> dict[str, Any]:
    llm_scope = candidates[: max(0, args.llm_limit)] if args.run_llm else []
    entity_ids = {row["entity_id"] for row in entities}
    accepted_source_ids = {row["source_entity"] for row in accepted_edges}
    accepted_target_ids = {row["target_entity"] for row in accepted_edges}
    llm_target_ids = {row["target_entity"] for row in llm_scope}
    return {
        "run_root": str(run_root),
        "output_root": str(output_root),
        "config_path": str(args.config.expanduser().resolve()),
        "documents": len(docs),
        "entities": len(entities),
        "mentions": sum(len(rows) for rows in mentions.values()),
        "candidate_limit": args.candidate_limit,
        "candidate_count": len(candidates),
        "llm_run": bool(args.run_llm),
        "llm_limit": args.llm_limit,
        "llm_candidate_count": len(llm_scope),
        "llm_target_entities": len(llm_target_ids),
        "llm_records": len(llm_records),
        "llm_errors": dict(Counter(str(row.get("error") or "") for row in llm_records)),
        "accepted_edges": len(accepted_edges),
        "accepted_predecessor_source_entities": len(accepted_source_ids),
        "accepted_successor_target_entities": len(accepted_target_ids),
        "llm_target_entities_without_accepted_predecessor": len(llm_target_ids - accepted_target_ids),
        "all_entities_without_accepted_predecessor_in_this_extraction": len(entity_ids - accepted_target_ids),
        "accepted_relation_types": dict(Counter(edge.get("edge_type") for edge in accepted_edges)),
        "rejection_reasons": dict(Counter(row.get("rejection_reason") for row in decisions if not row.get("accepted"))),
        "candidate_type_counts": dict(Counter(row.get("entity_type") for row in candidates)),
        "candidate_schema_group_counts": dict(Counter(row.get("schema_group") for row in candidates)),
        "candidate_filter_counts": dict(candidate_filter_counts),
        "candidate_scope": str(getattr(args, "candidate_scope", "schema_group")),
        "candidate_score": score_summary(candidates),
        "workers": max(1, args.workers),
        "batch_size": max(1, args.batch_size),
        "max_sources_per_target": args.max_sources_per_target,
        "per_target_candidates": args.per_target_candidates,
        "resume": bool(args.resume),
        "retry_failed_decisions": bool(getattr(args, "retry_failed_decisions", False)),
        "predecessor_policy": "Do not force an evolution edge for genuinely new concepts or candidates without predecessor evidence.",
        "installed_path": str(run_root / "graph" / "successor_edges.accepted.jsonl") if installed else "",
        "model": config.llm.model,
        "base_url": config.llm.base_url,
    }


def load_documents(run_root: Path) -> dict[str, dict[str, Any]]:
    docs = {}
    for row in iter_jsonl(run_root / "corpus" / "documents.normalized.jsonl"):
        doc_id = str(row.get("doc_id") or "")
        if not doc_id:
            continue
        docs[doc_id] = {
            "doc_id": doc_id,
            "title": normalize_space(row.get("title") or doc_id),
            "text": normalize_space(row.get("text") or ""),
            "published_at": str(row.get("published_at") or ""),
            "date": parse_date(row.get("published_at")),
        }
    return docs


def load_entities(run_root: Path) -> list[dict[str, Any]]:
    rows = []
    for row in iter_jsonl(run_root / "graph" / "method_registry.jsonl"):
        entity_id = str(row.get("entity_id") or "")
        first_seen = parse_date(row.get("first_seen_date"))
        if not entity_id or not first_seen:
            continue
        name = normalize_space(row.get("canonical_name") or entity_name_from_id(entity_id))
        if not entity_name_usable(name):
            continue
        rows.append(
            {
                "entity_id": entity_id,
                "canonical_name": name,
                "entity_type": str(row.get("entity_type") or entity_id.split("__", 1)[0]),
                "schema_group": schema_group_for_type(str(row.get("entity_type") or entity_id.split("__", 1)[0])),
                "first_seen_date": first_seen,
                "first_seen": first_seen.isoformat(),
                "support_documents": [str(item) for item in row.get("support_documents") or []],
                "taxonomy_nodes": [str(item) for item in row.get("taxonomy_nodes") or []],
                "aliases": [str(item) for item in row.get("aliases") or []],
            }
        )
    return rows


def load_mentions(run_root: Path) -> dict[str, list[dict[str, Any]]]:
    mentions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    path = run_root / "graph" / "paper_method_mentions.jsonl"
    if not path.exists():
        return mentions
    for row in iter_jsonl(path):
        entity_id = str(row.get("entity_id") or "")
        if entity_id:
            mentions[entity_id].append(row)
    return mentions


def build_successor_candidates(
    *,
    entities: list[dict[str, Any]],
    docs: dict[str, dict[str, Any]],
    mentions: dict[str, list[dict[str, Any]]],
    max_source_age_years: float,
    min_candidate_score: float,
    max_sources_per_target: int,
    per_target_candidates: int,
    limit: int,
    skip_label_variants: bool,
    candidate_scope: str = "schema_group",
) -> tuple[list[dict[str, Any]], Counter[str]]:
    by_scope: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entity in entities:
        scope_value = str(entity.get(candidate_scope) or entity.get("schema_group") or entity.get("entity_type") or "unknown")
        by_scope[scope_value].append(entity)

    candidates = []
    filter_counts: Counter[str] = Counter()
    filter_counts[f"scope_{candidate_scope}"] += len(by_scope)
    for scope_value, rows in by_scope.items():
        ordered = sorted(rows, key=lambda row: (row["first_seen_date"], row["entity_id"]))
        earlier_sources: list[dict[str, Any]] = []
        for target in ordered:
            target_doc = best_document(target, docs)
            if not target_doc:
                earlier_sources.append(target)
                continue
            source_pool = []
            source_candidates = prefilter_sources_for_target(
                target=target,
                target_doc=target_doc,
                earlier_sources=earlier_sources,
                max_source_age_years=max_source_age_years,
                max_sources=max_sources_per_target,
            )
            for source in source_candidates:
                filter_counts["source_pairs_considered"] += 1
                if skip_label_variants:
                    label_reason = label_variant_reason(source["canonical_name"], target["canonical_name"])
                    if label_reason:
                        filter_counts[f"skipped_{label_reason}"] += 1
                        continue
                    predecessor_reason = generic_predecessor_reason(source["canonical_name"], source["entity_type"])
                    if predecessor_reason:
                        filter_counts[f"skipped_{predecessor_reason}"] += 1
                        continue
                delta = (target["first_seen_date"] - source["first_seen_date"]).days
                score, reasons = candidate_score(source, target, target_doc)
                if score < min_candidate_score:
                    filter_counts["skipped_below_min_candidate_score"] += 1
                    continue
                reasons = list(reasons)
                if source.get("entity_type") != target.get("entity_type"):
                    reasons.append("cross_entity_type_within_schema_group")
                source_doc = best_document(source, docs)
                if not source_doc:
                    filter_counts["skipped_missing_source_document"] += 1
                    continue
                source_pool.append(
                    {
                        "pair_id": f"successor__{slugify(source['entity_id'])}__{slugify(target['entity_id'])}__{target_doc['doc_id']}",
                        "source_entity": source["entity_id"],
                        "source_name": source["canonical_name"],
                        "target_entity": target["entity_id"],
                        "target_name": target["canonical_name"],
                        "entity_type": scope_value,
                        "schema_group": source.get("schema_group") or schema_group_for_type(source.get("entity_type")),
                        "candidate_scope_value": scope_value,
                        "source_entity_type": source.get("entity_type"),
                        "target_entity_type": target.get("entity_type"),
                        "source_schema_group": source.get("schema_group") or schema_group_for_type(source.get("entity_type")),
                        "target_schema_group": target.get("schema_group") or schema_group_for_type(target.get("entity_type")),
                        "candidate_scope": candidate_scope,
                        "source_document": source_doc["doc_id"],
                        "target_document": target_doc["doc_id"],
                        "source_date": source["first_seen"],
                        "target_date": target["first_seen"],
                        "time_delta_days": delta,
                        "taxonomy_nodes": sorted(set(source["taxonomy_nodes"]) & set(target["taxonomy_nodes"])),
                        "source_taxonomy_nodes": source["taxonomy_nodes"],
                        "target_taxonomy_nodes": target["taxonomy_nodes"],
                        "candidate_score": round(score, 3),
                        "candidate_reasons": reasons,
                        "source_quote": best_mention_quote(source["entity_id"], mentions) or excerpt_for_entity(source, source_doc),
                        "target_quote": best_mention_quote(target["entity_id"], mentions) or excerpt_for_entity(target, target_doc),
                        "source_title": source_doc["title"],
                        "target_title": target_doc["title"],
                        "source_text": source_doc["text"][:1800],
                        "target_text": target_doc["text"][:2200],
                    }
                )
            source_pool.sort(key=lambda row: (-row["candidate_score"], row["time_delta_days"], row["source_entity"]))
            filter_counts["retained_before_per_target_cap"] += len(source_pool)
            retained = source_pool[: max(1, per_target_candidates)]
            filter_counts["retained_after_per_target_cap"] += len(retained)
            candidates.extend(retained)
            earlier_sources.append(target)
    candidates.sort(key=lambda row: (-row["candidate_score"], row["target_date"], row["source_entity"], row["target_entity"]))
    if limit > 0:
        filter_counts["retained_after_global_limit"] = min(limit, len(candidates))
        return candidates[:limit], filter_counts
    filter_counts["retained_after_global_limit"] = len(candidates)
    return candidates, filter_counts


def prefilter_sources_for_target(
    *,
    target: dict[str, Any],
    target_doc: dict[str, Any],
    earlier_sources: list[dict[str, Any]],
    max_source_age_years: float,
    max_sources: int,
) -> list[dict[str, Any]]:
    target_tokens = content_tokens(target["canonical_name"])
    target_taxonomy = set(target["taxonomy_nodes"])
    target_text = target_doc["text"].lower()
    rows: list[tuple[float, int, str, dict[str, Any]]] = []
    max_delta_days = max_source_age_years * 365.25
    for source in earlier_sources:
        delta = (target["first_seen_date"] - source["first_seen_date"]).days
        if delta <= 0 or delta > max_delta_days:
            continue
        shared_taxonomy = len(target_taxonomy & set(source["taxonomy_nodes"]))
        source_tokens = content_tokens(source["canonical_name"])
        token_overlap = len(target_tokens & source_tokens)
        mentions_source = source["canonical_name"].lower() in target_text
        if not shared_taxonomy and not token_overlap and not mentions_source:
            continue
        years = delta / 365.25
        recency = 1.0 / (1.0 + max(0.0, years))
        support = math.log1p(len(source["support_documents"]))
        pre_score = shared_taxonomy * 2.0 + token_overlap * 1.5 + (4.0 if mentions_source else 0.0) + recency + min(2.0, support * 0.25)
        rows.append((pre_score, delta, source["entity_id"], source))
    rows.sort(key=lambda item: (-item[0], item[1], item[2]))
    if max_sources > 0:
        rows = rows[:max_sources]
    return [row[-1] for row in rows]


def candidate_score(source: dict[str, Any], target: dict[str, Any], target_doc: dict[str, Any]) -> tuple[float, list[str]]:
    score = 0.0
    reasons = []
    shared_nodes = sorted(set(source["taxonomy_nodes"]) & set(target["taxonomy_nodes"]))
    if shared_nodes:
        score += min(0.28, 0.08 * len(shared_nodes))
        reasons.append("shared_taxonomy")
    source_tokens = content_tokens(source["canonical_name"])
    target_tokens = content_tokens(target["canonical_name"])
    overlap = source_tokens & target_tokens
    if overlap:
        score += min(0.16, 0.06 * len(overlap))
        reasons.append("name_token_overlap")
    source_name_low = source["canonical_name"].lower()
    target_name_low = target["canonical_name"].lower()
    target_text_low = target_doc["text"].lower()
    if source_name_low in target_text_low:
        if source_name_low in target_name_low:
            reasons.append("target_label_contains_source_label")
        elif evolution_cue_near_text(target_text_low, source_name_low):
            score += 0.24
            reasons.append("target_text_mentions_source_with_evolution_cue")
        else:
            score += 0.12
            reasons.append("target_text_mentions_source")
    if evolution_cue_hit(target_doc["text"]):
        score += 0.08
        reasons.append("target_text_has_evolution_cue")
    years = (target["first_seen_date"] - source["first_seen_date"]).days / 365.25
    if years <= 6:
        score += 0.12
        reasons.append("near_temporal_successor")
    elif years <= 12:
        score += 0.06
        reasons.append("medium_temporal_successor")
    score += min(0.08, math.log1p(len(target["support_documents"])) * 0.03)
    return min(1.0, score), reasons


def candidate_for_prompt(*, index: int, row: dict[str, Any]) -> dict[str, Any]:
    keep = [
        "pair_id",
        "source_entity",
        "source_name",
        "target_entity",
        "target_name",
        "entity_type",
        "schema_group",
        "candidate_scope_value",
        "source_entity_type",
        "target_entity_type",
        "source_schema_group",
        "target_schema_group",
        "candidate_scope",
        "source_date",
        "target_date",
        "time_delta_days",
        "taxonomy_nodes",
        "candidate_score",
        "candidate_reasons",
        "source_title",
        "target_title",
        "source_quote",
        "target_quote",
        "source_text",
        "target_text",
    ]
    return {"pair_index": index, **{key: row.get(key) for key in keep}}


def outputs_by_pair(rows: Any) -> dict[int, dict[str, Any]]:
    outputs = {}
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


def rejection(index: int, reason: str) -> dict[str, Any]:
    return {
        "pair_index": index,
        "accept": False,
        "relation_type": "background",
        "confidence": 0.0,
        "evidence": {},
        "rationale": "",
        "rejection_reason": reason,
    }


def decision_row(index: int, candidate: dict[str, Any], output: dict[str, Any], record: Any) -> dict[str, Any]:
    accepted = bool(output.get("accept")) and str(output.get("relation_type") or "") in set(ALLOWED_RELATION_TYPES)
    return {
        "pair_index": index,
        **{key: value for key, value in candidate.items() if key not in {"source_text", "target_text"}},
        "accepted": accepted,
        "edge_type": str(output.get("relation_type") or "background"),
        "confidence": safe_float(output.get("confidence")),
        "evidence": output.get("evidence") if isinstance(output.get("evidence"), dict) else {},
        "rationale": normalize_space(output.get("rationale") or ""),
        "rejection_reason": "" if accepted else str(output.get("rejection_reason") or "not_accepted"),
        "used_model": bool(record.used_model),
        "llm_error": str(record.error or ""),
        "json_repaired": bool(record.json_repaired),
        "attempts": int(record.attempts or 0),
    }


def decision_needs_retry(row: dict[str, Any]) -> bool:
    if row.get("accepted"):
        return False
    if not row.get("used_model"):
        return True
    if str(row.get("llm_error") or "").strip():
        return True
    if str(row.get("rejection_reason") or "") in {"missing_output", "model_not_run"}:
        return True
    try:
        attempts = int(row.get("attempts") or 0)
    except (TypeError, ValueError):
        attempts = 0
    return attempts <= 0


def edge_from_decision(row: dict[str, Any]) -> dict[str, Any]:
    edge_type = row["edge_type"]
    edge_id = f"{slugify(edge_type)}__{slugify(row['source_entity'])}__{slugify(row['target_entity'])}__{slugify(row['target_document'])}"
    evidence = dict(row.get("evidence")) if isinstance(row.get("evidence"), dict) else {}
    evidence["schema_slots"] = sorted(set(evidence) | {"mechanism", "methodological_problem", "tradeoff"})
    evidence["cue"] = "llm_successor_edge"
    if row.get("rationale"):
        evidence["successor_rationale"] = row["rationale"]
    return {
        "edge_id": edge_id,
        "source_entity": row["source_entity"],
        "target_entity": row["target_entity"],
        "edge_type": edge_type,
        "entity_type": row.get("entity_type") or "",
        "schema_group": row.get("schema_group") or "",
        "source_entity_type": row.get("source_entity_type") or "",
        "target_entity_type": row.get("target_entity_type") or "",
        "source_schema_group": row.get("source_schema_group") or row.get("schema_group") or "",
        "target_schema_group": row.get("target_schema_group") or row.get("schema_group") or "",
        "candidate_scope_value": row.get("candidate_scope_value") or row.get("schema_group") or row.get("entity_type") or "",
        "source_document": row["source_document"],
        "target_document": row["target_document"],
        "time_delta_days": row["time_delta_days"],
        "taxonomy_nodes": row.get("taxonomy_nodes") or [],
        "confidence": round(float(row.get("confidence") or 0.0), 3),
        "evidence": evidence,
        "substring_verified": True,
        "successor_extraction": {
            "candidate_score": row.get("candidate_score"),
            "candidate_reasons": row.get("candidate_reasons") or [],
            "candidate_scope": row.get("candidate_scope") or "",
            "rationale": row.get("rationale") or "",
        },
    }


def best_document(entity: dict[str, Any], docs: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for doc_id in entity["support_documents"]:
        if doc_id in docs:
            return docs[doc_id]
    return None


def best_mention_quote(entity_id: str, mentions: dict[str, list[dict[str, Any]]]) -> str:
    rows = mentions.get(entity_id) or []
    rows = sorted(rows, key=lambda row: -len(str(row.get("evidence") or "")))
    return normalize_space(rows[0].get("evidence") or "")[:500] if rows else ""


def excerpt_for_entity(entity: dict[str, Any], doc: dict[str, Any]) -> str:
    text = doc["text"]
    name = entity["canonical_name"].lower()
    low = text.lower()
    pos = low.find(name)
    if pos < 0:
        return text[:360]
    return normalize_space(text[max(0, pos - 120) : pos + 300])


def entity_name_from_id(entity_id: str) -> str:
    value = entity_id.split("__", 1)[1] if "__" in entity_id else entity_id
    return value.replace("_", " ")


def entity_name_usable(name: str) -> bool:
    low = name.lower().strip()
    if low in GENERIC_NAMES:
        return False
    if len(low) < 4:
        return False
    if len(low.split()) > 7:
        return False
    if any(part in f" {low} " for part in NAME_STOP_SUBSTRINGS):
        return False
    tokens = low.split()
    if len(tokens) == 1 and (low not in {"bert", "gpt", "llm", "lda", "svm"}):
        return False
    if low.startswith(("it ", "this ", "that ", "there ", "these ", "those ")):
        return False
    if low.endswith((" that", " and", " of", " for", " with", " by")):
        return False
    if low in {
        "arbitrary reordering of an entire vote",
        "basque country",
        "caveat emptor",
        "empirical performance",
        "free text",
        "human health",
        "intimate connections",
        "political behavior",
        "simulating organizations",
    }:
        return False
    if tokens and tokens[0] in ACTION_GERUND_PREFIXES and tokens[-1] not in METHOD_HEAD_NOUNS:
        return False
    if len(tokens) <= 3 and tokens[-1:] == ["and"]:
        return False
    return True


def label_tokens(text: str) -> list[str]:
    return [token for token in slugify(text, max_len=200).split("_") if len(token) >= 2]


def acronym_for_tokens(tokens: list[str]) -> str:
    core = [token for token in tokens if token not in LABEL_STRUCTURE_TOKENS]
    if len(core) < 2:
        return ""
    return "".join(token[0] for token in core)


def label_core_tokens(tokens: list[str], *, paired_acronyms: set[str]) -> set[str]:
    filler = LABEL_STRUCTURE_TOKENS | {token for token in paired_acronyms if len(token) >= 2}
    return {token for token in tokens if token not in filler}


def label_variant_reason(source_name: str, target_name: str) -> str:
    source_tokens = label_tokens(source_name)
    target_tokens = label_tokens(target_name)
    if not source_tokens or not target_tokens:
        return ""
    if source_tokens == target_tokens:
        return "duplicate_label"
    if normalized_label_tokens(source_tokens) == normalized_label_tokens(target_tokens):
        return "same_core_label"

    paired_acronyms = {acronym_for_tokens(source_tokens), acronym_for_tokens(target_tokens)}
    source_core = normalized_core_tokens(source_tokens, paired_acronyms=paired_acronyms)
    target_core = normalized_core_tokens(target_tokens, paired_acronyms=paired_acronyms)
    if not source_core or not target_core:
        return ""

    if source_core == target_core:
        return "same_core_label"

    source_norm = " ".join(source_tokens)
    target_norm = " ".join(target_tokens)
    source_in_target_label = f" {source_norm} " in f" {target_norm} "
    target_in_source_label = f" {target_norm} " in f" {source_norm} "
    generic_extras = LABEL_VARIANT_EXTRA_TOKENS | LABEL_CONTEXT_EXTRA_TOKENS

    if source_core <= target_core:
        extras = target_core - source_core
        if extras <= LABEL_VARIANT_EXTRA_TOKENS:
            return "source_label_with_generic_modifier"
        if source_in_target_label and extras <= generic_extras:
            return "source_label_with_context_suffix"

    if target_core <= source_core:
        extras = source_core - target_core
        if extras <= LABEL_VARIANT_EXTRA_TOKENS:
            return "target_label_with_generic_modifier"
        if target_in_source_label and extras <= generic_extras:
            return "target_label_with_context_suffix"

    overlap = len(source_core & target_core)
    union = len(source_core | target_core)
    if union and overlap / union >= 0.86 and (source_in_target_label or target_in_source_label):
        return "near_duplicate_label"
    return ""


def normalized_label_tokens(tokens: list[str]) -> list[str]:
    return [singularize_label_token(token) for token in tokens]


def normalized_core_tokens(tokens: list[str], *, paired_acronyms: set[str]) -> set[str]:
    return {singularize_label_token(token) for token in label_core_tokens(tokens, paired_acronyms=paired_acronyms)}


def singularize_label_token(token: str) -> str:
    token = token.lower()
    if len(token) <= 3:
        return token
    if token.endswith(("ss", "us", "is")):
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith(("ches", "shes", "xes", "zes")) and len(token) > 5:
        return token[:-2]
    if token.endswith("s") and len(token) > 4:
        return token[:-1]
    return token


def generic_predecessor_reason(source_name: str, entity_type: str) -> str:
    tokens = label_tokens(source_name)
    if not tokens:
        return ""
    paired_acronyms = {acronym_for_tokens(tokens)}
    core_tokens = label_core_tokens(tokens, paired_acronyms=paired_acronyms)
    core_phrase = " ".join(tokens)
    stripped_core_phrase = " ".join(token for token in tokens if token not in LABEL_STRUCTURE_TOKENS)
    tail = tokens[-1]
    if source_name.lower().strip() in BROAD_PREDECESSOR_CORE_PHRASES:
        return "generic_predecessor_source"
    if stripped_core_phrase in BROAD_PREDECESSOR_CORE_PHRASES:
        return "generic_predecessor_source"
    if core_phrase in BROAD_PREDECESSOR_CORE_PHRASES:
        return "generic_predecessor_source"
    if "machine learning" in stripped_core_phrase and len(core_tokens) <= 3:
        return "generic_predecessor_source"
    if "deep learning" in stripped_core_phrase and len(core_tokens) <= 3:
        return "generic_predecessor_source"
    if {"machine", "learning"} <= core_tokens and len(core_tokens - GENERIC_ML_MODIFIERS) <= 2:
        return "generic_predecessor_source"
    if {"deep", "learning"} <= core_tokens and len(core_tokens - GENERIC_ML_MODIFIERS) <= 2:
        return "generic_predecessor_source"
    if {"machine", "learning"} <= set(tokens) and tail in LABEL_STRUCTURE_TOKENS:
        return "generic_predecessor_source"
    if {"deep", "learning"} <= set(tokens) and tail in LABEL_STRUCTURE_TOKENS:
        return "generic_predecessor_source"
    if entity_type in {"data_source", "evaluation_protocol", "governance_practice", "measurement_strategy"}:
        if tail in BROAD_PREDECESSOR_ENTITY_TERMS and len(core_tokens) <= 2:
            return "generic_predecessor_source"
    if tail in BROAD_PREDECESSOR_HEAD_TOKENS and len(core_tokens) <= 2:
        return "generic_predecessor_source"
    if tail in {"model", "models"} and stripped_core_phrase in {"deep learning", "machine learning", "supervised learning"}:
        return "generic_predecessor_source"
    if len(core_tokens) <= 1 and tail in LABEL_STRUCTURE_TOKENS and not (core_tokens & SPECIFIC_METHOD_ANCHOR_TOKENS):
        return "generic_predecessor_source"
    return ""


def content_tokens(text: str) -> set[str]:
    excluded = GENERIC_NAMES | LABEL_STRUCTURE_TOKENS
    return {token for token in slugify(text, max_len=200).split("_") if len(token) >= 4 and token not in excluded}


def evolution_cue_hit(text: str) -> bool:
    low = text.lower()
    cues = [
        "adapt",
        "based on",
        "benchmark",
        "build",
        "extend",
        "improv",
        "instead of",
        "move beyond",
        "new method",
        "outperform",
        "replace",
        "robust",
        "scale",
        "supersed",
    ]
    return any(cue in low for cue in cues)


def evolution_cue_near_text(text_low: str, needle_low: str, *, radius: int = 160) -> bool:
    pos = text_low.find(needle_low)
    if pos < 0:
        return False
    context = text_low[max(0, pos - radius) : pos + len(needle_low) + radius]
    return evolution_cue_hit(context)


def score_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(row.get("candidate_score") or 0.0) for row in rows]
    if not values:
        return {"min": None, "mean": None, "max": None}
    return {"min": round(min(values), 3), "mean": round(sum(values) / len(values), 3), "max": round(max(values), 3)}


def safe_float(value: Any) -> float:
    try:
        return round(max(0.0, min(1.0, float(value))), 3)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
