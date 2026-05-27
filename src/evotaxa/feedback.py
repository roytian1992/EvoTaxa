from __future__ import annotations

from collections import defaultdict
from typing import Any

from evotaxa.models import EvolutionEdge, EvolutionEntity, TaxonomyNode


def build_taxonomy_graph_feedback(
    nodes: list[TaxonomyNode],
    entities: list[EvolutionEntity],
    edges: list[EvolutionEdge],
    expansion_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    entity_by_node: dict[str, list[EvolutionEntity]] = defaultdict(list)
    edge_by_node: dict[str, list[EvolutionEdge]] = defaultdict(list)
    strong_by_node: dict[str, list[EvolutionEdge]] = defaultdict(list)
    for entity in entities:
        for node_id in entity.taxonomy_nodes:
            entity_by_node[node_id].append(entity)
    for edge in edges:
        for node_id in edge.taxonomy_nodes:
            edge_by_node[node_id].append(edge)
            if edge.edge_type in {"extends", "improves", "replaces", "adapts"} and edge.substring_verified:
                strong_by_node[node_id].append(edge)

    expansion_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in expansion_candidates:
        expansion_by_node[str(candidate.get("trigger_node_id") or "")].append(candidate)

    rows: list[dict[str, Any]] = []
    for node in nodes:
        local_entities = entity_by_node.get(node.node_id, [])
        local_edges = edge_by_node.get(node.node_id, [])
        strong_edges = strong_by_node.get(node.node_id, [])
        successors = {edge.target_entity for edge in strong_edges}
        sources = {edge.source_entity for edge in strong_edges}
        disconnected_lineage_hint = len(successors) >= 3 and len(sources) >= 2
        shared_entity_pressure = len(local_entities) >= 4
        expansion_pressure = expansion_by_node.get(node.node_id, [])
        recommendations: list[str] = []
        if disconnected_lineage_hint:
            recommendations.append("split_review")
        if shared_entity_pressure and len(local_edges) >= 4:
            recommendations.append("cross_link_review")
        if expansion_pressure:
            recommendations.append("apply_or_audit_expansion_candidates")
        if any(_edge_has_bottleneck(edge) for edge in local_edges) and strong_edges:
            recommendations.append("mark_fragmenting_or_growing")
        if not recommendations:
            recommendations.append("monitor")

        rows.append(
            {
                "node_id": node.node_id,
                "dimension": node.dimension,
                "entity_count": len(local_entities),
                "edge_count": len(local_edges),
                "verified_strong_edge_count": len(strong_edges),
                "expansion_candidate_count": len(expansion_pressure),
                "signals": {
                    "disconnected_lineage_hint": disconnected_lineage_hint,
                    "shared_entity_pressure": shared_entity_pressure,
                    "bottleneck_with_successor": any(_edge_has_bottleneck(edge) for edge in local_edges) and bool(strong_edges),
                },
                "recommendations": recommendations,
                "support_entities": [entity.entity_id for entity in local_entities[:20]],
                "support_edges": [edge.edge_id for edge in local_edges[:20]],
                "support_expansion_candidates": [candidate["candidate_id"] for candidate in expansion_pressure[:20]],
            }
        )
    return rows


def synthesize_feedback_events(feedback_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in feedback_rows:
        if "split_review" in row["recommendations"]:
            events.append(
                {
                    "event_id": f"feedback_split__{row['node_id']}",
                    "event_type": "fragmentation",
                    "time_slice": "",
                    "source_node_ids": [row["node_id"]],
                    "target_node_ids": [],
                    "support_documents": [],
                    "reason": "Graph feedback found multiple strong successor lineages inside the node.",
                    "confidence": 0.7,
                    "support_edges": row["support_edges"],
                }
            )
        if "cross_link_review" in row["recommendations"]:
            events.append(
                {
                    "event_id": f"feedback_cross_link__{row['node_id']}",
                    "event_type": "cross_link",
                    "time_slice": "",
                    "source_node_ids": [row["node_id"]],
                    "target_node_ids": [],
                    "support_documents": [],
                    "reason": "Graph feedback found shared entities and edges suggesting cross-node coupling.",
                    "confidence": 0.6,
                    "support_edges": row["support_edges"],
                }
            )
    return events


def _edge_has_bottleneck(edge: EvolutionEdge) -> bool:
    return bool(((edge.evidence or {}).get("bottleneck") or {}).get("description"))

