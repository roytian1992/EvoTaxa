from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evotaxa.coevolution import apply_taxonomy_revisions, propose_taxonomy_revisions
from evotaxa.config import EvoTaxaConfig, load_config
from evotaxa.edge_evidence import stratify_edges_by_evidence
from evotaxa.entity_linking import canonicalize_entities, remap_edges_to_canonical_entities
from evotaxa.entity_quality import filter_entities_by_quality
from evotaxa.evaluation import build_quality_report
from evotaxa.feedback import build_taxonomy_graph_feedback, synthesize_feedback_events
from evotaxa.graph import aggregate_edges, build_edges, entity_frequency_summary, extract_entities, merge_llm_entity_mentions
from evotaxa.hooks import build_forecast_hooks, build_social_analysis_hooks
from evotaxa.induction import (
    apply_expansion_candidates,
    build_induction_assignments,
    induce_initial_taxonomy,
    propose_expansion_candidates,
    score_expansion_triggers,
)
from evotaxa.io import write_json, write_jsonl
from evotaxa.loaders import attach_node_support, infer_assignments_from_text, load_assignments, load_documents, load_taxonomy_nodes
from evotaxa.llm import build_llm_client, extract_document_entities, judge_edge_evidence, judge_taxonomy_candidate
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
    if full and config.llm.cache_path is None:
        config.llm.cache_path = output_root / "audit" / "llm_cache.jsonl"

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

    llm_client = build_llm_client(config.llm)
    llm_records: list[Any] = []
    entities, mentions, entity_link_rows, entity_quality_report, llm_entity_report, raw_entity_count = _extract_prepare_entities(
        docs,
        assignments,
        config,
        llm_client,
        full=full,
        llm_records=llm_records,
    )
    expansion_enabled = config.taxonomy.expansion_enabled
    expansion_signals = score_expansion_triggers(docs, nodes, assignments, entities) if expansion_enabled else []
    expansion_candidates = propose_expansion_candidates(docs, nodes, expansion_signals, config.taxonomy) if expansion_enabled else []

    taxonomy_judgements: dict[str, dict[str, Any]] = {}
    if full and expansion_candidates:
        doc_map = {doc.doc_id: doc for doc in docs}
        for candidate in expansion_candidates[:20]:
            context = "\n\n".join(doc_map[doc_id].full_text for doc_id in candidate.get("support_documents", []) if doc_id in doc_map)
            record = judge_taxonomy_candidate(llm_client, candidate=candidate, context=context)
            llm_records.append(record)
            taxonomy_judgements[str(candidate.get("candidate_id") or "")] = record.output

    expanded_nodes = nodes
    expanded_assignments = assignments
    expansion_application_report: list[dict[str, Any]] = []
    if full and expansion_candidates:
        expanded_nodes, expanded_assignments, expansion_application_report = apply_expansion_candidates(
            nodes,
            assignments,
            expansion_candidates,
            taxonomy_judgements,
            config.taxonomy,
        )
        if any(row.get("status") == "applied" for row in expansion_application_report):
            nodes = attach_node_support(docs, expanded_nodes, expanded_assignments)
            assignments = expanded_assignments
            enriched_nodes = enrich_taxonomy_nodes(docs, nodes)
            node_quality = judge_taxonomy_quality(docs, nodes)
            entities, mentions, entity_link_rows, entity_quality_report, llm_entity_report, raw_entity_count = _extract_prepare_entities(
                docs,
                assignments,
                config,
                llm_client,
                full=full,
                llm_records=llm_records,
            )
            taxonomy_events = [*taxonomy_events, *_expansion_application_events(expansion_application_report)]

    graph_layer = _build_graph_layer(
        docs,
        entities,
        mentions,
        entity_link_rows,
        config,
        llm_client,
        llm_records,
        full=full,
    )
    feedback_rows = build_taxonomy_graph_feedback(nodes, entities, graph_layer["downstream_edges"], expansion_candidates) if full else []
    revision_candidates: list[dict[str, Any]] = []
    revision_application_report: list[dict[str, Any]] = []
    coevolution_iteration_reports: list[dict[str, Any]] = []
    if full and config.taxonomy.coevolution_enabled:
        for iteration in range(max(0, config.taxonomy.max_coevolution_iterations)):
            revision_candidates = propose_taxonomy_revisions(
                nodes,
                entities,
                graph_layer["downstream_edges"],
                feedback_rows,
                config.taxonomy,
            )
            if not revision_candidates:
                coevolution_iteration_reports.append({"iteration": iteration + 1, "status": "no_revision_candidates"})
                break
            revised_nodes, revised_assignments, revision_application_report = apply_taxonomy_revisions(
                nodes,
                assignments,
                revision_candidates,
                config.taxonomy,
            )
            applied_revisions = [row for row in revision_application_report if row.get("status") == "applied"]
            coevolution_iteration_reports.append(
                {
                    "iteration": iteration + 1,
                    "status": "applied" if applied_revisions else "no_applied_revisions",
                    "revision_candidates": len(revision_candidates),
                    "applied_revisions": len(applied_revisions),
                }
            )
            if not applied_revisions:
                break
            nodes = attach_node_support(docs, revised_nodes, revised_assignments)
            assignments = revised_assignments
            enriched_nodes = enrich_taxonomy_nodes(docs, nodes)
            node_quality = judge_taxonomy_quality(docs, nodes)
            entities, mentions, entity_link_rows, entity_quality_report, llm_entity_report, raw_entity_count = _extract_prepare_entities(
                docs,
                assignments,
                config,
                llm_client,
                full=full,
                llm_records=llm_records,
            )
            graph_layer = _build_graph_layer(
                docs,
                entities,
                mentions,
                entity_link_rows,
                config,
                llm_client,
                llm_records,
                full=full,
            )
            feedback_rows = build_taxonomy_graph_feedback(nodes, entities, graph_layer["downstream_edges"], expansion_candidates)
            taxonomy_events = [*taxonomy_events, *_revision_application_events(revision_application_report)]

    chains = graph_layer["chains"]
    forecast_hooks = graph_layer["forecast_hooks"]
    social_hooks = build_social_analysis_hooks(forecast_hooks)
    feedback_events = synthesize_feedback_events(feedback_rows) if full else []
    taxonomy_events = [*taxonomy_events, *feedback_events]
    hook_score_report = build_hook_score_report(forecast_hooks) if full else {"hook_count": len(forecast_hooks)}
    quality_report = build_quality_report(
        node_quality=node_quality,
        entity_quality_report=entity_quality_report,
        edge_evidence_audit=graph_layer["edge_evidence_audit"],
        hook_score_report=hook_score_report,
        feedback_rows=feedback_rows,
        expansion_application_report=expansion_application_report,
        revision_application_report=revision_application_report,
        llm_records=llm_records,
    )

    write_jsonl(output_root / "corpus" / "documents.normalized.jsonl", (doc.to_record() for doc in docs))
    write_json(output_root / "corpus" / "manifest.json", corpus_manifest)
    write_json(output_root / "taxonomy" / "taxonomy_nodes.enriched.json", enriched_nodes)
    write_json(output_root / "taxonomy" / "taxonomy_nodes.expanded.json", [node.to_record() for node in nodes])
    write_jsonl(output_root / "taxonomy" / "taxonomy_events.jsonl", taxonomy_events)
    write_jsonl(output_root / "taxonomy" / "node_quality_scores.jsonl", (row.to_record() for row in node_quality))
    write_json(output_root / "taxonomy" / "taxonomy_judge_report.json", _taxonomy_report(node_quality))
    write_jsonl(output_root / "taxonomy" / "document_assignments.normalized.jsonl", _assignment_rows(assignments))
    write_jsonl(output_root / "taxonomy" / "document_assignments.expanded.jsonl", _assignment_rows(assignments))
    write_jsonl(output_root / "taxonomy" / "taxonomy_induction_audit.jsonl", induction_audit)
    write_jsonl(output_root / "taxonomy" / "expansion_trigger_scores.jsonl", (row.to_record() for row in expansion_signals))
    write_jsonl(output_root / "taxonomy" / "expansion_candidates.jsonl", expansion_candidates)
    write_jsonl(output_root / "taxonomy" / "expansion_application_report.jsonl", expansion_application_report)
    write_jsonl(output_root / "taxonomy" / "revision_candidates.jsonl", revision_candidates)
    write_jsonl(output_root / "taxonomy" / "revision_application_report.jsonl", revision_application_report)
    write_jsonl(output_root / "taxonomy" / "coevolution_iterations.jsonl", coevolution_iteration_reports)

    write_jsonl(output_root / "graph" / "method_registry.jsonl", (entity.to_record() for entity in entities))
    write_jsonl(output_root / "graph" / "method_aliases.jsonl", entity_link_rows)
    write_jsonl(output_root / "graph" / "entity_linking_report.jsonl", entity_link_rows)
    write_jsonl(output_root / "graph" / "entity_quality_report.jsonl", entity_quality_report)
    write_jsonl(output_root / "graph" / "llm_entity_mentions.jsonl", llm_entity_report)
    write_jsonl(output_root / "graph" / "paper_method_mentions.jsonl", (mention.to_record() for mention in mentions))
    write_jsonl(output_root / "graph" / "method_edges.paper_level.jsonl", (edge.to_record() for edge in graph_layer["edges"]))
    write_jsonl(output_root / "graph" / "method_edges.trusted.jsonl", (edge.to_record() for edge in graph_layer["trusted_edges"]))
    write_jsonl(output_root / "graph" / "method_edges.candidate.jsonl", (edge.to_record() for edge in graph_layer["candidate_edges"]))
    write_jsonl(output_root / "graph" / "method_edges.unverified.jsonl", (edge.to_record() for edge in graph_layer["unverified_edges"]))
    write_jsonl(output_root / "graph" / "method_edges.aggregated.jsonl", graph_layer["aggregated_edges"])
    write_jsonl(output_root / "graph" / "method_edges.all_aggregated.jsonl", aggregate_edges(graph_layer["edges"]))
    write_jsonl(output_root / "graph" / "edge_evidence_audit.jsonl", graph_layer["edge_evidence_audit"])
    write_jsonl(output_root / "graph" / "method_evidence_records.jsonl", _evidence_rows(graph_layer["edges"]))
    write_json(output_root / "graph" / "entity_summary.json", entity_frequency_summary(entities))

    write_jsonl(output_root / "search" / "evolution_chains.jsonl", (chain.to_record() for chain in graph_layer["chains"]))
    write_jsonl(output_root / "search" / "branch_points.jsonl", graph_layer["branch_points"])
    write_jsonl(output_root / "hooks" / "forecast_hooks.jsonl", forecast_hooks)
    write_jsonl(output_root / "hooks" / "social_analysis_hooks.jsonl", social_hooks)
    write_json(output_root / "hooks" / "hook_score_report.json", hook_score_report)
    write_jsonl(output_root / "feedback" / "taxonomy_graph_feedback.jsonl", feedback_rows)
    write_json(output_root / "evaluation" / "quality_report.json", quality_report)
    write_jsonl(output_root / "audit" / "llm_judge_records.jsonl", (record.to_record() for record in llm_records))
    write_jsonl(output_root / "audit" / "unverified_edges.jsonl", (edge.to_record() for edge in graph_layer["unverified_edges"]))
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
            "applied_expansions": sum(1 for row in expansion_application_report if row.get("status") == "applied"),
            "revision_candidates": len(revision_candidates),
            "applied_revisions": sum(1 for row in revision_application_report if row.get("status") == "applied"),
            "coevolution_iterations": len(coevolution_iteration_reports),
            "entities": len(entities),
            "raw_entities": raw_entity_count,
            "filtered_entities": max(0, raw_entity_count - len(entities)),
            "entity_link_records": len(entity_link_rows),
            "llm_entity_mentions": sum(1 for row in llm_entity_report if row.get("status") == "accepted"),
            "mentions": len(mentions),
            "paper_level_edges": len(graph_layer["edges"]),
            "trusted_edges": len(graph_layer["trusted_edges"]),
            "candidate_edges": len(graph_layer["candidate_edges"]),
            "unverified_edges": len(graph_layer["unverified_edges"]),
            "downstream_edges": len(graph_layer["downstream_edges"]),
            "aggregated_edges": len(graph_layer["aggregated_edges"]),
            "evolution_chains": len(graph_layer["chains"]),
            "branch_points": len(graph_layer["branch_points"]),
            "forecast_hooks": len(forecast_hooks),
            "social_analysis_hooks": len(social_hooks),
            "feedback_rows": len(feedback_rows),
            "llm_judge_records": len(llm_records),
            "quality_score": quality_report["overall_quality_score"],
        },
        "artifact_layout": {
            "taxonomy_nodes": "taxonomy/taxonomy_nodes.enriched.json",
            "taxonomy_events": "taxonomy/taxonomy_events.jsonl",
            "node_quality_scores": "taxonomy/node_quality_scores.jsonl",
            "expansion_trigger_scores": "taxonomy/expansion_trigger_scores.jsonl",
            "expansion_candidates": "taxonomy/expansion_candidates.jsonl",
            "expansion_application_report": "taxonomy/expansion_application_report.jsonl",
            "revision_candidates": "taxonomy/revision_candidates.jsonl",
            "revision_application_report": "taxonomy/revision_application_report.jsonl",
            "coevolution_iterations": "taxonomy/coevolution_iterations.jsonl",
            "expanded_taxonomy_nodes": "taxonomy/taxonomy_nodes.expanded.json",
            "method_registry": "graph/method_registry.jsonl",
            "method_aliases": "graph/method_aliases.jsonl",
            "entity_linking_report": "graph/entity_linking_report.jsonl",
            "entity_quality_report": "graph/entity_quality_report.jsonl",
            "llm_entity_mentions": "graph/llm_entity_mentions.jsonl",
            "method_edges": "graph/method_edges.paper_level.jsonl",
            "trusted_method_edges": "graph/method_edges.trusted.jsonl",
            "candidate_method_edges": "graph/method_edges.candidate.jsonl",
            "unverified_method_edges": "graph/method_edges.unverified.jsonl",
            "edge_evidence_audit": "graph/edge_evidence_audit.jsonl",
            "evolution_chains": "search/evolution_chains.jsonl",
            "forecast_hooks": "hooks/forecast_hooks.jsonl",
            "taxonomy_graph_feedback": "feedback/taxonomy_graph_feedback.jsonl",
            "quality_report": "evaluation/quality_report.json",
            "llm_judge_records": "audit/llm_judge_records.jsonl",
            "audit": "audit/",
        },
    }
    write_json(output_root / "manifest.json", manifest)
    return manifest


def _extract_prepare_entities(
    docs: list[Any],
    assignments: dict[str, list[str]],
    config: EvoTaxaConfig,
    llm_client: Any,
    *,
    full: bool,
    llm_records: list[Any],
) -> tuple[list[Any], list[Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int]:
    entities, mentions = extract_entities(docs, assignments, config.graph)
    llm_entity_records: list[Any] = []
    if full:
        for doc in docs:
            record = extract_document_entities(
                llm_client,
                doc_id=doc.doc_id,
                title=doc.title,
                text=doc.text,
                entity_types=config.graph.entity_types,
                max_entities=config.graph.llm_entity_extraction_limit,
            )
            llm_records.append(record)
            llm_entity_records.append(record)
        entities, mentions, llm_entity_report = merge_llm_entity_mentions(
            docs,
            assignments,
            entities,
            mentions,
            llm_entity_records,
            config.graph,
        )
    else:
        llm_entity_report = []
    entities, mentions, entity_link_rows = canonicalize_entities(entities, mentions, config.graph)
    raw_entity_count = len(entities)
    entities, mentions, entity_quality_report = filter_entities_by_quality(entities, mentions, config.graph)
    return entities, mentions, entity_link_rows, entity_quality_report, llm_entity_report, raw_entity_count


def _build_graph_layer(
    docs: list[Any],
    entities: list[Any],
    mentions: list[Any],
    entity_link_rows: list[dict[str, Any]],
    config: EvoTaxaConfig,
    llm_client: Any,
    llm_records: list[Any],
    *,
    full: bool,
) -> dict[str, Any]:
    edges = build_edges(docs, entities, mentions, config.graph)
    edges = remap_edges_to_canonical_entities(edges, entity_link_rows)
    if full and edges:
        doc_map = {doc.doc_id: doc for doc in docs}
        judged_edges = []
        for edge in edges[: max(0, config.graph.llm_edge_judge_limit)]:
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
    trusted_edges, candidate_edges, unverified_edges, edge_evidence_audit = stratify_edges_by_evidence(edges, docs, config.graph)
    downstream_edges = _downstream_edges(trusted_edges, candidate_edges, unverified_edges)
    aggregated_edges = aggregate_edges(downstream_edges)
    chains = search_evolution_chains(downstream_edges, strong_edge_types=config.graph.strong_edge_types)
    branch_points = extract_branch_points(downstream_edges, strong_edge_types=config.graph.strong_edge_types)
    forecast_hooks = build_forecast_hooks(downstream_edges, chains, branch_points, strong_edge_types=config.graph.strong_edge_types)
    edge_index = {edge.edge_id: edge.to_record() for edge in downstream_edges}
    forecast_hooks = score_forecast_hooks(forecast_hooks, edge_index) if full else forecast_hooks
    return {
        "edges": edges,
        "trusted_edges": trusted_edges,
        "candidate_edges": candidate_edges,
        "unverified_edges": unverified_edges,
        "edge_evidence_audit": edge_evidence_audit,
        "downstream_edges": downstream_edges,
        "aggregated_edges": aggregated_edges,
        "chains": chains,
        "branch_points": branch_points,
        "forecast_hooks": forecast_hooks,
    }


def _merge_assignments(left: dict[str, list[str]], right: dict[str, list[str]]) -> dict[str, list[str]]:
    merged: dict[str, set[str]] = {doc_id: set(node_ids) for doc_id, node_ids in left.items()}
    for doc_id, node_ids in right.items():
        merged.setdefault(doc_id, set()).update(node_ids)
    return {doc_id: sorted(node_ids) for doc_id, node_ids in sorted(merged.items())}


def _downstream_edges(trusted_edges: list[Any], candidate_edges: list[Any], unverified_edges: list[Any]) -> list[Any]:
    if trusted_edges:
        return trusted_edges
    if candidate_edges:
        return candidate_edges
    return unverified_edges


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


def _expansion_application_events(report: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in report:
        if row.get("status") != "applied":
            continue
        events.append(
            {
                "event_id": f"applied_expansion__{row['new_node_id']}",
                "event_type": "birth",
                "time_slice": "",
                "source_node_ids": [row.get("parent_node_id") or ""],
                "target_node_ids": [row["new_node_id"]],
                "support_documents": row.get("support_documents") or [],
                "reason": "Expansion candidate accepted by judge and applied to taxonomy snapshot.",
                "confidence": row.get("confidence", 0.0),
                "source_candidate_id": row.get("candidate_id"),
            }
        )
    return events


def _revision_application_events(report: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in report:
        if row.get("status") != "applied":
            continue
        revision_type = str(row.get("revision_type") or "")
        event_type = "revision"
        target_node_ids: list[str] = []
        if revision_type == "split_child":
            event_type = "split"
            target_node_ids = [str(row.get("new_node_id") or "")]
        elif revision_type == "cross_link":
            event_type = "cross_link"
        elif revision_type == "state_annotation":
            event_type = "state_update"
        events.append(
            {
                "event_id": f"revision__{event_type}__{row.get('candidate_id')}",
                "event_type": event_type,
                "time_slice": "",
                "source_node_ids": [str(row.get("source_node_id") or "")],
                "target_node_ids": [node_id for node_id in target_node_ids if node_id],
                "support_documents": row.get("support_documents") or [],
                "support_edges": row.get("support_edges") or [],
                "reason": row.get("reason") or "Applied taxonomy-graph coevolution revision.",
                "confidence": row.get("confidence", 0.0),
                "source_candidate_id": row.get("candidate_id"),
            }
        )
    return events


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
