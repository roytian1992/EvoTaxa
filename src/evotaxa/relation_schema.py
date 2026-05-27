from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from evotaxa.config import GraphConfig
from evotaxa.io import slugify


DEFAULT_RELATION_SCHEMA: dict[str, dict[str, Any]] = {
    "extends": {
        "label": "Extends",
        "definition": "The target entity builds on or adds capabilities to the source entity.",
        "source_role": "prior mechanism or method",
        "target_role": "successor mechanism or method",
        "directionality": "directed",
        "temporal_constraint": "source_before_or_same_as_target",
        "evidence_slots": ["mechanism", "bottleneck", "tradeoff"],
        "strong_edge": True,
        "schema_source": "fixed",
    },
    "improves": {
        "label": "Improves",
        "definition": "The target entity improves performance, robustness, coverage, or effectiveness over the source entity.",
        "source_role": "baseline or earlier form",
        "target_role": "improved form",
        "directionality": "directed",
        "temporal_constraint": "source_before_or_same_as_target",
        "evidence_slots": ["mechanism", "bottleneck", "tradeoff"],
        "strong_edge": True,
        "schema_source": "fixed",
    },
    "replaces": {
        "label": "Replaces",
        "definition": "The target entity substitutes for or supersedes the source entity.",
        "source_role": "displaced form",
        "target_role": "replacement form",
        "directionality": "directed",
        "temporal_constraint": "source_before_or_same_as_target",
        "evidence_slots": ["mechanism", "tradeoff"],
        "strong_edge": True,
        "schema_source": "fixed",
    },
    "adapts": {
        "label": "Adapts",
        "definition": "The target entity transfers or adapts the source entity to a new context, population, domain, or setting.",
        "source_role": "source mechanism or design",
        "target_role": "adapted mechanism or design",
        "directionality": "directed",
        "temporal_constraint": "source_before_or_same_as_target",
        "evidence_slots": ["mechanism", "bottleneck", "tradeoff"],
        "strong_edge": True,
        "schema_source": "fixed",
    },
    "uses_component": {
        "label": "Uses Component",
        "definition": "The target entity incorporates the source entity as a component, module, instrument, or dependency.",
        "source_role": "component",
        "target_role": "composed system or intervention",
        "directionality": "directed",
        "temporal_constraint": "none",
        "evidence_slots": ["mechanism"],
        "strong_edge": False,
        "schema_source": "fixed",
    },
    "compares": {
        "label": "Compares",
        "definition": "The entities are compared, benchmarked, or contrasted without a confirmed successor relation.",
        "source_role": "comparison reference",
        "target_role": "compared entity",
        "directionality": "directed",
        "temporal_constraint": "none",
        "evidence_slots": ["mechanism", "tradeoff"],
        "strong_edge": False,
        "schema_source": "fixed",
    },
    "background": {
        "label": "Background",
        "definition": "The relation is weak background context rather than a confirmed evolution edge.",
        "source_role": "background entity",
        "target_role": "background entity",
        "directionality": "undirected",
        "temporal_constraint": "none",
        "evidence_slots": ["mechanism"],
        "strong_edge": False,
        "schema_source": "fixed",
    },
}


def fixed_relation_schema(config: GraphConfig) -> dict[str, dict[str, Any]]:
    schema = {key: dict(value) for key, value in DEFAULT_RELATION_SCHEMA.items()}
    for edge_type, cues in config.edge_cues.items():
        schema.setdefault(
            edge_type,
            {
                "label": edge_type.replace("_", " ").title(),
                "definition": f"Configured relation type inferred from cues for {edge_type}.",
                "source_role": "source entity",
                "target_role": "target entity",
                "directionality": "directed",
                "temporal_constraint": "none",
                "evidence_slots": ["mechanism", "bottleneck", "tradeoff"],
                "strong_edge": edge_type in set(config.strong_edge_types),
                "schema_source": "fixed",
            },
        )
        schema[edge_type]["cues"] = list(cues)
    for edge_type, spec in config.relation_schema.items():
        merged = dict(schema.get(edge_type, {}))
        merged.update(spec)
        schema[edge_type] = merged
    return _limit_schema(schema, config.max_relation_types)


def normalize_relation_schema(raw_schema: dict[str, Any], config: GraphConfig) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    base = fixed_relation_schema(config)
    report: list[dict[str, Any]] = []
    rows = raw_schema.get("relation_types") if isinstance(raw_schema, dict) else None
    if not isinstance(rows, list):
        return base, [{"status": "fallback", "reason": "missing_relation_types"}]

    for row in rows:
        if not isinstance(row, dict):
            continue
        edge_type = _edge_type(row)
        if not edge_type:
            report.append({"status": "rejected", "reason": "missing_edge_type", "row": row})
            continue
        spec = {
            "label": str(row.get("label") or edge_type.replace("_", " ").title()),
            "definition": str(row.get("definition") or ""),
            "source_role": str(row.get("source_role") or "source entity"),
            "target_role": str(row.get("target_role") or "target entity"),
            "directionality": str(row.get("directionality") or "directed"),
            "temporal_constraint": str(row.get("temporal_constraint") or "none"),
            "evidence_slots": _evidence_slots(row.get("evidence_slots") or row.get("evidence_fields")),
            "cues": [str(item) for item in row.get("cues") or [] if str(item).strip()],
            "positive_cues": [str(item) for item in row.get("positive_cues") or [] if str(item).strip()],
            "negative_cues": [str(item) for item in row.get("negative_cues") or [] if str(item).strip()],
            "counterexamples": [str(item) for item in row.get("counterexamples") or [] if str(item).strip()],
            "strong_edge": bool(row.get("strong_edge", edge_type in set(config.strong_edge_types))),
            "schema_source": "inferred",
        }
        if not spec["definition"]:
            report.append({"status": "rejected", "edge_type": edge_type, "reason": "missing_definition"})
            continue
        base[edge_type] = {**base.get(edge_type, {}), **spec}
        report.append({"status": "accepted", "edge_type": edge_type})
    return _limit_schema(base, config.max_relation_types), report


def adapt_relation_schema(
    schema: dict[str, dict[str, Any]],
    edge_evidence_audit: list[dict[str, Any]],
    config: GraphConfig,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    adapted = {key: dict(value) for key, value in schema.items()}
    report: list[dict[str, Any]] = []
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in edge_evidence_audit:
        by_type[str(row.get("edge_type") or "background")].append(row)

    for edge_type, rows in sorted(by_type.items()):
        support = len(rows)
        if support < config.relation_schema_adaptation_min_support:
            continue
        verified_rate = sum(1 for row in rows if int(row.get("verified_quote_count") or 0) > 0) / support
        mean_confidence = sum(float(row.get("confidence") or 0.0) for row in rows) / support
        spec = adapted.setdefault(edge_type, {})
        spec["observed_support"] = support
        spec["observed_verified_rate"] = round(verified_rate, 3)
        spec["observed_mean_confidence"] = round(mean_confidence, 3)
        if spec.get("schema_source") not in {"fixed", "inferred"}:
            spec["schema_source"] = "adaptive"
        report.append(
            {
                "edge_type": edge_type,
                "status": "updated",
                "support": support,
                "verified_rate": round(verified_rate, 3),
                "mean_confidence": round(mean_confidence, 3),
            }
        )

    missing_counts = Counter(str(row.get("edge_type") or "") for row in edge_evidence_audit if row.get("status") == "candidate")
    for edge_type, count in missing_counts.items():
        if count >= config.relation_schema_adaptation_min_support and edge_type in adapted:
            adapted[edge_type]["needs_review"] = True
            report.append({"edge_type": edge_type, "status": "needs_review", "candidate_edges": count})
    return _limit_schema(adapted, config.max_relation_types), report


def relation_schema_prompt(schema: dict[str, dict[str, Any]]) -> str:
    rows = []
    for edge_type, spec in sorted(schema.items()):
        rows.append(
            {
                "edge_type": edge_type,
                "definition": spec.get("definition", ""),
                "source_role": spec.get("source_role", ""),
                "target_role": spec.get("target_role", ""),
                "directionality": spec.get("directionality", "directed"),
                "temporal_constraint": spec.get("temporal_constraint", "none"),
                "evidence_slots": spec.get("evidence_slots", spec.get("evidence_fields", [])),
                "positive_cues": spec.get("positive_cues") or spec.get("cues", []),
                "negative_cues": spec.get("negative_cues", []),
                "strong_edge": bool(spec.get("strong_edge", False)),
            }
        )
    return str(rows)


def relation_schema_records(schema: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"edge_type": edge_type, **spec} for edge_type, spec in sorted(schema.items())]


def _edge_type(row: dict[str, Any]) -> str:
    raw = str(row.get("edge_type") or row.get("id") or row.get("name") or "").strip()
    return slugify(raw) if raw else ""


def _evidence_slots(value: Any) -> list[str]:
    if not isinstance(value, list):
        return ["mechanism", "bottleneck", "tradeoff"]
    fields = [str(item).strip() for item in value if str(item).strip()]
    return fields or ["mechanism", "bottleneck", "tradeoff"]


def _limit_schema(schema: dict[str, dict[str, Any]], limit: int) -> dict[str, dict[str, Any]]:
    if limit <= 0:
        return schema
    preferred = ["extends", "improves", "replaces", "adapts", "uses_component", "compares", "background"]
    keys = [key for key in preferred if key in schema]
    keys.extend(key for key in sorted(schema) if key not in set(keys))
    return {key: schema[key] for key in keys[:limit]}
