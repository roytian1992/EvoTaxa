from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from evotaxa.models import EvolutionChain, EvolutionEdge


def infer_evolution_trajectories(
    edges: list[EvolutionEdge],
    *,
    strong_edge_types: list[str],
    max_depth: int = 4,
    beam_size: int = 6,
) -> tuple[list[EvolutionChain], list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = _eligible_edges(edges, strong_edge_types)
    outgoing: dict[str, list[EvolutionEdge]] = defaultdict(list)
    for edge in candidates:
        outgoing[edge.source_entity].append(edge)
    for source in outgoing:
        outgoing[source].sort(key=lambda edge: (-_edge_prior(edge), edge.target_entity))

    chains: list[EvolutionChain] = []
    rows: list[dict[str, Any]] = []
    for start in sorted(outgoing):
        beam = [([start], [], 1.0, [])]
        for _ in range(max_depth):
            next_beam: list[tuple[list[str], list[str], float, list[float]]] = []
            for entity_path, edge_path, _, component_scores in beam:
                current = entity_path[-1]
                for edge in outgoing.get(current, [])[:beam_size]:
                    if edge.target_entity in entity_path:
                        continue
                    step_score = _trajectory_step_score(edge, len(edge_path))
                    next_beam.append(
                        (
                            [*entity_path, edge.target_entity],
                            [*edge_path, edge.edge_id],
                            _mean([*component_scores, step_score]),
                            [*component_scores, step_score],
                        )
                    )
            if not next_beam:
                break
            next_beam.sort(key=lambda item: (-item[2], item[0]))
            beam = next_beam[:beam_size]
            for entity_path, edge_path, score, component_scores in beam:
                if not edge_path:
                    continue
                chain_edges = [edge for edge in candidates if edge.edge_id in set(edge_path)]
                chain_id = f"trajectory__{len(rows) + 1:06d}"
                taxonomy_nodes = sorted({node_id for edge in chain_edges for node_id in edge.taxonomy_nodes})
                rows.append(
                    {
                        "trajectory_id": chain_id,
                        "entity_path": entity_path,
                        "edge_path": edge_path,
                        "taxonomy_nodes": taxonomy_nodes,
                        "trajectory_score": round(score, 3),
                        "path_length": len(edge_path),
                        "mean_edge_confidence": _mean([float(edge.confidence or 0.0) for edge in chain_edges]),
                        "temporal_coherence": _mean([_temporal_component(edge) for edge in chain_edges]),
                        "quote_grounding": _mean([1.0 if edge.substring_verified else 0.0 for edge in chain_edges]),
                        "schema_coherence": _mean([_schema_component(edge) for edge in chain_edges]),
                        "branching_factor": _branching_factor(entity_path, outgoing),
                    }
                )
    unique = _unique_trajectory_rows(rows)
    chains = [
        EvolutionChain(
            chain_id=row["trajectory_id"],
            entity_path=row["entity_path"],
            edge_path=row["edge_path"],
            taxonomy_nodes=row["taxonomy_nodes"],
            score=row["trajectory_score"],
        )
        for row in unique
    ]
    evaluation = evaluate_trajectories(unique)
    return chains, unique, evaluation


def evaluate_trajectories(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return [
            {
                "metric": "trajectory_count",
                "value": 0,
                "interpretation": "No eligible trajectories were inferred.",
            }
        ]
    lengths = [int(row.get("path_length") or 0) for row in rows]
    scores = [float(row.get("trajectory_score") or 0.0) for row in rows]
    temporal = [float(row.get("temporal_coherence") or 0.0) for row in rows]
    quote = [float(row.get("quote_grounding") or 0.0) for row in rows]
    taxonomy_coverage = Counter(node for row in rows for node in row.get("taxonomy_nodes") or [])
    return [
        {"metric": "trajectory_count", "value": len(rows), "interpretation": "Number of unique inferred evolution trajectories."},
        {"metric": "mean_trajectory_score", "value": _mean(scores), "interpretation": "Average confidence of inferred trajectories."},
        {"metric": "mean_path_length", "value": _mean([float(value) for value in lengths]), "interpretation": "Average number of edges per trajectory."},
        {"metric": "max_path_length", "value": max(lengths), "interpretation": "Longest inferred trajectory length."},
        {"metric": "temporal_coherence", "value": _mean(temporal), "interpretation": "Average temporal consistency across trajectory edges."},
        {"metric": "quote_grounding", "value": _mean(quote), "interpretation": "Average quote-grounded edge rate in trajectories."},
        {
            "metric": "taxonomy_coverage",
            "value": len(taxonomy_coverage),
            "interpretation": "Number of taxonomy nodes covered by at least one trajectory.",
            "top_nodes": dict(taxonomy_coverage.most_common(10)),
        },
    ]


def _eligible_edges(edges: list[EvolutionEdge], strong_edge_types: list[str]) -> list[EvolutionEdge]:
    strong = set(strong_edge_types)
    return [
        edge
        for edge in edges
        if edge.edge_type in strong
        and edge.substring_verified
        and float(edge.confidence or 0.0) > 0.0
        and _temporal_component(edge) > 0.0
    ]


def _trajectory_step_score(edge: EvolutionEdge, depth: int) -> float:
    confidence = float(edge.confidence or 0.0)
    temporal = _temporal_component(edge)
    quote = 1.0 if edge.substring_verified else 0.0
    schema = _schema_component(edge)
    locality = 1.0 if edge.taxonomy_nodes else 0.6
    depth_penalty = max(0.75, 1.0 - 0.04 * depth)
    return round((0.34 * confidence + 0.24 * temporal + 0.18 * quote + 0.14 * schema + 0.10 * locality) * depth_penalty, 3)


def _edge_prior(edge: EvolutionEdge) -> float:
    return _trajectory_step_score(edge, 0)


def _temporal_component(edge: EvolutionEdge) -> float:
    if edge.time_delta_days is None:
        return 0.6
    if edge.time_delta_days < 0:
        return 0.0
    if edge.time_delta_days == 0:
        return 0.8
    return 1.0


def _schema_component(edge: EvolutionEdge) -> float:
    score = ((edge.evidence or {}).get("edge_score") or {}).get("schema_fit")
    try:
        return max(0.0, min(1.0, float(score)))
    except (TypeError, ValueError):
        return 0.75


def _branching_factor(entity_path: list[str], outgoing: dict[str, list[EvolutionEdge]]) -> int:
    return max([len(outgoing.get(entity_id, [])) for entity_id in entity_path] or [0])


def _unique_trajectory_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(row.get("entity_path") or [])
        existing = unique.get(key)
        if existing is None or float(row.get("trajectory_score") or 0.0) > float(existing.get("trajectory_score") or 0.0):
            unique[key] = row
    sorted_rows = sorted(unique.values(), key=lambda row: (-float(row.get("trajectory_score") or 0.0), -int(row.get("path_length") or 0), row.get("trajectory_id", "")))
    for index, row in enumerate(sorted_rows, start=1):
        row["trajectory_id"] = f"trajectory__{index:06d}"
    return sorted_rows


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)
