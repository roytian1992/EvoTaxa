from __future__ import annotations

from typing import Any

from evotaxa.config import GraphConfig
from evotaxa.models import EvolutionEdge


def score_edges(
    edges: list[EvolutionEdge],
    *,
    relation_schema: dict[str, dict[str, Any]],
    evidence_schema: dict[str, dict[str, Any]],
    config: GraphConfig,
) -> list[dict[str, Any]]:
    rows = []
    for edge in edges:
        scores = edge_score_components(edge, relation_schema=relation_schema, evidence_schema=evidence_schema, config=config)
        previous_confidence = _clamp(float(edge.confidence or 0.0))
        edge.evidence = {**(edge.evidence or {}), "edge_score": scores}
        edge.confidence = float(scores["edge_score"])
        rows.append(
            {
                "edge_id": edge.edge_id,
                "source_entity": edge.source_entity,
                "target_entity": edge.target_entity,
                "edge_type": edge.edge_type,
                "previous_confidence": round(previous_confidence, 3),
                **scores,
            }
        )
    return rows


def edge_score_components(
    edge: EvolutionEdge,
    *,
    relation_schema: dict[str, dict[str, Any]],
    evidence_schema: dict[str, dict[str, Any]],
    config: GraphConfig,
) -> dict[str, float]:
    relation_confidence = _clamp(float(edge.confidence or 0.0))
    quote_grounding = 1.0 if edge.substring_verified else _quote_grounding(edge)
    temporal_order = _temporal_order(edge)
    taxonomy_locality = 1.0 if edge.taxonomy_nodes else 0.55
    schema_fit = _schema_fit(edge, relation_schema, config)
    evidence_slot_completeness = _evidence_slot_completeness(edge, relation_schema, evidence_schema)
    score = (
        0.30 * relation_confidence
        + 0.22 * quote_grounding
        + 0.16 * temporal_order
        + 0.12 * taxonomy_locality
        + 0.12 * schema_fit
        + 0.08 * evidence_slot_completeness
    )
    return {
        "relation_confidence": round(relation_confidence, 3),
        "quote_grounding": round(quote_grounding, 3),
        "temporal_order": round(temporal_order, 3),
        "taxonomy_locality": round(taxonomy_locality, 3),
        "schema_fit": round(schema_fit, 3),
        "evidence_slot_completeness": round(evidence_slot_completeness, 3),
        "edge_score": round(_clamp(score), 3),
    }


def _quote_grounding(edge: EvolutionEdge) -> float:
    checks = ((edge.evidence or {}).get("evidence_audit") or {}).get("verified_quote_count")
    try:
        count = int(checks or 0)
    except (TypeError, ValueError):
        count = 0
    if count > 0:
        return 0.75
    evidence = edge.evidence or {}
    slot_values = [value for value in evidence.values() if isinstance(value, dict)]
    if any(str(value.get("quote") or "").strip() for value in slot_values):
        return 0.45
    return 0.1


def _temporal_order(edge: EvolutionEdge) -> float:
    if edge.time_delta_days is None:
        return 0.6
    if edge.time_delta_days < 0:
        return 0.0
    if edge.time_delta_days == 0:
        return 0.8
    return 1.0


def _schema_fit(edge: EvolutionEdge, relation_schema: dict[str, dict[str, Any]], config: GraphConfig) -> float:
    spec = relation_schema.get(edge.edge_type)
    if not spec:
        return 0.25
    score = 0.55
    if edge.edge_type in set(config.strong_edge_types):
        score += 0.2
    if spec.get("evidence_slots"):
        score += 0.15
    if spec.get("definition"):
        score += 0.1
    return _clamp(score)


def _evidence_slot_completeness(
    edge: EvolutionEdge,
    relation_schema: dict[str, dict[str, Any]],
    evidence_schema: dict[str, dict[str, Any]],
) -> float:
    slots = list((relation_schema.get(edge.edge_type) or {}).get("evidence_slots") or [])
    if not slots:
        slots = [slot for slot, spec in evidence_schema.items() if spec.get("required")]
    if not slots:
        return 0.8
    evidence = edge.evidence or {}
    filled = 0
    for slot in slots:
        value = evidence.get(slot)
        if isinstance(value, dict) and (str(value.get("quote") or "").strip() or str(value.get("description") or "").strip()):
            filled += 1
    return filled / len(slots)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
