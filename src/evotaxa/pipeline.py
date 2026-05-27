from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evotaxa.config import EvoTaxaConfig, load_config
from evotaxa.graph import aggregate_edges, build_edges, entity_frequency_summary, extract_entities
from evotaxa.hooks import build_forecast_hooks, build_social_analysis_hooks
from evotaxa.io import write_json, write_jsonl
from evotaxa.loaders import attach_node_support, infer_assignments_from_text, load_assignments, load_documents, load_taxonomy_nodes
from evotaxa.search import extract_branch_points, search_evolution_chains
from evotaxa.taxonomy import build_taxonomy_events, enrich_taxonomy_nodes, judge_taxonomy_quality


def run_lite(config_or_path: EvoTaxaConfig | str | Path) -> dict[str, Any]:
    config = load_config(config_or_path) if not isinstance(config_or_path, EvoTaxaConfig) else config_or_path
    output_root = Path(config.output.root)
    output_root.mkdir(parents=True, exist_ok=True)

    docs, corpus_manifest = load_documents(config)
    current_nodes, taxonomy_manifest = load_taxonomy_nodes(config)
    previous_nodes, previous_taxonomy_manifest = load_taxonomy_nodes(config, previous=True)
    assignments, assignment_manifest = load_assignments(config)
    if not assignments:
        assignments = infer_assignments_from_text(docs, current_nodes)
        assignment_manifest["inferred_from_text"] = True
        assignment_manifest["loaded_assignments"] = len(assignments)
    nodes = attach_node_support(docs, current_nodes, assignments)

    enriched_nodes = enrich_taxonomy_nodes(docs, nodes)
    taxonomy_events = build_taxonomy_events(previous_nodes, nodes)
    node_quality = judge_taxonomy_quality(docs, nodes)

    entities, mentions = extract_entities(docs, assignments, config.graph)
    edges = build_edges(docs, entities, mentions, config.graph)
    aggregated_edges = aggregate_edges(edges)
    chains = search_evolution_chains(edges, strong_edge_types=config.graph.strong_edge_types)
    branch_points = extract_branch_points(edges, strong_edge_types=config.graph.strong_edge_types)
    forecast_hooks = build_forecast_hooks(edges, chains, branch_points, strong_edge_types=config.graph.strong_edge_types)
    social_hooks = build_social_analysis_hooks(forecast_hooks)

    write_jsonl(output_root / "corpus" / "documents.normalized.jsonl", (doc.to_record() for doc in docs))
    write_json(output_root / "corpus" / "manifest.json", corpus_manifest)
    write_json(output_root / "taxonomy" / "taxonomy_nodes.enriched.json", enriched_nodes)
    write_jsonl(output_root / "taxonomy" / "taxonomy_events.jsonl", taxonomy_events)
    write_jsonl(output_root / "taxonomy" / "node_quality_scores.jsonl", (row.to_record() for row in node_quality))
    write_json(output_root / "taxonomy" / "taxonomy_judge_report.json", _taxonomy_report(node_quality))
    write_jsonl(output_root / "taxonomy" / "document_assignments.normalized.jsonl", _assignment_rows(assignments))

    write_jsonl(output_root / "graph" / "method_registry.jsonl", (entity.to_record() for entity in entities))
    write_jsonl(output_root / "graph" / "paper_method_mentions.jsonl", (mention.to_record() for mention in mentions))
    write_jsonl(output_root / "graph" / "method_edges.paper_level.jsonl", (edge.to_record() for edge in edges))
    write_jsonl(output_root / "graph" / "method_edges.aggregated.jsonl", aggregated_edges)
    write_jsonl(output_root / "graph" / "method_evidence_records.jsonl", _evidence_rows(edges))
    write_json(output_root / "graph" / "entity_summary.json", entity_frequency_summary(entities))

    write_jsonl(output_root / "search" / "evolution_chains.jsonl", (chain.to_record() for chain in chains))
    write_jsonl(output_root / "search" / "branch_points.jsonl", branch_points)
    write_jsonl(output_root / "hooks" / "forecast_hooks.jsonl", forecast_hooks)
    write_jsonl(output_root / "hooks" / "social_analysis_hooks.jsonl", social_hooks)
    write_jsonl(output_root / "audit" / "unverified_edges.jsonl", (edge.to_record() for edge in edges if not edge.substring_verified))
    write_jsonl(output_root / "audit" / "low_confidence_nodes.jsonl", _low_confidence_nodes(node_quality))

    manifest = {
        "project": {
            "name": config.project.name,
            "domain_id": config.project.domain_id,
            "run_id": config.project.run_id,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_path": str(config.path),
        "output_root": str(output_root),
        "inputs": {
            "corpus": corpus_manifest,
            "taxonomy": taxonomy_manifest,
            "previous_taxonomy": previous_taxonomy_manifest,
            "assignments": assignment_manifest,
        },
        "counts": {
            "documents": len(docs),
            "taxonomy_nodes": len(nodes),
            "taxonomy_events": len(taxonomy_events),
            "entities": len(entities),
            "mentions": len(mentions),
            "paper_level_edges": len(edges),
            "aggregated_edges": len(aggregated_edges),
            "evolution_chains": len(chains),
            "branch_points": len(branch_points),
            "forecast_hooks": len(forecast_hooks),
            "social_analysis_hooks": len(social_hooks),
        },
        "artifact_layout": {
            "taxonomy_nodes": "taxonomy/taxonomy_nodes.enriched.json",
            "taxonomy_events": "taxonomy/taxonomy_events.jsonl",
            "node_quality_scores": "taxonomy/node_quality_scores.jsonl",
            "method_registry": "graph/method_registry.jsonl",
            "method_edges": "graph/method_edges.paper_level.jsonl",
            "evolution_chains": "search/evolution_chains.jsonl",
            "forecast_hooks": "hooks/forecast_hooks.jsonl",
            "audit": "audit/",
        },
    }
    write_json(output_root / "manifest.json", manifest)
    return manifest


def _assignment_rows(assignments: dict[str, list[str]]) -> list[dict[str, Any]]:
    return [{"doc_id": doc_id, "taxonomy_nodes": node_ids} for doc_id, node_ids in sorted(assignments.items())]


def _evidence_rows(edges: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "edge_id": edge.edge_id,
            "source_entity": edge.source_entity,
            "target_entity": edge.target_entity,
            "edge_type": edge.edge_type,
            "source_document": edge.source_document,
            "target_document": edge.target_document,
            "evidence": edge.evidence,
            "confidence": edge.confidence,
            "substring_verified": edge.substring_verified,
        }
        for edge in edges
    ]


def _taxonomy_report(rows: list[Any]) -> dict[str, Any]:
    metric_names = [
        "dimension_alignment",
        "granularity",
        "sibling_coherence",
        "uniqueness",
        "paper_relevance",
        "coverage",
        "temporal_stability",
        "boundary_clarity",
    ]
    summary: dict[str, Any] = {"node_count": len(rows), "metrics": {}, "notes": dict(Counter(row.judge_notes for row in rows if row.judge_notes))}
    for metric in metric_names:
        values = [float(getattr(row, metric)) for row in rows]
        summary["metrics"][metric] = round(sum(values) / len(values), 3) if values else 0.0
    return summary


def _low_confidence_nodes(rows: list[Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        score = sum(
            [
                row.dimension_alignment,
                row.granularity,
                row.sibling_coherence,
                row.uniqueness,
                row.paper_relevance,
                row.coverage,
                row.temporal_stability,
                row.boundary_clarity,
            ]
        ) / 8.0
        if score < 0.55:
            record = row.to_record()
            record["mean_quality"] = round(score, 3)
            output.append(record)
    return output

