from __future__ import annotations

from collections import defaultdict
from typing import Any

from evotaxa.models import EvolutionChain, EvolutionEdge


def search_evolution_chains(
    edges: list[EvolutionEdge],
    *,
    strong_edge_types: list[str],
    max_depth: int = 4,
    beam_size: int = 5,
) -> list[EvolutionChain]:
    strong = [edge for edge in edges if edge.edge_type in set(strong_edge_types) and edge.substring_verified]
    outgoing: dict[str, list[EvolutionEdge]] = defaultdict(list)
    for edge in strong:
        outgoing[edge.source_entity].append(edge)
    for entity_id in outgoing:
        outgoing[entity_id].sort(key=lambda edge: (-edge.confidence, edge.target_entity))

    chains: list[EvolutionChain] = []
    for start in sorted(outgoing):
        beam = [([start], [], 0.0)]
        for _ in range(max_depth):
            next_beam: list[tuple[list[str], list[str], float]] = []
            for entity_path, edge_path, score in beam:
                current = entity_path[-1]
                for edge in outgoing.get(current, [])[:beam_size]:
                    if edge.target_entity in entity_path:
                        continue
                    next_beam.append(
                        (
                            [*entity_path, edge.target_entity],
                            [*edge_path, edge.edge_id],
                            score + edge.confidence,
                        )
                    )
            if not next_beam:
                break
            next_beam.sort(key=lambda item: (-item[2], item[0]))
            beam = next_beam[:beam_size]
            for entity_path, edge_path, score in beam:
                if len(edge_path) >= 1:
                    chain_id = f"chain__{len(chains) + 1:06d}"
                    chain_edges = [edge for edge in strong if edge.edge_id in set(edge_path)]
                    chains.append(
                        EvolutionChain(
                            chain_id=chain_id,
                            entity_path=entity_path,
                            edge_path=edge_path,
                            taxonomy_nodes=sorted({node_id for edge in chain_edges for node_id in edge.taxonomy_nodes}),
                            score=round(score / max(1, len(edge_path)), 3),
                        )
                    )
    unique: dict[tuple[str, ...], EvolutionChain] = {}
    for chain in chains:
        key = tuple(chain.entity_path)
        if key not in unique or chain.score > unique[key].score:
            unique[key] = chain
    return sorted(unique.values(), key=lambda chain: (-chain.score, -len(chain.edge_path), chain.chain_id))


def extract_branch_points(edges: list[EvolutionEdge], *, strong_edge_types: list[str]) -> list[dict[str, Any]]:
    outgoing: dict[str, list[EvolutionEdge]] = defaultdict(list)
    for edge in edges:
        if edge.edge_type in set(strong_edge_types) and edge.substring_verified:
            outgoing[edge.source_entity].append(edge)
    rows: list[dict[str, Any]] = []
    for entity_id, entity_edges in sorted(outgoing.items()):
        targets = sorted({edge.target_entity for edge in entity_edges})
        if len(targets) < 2:
            continue
        rows.append(
            {
                "entity_id": entity_id,
                "successor_entities": targets,
                "support_edge_ids": [edge.edge_id for edge in entity_edges],
                "taxonomy_nodes": sorted({node_id for edge in entity_edges for node_id in edge.taxonomy_nodes}),
                "mean_confidence": round(sum(edge.confidence for edge in entity_edges) / len(entity_edges), 3),
            }
        )
    return rows

