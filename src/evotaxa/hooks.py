from __future__ import annotations

from collections import defaultdict
from typing import Any

from evotaxa.models import EvolutionChain, EvolutionEdge


def build_forecast_hooks(
    edges: list[EvolutionEdge],
    chains: list[EvolutionChain],
    branch_points: list[dict[str, Any]],
    *,
    strong_edge_types: list[str],
) -> list[dict[str, Any]]:
    hooks: list[dict[str, Any]] = []
    edge_by_id = {edge.edge_id: edge for edge in edges}

    for chain in chains[:100]:
        chain_edges = [edge_by_id[edge_id] for edge_id in chain.edge_path if edge_id in edge_by_id]
        if not chain_edges:
            continue
        root_bottleneck = _first_bottleneck(chain_edges)
        hooks.append(
            {
                "hook_id": f"successor__{chain.chain_id}",
                "hook_type": "successor_mechanism",
                "taxonomy_node": chain.taxonomy_nodes[0] if chain.taxonomy_nodes else "",
                "evolution_chain": chain.entity_path,
                "root_bottleneck": root_bottleneck,
                "candidate_successor": chain.entity_path[-1],
                "support_edges": chain.edge_path,
                "support_documents": sorted({edge.source_document for edge in chain_edges} | {edge.target_document for edge in chain_edges}),
                "risk_or_tradeoff": _first_tradeoff(chain_edges),
                "cutoff_valid": True,
                "confidence": chain.score,
            }
        )

    for index, branch in enumerate(branch_points[:100], start=1):
        hooks.append(
            {
                "hook_id": f"branch__{index:06d}",
                "hook_type": "fragmenting_node",
                "taxonomy_node": (branch.get("taxonomy_nodes") or [""])[0],
                "evolution_chain": [branch["entity_id"], *branch["successor_entities"]],
                "root_bottleneck": "",
                "candidate_successor": ", ".join(branch["successor_entities"]),
                "support_edges": branch["support_edge_ids"],
                "support_documents": [],
                "risk_or_tradeoff": "Multiple successor mechanisms are emerging from the same source entity.",
                "cutoff_valid": True,
                "confidence": branch["mean_confidence"],
            }
        )

    hooks.extend(_unresolved_bottleneck_hooks(edges, strong_edge_types))
    return sorted(hooks, key=lambda row: (-float(row.get("confidence") or 0.0), row["hook_id"]))


def build_social_analysis_hooks(forecast_hooks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for hook in forecast_hooks:
        if hook["hook_type"] not in {"successor_mechanism", "fragmenting_node", "unresolved_bottleneck"}:
            continue
        rows.append(
            {
                "analysis_id": hook["hook_id"].replace("successor__", "social__").replace("branch__", "social_branch__"),
                "analysis_type": hook["hook_type"],
                "taxonomy_node": hook["taxonomy_node"],
                "mechanism_path": hook["evolution_chain"],
                "interpretation": _social_interpretation(hook),
                "support_edges": hook["support_edges"],
                "confidence": hook["confidence"],
            }
        )
    return rows


def _first_bottleneck(edges: list[EvolutionEdge]) -> str:
    for edge in edges:
        value = ((edge.evidence or {}).get("bottleneck") or {}).get("description") or ""
        if value:
            return value
    return ""


def _first_tradeoff(edges: list[EvolutionEdge]) -> str:
    for edge in edges:
        value = ((edge.evidence or {}).get("tradeoff") or {}).get("description") or ""
        if value:
            return value
    return ""


def _unresolved_bottleneck_hooks(edges: list[EvolutionEdge], strong_edge_types: list[str]) -> list[dict[str, Any]]:
    by_source: dict[str, list[EvolutionEdge]] = defaultdict(list)
    for edge in edges:
        bottleneck = ((edge.evidence or {}).get("bottleneck") or {}).get("description") or ""
        if bottleneck and edge.edge_type not in set(strong_edge_types):
            by_source[edge.source_entity].append(edge)
    rows = []
    for index, (entity_id, support_edges) in enumerate(sorted(by_source.items()), start=1):
        rows.append(
            {
                "hook_id": f"bottleneck__{index:06d}",
                "hook_type": "unresolved_bottleneck",
                "taxonomy_node": (support_edges[0].taxonomy_nodes or [""])[0],
                "evolution_chain": [entity_id],
                "root_bottleneck": ((support_edges[0].evidence or {}).get("bottleneck") or {}).get("description") or "",
                "candidate_successor": "",
                "support_edges": [edge.edge_id for edge in support_edges],
                "support_documents": sorted({edge.source_document for edge in support_edges} | {edge.target_document for edge in support_edges}),
                "risk_or_tradeoff": "No verified strong successor edge was found for this bottleneck.",
                "cutoff_valid": True,
                "confidence": round(sum(edge.confidence for edge in support_edges) / len(support_edges), 3),
            }
        )
    return rows


def _social_interpretation(hook: dict[str, Any]) -> str:
    if hook["hook_type"] == "successor_mechanism":
        return "A mechanism or intervention appears to evolve into a successor form under the configured evidence cues."
    if hook["hook_type"] == "fragmenting_node":
        return "A taxonomy region may be splitting into multiple intervention, mechanism, or framing branches."
    return "A recurring bottleneck is visible, but no trusted successor mechanism has been confirmed."

