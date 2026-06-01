#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from evotaxa.io import iter_jsonl, slugify, write_json, write_jsonl  # noqa: E402
from extract_successor_edges import (  # noqa: E402
    ALLOWED_RELATION_TYPES,
    SPECIFIC_METHOD_ANCHOR_TOKENS,
    content_tokens,
    edge_from_decision,
    evolution_cue_hit,
    generic_predecessor_reason,
    label_tokens,
    label_variant_reason,
)
from schema_groups import SCHEMA_GROUPS, schema_group_for_type  # noqa: E402


DEFAULT_DISPLAY_RELATIONS = {"adapts", "extends", "improves", "replaces", "specializes", "generalizes"}
WEAK_LABEL_PHRASES = {
    "computational methodologies",
    "fine tuned machine learning models",
    "machine and deep learning",
    "machine learning based modeling",
    "machine learning classification models",
    "machine learning applied to political",
    "machine learning ml methods",
    "mame re",
    "methodological approach",
    "methodological foundation",
    "ongoing methodological program",
    "parameter settings",
    "political science",
    "preprocessing steps",
    "python implementation",
    "replicable methodology",
    "statistical inference",
    "survey research",
    "systematic review",
    "traditional machine learning",
    "unsupervised machine learning method",
    "working python implementation",
}
WEAK_LABEL_TAILS = {
    "actor",
    "actors",
    "baseline",
    "baselines",
    "challenge",
    "challenges",
    "consideration",
    "considerations",
    "data",
    "methodologies",
    "methodology",
    "posts",
    "practice",
    "practices",
    "program",
    "programs",
    "process",
    "processes",
    "recommendation",
    "recommendations",
    "sample",
    "samples",
    "science",
    "settings",
    "steps",
    "structure",
    "task",
    "tasks",
}
TASK_TAILS = {
    "analysis",
    "classification",
    "coding",
    "detection",
    "estimation",
    "extraction",
    "identification",
    "measurement",
    "prediction",
    "recognition",
}
TARGET_BROAD_FAMILY_TAILS = {
    "approach",
    "approaches",
    "framework",
    "frameworks",
    "method",
    "methods",
    "model",
    "models",
    "strategy",
    "strategies",
    "technique",
    "techniques",
}
MISBUCKETED_DATA_SOURCE_TOKENS = {
    "bert",
    "embedding",
    "embeddings",
    "language",
    "llm",
    "model",
    "models",
    "neural",
    "transformer",
    "transformers",
}
LINEAGE_CUES = {
    "adapt",
    "alternative",
    "benchmark",
    "build",
    "complement",
    "extend",
    "improv",
    "instead",
    "limitation",
    "move beyond",
    "outperform",
    "overcome",
    "propose",
    "replace",
    "supersed",
}
GENERIC_ML_ARCHITECTURE_TERMS = {
    "ann",
    "artificial",
    "attention",
    "bayesian",
    "bert",
    "cnn",
    "convolutional",
    "deep",
    "embedding",
    "embeddings",
    "encoder",
    "gcn",
    "genn",
    "gnn",
    "graph",
    "language",
    "lstm",
    "mlp",
    "neural",
    "recurrent",
    "transformer",
    "transformers",
}
CSS_DOMAIN_GROUNDING_TERMS = {
    "annotation",
    "behavior",
    "behaviour",
    "bias",
    "classification",
    "coding",
    "discourse",
    "election",
    "emotion",
    "event",
    "gender",
    "hate",
    "ideology",
    "misinformation",
    "network",
    "political",
    "propaganda",
    "public",
    "sentiment",
    "sexism",
    "social",
    "survey",
    "text",
    "tweet",
    "twitter",
    "user",
}
EXTERNAL_KNOWLEDGE_MARKERS = {
    "does not explicitly cite",
    "not explicitly cite",
    "well-established",
    "general machine learning literature",
    "broader machine learning",
    "known in machine learning",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply a high-precision display filter to LLM successor decisions.")
    parser.add_argument("--input-root", type=Path, required=True, help="Directory containing successor_decisions.jsonl.")
    parser.add_argument("--run-root", type=Path, default=None, help="Completed EvoTaxa run root. Required with --install.")
    parser.add_argument("--output-root", type=Path, default=None, help="Defaults to --input-root.")
    parser.add_argument("--min-confidence", type=float, default=0.84)
    parser.add_argument("--min-time-delta-days", type=int, default=180)
    parser.add_argument(
        "--display-relation-types",
        nargs="*",
        default=sorted(DEFAULT_DISPLAY_RELATIONS),
        choices=ALLOWED_RELATION_TYPES,
    )
    parser.add_argument("--install", action="store_true", help="Install strict accepted edges into <run-root>/graph/successor_edges.accepted.jsonl.")
    args = parser.parse_args()

    input_root = args.input_root.expanduser().resolve()
    output_root = (args.output_root or args.input_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    decisions_path = input_root / "successor_decisions.jsonl"
    decisions = list(iter_jsonl(decisions_path))
    strict_decisions: list[dict[str, Any]] = []
    strict_edges: list[dict[str, Any]] = []
    relation_types = set(args.display_relation_types)

    for row in decisions:
        reason = strict_rejection_reason(
            row,
            relation_types=relation_types,
            min_confidence=args.min_confidence,
            min_time_delta_days=args.min_time_delta_days,
        )
        strict_row = dict(row)
        strict_row["strict_accepted"] = not reason
        strict_row["strict_rejection_reason"] = reason
        strict_decisions.append(strict_row)
        if reason:
            continue
        edge = edge_from_decision(row)
        edge.setdefault("successor_extraction", {})
        edge["successor_extraction"]["strict_filter"] = {
            "accepted": True,
            "min_confidence": args.min_confidence,
            "min_time_delta_days": args.min_time_delta_days,
            "display_relation_types": sorted(relation_types),
        }
        strict_edges.append(edge)

    strict_decisions_path = output_root / "successor_decisions.strict.jsonl"
    strict_edges_path = output_root / "successor_edges.strict_accepted.jsonl"
    summary_path = output_root / "successor_edges.strict_summary.json"
    write_jsonl(strict_decisions_path, strict_decisions)
    write_jsonl(strict_edges_path, strict_edges)

    summary = {
        "input_root": str(input_root),
        "output_root": str(output_root),
        "decisions": len(decisions),
        "raw_accepted": sum(1 for row in decisions if row.get("accepted")),
        "strict_accepted": len(strict_edges),
        "strict_rejected_raw_accepted": sum(1 for row in strict_decisions if row.get("accepted") and not row.get("strict_accepted")),
        "raw_rejection_reasons": dict(Counter(str(row.get("rejection_reason") or "") for row in decisions if not row.get("accepted"))),
        "strict_rejection_reasons": dict(Counter(str(row.get("strict_rejection_reason") or "") for row in strict_decisions if row.get("strict_rejection_reason"))),
        "strict_relation_types": dict(Counter(str(edge.get("edge_type") or "") for edge in strict_edges)),
        "strict_schema_groups": dict(Counter(str(edge.get("schema_group") or "") for edge in strict_edges)),
        "strict_source_entities": len({edge.get("source_entity") for edge in strict_edges}),
        "strict_target_entities": len({edge.get("target_entity") for edge in strict_edges}),
        "min_confidence": args.min_confidence,
        "min_time_delta_days": args.min_time_delta_days,
        "display_relation_types": sorted(relation_types),
        "strict_edges_path": str(strict_edges_path),
        "strict_decisions_path": str(strict_decisions_path),
        "installed_path": "",
        "policy": "High-precision display filter; raw LLM decisions remain unchanged.",
    }
    write_json(summary_path, summary)
    if args.install:
        if not args.run_root:
            raise ValueError("--run-root is required with --install")
        run_root = args.run_root.expanduser().resolve()
        target = run_root / "graph" / "successor_edges.accepted.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(strict_edges_path, target)
        shutil.copyfile(summary_path, run_root / "graph" / "successor_edges.strict_summary.json")
        summary["installed_path"] = str(target)
        write_json(summary_path, summary)
        write_json(run_root / "graph" / "successor_edges.strict_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def strict_rejection_reason(
    row: dict[str, Any],
    *,
    relation_types: set[str],
    min_confidence: float,
    min_time_delta_days: int,
) -> str:
    if not row.get("accepted"):
        return "raw_rejected"
    edge_type = str(row.get("edge_type") or "")
    if edge_type not in relation_types:
        return "relation_type_not_for_display"
    if float(row.get("confidence") or 0.0) < min_confidence:
        return "low_confidence"
    try:
        delta = int(row.get("time_delta_days") or 0)
    except (TypeError, ValueError):
        return "missing_time_delta"
    if delta < min_time_delta_days:
        return "too_near_in_time"
    if row.get("source_document") and row.get("source_document") == row.get("target_document"):
        return "same_source_and_target_document"

    source_name = str(row.get("source_name") or "")
    target_name = str(row.get("target_name") or "")
    entity_type = row_schema_group(row)
    source_entity_type = row_source_entity_type(row)
    target_entity_type = row_target_entity_type(row)
    variant_reason = label_variant_reason(source_name, target_name)
    if variant_reason:
        return f"label_variant:{variant_reason}"
    predecessor_reason = generic_predecessor_reason(source_name, source_entity_type)
    if predecessor_reason:
        return predecessor_reason
    source_label_reason = weak_label_reason(source_name, source_entity_type, position="source")
    if source_label_reason:
        return source_label_reason
    target_label_reason = weak_label_reason(target_name, target_entity_type, position="target")
    if target_label_reason:
        return target_label_reason
    if (source_entity_type == "data_source" or target_entity_type == "data_source") and misbucketed_data_source(source_name, target_name):
        return "misbucketed_data_source_label"
    if source_task_problem_only(source_name, target_name, source_entity_type, schema_group=entity_type):
        return "source_is_task_not_predecessor"
    if edge_type == "generalizes" and broad_generalization_target(source_name, target_name, target_entity_type, schema_group=entity_type):
        return "broad_generalization_not_display_edge"
    if generic_ml_architecture_lineage(row):
        return "generic_ml_architecture_not_css_evolution"
    if not lineage_evidence_supported(row):
        return "weak_lineage_evidence"
    return ""


def row_source_entity_type(row: dict[str, Any]) -> str:
    value = str(row.get("source_entity_type") or "")
    if value:
        return value
    candidate_type = str(row.get("entity_type") or "")
    if candidate_type and candidate_type not in SCHEMA_GROUPS:
        return candidate_type
    source_id = str(row.get("source_entity") or "")
    return source_id.split("__", 1)[0] if "__" in source_id else candidate_type


def row_target_entity_type(row: dict[str, Any]) -> str:
    value = str(row.get("target_entity_type") or "")
    if value:
        return value
    candidate_type = str(row.get("entity_type") or "")
    if candidate_type and candidate_type not in SCHEMA_GROUPS:
        return candidate_type
    target_id = str(row.get("target_entity") or "")
    return target_id.split("__", 1)[0] if "__" in target_id else candidate_type


def row_schema_group(row: dict[str, Any]) -> str:
    value = str(row.get("schema_group") or row.get("source_schema_group") or row.get("target_schema_group") or "")
    if value:
        return value
    candidate_type = str(row.get("entity_type") or "")
    if candidate_type in SCHEMA_GROUPS:
        return candidate_type
    return schema_group_for_type(candidate_type)


def weak_label_reason(name: str, entity_type: str, *, position: str) -> str:
    low = " ".join(name.lower().split())
    tokens = label_tokens(name)
    if not tokens:
        return f"weak_{position}_label"
    if low in WEAK_LABEL_PHRASES:
        return f"weak_{position}_label"
    if len(tokens) == 1 and tokens[0] not in SPECIFIC_METHOD_ANCHOR_TOKENS and tokens[0] not in {"bert", "gpt", "lda", "llm", "mcmc", "svm"}:
        return f"weak_{position}_label"
    tail = tokens[-1]
    core = content_tokens(name)
    anchor_hit = bool(core & (SPECIFIC_METHOD_ANCHOR_TOKENS | {"centrality", "clustering", "cosine", "digital", "filtering", "graph", "hierarchical", "language", "likelihood", "network", "neural", "similarity", "text", "twins"}))
    if tail in WEAK_LABEL_TAILS and not anchor_hit:
        return f"weak_{position}_label"
    if position == "target" and tail in TARGET_BROAD_FAMILY_TAILS and len(core) <= 2 and not anchor_hit:
        return "broad_target_label"
    if position == "source" and "baseline" in tokens and len(core - {"baseline", "baselines"}) <= 2:
        return "baseline_source_not_predecessor"
    if position == "source" and tail in {"inference", "learning", "research"} and len(core) <= 2 and not anchor_hit:
        return "weak_source_label"
    if "methodological" in tokens and tail in {"foundation", "program", "approach"}:
        return f"weak_{position}_label"
    if tail in {"implementation", "program"} and len(core) <= 2:
        return f"weak_{position}_label"
    if entity_type == "data_source" and tail in {"posts", "platforms"} and position == "source":
        return "weak_source_label"
    return ""


def misbucketed_data_source(source_name: str, target_name: str) -> bool:
    source_tokens = set(label_tokens(source_name))
    target_tokens = set(label_tokens(target_name))
    return bool((source_tokens | target_tokens) & MISBUCKETED_DATA_SOURCE_TOKENS)


def source_task_problem_only(source_name: str, target_name: str, entity_type: str, *, schema_group: str = "") -> bool:
    if entity_type not in {"method", "measurement_strategy"} and schema_group != "analytic_method":
        return False
    source_tokens = label_tokens(source_name)
    if not source_tokens or source_tokens[-1] not in TASK_TAILS:
        return False
    source_core = content_tokens(source_name)
    target_core = content_tokens(target_name)
    if source_core & target_core:
        return False
    if source_core & SPECIFIC_METHOD_ANCHOR_TOKENS:
        return False
    return True


def broad_generalization_target(source_name: str, target_name: str, entity_type: str, *, schema_group: str = "") -> bool:
    if entity_type not in {"method", "modeling_strategy", "measurement_strategy", "data_source"} and schema_group not in {"analytic_method", "evidence_and_infrastructure"}:
        return False
    source_core = content_tokens(source_name)
    target_core = content_tokens(target_name)
    target_tokens = label_tokens(target_name)
    if not target_tokens:
        return True
    if target_tokens[-1] in TARGET_BROAD_FAMILY_TAILS and len(target_core) <= 2:
        return True
    if source_core and target_core and target_core < source_core:
        return True
    if len(target_core) <= 1 and not (target_core & SPECIFIC_METHOD_ANCHOR_TOKENS):
        return True
    return False


def generic_ml_architecture_lineage(row: dict[str, Any]) -> bool:
    entity_type = row_source_entity_type(row)
    schema_group = row_schema_group(row)
    if entity_type not in {"method", "modeling_strategy", "measurement_strategy"} and schema_group != "analytic_method":
        return False
    source_tokens = set(label_tokens(str(row.get("source_name") or "")))
    target_tokens = set(label_tokens(str(row.get("target_name") or "")))
    architecture_tokens = {"ann", "cnn", "gcn", "gnn", "lstm", "neural", "transformer", "transformers"}
    if not ((source_tokens | target_tokens) & architecture_tokens):
        return False
    combined = source_tokens | target_tokens
    generic_ratio = len(combined & GENERIC_ML_ARCHITECTURE_TERMS) / max(1, len(combined))
    evidence_text = evidence_text_for_row(row).lower()
    source_quote = str(row.get("source_quote") or "").lower()
    target_quote = str(row.get("target_quote") or "").lower()
    rationale = str(row.get("rationale") or "").lower()
    target_domain_grounded = bool((set(label_tokens(target_quote)) | set(label_tokens(source_quote))) & CSS_DOMAIN_GROUNDING_TERMS)
    text_lineage = "target_text_mentions_source_with_evolution_cue" in set(str(item) for item in row.get("candidate_reasons") or [])
    external_knowledge = any(marker in rationale for marker in EXTERNAL_KNOWLEDGE_MARKERS)
    if external_knowledge:
        return True
    if generic_ratio >= 0.55 and not text_lineage:
        return True
    if generic_ratio >= 0.45 and not target_domain_grounded and not text_lineage:
        return True
    if generic_ratio >= 0.45 and not text_lineage:
        target_mentions_source = bool(source_tokens & set(label_tokens(target_quote)))
        target_has_comparison = any(cue in target_quote for cue in ["baseline", "outperform", "improve", "compared", "limitation", "instead"])
        if not (target_mentions_source and target_has_comparison):
            return True
    return False


def lineage_evidence_supported(row: dict[str, Any]) -> bool:
    candidate_reasons = set(str(item) for item in row.get("candidate_reasons") or [])
    evidence_text = evidence_text_for_row(row)
    if "target_text_mentions_source_with_evolution_cue" in candidate_reasons:
        return True
    if "target_text_mentions_source" in candidate_reasons and evolution_cue_hit(evidence_text):
        return True
    source_tokens = content_tokens(str(row.get("source_name") or ""))
    target_tokens = content_tokens(str(row.get("target_name") or ""))
    evidence_tokens = content_tokens(evidence_text)
    source_seen = bool(source_tokens & evidence_tokens)
    target_seen = bool(target_tokens & evidence_tokens)
    if source_seen and target_seen and evolution_cue_hit(evidence_text):
        return True
    if row.get("edge_type") in {"improves", "replaces"} and source_seen and improvement_evidence_hit(evidence_text):
        return True
    return False


def evidence_text_for_row(row: dict[str, Any]) -> str:
    chunks = [str(row.get("rationale") or ""), str(row.get("source_quote") or ""), str(row.get("target_quote") or "")]
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    for value in evidence.values():
        if isinstance(value, dict):
            chunks.append(str(value.get("description") or ""))
            chunks.append(str(value.get("quote") or ""))
    return " ".join(chunk for chunk in chunks if chunk)


def improvement_evidence_hit(text: str) -> bool:
    low = text.lower()
    return any(cue in low for cue in LINEAGE_CUES | {"accuracy", "baseline", "f1", "performance", "reduce", "superior"})


if __name__ == "__main__":
    raise SystemExit(main())
