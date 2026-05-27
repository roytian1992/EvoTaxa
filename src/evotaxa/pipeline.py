from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evotaxa.config import EvoTaxaConfig, load_config
from evotaxa.feedback import build_taxonomy_graph_feedback, synthesize_feedback_events
from evotaxa.graph import aggregate_edges, build_edges, entity_frequency_summary, extract_entities
from evotaxa.hooks import build_forecast_hooks, build_social_analysis_hooks
from evotaxa.induction import build_induction_assignments, induce_initial_taxonomy, propose_expansion_candidates, score_expansion_triggers
from evotaxa.io import write_json, write_jsonl
from evotaxa.loaders import attach_node_support, infer_assignments_from_text, load_assignments, load_documents, load_taxonomy_nodes
from evotaxa.llm import build_llm_client, judge_edge_evidence, judge_taxonomy_candidate
from evotaxa.search import extract_branch_points, search_evolution_chains
from evotaxa.scoring import build_hook_score_report, score_forecast_hooks
from evotaxa.taxonomy import build_taxonomy_events, enrich_taxonomy_nodes, judge_taxonomy_quality


def run_lite(config_or_path: EvoTaxaConfig | str | Path) -> dict[str, Any]:
    return _run(config_or_path, full=False)


def run_full(config_or_path: EvoTaxaConfig | str | Path) -> dict[str, Any]:
    return _run(config_or_path, full=True)


def _run(config_or_path: EvoTaxaConfig | str | Path, *, full: bool) -> dict[str, Any]:
    config = load_config(config_or_path) if not isinstance(config_or_path, EvoTaxaConfig) else config_or_path
    output_root = Path(config.output.root)
    output_root.mkdir(parents=True, exist_ok=True)

    docs, corpus_manifest = load_documents(config)
    current_nodes, taxonomy_manifest = load_taxonomy_nodes(config)
    previous_nodes, previous_taxonomy_manifest = load_taxonomy_nodes(config, previous=True)
    assignments, assignment_manifest = load_assignments(config)
    induction_audit: list[dict[str, Any]] = []
    if not current_nodes and not (full or config.taxonomy.induction_enabled):
        raise ValueError("taxonomy.nodes_path is required unless run-full or taxonomy.induction_enabled is set.")
    if (full or config.taxonomy.induction_enabled) and not current_nodes:
        induced_nodes, induced_assignments, induction_audit = induce_initial_taxonomy(docs, config.taxonomy.dimensions, config.taxonomy)
        current_nodes = induced_nodes
        assignments = _merge_assignments(assignments, induced_assignments)
        taxonomy_manifest["induced_from_corpus"] = True
        taxonomy_manifest["loaded_nodes"] = len(current_nodes)
        assignment_manifest["induced_assignments"] = len(induced_assignments)
    if not assignments:
        assignments = infer_assignments_from_text(docs, current_nodes)
        assignment_manifest["inferred_from_text"] = True
        assignment_manifest["loaded_assignments"] = len(assignments)
    if full:
        assignments = build_induction_assignments(docs, current_nodes, assignments)
    nodes = attach_node_support(docs, current_nodes, assignments)

    enriched_nodes = enrich_taxonomy_nodes(docs, nodes)
    taxonomy_events = build_taxonomy_events(previous_nodes, nodes)
    node_quality = judge_taxonomy_quality(docs, nodes)

    entities, mentions = extract_entities(docs, assignments, config.graph)
    expansion_signals = score_expansion_triggers(docs, nodes, assignments, entities) if full or config.taxonomy.expansion_enabled else []
    expansion_candidates = propose_expansion_candidates(docs, nodes, expansion_signals, config.taxonomy) if full or config.taxonomy.expansion_enabled else []

    llm_client = build_llm_client(config.llm)
    llm_records: list[Any] = []
    if full and expansion_candidates:
        doc_map = {doc.doc_id: doc for doc in docs}
        for candidate in expansion_candidates[:20]:
            context = "\n\n".join(doc_map[doc_id].full_text for doc_id in candidate.get("support_documents", []) if doc_id in doc_map)
            llm_records.append(judge_taxonomy_candidate(llm_client, candidate=candidate, context=context))

    edges = build_edges(docs, entities, mentions, config.graph)
    if full and edges:
        doc_map = {doc.doc_id: doc for doc in docs}
        judged_edges = []
        for edge in edges[:100]:
            record = judge_edge_evidence(
                llm_client,
                edge=edge.to_record(),
                source_text=doc_map.get(edge.source_document).full_text if doc_map.get(edge.source_document) else "",
                target_text=doc_map.get(edge.target_document).full_text if doc_map.get(edge.target_document) else "",
            )
            llm_records.append(record)
            judged_edges.append(_apply_edge_judgement(edge, record.output))
        judged_ids = {edge.edge_id for edge in judged_edges}
        edges = [*judged_edges, *[edge for edge in edges if edge.edge_id not in judged_ids]]
    aggregated_edges = aggregate_edges(edges)
    chains = search_evolution_chains(edges, strong_edge_types=config.graph.strong_edge_types)
    branch_points = extract_branch_points(edges, strong_edge_types=config.graph.strong_edge_types)
    forecast_hooks = build_forecast_hooks(edges, chains, branch_points, strong_edge_types=config.graph.strong_edge_types)
    edge_index = {edge.edge_id: edge.to_record() for edge in edges}
    forecast_hooks = score_forecast_hooks(forecast_hooks, edge_index) if full else forecast_hooks
    social_hooks = build_social_analysis_hooks(forecast_hooks)
    feedback_rows = build_taxonomy_graph_feedback(nodes, entities, edges, expansion_candidates) if full else []
    feedback_events = synthesize_feedback_events(feedback_rows) if full else []
    taxonomy_events = [*taxonomy_events, *feedback_events]

    write_jsonl(output_root / "corpus" / "documents.normalized.jsonl", (doc.to_record() for doc in docs))
    write_json(output_root / "corpus" / "manifest.json", corpus_manifest)
    write_json(output_root / "taxonomy" / "taxonomy_nodes.enriched.json", enriched_nodes)
    write_jsonl(output_root / "taxonomy" / "taxonomy_events.jsonl", taxonomy_events)
    write_jsonl(output_root / "taxonomy" / "node_quality_scores.jsonl", (row.to_record() for row in node_quality))
    write_json(output_root / "taxonomy" / "taxonomy_judge_report.json", _taxonomy_report(node_quality))
    write_jsonl(output_root / "taxonomy" / "document_assignments.normalized.jsonl", _assignment_rows(assignments))
    write_jsonl(output_root / "taxonomy" / "taxonomy_induction_audit.jsonl", induction_audit)
    write_jsonl(output_root / "taxonomy" / "expansion_trigger_scores.jsonl", (row.to_record() for row in expansion_signals))
    write_jsonl(output_root / "taxonomy" / "expansion_candidates.jsonl", expansion_candidates)

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
    write_json(output_root / "hooks" / "hook_score_report.json", build_hook_score_report(forecast_hooks) if full else {"hook_count": len(forecast_hooks)})
    write_jsonl(output_root / "feedback" / "taxonomy_graph_feedback.jsonl", feedback_rows)
    write_jsonl(output_root / "audit" / "llm_judge_records.jsonl", (record.to_record() for record in llm_records))
    write_jsonl(output_root / "audit" / "unverified_edges.jsonl", (edge.to_record() for edge in edges if not edge.substring_verified))
    write_jsonl(output_root / "audit" / "low_confidence_nodes.jsonl", _low_confidence_nodes(node_quality))

    manifest = {
        "project": {
            "name": config.project.name,
            "domain_id": config.project.domain_id,
            "run_id": config.project.run_id,
        },
        "mode": "full" if full else "lite",
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
            "expansion_signals": len(expansion_signals),
            "expansion_candidates": len(expansion_candidates),
            "entities": len(entities),
            "mentions": len(mentions),
            "paper_level_edges": len(edges),
            "aggregated_edges": len(aggregated_edges),
            "evolution_chains": len(chains),
            "branch_points": len(branch_points),
            "forecast_hooks": len(forecast_hooks),
            "social_analysis_hooks": len(social_hooks),
            "feedback_rows": len(feedback_rows),
            "llm_judge_records": len(llm_records),
        },
        "artifact_layout": {
            "taxonomy_nodes": "taxonomy/taxonomy_nodes.enriched.json",
            "taxonomy_events": "taxonomy/taxonomy_events.jsonl",
            "node_quality_scores": "taxonomy/node_quality_scores.jsonl",
            "expansion_trigger_scores": "taxonomy/expansion_trigger_scores.jsonl",
            "expansion_candidates": "taxonomy/expansion_candidates.jsonl",
            "method_registry": "graph/method_registry.jsonl",
            "method_edges": "graph/method_edges.paper_level.jsonl",
            "evolution_chains": "search/evolution_chains.jsonl",
            "forecast_hooks": "hooks/forecast_hooks.jsonl",
            "taxonomy_graph_feedback": "feedback/taxonomy_graph_feedback.jsonl",
            "llm_judge_records": "audit/llm_judge_records.jsonl",
            "audit": "audit/",
        },
    }
    write_json(output_root / "manifest.json", manifest)
    return manifest


def _merge_assignments(left: dict[str, list[str]], right: dict[str, list[str]]) -> dict[str, list[str]]:
    merged: dict[str, set[str]] = {doc_id: set(node_ids) for doc_id, node_ids in left.items()}
    for doc_id, node_ids in right.items():
        merged.setdefault(doc_id, set()).update(node_ids)
    return {doc_id: sorted(node_ids) for doc_id, node_ids in sorted(merged.items())}


def _apply_edge_judgement(edge: Any, judgement: dict[str, Any]) -> Any:
    edge.edge_type = str(judgement.get("edge_type") or edge.edge_type)
    try:
        edge.confidence = round(float(judgement.get("confidence", edge.confidence)), 3)
    except (TypeError, ValueError):
        pass
    evidence = dict(edge.evidence or {})
    for key in ["bottleneck", "mechanism", "tradeoff"]:
        if isinstance(judgement.get(key), dict):
            evidence[key] = judgement[key]
    if judgement.get("rationale"):
        evidence["judge_rationale"] = str(judgement["rationale"])
    edge.evidence = evidence
    return edge


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
