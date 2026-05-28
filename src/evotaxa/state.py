from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def build_evolution_state_snapshot(
    *,
    docs: list[Any],
    nodes: list[Any],
    entities: list[Any],
    edges: list[Any],
    taxonomy_events: list[dict[str, Any]],
    schema_bundle: Any,
) -> dict[str, Any]:
    """Build a compact domain-state view for evolution modeling."""
    documents_by_slice = Counter(_slice(doc) for doc in docs)
    nodes_by_dimension = Counter(str(getattr(node, "dimension", "") or "unknown") for node in nodes)
    entities_by_type = Counter(str(getattr(entity, "entity_type", "") or "entity") for entity in entities)
    edges_by_type = Counter(str(getattr(edge, "edge_type", "") or "background") for edge in edges)
    events_by_type = Counter(str(row.get("event_type") or "unknown") for row in taxonomy_events)
    node_states = _node_states(nodes, edges, taxonomy_events)
    return {
        "state_id": "state__current",
        "documents": {
            "count": len(docs),
            "by_slice": dict(sorted(documents_by_slice.items())),
        },
        "taxonomy": {
            "node_count": len(nodes),
            "nodes_by_dimension": dict(sorted(nodes_by_dimension.items())),
            "events_by_type": dict(sorted(events_by_type.items())),
            "node_states": node_states,
        },
        "entities": {
            "entity_count": len(entities),
            "entities_by_type": dict(sorted(entities_by_type.items())),
        },
        "relations": {
            "edge_count": len(edges),
            "edges_by_type": dict(sorted(edges_by_type.items())),
            "mean_confidence": _mean([float(getattr(edge, "confidence", 0.0) or 0.0) for edge in edges]),
            "verified_edge_rate": _mean([1.0 if getattr(edge, "substring_verified", False) else 0.0 for edge in edges]),
        },
        "schema": {
            "entity_types": sorted(schema_bundle.entity_schema),
            "relation_types": sorted(schema_bundle.relation_schema),
            "evidence_slots": sorted(schema_bundle.evidence_schema),
            "revision_candidates": len(schema_bundle.revision_candidates),
        },
    }


def build_state_transition_report(
    *,
    taxonomy_events: list[dict[str, Any]],
    schema_revisions: list[dict[str, Any]],
    edge_score_rows: list[dict[str, Any]],
    relation_rejections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in taxonomy_events:
        rows.append(
            {
                "transition_id": f"taxonomy__{event.get('event_id', len(rows))}",
                "transition_family": "taxonomy",
                "transition_type": event.get("event_type") or "unknown",
                "source": event.get("source_node_ids") or [],
                "target": event.get("target_node_ids") or [],
                "support": len(event.get("support_documents") or []) + len(event.get("support_edges") or []),
                "confidence": float(event.get("confidence") or 0.0),
                "reason": event.get("reason") or "",
            }
        )
    for revision in schema_revisions:
        rows.append(
            {
                "transition_id": f"schema__{revision.get('candidate_id', len(rows))}",
                "transition_family": "schema",
                "transition_type": revision.get("revision_type") or "unknown",
                "source": revision.get("schema_family") or "",
                "target": revision.get("schema_name") or revision.get("edge_type") or "",
                "support": int(revision.get("support") or 0),
                "confidence": float(revision.get("confidence") or revision.get("judge_confidence") or 0.0),
                "reason": revision.get("reason") or revision.get("judge_rationale") or "",
                "decision": revision.get("decision") or revision.get("status") or "",
            }
        )
    for row in edge_score_rows:
        if float(row.get("edge_score") or 0.0) < 0.55 or float(row.get("temporal_order") or 1.0) < 0.5:
            rows.append(
                {
                    "transition_id": f"relation_quality__{row.get('edge_id', len(rows))}",
                    "transition_family": "relation_quality",
                    "transition_type": "edge_downweighted",
                    "source": row.get("source_entity") or "",
                    "target": row.get("target_entity") or "",
                    "support": 1,
                    "confidence": float(row.get("edge_score") or 0.0),
                    "reason": "Low trajectory evidence, temporal order, schema fit, or quote grounding.",
                }
            )
    rejection_counts = Counter(str(row.get("rejection_reason") or "unknown") for row in relation_rejections)
    for reason, count in sorted(rejection_counts.items()):
        rows.append(
            {
                "transition_id": f"negative_relation__{reason}",
                "transition_family": "negative_relation",
                "transition_type": reason,
                "source": "",
                "target": "",
                "support": count,
                "confidence": round(min(0.95, 0.35 + 0.04 * count), 3),
                "reason": "Rejected relation pairs constrain schema and trajectory interpretation.",
            }
        )
    return rows


def _node_states(nodes: list[Any], edges: list[Any], taxonomy_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edge_counts: dict[str, int] = defaultdict(int)
    event_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for edge in edges:
        for node_id in getattr(edge, "taxonomy_nodes", []) or []:
            edge_counts[str(node_id)] += 1
    for event in taxonomy_events:
        for node_id in (event.get("source_node_ids") or []) + (event.get("target_node_ids") or []):
            event_counts[str(node_id)][str(event.get("event_type") or "unknown")] += 1
    rows = []
    for node in nodes:
        node_id = str(getattr(node, "node_id", "") or "")
        events = event_counts.get(node_id, Counter())
        support = len(getattr(node, "support_documents", []) or [])
        edge_support = edge_counts.get(node_id, 0)
        state = "stable"
        if events.get("birth") or events.get("split"):
            state = "emerging"
        if events.get("state_update") or edge_support >= 3:
            state = "active"
        if events.get("cross_link"):
            state = "bridging"
        rows.append(
            {
                "node_id": node_id,
                "dimension": getattr(node, "dimension", "") or "",
                "label": getattr(node, "canonical_label", "") or "",
                "state": state,
                "support_documents": support,
                "support_edges": edge_support,
                "events": dict(sorted(events.items())),
            }
        )
    return rows


def _slice(doc: Any) -> str:
    value = getattr(doc, "chronology_slice", "") or getattr(doc, "published_at", None) or "unknown"
    return str(value)


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)
