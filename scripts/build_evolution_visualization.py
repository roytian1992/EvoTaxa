#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from evotaxa.io import iter_jsonl, normalize_space, parse_date, write_json  # noqa: E402
from schema_groups import schema_group_for_type, schema_group_label, schema_group_records  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a static EvoTaxa evolution dashboard from a completed run.")
    parser.add_argument("--run-root", type=Path, required=True, help="Completed EvoTaxa output root.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="HTML output path. Defaults to <run-root>/visualization/evolution_dashboard.html.",
    )
    parser.add_argument("--max-nodes", type=int, default=240, help="Maximum graph nodes embedded for display.")
    parser.add_argument("--max-edges", type=int, default=320, help="Maximum graph edges embedded for display.")
    parser.add_argument("--max-trajectories", type=int, default=240, help="Maximum trajectories embedded for display.")
    parser.add_argument("--max-windows", type=int, default=240, help="Maximum temporal windows embedded for display.")
    parser.add_argument("--support-doc-limit", type=int, default=8, help="Support documents retained per entity/window.")
    args = parser.parse_args()

    run_root = args.run_root.expanduser().resolve()
    if not run_root.exists():
        raise FileNotFoundError(f"Run root does not exist: {run_root}")
    output = args.output.expanduser().resolve() if args.output else run_root / "visualization" / "evolution_dashboard.html"
    payload = build_payload(
        run_root=run_root,
        max_nodes=max(1, args.max_nodes),
        max_edges=max(1, args.max_edges),
        max_trajectories=max(1, args.max_trajectories),
        max_windows=max(1, args.max_windows),
        support_doc_limit=max(1, args.support_doc_limit),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(payload), encoding="utf-8")

    summary_path = output.with_suffix(".summary.json")
    write_json(
        summary_path,
        {
            "generated_at": payload["generated_at"],
            "run_root": payload["run_root"],
            "html_output": str(output),
            "summary": payload["summary"],
            "embedded_counts": {
                "entities": len(payload["entities"]),
                "edges": len(payload["edges"]),
                "trajectories": len(payload["trajectories"]),
                "patterns": len(payload["patterns"]),
                "windows": len(payload["windows"]),
                "documents": len(payload["documents"]),
            },
        },
    )
    print(json.dumps({"html_output": str(output), "summary_output": str(summary_path), "summary": payload["summary"]}, ensure_ascii=False, indent=2))
    return 0


def build_payload(
    *,
    run_root: Path,
    max_nodes: int,
    max_edges: int,
    max_trajectories: int,
    max_windows: int,
    support_doc_limit: int,
) -> dict[str, Any]:
    manifest = read_json(run_root / "manifest.json", default={})
    counts = manifest.get("counts") if isinstance(manifest.get("counts"), dict) else {}
    quality_report = read_json(run_root / "evaluation" / "quality_report.json", default={})
    documents_raw = read_jsonl(run_root / "corpus" / "documents.normalized.jsonl")
    entities_raw = read_jsonl(run_root / "graph" / "method_registry.jsonl")
    entity_cards_raw = read_jsonl(run_root / "graph" / "entity_cards.jsonl")
    successor_edges_path = run_root / "graph" / "successor_edges.accepted.jsonl"
    successor_edges_raw = read_jsonl(successor_edges_path)
    if successor_edges_path.exists():
        edges_raw = successor_edges_raw
        edge_source = "graph/successor_edges.accepted.jsonl"
    else:
        edges_raw = read_jsonl(run_root / "graph" / "method_edges.trusted.jsonl")
        edge_source = "graph/method_edges.trusted.jsonl"
    successor_trajectories_path = run_root / "trajectory" / "successor_trajectories.jsonl"
    successor_trajectories_raw = read_jsonl(successor_trajectories_path)
    trajectories_raw = read_jsonl(run_root / "trajectory" / "evolution_trajectories.jsonl")
    patterns_raw = read_jsonl(run_root / "macro_patterns" / "pattern_profiles.jsonl")
    pattern_timeline_raw = read_jsonl(run_root / "macro_patterns" / "pattern_timeline.jsonl")
    windows_raw = read_jsonl(run_root / "temporal_windows" / "micro_windows.jsonl")
    taxonomy_raw = read_json(run_root / "taxonomy" / "taxonomy_nodes.expanded.json", default=[])
    if not taxonomy_raw:
        taxonomy_raw = read_json(run_root / "taxonomy" / "taxonomy_nodes.enriched.json", default=[])
    entity_schema = read_json(run_root / "schema" / "entity_schema.final.json", default={})
    entity_schema_groups = read_json(run_root / "schema" / "entity_schema_groups.json", default=[])
    if not entity_schema_groups:
        entity_schema_groups = schema_group_records(entity_schema)
    relation_schema = read_json(run_root / "schema" / "relation_schema.final.json", default={})

    docs = build_document_map(documents_raw)
    taxonomy = build_taxonomy_map(taxonomy_raw)
    entities_by_id = {str(row.get("entity_id") or ""): row for row in entities_raw if row.get("entity_id")}
    entity_cards_by_id = {str(row.get("entity_id") or ""): row for row in entity_cards_raw if row.get("entity_id")}
    for edge in edges_raw:
        for entity_id in [edge.get("source_entity"), edge.get("target_entity")]:
            if entity_id and entity_id not in entities_by_id:
                entities_by_id[str(entity_id)] = fallback_entity(str(entity_id), docs, edge)

    ranked_edges = sorted(
        edges_raw,
        key=lambda row: (
            safe_float(row.get("confidence")),
            -abs(int(row.get("time_delta_days") or 0)),
            str(row.get("edge_id") or ""),
        ),
        reverse=True,
    )
    evolution_edges_ranked = [
        edge
        for edge in ranked_edges
        if is_strict_evolution_edge(edge, entities_by_id, entity_cards_by_id)
    ]
    predecessor_source_ids = {str(edge.get("source_entity") or "") for edge in evolution_edges_ranked if edge.get("source_entity")}
    predecessor_target_ids = {str(edge.get("target_entity") or "") for edge in evolution_edges_ranked if edge.get("target_entity")}
    registry_entity_ids = {str(row.get("entity_id") or "") for row in entities_raw if row.get("entity_id")}
    entity_scope_ids = registry_entity_ids or set(entities_by_id)
    entities_without_accepted_predecessor = sorted(entity_scope_ids - predecessor_target_ids)
    evolution_edge_ids = {str(edge.get("edge_id") or "") for edge in evolution_edges_ranked}
    degree = Counter()
    for edge in evolution_edges_ranked:
        source = str(edge.get("source_entity") or "")
        target = str(edge.get("target_entity") or "")
        if source:
            degree[source] += 1
        if target:
            degree[target] += 1
    strict_trajectories_raw = [
        trajectory
        for trajectory in trajectories_raw
        if trajectory_uses_only_edges(trajectory, evolution_edge_ids)
    ]
    pattern_links: dict[str, dict[str, set[str]]] = {}
    pattern_entity_ids: set[str] = set()
    pattern_trajectory_ids: set[str] = set()
    strict_successor_trajectory_by_id = {
        str(row.get("trajectory_id") or ""): row
        for row in successor_trajectories_raw
        if row.get("trajectory_id")
    }
    if edge_source == "graph/successor_edges.accepted.jsonl":
        pattern_links = build_pattern_links(patterns_raw, strict_successor_trajectory_by_id, evolution_edge_ids)
        pattern_entity_ids = set().union(*(link["entity_ids"] for link in pattern_links.values())) if pattern_links else set()
        pattern_trajectory_ids = set().union(*(link["trajectory_ids"] for link in pattern_links.values())) if pattern_links else set()
    selected_edges_seed = evolution_edges_ranked[:max_edges]
    pinned_entities: set[str] = set(pattern_entity_ids)
    for edge in selected_edges_seed:
        pinned_entities.add(str(edge.get("source_entity") or ""))
        pinned_entities.add(str(edge.get("target_entity") or ""))
    pinned_entities.discard("")

    def entity_rank(item: tuple[str, dict[str, Any]]) -> tuple[float, int, str]:
        entity_id, row = item
        support_count = len(row.get("support_documents") or [])
        score = degree[entity_id] * 100.0 + math.log1p(support_count) * 8.0
        if entity_id in pinned_entities:
            score += 1000.0
        return (score, support_count, entity_id)

    selected_entity_ids = [
        entity_id
        for entity_id, _row in sorted(entities_by_id.items(), key=entity_rank, reverse=True)[:max_nodes]
    ]
    selected_entity_set = set(selected_entity_ids)
    selected_edges = [
        edge
        for edge in evolution_edges_ranked
        if str(edge.get("source_entity") or "") in selected_entity_set
        and str(edge.get("target_entity") or "") in selected_entity_set
    ][:max_edges]
    selected_edge_ids = {str(edge.get("edge_id") or "") for edge in selected_edges}

    if edge_source == "graph/successor_edges.accepted.jsonl":
        strict_trajectories_raw = [
            trajectory
            for trajectory in successor_trajectories_raw
            if trajectory_uses_only_edges(trajectory, evolution_edge_ids)
        ]
        if not strict_trajectories_raw:
            strict_trajectories_raw = build_successor_trajectory_rows(evolution_edges_ranked)
        selected_trajectory_ids = set(pattern_trajectory_ids)
        for trajectory in sorted(strict_trajectories_raw, key=lambda row: safe_float(row.get("trajectory_score")), reverse=True):
            if len(selected_trajectory_ids) >= max_trajectories:
                break
            if all(edge_id in selected_edge_ids for edge_id in as_str_list(trajectory.get("edge_path"))):
                selected_trajectory_ids.add(str(trajectory.get("trajectory_id") or ""))
        selected_trajectories_raw = [
            trajectory
            for trajectory in strict_trajectories_raw
            if str(trajectory.get("trajectory_id") or "") in selected_trajectory_ids
        ][:max_trajectories]
    else:
        strict_trajectory_by_id = {
            str(row.get("trajectory_id") or ""): row
            for row in strict_trajectories_raw
            if row.get("trajectory_id")
        }
        pattern_links = build_pattern_links(patterns_raw, strict_trajectory_by_id, evolution_edge_ids)
        pattern_entity_ids = set().union(*(link["entity_ids"] for link in pattern_links.values())) if pattern_links else set()
        pattern_trajectory_ids = set().union(*(link["trajectory_ids"] for link in pattern_links.values())) if pattern_links else set()
        selected_trajectory_ids = pattern_trajectory_ids & set(strict_trajectory_by_id)
        for trajectory in sorted(strict_trajectories_raw, key=lambda row: safe_float(row.get("trajectory_score")), reverse=True)[:max_trajectories]:
            selected_trajectory_ids.add(str(trajectory.get("trajectory_id") or ""))
        selected_trajectories_raw = [
            trajectory
            for trajectory in strict_trajectories_raw
            if str(trajectory.get("trajectory_id") or "") in selected_trajectory_ids
        ][: max_trajectories + len(pattern_trajectory_ids)]

    windows = build_windows(
        windows_raw,
        taxonomy,
        max_windows=max_windows,
        support_doc_limit=support_doc_limit,
        allowed_edge_ids=evolution_edge_ids,
    )
    referenced_doc_ids = referenced_documents(
        entities_by_id=entities_by_id,
        selected_entity_ids=selected_entity_ids,
        edges=selected_edges,
        trajectories=selected_trajectories_raw,
        windows=windows,
        support_doc_limit=support_doc_limit,
    )
    document_payload = {doc_id: docs[doc_id] for doc_id in sorted(referenced_doc_ids) if doc_id in docs}
    entity_payload = [
        build_entity_payload(
            entity_id,
            entities_by_id[entity_id],
            entity_card=entity_cards_by_id.get(entity_id),
            degree=degree,
            docs=docs,
            taxonomy=taxonomy,
            entity_schema=entity_schema,
            support_doc_limit=support_doc_limit,
        )
        for entity_id in selected_entity_ids
        if entity_id in entities_by_id
    ]
    edge_payload = [
        build_edge_payload(edge, docs=docs, taxonomy=taxonomy, relation_schema=relation_schema)
        for edge in selected_edges
    ]
    trajectory_payload = [
        build_trajectory_payload(trajectory, entities_by_id=entities_by_id, taxonomy=taxonomy)
        for trajectory in selected_trajectories_raw
    ]
    timeline_by_pattern = group_pattern_timeline(pattern_timeline_raw)
    pattern_payload = [
        build_pattern_payload(pattern, timeline_by_pattern, pattern_links.get(str(pattern.get("pattern_id") or ""), {}))
        for pattern in sorted(patterns_raw, key=lambda row: safe_float(row.get("pattern_score")), reverse=True)
    ]

    years = build_yearly_series(documents_raw, entities_by_id.values(), edge_payload, windows)
    date_span = infer_date_span(documents_raw)
    counts_with_fallback = build_counts(manifest, counts, quality_report)
    summary = {
        "project_name": get_path(manifest, ["project", "name"]) or "EvoTaxa",
        "run_id": get_path(manifest, ["project", "run_id"]) or run_root.name,
        "edge_source": edge_source,
        "documents": counts_with_fallback.get("documents", len(documents_raw)),
        "entities": counts_with_fallback.get("entities", len(entities_raw)),
        "raw_entities": counts_with_fallback.get("raw_entities"),
        "filtered_entities": counts_with_fallback.get("filtered_entities"),
        "trusted_edges": counts_with_fallback.get("trusted_edges", len(edges_raw)),
        "successor_edges": len(successor_edges_raw),
        "strict_evolution_edges": len(evolution_edges_ranked),
        "entities_with_accepted_predecessor": len(predecessor_target_ids),
        "entities_as_accepted_predecessor": len(predecessor_source_ids),
        "entities_without_accepted_predecessor": len(entities_without_accepted_predecessor),
        "predecessor_policy": "No edge is forced for genuinely new or currently unlinked concepts.",
        "candidate_edges": counts_with_fallback.get("candidate_edges"),
        "trajectories": len(strict_trajectories_raw),
        "successor_trajectories": len(successor_trajectories_raw),
        "raw_trajectories": counts_with_fallback.get("trajectories", len(trajectories_raw)),
        "macro_patterns": counts_with_fallback.get("macro_patterns", len(patterns_raw)),
        "temporal_windows": counts_with_fallback.get("temporal_windows", len(windows_raw)),
        "quality_score": counts_with_fallback.get("quality_score"),
        "date_start": date_span[0],
        "date_end": date_span[1],
        "embedded_entities": len(entity_payload),
        "embedded_edges": len(edge_payload),
        "embedded_trajectories": len(trajectory_payload),
        "entity_cards": len(entity_cards_raw),
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_root": str(run_root),
        "summary": summary,
        "years": years,
        "year_min": min((row["year"] for row in years), default=1990),
        "year_max": max((row["year"] for row in years), default=2026),
        "entity_types": sorted({row.get("type") or "unknown" for row in entity_payload}),
        "edge_types": sorted({row.get("type") or "unknown" for row in edge_payload}),
        "entities": entity_payload,
        "edges": edge_payload,
        "trajectories": trajectory_payload,
        "patterns": pattern_payload,
        "windows": windows,
        "documents": document_payload,
        "taxonomy": build_taxonomy_payload(taxonomy, entity_payload, edge_payload, pattern_payload, windows),
        "relation_labels": build_schema_labels(relation_schema),
        "entity_type_labels": build_schema_group_labels(entity_schema_groups, entity_schema),
        "raw_entity_type_labels": build_schema_labels(entity_schema),
    }


def read_json(path: Path, *, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        return default


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return list(iter_jsonl(path))


def build_document_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    docs: dict[str, dict[str, Any]] = {}
    for row in rows:
        doc_id = str(row.get("doc_id") or "")
        if not doc_id:
            continue
        date_value = str(row.get("published_at") or "")
        parsed = parse_date(date_value)
        docs[doc_id] = {
            "doc_id": doc_id,
            "title": normalize_space(row.get("title") or doc_id),
            "published_at": parsed.isoformat() if parsed else date_value,
            "year": parsed.year if parsed else year_from_value(row.get("chronology_slice") or date_value),
            "role": str(row.get("role") or ""),
            "source_type": str(row.get("source_type") or ""),
        }
    return docs


def build_taxonomy_map(value: Any) -> dict[str, dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    taxonomy: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        node_id = str(row.get("node_id") or "")
        if not node_id:
            continue
        taxonomy[node_id] = {
            "node_id": node_id,
            "label": normalize_space(row.get("canonical_label") or node_id),
            "dimension": str(row.get("dimension") or ""),
            "definition": normalize_space(row.get("definition") or ""),
            "support_count": len(row.get("support_documents") or []),
        }
    return taxonomy


def fallback_entity(entity_id: str, docs: dict[str, dict[str, Any]], edge: dict[str, Any]) -> dict[str, Any]:
    doc_id = str(edge.get("source_document") or edge.get("target_document") or "")
    doc = docs.get(doc_id, {})
    raw_type = entity_id.split("__", 1)[0] if "__" in entity_id else "unknown"
    return {
        "entity_id": entity_id,
        "canonical_name": entity_name_from_id(entity_id),
        "aliases": [],
        "first_seen_date": doc.get("published_at") or "",
        "support_documents": [doc_id] if doc_id else [],
        "taxonomy_nodes": edge.get("taxonomy_nodes") or [],
        "entity_type": raw_type,
        "schema_group": schema_group_for_type(raw_type),
    }


def is_strict_evolution_edge(
    edge: dict[str, Any],
    entities_by_id: dict[str, dict[str, Any]],
    entity_cards_by_id: dict[str, dict[str, Any]] | None = None,
) -> bool:
    source_id = str(edge.get("source_entity") or "")
    target_id = str(edge.get("target_entity") or "")
    source_type = str((entities_by_id.get(source_id) or {}).get("entity_type") or source_id.split("__", 1)[0])
    target_type = str((entities_by_id.get(target_id) or {}).get("entity_type") or target_id.split("__", 1)[0])
    source_card = (entity_cards_by_id or {}).get(source_id) or {}
    target_card = (entity_cards_by_id or {}).get(target_id) or {}
    source_group = str(edge.get("source_schema_group") or edge.get("schema_group") or source_card.get("schema_group") or (entities_by_id.get(source_id) or {}).get("schema_group") or schema_group_for_type(source_type))
    target_group = str(edge.get("target_schema_group") or edge.get("schema_group") or target_card.get("schema_group") or (entities_by_id.get(target_id) or {}).get("schema_group") or schema_group_for_type(target_type))
    if not source_group or source_group != target_group:
        return False
    try:
        delta = int(edge.get("time_delta_days"))
    except (TypeError, ValueError):
        return False
    return delta > 0


def trajectory_uses_only_edges(trajectory: dict[str, Any], allowed_edge_ids: set[str]) -> bool:
    edge_path = as_str_list(trajectory.get("edge_path"))
    return bool(edge_path) and all(edge_id in allowed_edge_ids for edge_id in edge_path)


def build_successor_trajectory_rows(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, edge in enumerate(edges):
        edge_id = str(edge.get("edge_id") or "")
        source = str(edge.get("source_entity") or "")
        target = str(edge.get("target_entity") or "")
        if not edge_id or not source or not target:
            continue
        rows.append(
            {
                "trajectory_id": f"successor_trajectory__{index:06d}",
                "entity_path": [source, target],
                "edge_path": [edge_id],
                "taxonomy_nodes": as_str_list(edge.get("taxonomy_nodes")),
                "trajectory_score": safe_float(edge.get("confidence")),
                "path_length": 1,
                "mean_edge_confidence": safe_float(edge.get("confidence")),
                "temporal_coherence": 1.0,
                "quote_grounding": 1.0 if edge.get("substring_verified") else 0.75,
                "schema_coherence": 1.0,
                "branching_factor": 1,
            }
        )
    return rows


def build_pattern_links(
    patterns: list[dict[str, Any]],
    trajectory_by_id: dict[str, dict[str, Any]],
    edge_ids: set[str],
) -> dict[str, dict[str, set[str]]]:
    links: dict[str, dict[str, set[str]]] = {}
    for pattern in patterns:
        pattern_id = str(pattern.get("pattern_id") or "")
        edge_set: set[str] = set()
        trajectory_set: set[str] = set()
        entity_set: set[str] = set()
        for evidence_id in as_str_list(pattern.get("evidence_ids")):
            if evidence_id in edge_ids:
                edge_set.add(evidence_id)
            if evidence_id in trajectory_by_id:
                trajectory_set.add(evidence_id)
        for trajectory_id in as_str_list(pattern.get("representative_trajectories")):
            if trajectory_id in trajectory_by_id:
                trajectory_set.add(trajectory_id)
        for trajectory_id in trajectory_set:
            trajectory = trajectory_by_id.get(trajectory_id) or {}
            for edge_id in as_str_list(trajectory.get("edge_path")):
                if edge_id in edge_ids:
                    edge_set.add(edge_id)
            for entity_id in as_str_list(trajectory.get("entity_path")):
                entity_set.add(entity_id)
        links[pattern_id] = {"edge_ids": edge_set, "trajectory_ids": trajectory_set, "entity_ids": entity_set}
    return links


def build_entity_payload(
    entity_id: str,
    row: dict[str, Any],
    *,
    entity_card: dict[str, Any] | None = None,
    degree: Counter[str],
    docs: dict[str, dict[str, Any]],
    taxonomy: dict[str, dict[str, Any]],
    entity_schema: dict[str, Any],
    support_doc_limit: int,
) -> dict[str, Any]:
    if entity_card:
        taxonomy_nodes = as_str_list(entity_card.get("taxonomy_nodes"))
        first_seen = str(entity_card.get("first_seen_date") or "")
        raw_type = str(entity_card.get("entity_type") or row.get("entity_type") or "unknown")
        schema_group = str(entity_card.get("schema_group") or schema_group_for_type(raw_type))
        return {
            "id": entity_id,
            "name": normalize_space(entity_card.get("display_name") or entity_card.get("contextual_name") or entity_card.get("canonical_name") or row.get("canonical_name") or entity_name_from_id(entity_id)),
            "canonical_name": normalize_space(entity_card.get("canonical_name") or row.get("canonical_name") or entity_name_from_id(entity_id)),
            "contextual_name": normalize_space(entity_card.get("contextual_name") or ""),
            "domain_context": normalize_space(entity_card.get("domain_context") or ""),
            "method_role": normalize_space(entity_card.get("method_role") or ""),
            "domain_grounding_score": safe_float(entity_card.get("domain_grounding_score")),
            "generic_technology_name": bool(entity_card.get("generic_technology_name")),
            "aliases": as_str_list(entity_card.get("aliases"))[:8],
            "type": schema_group,
            "type_label": normalize_space(entity_card.get("schema_group_label") or schema_group_label(schema_group)),
            "definition": normalize_space(entity_card.get("schema_group_definition") or ""),
            "entity_type": raw_type,
            "entity_type_label": normalize_space(entity_card.get("entity_type_label") or raw_type),
            "entity_type_definition": normalize_space(entity_card.get("entity_type_definition") or ""),
            "schema_group": schema_group,
            "schema_group_label": normalize_space(entity_card.get("schema_group_label") or schema_group_label(schema_group)),
            "first_seen": first_seen,
            "year": year_from_value(first_seen),
            "support_count": int(entity_card.get("support_document_count") or 0),
            "support_documents": [str((doc or {}).get("doc_id") or "") for doc in as_dict_list(entity_card.get("support_documents"))[:support_doc_limit] if (doc or {}).get("doc_id")],
            "taxonomy_nodes": taxonomy_nodes,
            "taxonomy_labels": as_str_list(entity_card.get("taxonomy_labels")) or [taxonomy_label(taxonomy, node_id) for node_id in taxonomy_nodes],
            "degree": int(entity_card.get("successor_degree") or degree[entity_id]),
        }
    support_docs = as_str_list(row.get("support_documents"))
    first_seen = str(row.get("first_seen_date") or "")
    first_date = parse_date(first_seen)
    if not first_date:
        support_years = [docs[doc_id]["year"] for doc_id in support_docs if doc_id in docs and docs[doc_id].get("year")]
        if support_years:
            first_seen = f"{min(support_years)}-01-01"
    entity_type = str(row.get("entity_type") or "unknown")
    schema_group = str(row.get("schema_group") or schema_group_for_type(entity_type))
    schema = entity_schema.get(entity_type) if isinstance(entity_schema, dict) else {}
    return {
        "id": entity_id,
        "name": normalize_space(row.get("canonical_name") or entity_name_from_id(entity_id)),
        "canonical_name": normalize_space(row.get("canonical_name") or entity_name_from_id(entity_id)),
        "contextual_name": "",
        "domain_context": "",
        "method_role": "",
        "domain_grounding_score": 0,
        "generic_technology_name": False,
        "aliases": as_str_list(row.get("aliases"))[:8],
        "type": schema_group,
        "type_label": schema_group_label(schema_group),
        "definition": "",
        "entity_type": entity_type,
        "entity_type_label": normalize_space((schema or {}).get("label") or entity_type),
        "entity_type_definition": normalize_space((schema or {}).get("definition") or ""),
        "schema_group": schema_group,
        "schema_group_label": schema_group_label(schema_group),
        "first_seen": first_seen,
        "year": year_from_value(first_seen),
        "support_count": len(support_docs),
        "support_documents": support_docs[:support_doc_limit],
        "taxonomy_nodes": as_str_list(row.get("taxonomy_nodes")),
        "taxonomy_labels": [taxonomy_label(taxonomy, node_id) for node_id in as_str_list(row.get("taxonomy_nodes"))],
        "degree": degree[entity_id],
    }


def build_edge_payload(
    edge: dict[str, Any],
    *,
    docs: dict[str, dict[str, Any]],
    taxonomy: dict[str, dict[str, Any]],
    relation_schema: dict[str, Any],
) -> dict[str, Any]:
    source_doc = str(edge.get("source_document") or "")
    target_doc = str(edge.get("target_document") or "")
    source_doc_row = docs.get(source_doc, {})
    target_doc_row = docs.get(target_doc, {})
    evidence = edge.get("evidence") if isinstance(edge.get("evidence"), dict) else {}
    evidence_fields = extract_evidence_fields(evidence)
    edge_type = str(edge.get("edge_type") or "unknown")
    schema = relation_schema.get(edge_type) if isinstance(relation_schema, dict) else {}
    audit = evidence.get("evidence_audit") if isinstance(evidence, dict) and isinstance(evidence.get("evidence_audit"), dict) else {}
    return {
        "id": str(edge.get("edge_id") or ""),
        "source": str(edge.get("source_entity") or ""),
        "target": str(edge.get("target_entity") or ""),
        "type": edge_type,
        "type_label": normalize_space((schema or {}).get("label") or edge_type),
        "definition": normalize_space((schema or {}).get("definition") or ""),
        "schema_group": str(edge.get("schema_group") or ""),
        "source_schema_group": str(edge.get("source_schema_group") or edge.get("schema_group") or ""),
        "target_schema_group": str(edge.get("target_schema_group") or edge.get("schema_group") or ""),
        "source_entity_type": str(edge.get("source_entity_type") or ""),
        "target_entity_type": str(edge.get("target_entity_type") or ""),
        "confidence": round(safe_float(edge.get("confidence")), 3),
        "time_delta_days": edge.get("time_delta_days"),
        "source_document": source_doc,
        "target_document": target_doc,
        "source_title": source_doc_row.get("title") or source_doc,
        "target_title": target_doc_row.get("title") or target_doc,
        "source_date": source_doc_row.get("published_at") or "",
        "target_date": target_doc_row.get("published_at") or "",
        "source_year": source_doc_row.get("year"),
        "target_year": target_doc_row.get("year"),
        "year": target_doc_row.get("year") or source_doc_row.get("year"),
        "taxonomy_nodes": as_str_list(edge.get("taxonomy_nodes")),
        "taxonomy_labels": [taxonomy_label(taxonomy, node_id) for node_id in as_str_list(edge.get("taxonomy_nodes"))],
        "cue": normalize_space(evidence.get("cue") or "") if isinstance(evidence, dict) else "",
        "quote": first_quote(evidence_fields),
        "evidence_fields": evidence_fields,
        "audit_status": normalize_space(audit.get("status") or ""),
        "audit_reason": normalize_space(audit.get("reason") or ""),
        "substring_verified": bool(edge.get("substring_verified")),
    }


def extract_evidence_fields(evidence: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    skip = {"edge_score", "evidence_audit", "schema_slots"}
    preferred = [
        "mechanism",
        "methodological_problem",
        "validation_evidence",
        "implementation_context",
        "data_basis",
        "measurement_design",
        "bottleneck",
        "tradeoff",
    ]
    keys = preferred + [key for key in evidence.keys() if key not in preferred and key not in skip]
    seen: set[str] = set()
    for key in keys:
        if key in seen or key in skip:
            continue
        seen.add(key)
        value = evidence.get(key)
        if not isinstance(value, dict):
            continue
        description = normalize_space(value.get("description") or "")
        quote = normalize_space(value.get("quote") or "")
        if description or quote:
            rows.append({"field": key, "description": description, "quote": quote})
    return rows


def first_quote(fields: list[dict[str, str]]) -> str:
    for field in fields:
        quote = normalize_space(field.get("quote") or "")
        if quote:
            return quote
    for field in fields:
        description = normalize_space(field.get("description") or "")
        if description:
            return description
    return ""


def build_trajectory_payload(
    trajectory: dict[str, Any],
    *,
    entities_by_id: dict[str, dict[str, Any]],
    taxonomy: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    entity_path = as_str_list(trajectory.get("entity_path"))
    materialized_labels = as_str_list(trajectory.get("entity_labels"))
    canonical_labels = as_str_list(trajectory.get("canonical_entity_labels"))
    return {
        "id": str(trajectory.get("trajectory_id") or ""),
        "entity_path": entity_path,
        "entity_labels": materialized_labels
        or [
            normalize_space((entities_by_id.get(entity_id) or {}).get("canonical_name") or entity_name_from_id(entity_id))
            for entity_id in entity_path
        ],
        "canonical_entity_labels": canonical_labels,
        "edge_path": as_str_list(trajectory.get("edge_path")),
        "taxonomy_nodes": as_str_list(trajectory.get("taxonomy_nodes")),
        "taxonomy_labels": [taxonomy_label(taxonomy, node_id) for node_id in as_str_list(trajectory.get("taxonomy_nodes"))],
        "score": round(safe_float(trajectory.get("trajectory_score")), 3),
        "path_length": int(trajectory.get("path_length") or len(as_str_list(trajectory.get("edge_path")))),
        "mean_edge_confidence": round(safe_float(trajectory.get("mean_edge_confidence")), 3),
        "temporal_coherence": round(safe_float(trajectory.get("temporal_coherence")), 3),
        "quote_grounding": round(safe_float(trajectory.get("quote_grounding")), 3),
        "schema_coherence": round(safe_float(trajectory.get("schema_coherence")), 3),
        "branching_factor": trajectory.get("branching_factor"),
        "trajectory_source": str(trajectory.get("trajectory_source") or ""),
        "edge_types": as_str_list(trajectory.get("edge_types")),
    }


def build_windows(
    rows: list[dict[str, Any]],
    taxonomy: dict[str, dict[str, Any]],
    *,
    max_windows: int,
    support_doc_limit: int,
    allowed_edge_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    allowed_edge_ids = allowed_edge_ids or set()
    filtered_rows = []
    for row in rows:
        representative_edges = [edge_id for edge_id in as_str_list(row.get("representative_edges")) if edge_id in allowed_edge_ids]
        if allowed_edge_ids and not representative_edges and int(row.get("edge_count") or 0) > 0:
            continue
        updated = dict(row)
        updated["representative_edges"] = representative_edges
        updated["edge_count"] = len(representative_edges)
        filtered_rows.append(updated)

    def window_rank(row: dict[str, Any]) -> tuple[int, int, int, str]:
        return (
            int(row.get("edge_count") or 0),
            int(row.get("mention_count") or 0),
            int(row.get("document_count") or 0),
            str(row.get("start_date") or ""),
        )

    selected = sorted(filtered_rows, key=window_rank, reverse=True)[:max_windows]
    selected.sort(key=lambda row: (str(row.get("start_date") or ""), str(row.get("scope_type") or ""), str(row.get("window_id") or "")))
    payload = []
    for row in selected:
        taxonomy_nodes = as_str_list(row.get("taxonomy_nodes"))
        payload.append(
            {
                "id": str(row.get("window_id") or ""),
                "scope_type": str(row.get("scope_type") or ""),
                "scope_id": str(row.get("scope_id") or ""),
                "scope_label": normalize_space(row.get("scope_label") or row.get("scope_id") or ""),
                "window_index": row.get("window_index"),
                "start_date": str(row.get("start_date") or ""),
                "end_date": str(row.get("end_date") or ""),
                "start_year": year_from_value(row.get("start_date")),
                "end_year": year_from_value(row.get("end_date")),
                "duration_days": row.get("duration_days"),
                "trigger": str(row.get("trigger") or ""),
                "document_count": int(row.get("document_count") or 0),
                "mention_count": int(row.get("mention_count") or 0),
                "edge_count": int(row.get("edge_count") or 0),
                "event_count": int(row.get("event_count") or 0),
                "representative_documents": as_str_list(row.get("representative_documents"))[:support_doc_limit],
                "representative_entities": as_str_list(row.get("representative_entities"))[:support_doc_limit],
                "representative_edges": as_str_list(row.get("representative_edges"))[:support_doc_limit],
                "taxonomy_nodes": taxonomy_nodes,
                "taxonomy_labels": [taxonomy_label(taxonomy, node_id) for node_id in taxonomy_nodes],
            }
        )
    return payload


def group_pattern_timeline(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    timeline: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        pattern_id = str(row.get("pattern_id") or "")
        if not pattern_id:
            continue
        timeline[pattern_id].append(
            {
                "time_slice": str(row.get("time_slice") or ""),
                "score": round(safe_float(row.get("pattern_score")), 3),
                "evidence_count": len(row.get("evidence_ids") or []),
                "representative_trajectories": as_str_list(row.get("representative_trajectories"))[:10],
                "representative_node_ids": as_str_list(row.get("representative_node_ids"))[:10],
            }
        )
    for rows_for_pattern in timeline.values():
        rows_for_pattern.sort(key=lambda row: row["time_slice"])
    return dict(timeline)


def build_pattern_payload(
    pattern: dict[str, Any],
    timeline_by_pattern: dict[str, list[dict[str, Any]]],
    links: dict[str, set[str]],
) -> dict[str, Any]:
    pattern_id = str(pattern.get("pattern_id") or "")
    evidence_ids = as_str_list(pattern.get("evidence_ids"))
    return {
        "id": pattern_id,
        "label": normalize_space(pattern.get("pattern_label") or pattern_id),
        "definition": normalize_space(pattern.get("definition") or ""),
        "score": round(safe_float(pattern.get("pattern_score")), 3),
        "time_span": str(pattern.get("time_span") or ""),
        "representative_node_ids": as_str_list(pattern.get("representative_node_ids")),
        "representative_nodes": as_str_list(pattern.get("representative_nodes")),
        "representative_trajectories": as_str_list(pattern.get("representative_trajectories")),
        "evidence_ids": evidence_ids,
        "evidence_count": int(pattern.get("evidence_count") or len(evidence_ids)),
        "supporting_signal_count": int(pattern.get("supporting_signal_count") or 0),
        "insight": normalize_space(pattern.get("insight") or ""),
        "analytic_note": normalize_space(pattern.get("analytic_note") or ""),
        "interpretation_caveat": normalize_space(pattern.get("interpretation_caveat") or ""),
        "dominant_signals": as_dict_list(pattern.get("dominant_signals"))[:8],
        "dominant_artifacts": as_dict_list(pattern.get("dominant_artifacts"))[:8],
        "dominant_relations": as_dict_list(pattern.get("dominant_relations"))[:8],
        "dominant_type_transitions": as_dict_list(pattern.get("dominant_type_transitions"))[:8],
        "dominant_schema_groups": as_dict_list(pattern.get("dominant_schema_groups"))[:8],
        "temporal_hotspots": as_dict_list(pattern.get("temporal_hotspots"))[:8],
        "representative_evidence": as_dict_list(pattern.get("representative_evidence"))[:12],
        "explanation": normalize_space(pattern.get("explanation") or ""),
        "llm_summary_used": bool(pattern.get("llm_summary_used")),
        "timeline": timeline_by_pattern.get(pattern_id, []),
        "edge_ids": sorted(links.get("edge_ids") or []),
        "entity_ids": sorted(links.get("entity_ids") or []),
        "trajectory_ids": sorted(links.get("trajectory_ids") or []),
    }


def referenced_documents(
    *,
    entities_by_id: dict[str, dict[str, Any]],
    selected_entity_ids: list[str],
    edges: list[dict[str, Any]],
    trajectories: list[dict[str, Any]],
    windows: list[dict[str, Any]],
    support_doc_limit: int,
) -> set[str]:
    doc_ids: set[str] = set()
    for entity_id in selected_entity_ids:
        for doc_id in as_str_list((entities_by_id.get(entity_id) or {}).get("support_documents"))[:support_doc_limit]:
            doc_ids.add(doc_id)
    for edge in edges:
        for doc_id in [edge.get("source_document"), edge.get("target_document")]:
            if doc_id:
                doc_ids.add(str(doc_id))
    for trajectory in trajectories:
        for edge_id in as_str_list(trajectory.get("edge_path")):
            parts = edge_id.rsplit("__", 1)
            if len(parts) == 2 and parts[-1].startswith("w"):
                doc_ids.add(parts[-1].upper())
    for window in windows:
        for doc_id in as_str_list(window.get("representative_documents"))[:support_doc_limit]:
            doc_ids.add(doc_id)
    return doc_ids


def build_yearly_series(
    documents: list[dict[str, Any]],
    entities: Any,
    edges: list[dict[str, Any]],
    windows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    doc_counts = Counter()
    entity_counts = Counter()
    edge_counts = Counter()
    window_counts = Counter()
    for row in documents:
        year = year_from_value(row.get("published_at") or row.get("chronology_slice"))
        if year:
            doc_counts[year] += 1
    for row in entities:
        year = year_from_value(row.get("first_seen_date"))
        if year:
            entity_counts[year] += 1
    for row in edges:
        year = year_from_value(row.get("target_document_year") or row.get("year"))
        if not year:
            year = year_from_value(row.get("target_document") or row.get("source_document"))
        if year:
            edge_counts[year] += 1
    for row in windows:
        year = year_from_value(row.get("start_date"))
        if year:
            window_counts[year] += 1
    all_years = sorted(set(doc_counts) | set(entity_counts) | set(edge_counts) | set(window_counts))
    if not all_years:
        return []
    return [
        {
            "year": year,
            "documents": int(doc_counts[year]),
            "entity_first_seen": int(entity_counts[year]),
            "trusted_edges": int(edge_counts[year]),
            "windows_started": int(window_counts[year]),
        }
        for year in range(min(all_years), max(all_years) + 1)
    ]


def infer_date_span(documents: list[dict[str, Any]]) -> tuple[str, str]:
    dates = []
    for row in documents:
        parsed = parse_date(row.get("published_at"))
        if parsed:
            dates.append(parsed)
    if not dates:
        return ("", "")
    return (min(dates).isoformat(), max(dates).isoformat())


def build_counts(manifest: dict[str, Any], counts: dict[str, Any], quality_report: dict[str, Any]) -> dict[str, Any]:
    output = dict(counts)
    inputs = manifest.get("inputs") if isinstance(manifest.get("inputs"), dict) else {}
    corpus = inputs.get("corpus") if isinstance(inputs.get("corpus"), dict) else {}
    if "documents" not in output and corpus.get("loaded_documents") is not None:
        output["documents"] = corpus.get("loaded_documents")
    if "quality_score" not in output:
        for source in [manifest, quality_report]:
            if isinstance(source, dict) and source.get("quality_score") is not None:
                output["quality_score"] = source.get("quality_score")
                break
    return output


def build_taxonomy_payload(
    taxonomy: dict[str, dict[str, Any]],
    entities: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    patterns: list[dict[str, Any]],
    windows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    ids: set[str] = set()
    for row in entities + edges + windows:
        ids.update(as_str_list(row.get("taxonomy_nodes")))
    for pattern in patterns:
        ids.update(as_str_list(pattern.get("representative_node_ids")))
    return {node_id: taxonomy[node_id] for node_id in sorted(ids) if node_id in taxonomy}


def build_schema_labels(schema: dict[str, Any]) -> dict[str, str]:
    if not isinstance(schema, dict):
        return {}
    labels = {}
    for key, value in schema.items():
        if isinstance(value, dict):
            labels[str(key)] = normalize_space(value.get("label") or value.get("display_name") or value.get("entity_type") or key)
        else:
            labels[str(key)] = str(key)
    return labels


def build_schema_group_labels(groups: Any, entity_schema: dict[str, Any]) -> dict[str, str]:
    labels = {}
    rows = groups if isinstance(groups, list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("schema_group") or "")
        if key:
            labels[key] = normalize_space(row.get("label") or schema_group_label(key))
    for row in schema_group_records(entity_schema):
        key = str(row.get("schema_group") or "")
        labels.setdefault(key, normalize_space(row.get("label") or schema_group_label(key)))
    return labels


def get_path(row: dict[str, Any], path: list[str]) -> Any:
    current: Any = row
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def as_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def year_from_value(value: Any) -> int | None:
    if value is None:
        return None
    parsed = parse_date(value)
    if parsed:
        return parsed.year
    text = str(value)
    for token in text.replace("_", "-").split("-"):
        if token.isdigit() and len(token) == 4:
            year = int(token)
            if 1500 <= year <= 2100:
                return year
    return None


def taxonomy_label(taxonomy: dict[str, dict[str, Any]], node_id: str) -> str:
    return normalize_space((taxonomy.get(node_id) or {}).get("label") or node_id)


def entity_name_from_id(entity_id: str) -> str:
    raw = entity_id.split("__", 1)[-1]
    return normalize_space(raw.replace("_", " "))


def render_html(payload: dict[str, Any] | None = None, *, api_mode: bool = False, data_api: str = "/api/data") -> str:
    if api_mode:
        bootstrap = f'window.EVOTAXA_DATA_API = "{data_api}";'
    else:
        data_json = json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        bootstrap = f"window.EVOTAXA_BOOTSTRAP_DATA = {data_json};"
    return HTML_TEMPLATE.replace("__DATA_BOOTSTRAP__", bootstrap)


HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EvoTaxa 演化可视化</title>
  <style>
    :root {
      --bg: #f7f8fa;
      --panel: #ffffff;
      --line: #d9dee8;
      --line-strong: #aab4c3;
      --text: #111827;
      --muted: #5b6472;
      --subtle: #eef2f6;
      --teal: #0f766e;
      --blue: #2563eb;
      --violet: #7c3aed;
      --amber: #b45309;
      --red: #b91c1c;
      --green: #15803d;
      --ink: #263244;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--text);
      background: var(--bg);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }
    button, input { font: inherit; }
    .app-header {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      padding: 18px 22px 14px;
      border-bottom: 1px solid var(--line);
      background: #ffffff;
    }
    h1 { margin: 0 0 4px; font-size: 22px; font-weight: 720; letter-spacing: 0; }
    h2 { margin: 0; font-size: 15px; font-weight: 700; letter-spacing: 0; }
    h3 { margin: 0 0 6px; font-size: 16px; font-weight: 720; letter-spacing: 0; }
    h4 { margin: 14px 0 6px; font-size: 13px; font-weight: 720; color: var(--ink); letter-spacing: 0; }
    .meta { color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
    .header-note { max-width: 560px; color: var(--muted); font-size: 12px; text-align: right; overflow-wrap: anywhere; }
    .layout {
      display: grid;
      grid-template-columns: minmax(230px, 280px) minmax(0, 1fr) minmax(280px, 360px);
      gap: 14px;
      padding: 14px;
      align-items: start;
    }
    .stack { display: flex; flex-direction: column; gap: 14px; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 1px 1px rgba(17, 24, 39, 0.04);
      overflow: hidden;
    }
    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      padding: 11px 12px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfd;
    }
    .panel-body { padding: 12px; }
    .metrics {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 8px;
    }
    .metric {
      background: #ffffff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 11px;
      min-width: 0;
    }
    .metric-value { font-size: 21px; font-weight: 760; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .metric-label { margin-top: 2px; color: var(--muted); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .control-group { margin-bottom: 14px; }
    .control-label { display: block; margin-bottom: 6px; color: var(--ink); font-size: 12px; font-weight: 700; }
    .search-input, .range-input {
      width: 100%;
      border: 1px solid var(--line-strong);
      border-radius: 6px;
      padding: 8px 9px;
      background: #ffffff;
      color: var(--text);
    }
    .check-grid { display: grid; gap: 6px; }
    .check-row { display: flex; align-items: center; gap: 7px; color: var(--ink); font-size: 12px; min-width: 0; }
    .check-row span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .button-row { display: flex; flex-wrap: wrap; gap: 6px; }
    .timeline-controls {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
    }
    .graph-stage {
      position: relative;
      background: #ffffff;
    }
    .graph-nav-button {
      position: absolute;
      right: 10px;
      width: 34px;
      height: 34px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.96);
      color: var(--ink);
      box-shadow: 0 1px 3px rgba(17, 24, 39, 0.12);
      cursor: pointer;
      font-size: 18px;
      line-height: 1;
      z-index: 3;
    }
    .graph-nav-button:hover {
      border-color: var(--teal);
      color: var(--teal);
      background: #f0fdfa;
    }
    .graph-nav-button:disabled {
      opacity: 0.35;
      cursor: default;
      color: var(--muted);
      background: rgba(255, 255, 255, 0.82);
    }
    .graph-nav-earlier { top: 42px; }
    .graph-nav-later { bottom: 42px; }
    .selection-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 10px 12px 0;
    }
    .seg-button {
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #ffffff;
      color: var(--ink);
      padding: 5px 9px;
      cursor: pointer;
      font-size: 12px;
      max-width: 180px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .seg-button.active {
      border-color: var(--teal);
      color: #ffffff;
      background: var(--teal);
    }
    .time-window-label {
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 5px 9px;
      background: #ffffff;
      color: var(--ink);
      font-size: 12px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .small-button {
      border: 1px solid var(--line-strong);
      border-radius: 6px;
      background: #ffffff;
      color: var(--ink);
      padding: 6px 8px;
      cursor: pointer;
      font-size: 12px;
    }
    .small-button:hover, .small-button.active { border-color: var(--teal); color: var(--teal); background: #f0fdfa; }
    .small-button:disabled { opacity: 0.45; cursor: default; }
    .pattern-list, .trajectory-list, .window-list { display: flex; flex-direction: column; gap: 8px; }
    .list-row {
      width: 100%;
      text-align: left;
      border: 1px solid var(--line);
      background: #ffffff;
      border-radius: 7px;
      padding: 9px;
      cursor: pointer;
      color: var(--text);
    }
    .list-row:hover { border-color: var(--line-strong); background: #fbfcfd; }
    .list-row.active { border-color: var(--teal); box-shadow: inset 3px 0 0 var(--teal); }
    .list-row.dimmed { opacity: 0.48; }
    .row-title { display: flex; justify-content: space-between; gap: 8px; align-items: center; font-size: 13px; font-weight: 700; }
    .row-sub { margin-top: 4px; color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
    .scorebar { height: 6px; border-radius: 4px; background: var(--subtle); overflow: hidden; margin-top: 7px; }
    .scorebar > span { display: block; height: 100%; background: var(--teal); }
    .legend { display: flex; flex-wrap: wrap; gap: 10px; color: var(--muted); font-size: 12px; }
    .legend-item { display: inline-flex; align-items: center; gap: 5px; }
    .swatch { width: 10px; height: 10px; border-radius: 2px; display: inline-block; background: var(--line-strong); }
    .chart-svg, .graph-svg { width: 100%; display: block; background: #ffffff; }
    .chart-svg { height: 230px; }
    .graph-svg { height: 570px; }
    .graph-workbench {
      border-top: 1px solid var(--line);
      background: #fbfcfd;
    }
    .graph-workbench-header {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 10px;
      margin-bottom: 9px;
      color: var(--ink);
      font-size: 12px;
      font-weight: 700;
    }
    .edge-card-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      max-height: 330px;
      overflow: auto;
      padding-right: 2px;
    }
    .axis-line { stroke: #c8d0dc; stroke-width: 1; }
    .axis-label { fill: var(--muted); font-size: 11px; }
    .year-bar { fill: #dbe4ee; }
    .year-bar:hover { fill: #b7c7d8; }
    .node { cursor: pointer; stroke: #ffffff; stroke-width: 1.5; }
    .node.selected { stroke: var(--red); stroke-width: 3; }
    .node.pattern-hit { stroke: var(--amber); stroke-width: 3; }
    .edge { fill: none; stroke-width: 2.2; opacity: 0.88; }
    .edge.selected { stroke-width: 4.2; }
    .edge.pattern-hit { stroke-width: 3.8; opacity: 1; }
    .edge.dimmed, .node.dimmed, .node-label.dimmed { opacity: 0.2; }
    .edge-hit { fill: none; stroke: transparent; stroke-width: 12; cursor: pointer; }
    .node-label { font-size: 11px; fill: #243145; paint-order: stroke; stroke: #ffffff; stroke-width: 3px; stroke-linejoin: round; }
    .type-band { fill: #f8fafc; }
    .type-band:nth-of-type(even) { fill: #ffffff; }
    .detail-empty { color: var(--muted); font-size: 13px; }
    .kv { display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 6px 10px; font-size: 13px; }
    .kv dt { color: var(--muted); }
    .kv dd { margin: 0; overflow-wrap: anywhere; }
    .pill-row { display: flex; flex-wrap: wrap; gap: 5px; }
    .pill {
      display: inline-flex;
      align-items: center;
      max-width: 100%;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 3px 7px;
      color: var(--ink);
      background: #fbfcfd;
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .quote {
      border-left: 3px solid var(--teal);
      background: #f8fbfb;
      padding: 8px 10px;
      color: var(--ink);
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .doc-list, .evidence-list { margin: 7px 0 0; padding-left: 18px; color: var(--ink); font-size: 12px; }
    .doc-list li, .evidence-list li { margin-bottom: 5px; overflow-wrap: anywhere; }
    .edge-card-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-top: 7px;
    }
    .edge-card {
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #ffffff;
      padding: 8px;
      font-size: 12px;
    }
    .edge-card-title {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 8px;
      font-weight: 700;
      color: var(--ink);
    }
    .edge-card-path {
      margin-top: 4px;
      color: var(--text);
      overflow-wrap: anywhere;
    }
    .edge-card-quote {
      margin-top: 6px;
      color: var(--muted);
      overflow-wrap: anywhere;
    }
    .insight-box {
      border: 1px solid #bfdbfe;
      background: #eff6ff;
      border-radius: 6px;
      padding: 10px;
      color: #1e3a8a;
      line-height: 1.45;
    }
    .caveat-box {
      border: 1px solid #fde68a;
      background: #fffbeb;
      border-radius: 6px;
      padding: 9px;
      color: #78350f;
      line-height: 1.45;
    }
    .mini-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }
    .mini-table th,
    .mini-table td {
      border-bottom: 1px solid var(--line);
      padding: 6px 4px;
      text-align: left;
      vertical-align: top;
    }
    .mini-table th {
      color: var(--muted);
      font-weight: 700;
    }
    .mini-table td:last-child,
    .mini-table th:last-child {
      text-align: right;
      white-space: nowrap;
    }
    .inline-action {
      border: 0;
      padding: 0;
      color: var(--blue);
      background: transparent;
      cursor: pointer;
      text-align: left;
      overflow-wrap: anywhere;
    }
    .inline-action:hover { text-decoration: underline; }
    .muted { color: var(--muted); }
    .warn { color: var(--amber); }
    .loading {
      display: flex;
      align-items: center;
      min-height: 100vh;
      padding: 28px;
      color: var(--muted);
      font-size: 15px;
    }
    .node-browser-controls {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 8px;
      margin-bottom: 10px;
    }
    .select-input {
      width: 100%;
      border: 1px solid var(--line-strong);
      border-radius: 6px;
      padding: 8px 9px;
      background: #ffffff;
      color: var(--text);
    }
    .node-list {
      display: flex;
      flex-direction: column;
      gap: 7px;
      max-height: 360px;
      overflow: auto;
      padding-right: 2px;
    }
    .node-list .list-row {
      padding: 8px;
    }
    .raw-json {
      max-height: 260px;
      overflow: auto;
      padding: 9px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
      color: #1f2937;
      font-size: 11px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    details summary {
      cursor: pointer;
      color: var(--ink);
      font-size: 12px;
      font-weight: 700;
      margin-top: 12px;
    }
    @media (max-width: 1180px) {
      .layout { grid-template-columns: 260px minmax(0, 1fr); }
      .right-col { grid-column: 1 / -1; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
      .metrics { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    }
    @media (max-width: 780px) {
      .app-header { flex-direction: column; }
      .header-note { text-align: left; max-width: none; }
      .layout { grid-template-columns: 1fr; }
      .right-col { display: flex; flex-direction: column; }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .graph-svg { height: 460px; }
      .edge-card-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="loading" id="loadingView">正在加载 EvoTaxa 演化数据...</div>
  <header class="app-header">
    <div>
      <h1>EvoTaxa 演化可视化</h1>
      <div class="meta" id="runMeta"></div>
    </div>
    <div class="header-note" id="headerNote"></div>
  </header>
  <main class="layout">
    <aside class="stack">
      <section class="panel">
        <div class="panel-header"><h2>筛选</h2><button class="small-button" id="resetButton" type="button">重置</button></div>
        <div class="panel-body">
          <div class="control-group">
            <label class="control-label" for="searchInput">搜索节点、轨迹或证据</label>
            <input class="search-input" id="searchInput" type="search" placeholder="method, big data, trajectory..." autocomplete="off">
          </div>
          <div class="control-group">
            <label class="control-label" for="confidenceInput">最小边置信度 <span id="confidenceValue"></span></label>
            <input class="range-input" id="confidenceInput" type="range" min="0" max="1" step="0.01" value="0">
          </div>
          <div class="control-group">
            <div class="control-label">节点类型</div>
            <div class="check-grid" id="entityTypeFilters"></div>
          </div>
          <div class="control-group">
            <div class="control-label">关系类型</div>
            <div class="check-grid" id="edgeTypeFilters"></div>
          </div>
        </div>
      </section>
      <section class="panel">
        <div class="panel-header"><h2>宏观模式</h2><span class="muted" id="patternCount"></span></div>
        <div class="panel-body">
          <div class="pattern-list" id="patternList"></div>
        </div>
      </section>
    </aside>
    <section class="stack">
      <section class="metrics" id="metrics"></section>
      <section class="panel">
        <div class="panel-header">
          <h2>时间分布</h2>
          <div class="legend">
            <span class="legend-item"><span class="swatch" style="background:#dbe4ee"></span>文献</span>
            <span class="legend-item"><span class="swatch" style="background:#0f766e"></span>实体首现</span>
            <span class="legend-item"><span class="swatch" style="background:#7c3aed"></span>严格演化边</span>
            <span class="legend-item"><span class="swatch" style="background:#b45309"></span>窗口开始</span>
          </div>
        </div>
        <svg class="chart-svg" id="yearChart" viewBox="0 0 960 230" role="img" aria-label="年度演化分布"></svg>
      </section>
      <section class="panel">
        <div class="panel-header">
          <h2>演化浏览器</h2>
          <div class="timeline-controls">
            <span class="time-window-label" id="timeWindowLabel"></span>
            <button class="small-button" id="zoomOutButton" type="button">Zoom out</button>
            <button class="small-button" id="zoomInButton" type="button">Zoom in</button>
          </div>
        </div>
        <div class="panel-body" style="padding-bottom:0">
          <div class="legend" id="edgeLegend"></div>
        </div>
        <div class="selection-bar" id="entityTypeSelectionBar"></div>
        <div class="graph-stage">
          <svg class="graph-svg" id="evolutionGraph" viewBox="0 0 980 570" role="img" aria-label="实体和演化关系图"></svg>
          <button class="graph-nav-button graph-nav-earlier" id="timeEarlierButton" type="button" title="更早窗口" aria-label="更早窗口">↑</button>
          <button class="graph-nav-button graph-nav-later" id="timeLaterButton" type="button" title="更新窗口" aria-label="更新窗口">↓</button>
        </div>
        <div class="panel-body graph-workbench">
          <div class="graph-workbench-header">
            <span>当前窗口演化边</span>
            <span class="muted" id="graphEdgeCardCount"></span>
          </div>
          <div class="edge-card-grid" id="graphEdgeCards"></div>
        </div>
      </section>
      <section class="panel">
        <div class="panel-header"><h2>代表轨迹</h2><span class="muted" id="trajectoryCount"></span></div>
        <div class="panel-body">
          <div class="trajectory-list" id="trajectoryList"></div>
        </div>
      </section>
    </section>
    <aside class="stack right-col">
      <section class="panel">
        <div class="panel-header"><h2>证据卡</h2><span class="muted" id="selectionLabel"></span></div>
        <div class="panel-body" id="detailsContent"></div>
      </section>
      <section class="panel">
        <div class="panel-header"><h2>节点卡片</h2><span class="muted" id="nodeBrowserCount"></span></div>
        <div class="panel-body">
          <div class="node-browser-controls">
            <input class="search-input" id="nodeSearchInput" type="search" placeholder="搜索节点名称、类型、taxonomy..." autocomplete="off">
            <select class="select-input" id="nodeTypeSelect"></select>
          </div>
          <div class="node-list" id="nodeBrowserList"></div>
          <div class="button-row" style="margin-top:10px">
            <button class="small-button" id="nodePrevButton" type="button">上一页</button>
            <button class="small-button" id="nodeNextButton" type="button">下一页</button>
          </div>
        </div>
      </section>
      <section class="panel">
        <div class="panel-header"><h2>动态窗口</h2><span class="muted" id="windowCount"></span></div>
        <div class="panel-body">
          <div class="window-list" id="windowList"></div>
        </div>
      </section>
    </aside>
  </main>
  <script>
    __DATA_BOOTSTRAP__
    let DATA = window.EVOTAXA_BOOTSTRAP_DATA || null;
    const PALETTE = ["#2563eb", "#0f766e", "#7c3aed", "#b45309", "#b91c1c", "#15803d", "#475569", "#db2777", "#0891b2", "#9333ea"];
    const state = {
      query: "",
      minConfidence: 0,
      entityTypes: new Set(),
      edgeTypes: new Set(),
      patternId: null,
      selected: null,
      nodeQuery: "",
      nodeType: "all",
      nodePage: 0,
      nodePageSize: 30,
      timeGranularityIndex: 1,
      timeWindowStart: null,
      graphEntityType: "all"
    };
    let entityById = new Map();
    let edgeById = new Map();
    let trajectoryById = new Map();
    let patternById = new Map();
    let edgeColor = new Map();
    let entityColor = new Map();
    let nodeBrowserRequest = 0;
    const TIME_GRANULARITIES = [
      { label: "1个月", months: 1 },
      { label: "1年", months: 12 },
      { label: "5年", months: 60 },
      { label: "全局", months: null }
    ];

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
    }
    function compact(value, max = 120) {
      const text = String(value ?? "");
      return text.length > max ? text.slice(0, max - 1) + "…" : text;
    }
    function pct(value) {
      const num = Number(value || 0);
      return Math.round(num * 100) + "%";
    }
    function score(value) {
      const num = Number(value || 0);
      return num ? num.toFixed(3).replace(/0+$/, "").replace(/\.$/, "") : "0";
    }
    function matches(text) {
      if (!state.query) return true;
      return String(text ?? "").toLowerCase().includes(state.query);
    }
    function selectedPattern() {
      return state.patternId ? patternById.get(state.patternId) : null;
    }
    function patternSets() {
      const pattern = selectedPattern();
      return {
        pattern,
        edges: new Set(pattern ? pattern.edge_ids : []),
        entities: new Set(pattern ? pattern.entity_ids : []),
        trajectories: new Set(pattern ? pattern.trajectory_ids : []),
        taxonomy: new Set(pattern ? pattern.representative_node_ids : [])
      };
    }
    function hashOffset(text, spread) {
      let h = 0;
      for (let i = 0; i < text.length; i += 1) h = (h * 31 + text.charCodeAt(i)) >>> 0;
      return ((h % 1000) / 999 - 0.5) * spread;
    }

    function initializeMaps() {
      state.entityTypes = new Set(DATA.entity_types);
      state.edgeTypes = new Set(DATA.edge_types);
      entityById = new Map(DATA.entities.map(row => [row.id, row]));
      edgeById = new Map(DATA.edges.map(row => [row.id, row]));
      trajectoryById = new Map(DATA.trajectories.map(row => [row.id, row]));
      patternById = new Map(DATA.patterns.map(row => [row.id, row]));
      edgeColor = new Map(DATA.edge_types.map((type, index) => [type, PALETTE[index % PALETTE.length]]));
      entityColor = new Map(DATA.entity_types.map((type, index) => [type, PALETTE[(index + 2) % PALETTE.length]]));
      state.graphEntityType = dominantGraphEntityType();
      state.timeWindowStart = defaultTimeWindowStart();
    }

    function dominantGraphEntityType() {
      const counts = new Map(DATA.entity_types.map(type => [type, 0]));
      for (const edge of DATA.edges) {
        const type = edge.source_schema_group || edge.schema_group || edge.target_schema_group || "";
        if (counts.has(type)) counts.set(type, counts.get(type) + 1);
      }
      const ranked = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
      return ranked.length && ranked[0][1] > 0 ? ranked[0][0] : (DATA.entity_types[0] || "all");
    }

    function monthIndexFromDate(value) {
      if (!value && value !== 0) return null;
      const text = String(value);
      const match = text.match(/(\d{4})(?:-(\d{1,2}))?/);
      if (!match) return null;
      const year = Number(match[1]);
      const month = match[2] ? Number(match[2]) : 1;
      if (!Number.isFinite(year) || year < 1500 || year > 2100) return null;
      return year * 12 + Math.max(1, Math.min(12, month)) - 1;
    }

    function dateLabel(monthIndex) {
      const year = Math.floor(monthIndex / 12);
      const month = monthIndex % 12 + 1;
      return `${year}-${String(month).padStart(2, "0")}`;
    }

    function dataMonthExtent() {
      const values = [];
      for (const edge of DATA.edges) {
        const value = monthIndexFromDate(edge.target_date || edge.target_year || edge.year);
        if (value !== null) values.push(value);
      }
      for (const node of DATA.entities) {
        const value = monthIndexFromDate(node.first_seen || node.year);
        if (value !== null) values.push(value);
      }
      if (!values.length) return { min: DATA.year_min * 12, max: DATA.year_max * 12 + 11 };
      return { min: Math.min(...values), max: Math.max(...values) };
    }

    function currentGranularity() {
      return TIME_GRANULARITIES[state.timeGranularityIndex] || TIME_GRANULARITIES[1];
    }

    function currentWindow() {
      const extent = dataMonthExtent();
      const granularity = currentGranularity();
      if (granularity.months === null) return { start: extent.min, end: extent.max + 1, label: "全局", granularity };
      let start = state.timeWindowStart;
      if (start === null || start === undefined) start = defaultTimeWindowStart();
      start = Math.max(extent.min, Math.min(extent.max, start));
      let end = start + granularity.months;
      if (end > extent.max + 1) {
        end = extent.max + 1;
        start = Math.max(extent.min, end - granularity.months);
      }
      return { start, end, label: `${dateLabel(start)} 至 ${dateLabel(Math.max(start, end - 1))}`, granularity };
    }

    function defaultTimeWindowStart() {
      const granularity = TIME_GRANULARITIES[1];
      const edgeMonths = DATA.edges
        .filter(edge => {
          if (!isEvolutionEdge(edge)) return false;
          if (state.graphEntityType === "all") return true;
          const sourceType = (entityById.get(edge.source) || {}).type;
          const targetType = (entityById.get(edge.target) || {}).type;
          return sourceType === state.graphEntityType || targetType === state.graphEntityType;
        })
        .map(edge => graphTimeMonthForEdge(edge))
        .filter(month => month !== null)
        .sort((a, b) => a - b);
      if (edgeMonths.length) return Math.floor(edgeMonths[0] / granularity.months) * granularity.months;
      const extent = dataMonthExtent();
      return Math.floor(extent.min / granularity.months) * granularity.months;
    }

    function edgeSourceType(edge) {
      return edge.source_schema_group || (entityById.get(edge.source) || {}).type || "";
    }

    function edgeTargetType(edge) {
      return edge.target_schema_group || (entityById.get(edge.target) || {}).type || "";
    }

    function edgeTemporalDelta(edge) {
      const value = Number(edge.time_delta_days);
      return Number.isFinite(value) ? value : null;
    }

    function isEvolutionEdge(edge) {
      const sourceType = edgeSourceType(edge);
      const targetType = edgeTargetType(edge);
      const delta = edgeTemporalDelta(edge);
      return Boolean(sourceType && targetType && sourceType === targetType && delta !== null && delta > 0);
    }

    function shiftTimeWindow(direction) {
      const granularity = currentGranularity();
      if (granularity.months === null) return;
      const extent = dataMonthExtent();
      const current = currentWindow();
      const step = timeWindowStepMonths(granularity);
      const next = current.start + direction * step;
      const maxStart = Math.max(extent.min, extent.max + 1 - granularity.months);
      state.timeWindowStart = Math.max(extent.min, Math.min(maxStart, next));
      renderGraph();
    }

    function timeWindowStepMonths(granularity) {
      if (!granularity || granularity.months === null) return 1;
      if (granularity.months <= 12) return 1;
      if (granularity.months <= 60) return 3;
      return 12;
    }

    function changeZoom(direction) {
      const oldWindow = currentWindow();
      const oldCenter = (oldWindow.start + oldWindow.end) / 2;
      state.timeGranularityIndex = Math.max(0, Math.min(TIME_GRANULARITIES.length - 1, state.timeGranularityIndex + direction));
      const granularity = currentGranularity();
      if (granularity.months === null) {
        renderGraph();
        return;
      }
      const extent = dataMonthExtent();
      const maxStart = Math.max(extent.min, extent.max + 1 - granularity.months);
      state.timeWindowStart = Math.max(extent.min, Math.min(maxStart, Math.round(oldCenter - granularity.months / 2)));
      renderGraph();
    }

    async function boot() {
      if (!DATA && window.EVOTAXA_DATA_API) {
        const response = await fetch(window.EVOTAXA_DATA_API);
        if (!response.ok) throw new Error(`API ${response.status}`);
        DATA = await response.json();
      }
      if (!DATA) throw new Error("No EvoTaxa data available.");
      initializeMaps();
      document.getElementById("loadingView").style.display = "none";
      init();
    }

    function init() {
      document.getElementById("runMeta").textContent = `${DATA.summary.project_name} · ${DATA.summary.run_id}`;
      const edgeSource = DATA.summary.edge_source || "unknown edge source";
      document.getElementById("headerNote").textContent = `${DATA.summary.date_start || "未知"} 至 ${DATA.summary.date_end || "未知"} · 边源 ${edgeSource} · 未判定前身的节点不强制连边 · ${DATA.run_root}`;
      renderMetrics();
      renderFilters();
      renderPatterns();
      renderYearChart();
      renderEdgeLegend();
      renderEntityTypeSelectionBar();
      renderGraph();
      renderTrajectories();
      void renderNodeBrowser();
      renderWindows();
      renderDetails();
      bindControls();
    }

    function bindControls() {
      document.getElementById("searchInput").addEventListener("input", event => {
        state.query = event.target.value.trim().toLowerCase();
        renderGraph();
        renderTrajectories();
        renderWindows();
      });
      document.getElementById("confidenceInput").addEventListener("input", event => {
        state.minConfidence = Number(event.target.value);
        document.getElementById("confidenceValue").textContent = score(state.minConfidence);
        renderGraph();
      });
      document.getElementById("timeEarlierButton").addEventListener("click", () => shiftTimeWindow(-1));
      document.getElementById("timeLaterButton").addEventListener("click", () => shiftTimeWindow(1));
      document.getElementById("zoomInButton").addEventListener("click", () => changeZoom(-1));
      document.getElementById("zoomOutButton").addEventListener("click", () => changeZoom(1));
      document.getElementById("resetButton").addEventListener("click", () => {
        state.query = "";
        state.minConfidence = 0;
        state.entityTypes = new Set(DATA.entity_types);
        state.edgeTypes = new Set(DATA.edge_types);
        state.patternId = null;
        state.selected = null;
        state.nodeQuery = "";
        state.nodeType = "all";
        state.nodePage = 0;
        state.timeGranularityIndex = 1;
        state.graphEntityType = dominantGraphEntityType();
        state.timeWindowStart = defaultTimeWindowStart();
        document.getElementById("searchInput").value = "";
        document.getElementById("nodeSearchInput").value = "";
        document.getElementById("nodeTypeSelect").value = "all";
        document.getElementById("confidenceInput").value = "0";
        document.getElementById("confidenceValue").textContent = "0";
        renderFilters();
        renderPatterns();
        renderEntityTypeSelectionBar();
        renderGraph();
        renderTrajectories();
        void renderNodeBrowser();
        renderWindows();
        renderDetails();
      });
      document.getElementById("nodeSearchInput").addEventListener("input", event => {
        state.nodeQuery = event.target.value.trim().toLowerCase();
        state.nodePage = 0;
        void renderNodeBrowser();
      });
      document.getElementById("nodeTypeSelect").addEventListener("change", event => {
        state.nodeType = event.target.value;
        state.nodePage = 0;
        void renderNodeBrowser();
      });
      document.getElementById("nodePrevButton").addEventListener("click", () => {
        state.nodePage = Math.max(0, state.nodePage - 1);
        void renderNodeBrowser();
      });
      document.getElementById("nodeNextButton").addEventListener("click", () => {
        state.nodePage += 1;
        void renderNodeBrowser();
      });
      document.getElementById("detailsContent").addEventListener("click", event => {
        const button = event.target.closest("[data-select-kind]");
        if (!button) return;
        selectItem(button.getAttribute("data-select-kind"), button.getAttribute("data-select-id"));
      });
      document.getElementById("graphEdgeCards").addEventListener("click", event => {
        const button = event.target.closest("[data-select-kind]");
        if (!button) return;
        selectItem(button.getAttribute("data-select-kind"), button.getAttribute("data-select-id"));
      });
    }

    function renderMetrics() {
      const rows = [
        ["文献", DATA.summary.documents],
        ["实体卡", DATA.summary.entities],
        ["演化边", DATA.summary.strict_evolution_edges ?? DATA.summary.embedded_edges],
        ["有前身节点", DATA.summary.entities_with_accepted_predecessor ?? "n/a"],
        ["未连节点", DATA.summary.entities_without_accepted_predecessor ?? "n/a"],
        ["轨迹", DATA.summary.trajectories],
        ["宏观模式", DATA.summary.macro_patterns],
        ["质量分", DATA.summary.quality_score == null ? "n/a" : score(DATA.summary.quality_score)]
      ];
      document.getElementById("metrics").innerHTML = rows.map(([label, value]) => `
        <div class="metric"><div class="metric-value">${escapeHtml(value)}</div><div class="metric-label">${escapeHtml(label)}</div></div>
      `).join("");
    }

    function renderFilters() {
      document.getElementById("confidenceValue").textContent = score(state.minConfidence);
      document.getElementById("entityTypeFilters").innerHTML = DATA.entity_types.map(type => checkboxHtml("entity", type, state.entityTypes.has(type))).join("");
      document.getElementById("edgeTypeFilters").innerHTML = DATA.edge_types.map(type => checkboxHtml("edge", type, state.edgeTypes.has(type))).join("");
      document.querySelectorAll("[data-filter-kind]").forEach(input => {
        input.addEventListener("change", event => {
          const kind = event.target.getAttribute("data-filter-kind");
          const value = event.target.getAttribute("data-filter-value");
          const targetSet = kind === "entity" ? state.entityTypes : state.edgeTypes;
          if (event.target.checked) targetSet.add(value);
          else targetSet.delete(value);
          renderGraph();
          renderTrajectories();
        });
      });
    }
    function checkboxHtml(kind, value, checked) {
      const label = kind === "edge" ? (DATA.relation_labels[value] || value) : (DATA.entity_type_labels[value] || value);
      return `<label class="check-row"><input type="checkbox" data-filter-kind="${kind}" data-filter-value="${escapeHtml(value)}" ${checked ? "checked" : ""}><span>${escapeHtml(label)}</span></label>`;
    }

    function renderPatterns() {
      document.getElementById("patternCount").textContent = `${DATA.patterns.length} 个`;
      document.getElementById("patternList").innerHTML = DATA.patterns.map(pattern => {
        const active = state.patternId === pattern.id ? " active" : "";
        return `<button class="list-row${active}" type="button" data-pattern-id="${escapeHtml(pattern.id)}">
          <div class="row-title"><span>${escapeHtml(pattern.label)}</span><span>${score(pattern.score)}</span></div>
          <div class="row-sub">${escapeHtml(compact(pattern.insight || pattern.explanation || pattern.definition, 150))}</div>
          <div class="scorebar"><span style="width:${pct(pattern.score)}"></span></div>
        </button>`;
      }).join("");
      document.querySelectorAll("[data-pattern-id]").forEach(button => {
        button.addEventListener("click", () => {
          const id = button.getAttribute("data-pattern-id");
          state.patternId = state.patternId === id ? null : id;
          state.selected = state.patternId ? { kind: "pattern", id: state.patternId } : null;
          renderPatterns();
          renderGraph();
          renderTrajectories();
          renderWindows();
          renderDetails();
        });
      });
    }

    function renderYearChart() {
      const svg = document.getElementById("yearChart");
      const rows = DATA.years;
      if (!rows.length) {
        svg.innerHTML = `<text x="30" y="40" class="axis-label">没有可用时间数据</text>`;
        return;
      }
      const width = 960, height = 230, left = 46, right = 18, top = 16, bottom = 38;
      const innerW = width - left - right, innerH = height - top - bottom;
      const minYear = rows[0].year, maxYear = rows[rows.length - 1].year;
      const maxDocs = Math.max(1, ...rows.map(row => row.documents));
      const maxSignals = Math.max(1, ...rows.map(row => Math.max(row.entity_first_seen, row.trusted_edges, row.windows_started)));
      const step = innerW / rows.length;
      const bars = rows.map((row, index) => {
        const barH = row.documents / maxDocs * innerH;
        const x = left + index * step + 1;
        const y = top + innerH - barH;
        return `<rect class="year-bar" x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${Math.max(1, step - 2).toFixed(2)}" height="${barH.toFixed(2)}"><title>${row.year}: ${row.documents} 篇</title></rect>`;
      }).join("");
      function line(metric, color) {
        const points = rows.map((row, index) => {
          const x = left + index * step + step / 2;
          const y = top + innerH - (row[metric] / maxSignals * innerH);
          return `${x.toFixed(1)},${y.toFixed(1)}`;
        }).join(" ");
        const dots = rows.filter(row => row[metric] > 0).map(row => {
          const index = row.year - minYear;
          const x = left + index * step + step / 2;
          const y = top + innerH - (row[metric] / maxSignals * innerH);
          return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.2" fill="${color}"><title>${row.year}: ${row[metric]}</title></circle>`;
        }).join("");
        return `<polyline points="${points}" fill="none" stroke="${color}" stroke-width="2"/>${dots}`;
      }
      const ticks = [];
      const tickEvery = Math.max(1, Math.ceil((maxYear - minYear + 1) / 8));
      for (let year = minYear; year <= maxYear; year += tickEvery) {
        const index = year - minYear;
        const x = left + index * step + step / 2;
        ticks.push(`<line class="axis-line" x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${top}" y2="${top + innerH}"/>`);
        ticks.push(`<text class="axis-label" x="${x.toFixed(1)}" y="${height - 13}" text-anchor="middle">${year}</text>`);
      }
      svg.innerHTML = `
        <rect x="0" y="0" width="${width}" height="${height}" fill="#ffffff"/>
        <line class="axis-line" x1="${left}" x2="${width - right}" y1="${top + innerH}" y2="${top + innerH}"/>
        ${ticks.join("")}
        ${bars}
        ${line("entity_first_seen", "#0f766e")}
        ${line("trusted_edges", "#7c3aed")}
        ${line("windows_started", "#b45309")}
        <text class="axis-label" x="${left}" y="13">文献量为柱，其他信号为线</text>
      `;
    }

    function renderEdgeLegend() {
      document.getElementById("edgeLegend").innerHTML = DATA.edge_types.map(type => {
        const label = DATA.relation_labels[type] || type;
        return `<span class="legend-item"><span class="swatch" style="background:${edgeColor.get(type)}"></span>${escapeHtml(label)}</span>`;
      }).join("");
    }

    function renderEntityTypeSelectionBar() {
      const options = ["all", ...DATA.entity_types];
      document.getElementById("entityTypeSelectionBar").innerHTML = options.map(type => {
        const active = state.graphEntityType === type ? " active" : "";
        const label = type === "all" ? "全部" : (DATA.entity_type_labels[type] || type);
        return `<button class="seg-button${active}" type="button" data-graph-entity-type="${escapeHtml(type)}">${escapeHtml(label)}</button>`;
      }).join("");
      document.querySelectorAll("[data-graph-entity-type]").forEach(button => {
        button.addEventListener("click", () => {
          state.graphEntityType = button.getAttribute("data-graph-entity-type");
          state.timeWindowStart = defaultTimeWindowStart();
          renderEntityTypeSelectionBar();
          renderGraph();
        });
      });
    }

    function graphTimeMonthForEdge(edge) {
      return monthIndexFromDate(edge.target_date || edge.target_year || edge.year || edge.source_date || edge.source_year);
    }

    function graphTimeMonthForNode(node) {
      return monthIndexFromDate(node.first_seen || node.year);
    }

    function visibleGraphData() {
      const baseNodes = DATA.entities.filter(node => {
        if (!state.entityTypes.has(node.type)) return false;
        const text = [node.name, node.id, node.type, node.taxonomy_labels.join(" ")].join(" ").toLowerCase();
        return matches(text);
      });
      const baseNodeSet = new Set(baseNodes.map(node => node.id));
      const baseEdges = DATA.edges.filter(edge => {
        if (!isEvolutionEdge(edge)) return false;
        if (!state.edgeTypes.has(edge.type)) return false;
        if (edge.confidence < state.minConfidence) return false;
        if (!baseNodeSet.has(edge.source) || !baseNodeSet.has(edge.target)) return false;
        if (state.graphEntityType !== "all") {
          const sourceType = edgeSourceType(edge);
          const targetType = edgeTargetType(edge);
          if (sourceType !== state.graphEntityType && targetType !== state.graphEntityType) return false;
        }
        const text = [edge.id, edge.type, edge.source_title, edge.target_title, edge.quote, edge.taxonomy_labels.join(" ")].join(" ").toLowerCase();
        return matches(text) || matches((entityById.get(edge.source) || {}).name) || matches((entityById.get(edge.target) || {}).name);
      });
      const windowInfo = currentWindow();
      const selected = state.selected;
      const psets = patternSets();
      const byScore = (a, b) => edgeDisplayScore(b) - edgeDisplayScore(a);
      const nodeByScore = (a, b) => nodeDisplayScore(b) - nodeDisplayScore(a);
      const timeFilteredEdges = baseEdges.filter(edge => {
        const targetMonth = graphTimeMonthForEdge(edge);
        const sourceMonth = graphTimeMonthForNode(entityById.get(edge.source) || {});
        const targetInWindow = targetMonth !== null && targetMonth >= windowInfo.start && targetMonth < windowInfo.end;
        const sourceInWindow = sourceMonth !== null && sourceMonth >= windowInfo.start && sourceMonth < windowInfo.end;
        const targetAfterWindow = targetMonth !== null && targetMonth >= windowInfo.end;
        const targetBeforeWindow = targetMonth !== null && targetMonth < windowInfo.start;
        if (targetInWindow) return true;
        if (sourceInWindow && targetAfterWindow) return true;
        if (selected && selected.kind === "entity" && (edge.source === selected.id || edge.target === selected.id)) {
          return targetInWindow || sourceInWindow || targetBeforeWindow || targetAfterWindow;
        }
        return false;
      });
      const edgeEvidenceWindowCount = timeFilteredEdges.length;
      const timeFilteredNodeIds = new Set();
      for (const edge of timeFilteredEdges) {
        timeFilteredNodeIds.add(edge.source);
        timeFilteredNodeIds.add(edge.target);
      }
      for (const node of baseNodes) {
        const month = graphTimeMonthForNode(node);
        if (month !== null && month >= windowInfo.start && month < windowInfo.end) timeFilteredNodeIds.add(node.id);
      }
      let edges = [];
      let nodeIds = new Set();
      let mode = "概览";
      let note = "只显示有证据的 successor/predecessor 演化边；同题、共现或新概念首现不强制连边。";

      if (selected && selected.kind === "entity" && baseNodeSet.has(selected.id)) {
        mode = "节点邻域";
        edges = timeFilteredEdges.filter(edge => edge.source === selected.id || edge.target === selected.id).sort(byScore).slice(0, 32);
        nodeIds.add(selected.id);
        for (const edge of edges) {
          nodeIds.add(edge.source);
          nodeIds.add(edge.target);
        }
        note = "显示当前节点在时间切片内的一阶演化邻域。";
      } else if (selected && selected.kind === "edge" && edgeById.has(selected.id)) {
        mode = "关系上下文";
        const focus = edgeById.get(selected.id);
        nodeIds.add(focus.source);
        nodeIds.add(focus.target);
        edges = timeFilteredEdges.filter(edge => edge.id === selected.id || edge.source === focus.source || edge.target === focus.source || edge.source === focus.target || edge.target === focus.target).sort(byScore).slice(0, 30);
        if (!edges.some(edge => edge.id === focus.id)) edges.unshift(focus);
        for (const edge of edges) {
          nodeIds.add(edge.source);
          nodeIds.add(edge.target);
        }
        note = "显示选中关系及其两端节点在时间切片内的局部上下文。";
      } else if (selected && selected.kind === "trajectory" && trajectoryById.has(selected.id)) {
        mode = "轨迹路径";
        const trajectory = trajectoryById.get(selected.id);
        const edgeSet = new Set(trajectory.edge_path || []);
        edges = baseEdges.filter(edge => edgeSet.has(edge.id)).sort(byScore);
        for (const entityId of trajectory.entity_path || []) nodeIds.add(entityId);
        for (const edge of edges) {
          nodeIds.add(edge.source);
          nodeIds.add(edge.target);
        }
        note = "轨迹路径跨时间显示，作为选中对象的上下文。";
      } else if (psets.pattern) {
        mode = "模式子图";
        edges = timeFilteredEdges.filter(edge => psets.edges.has(edge.id)).sort(byScore).slice(0, 32);
        for (const edge of edges) {
          nodeIds.add(edge.source);
          nodeIds.add(edge.target);
        }
        for (const entityId of psets.entities) {
          if (timeFilteredNodeIds.has(entityId)) nodeIds.add(entityId);
        }
        if (!edges.length) {
          const taxonomyNodes = psets.taxonomy;
          for (const node of baseNodes.filter(node => timeFilteredNodeIds.has(node.id)).sort(nodeByScore)) {
            if (nodeIds.size >= 42) break;
            if ((node.taxonomy_nodes || []).some(nodeId => taxonomyNodes.has(nodeId))) nodeIds.add(node.id);
          }
        }
        note = "显示当前宏观模式在时间切片内绑定的代表性微观证据。";
      } else if (state.query) {
        mode = "搜索子图";
        const queryNodes = baseNodes.filter(node => timeFilteredNodeIds.has(node.id)).sort(nodeByScore).slice(0, 48);
        nodeIds = new Set(queryNodes.map(node => node.id));
        edges = timeFilteredEdges.filter(edge => nodeIds.has(edge.source) && nodeIds.has(edge.target)).sort(byScore).slice(0, 32);
        for (const edge of edges) {
          nodeIds.add(edge.source);
          nodeIds.add(edge.target);
        }
        note = "显示时间切片内搜索命中的节点及其高证据关系。";
      } else {
        edges = timeFilteredEdges.sort(byScore).slice(0, 24);
        for (const edge of edges) {
          nodeIds.add(edge.source);
          nodeIds.add(edge.target);
        }
        if (!edges.length) {
          for (const node of baseNodes.filter(node => timeFilteredNodeIds.has(node.id)).sort(nodeByScore).slice(0, 40)) nodeIds.add(node.id);
        }
      }

      let nodes = baseNodes.filter(node => nodeIds.has(node.id)).sort(nodeByScore);
      if (nodes.length > 56) {
        const kept = new Set(nodes.slice(0, 56).map(node => node.id));
        edges = edges.filter(edge => kept.has(edge.source) && kept.has(edge.target));
        nodes = nodes.filter(node => kept.has(node.id));
      }
      return { nodes, edges, mode, note, totalNodes: timeFilteredNodeIds.size, totalEdges: timeFilteredEdges.length, windowInfo, edgeEvidenceWindowCount };
    }

    function edgeDisplayScore(edge) {
      const source = entityById.get(edge.source) || {};
      const target = entityById.get(edge.target) || {};
      return Number(edge.confidence || 0) * 100 + Number(source.degree || 0) * 2 + Number(target.degree || 0) * 2 + (edge.quote ? 6 : 0);
    }

    function nodeDisplayScore(node) {
      return Number(node.degree || 0) * 20 + Math.log1p(Number(node.support_count || 0)) * 6 + Number(node.year || 0) / 10000;
    }

    function graphComponents(nodes, edges) {
      const ids = new Set(nodes.map(node => node.id));
      const adjacency = new Map(nodes.map(node => [node.id, new Set()]));
      for (const edge of edges) {
        if (!ids.has(edge.source) || !ids.has(edge.target)) continue;
        adjacency.get(edge.source).add(edge.target);
        adjacency.get(edge.target).add(edge.source);
      }
      const visited = new Set();
      const components = [];
      for (const node of nodes) {
        if (visited.has(node.id)) continue;
        const queue = [node.id];
        const component = [];
        visited.add(node.id);
        while (queue.length) {
          const id = queue.shift();
          component.push(id);
          for (const next of adjacency.get(id) || []) {
            if (visited.has(next)) continue;
            visited.add(next);
            queue.push(next);
          }
        }
        components.push(component);
      }
      const edgeCountByComponent = component => edges.filter(edge => component.includes(edge.source) && component.includes(edge.target)).length;
      components.sort((a, b) => edgeCountByComponent(b) - edgeCountByComponent(a) || b.length - a.length || a[0].localeCompare(b[0]));
      return components;
    }

    function renderGraph() {
      const svg = document.getElementById("evolutionGraph");
      const { nodes, edges, mode, note, totalNodes, totalEdges, windowInfo, edgeEvidenceWindowCount } = visibleGraphData();
      const width = 980, height = 570, left = 132, right = 26, top = 34, bottom = 40;
      const innerW = width - left - right, innerH = height - top - bottom;
      const psets = patternSets();
      const selected = state.selected;
      const nodePositions = new Map();
      const granularity = windowInfo.granularity;
      const stepMonths = timeWindowStepMonths(granularity);
      document.getElementById("timeWindowLabel").textContent = granularity.months === null
        ? `${granularity.label} · ${windowInfo.label}`
        : `${granularity.label} · ${windowInfo.label} · 步长${stepMonths}个月`;
      const extent = dataMonthExtent();
      const maxWindowStart = granularity.months === null ? extent.min : Math.max(extent.min, extent.max + 1 - granularity.months);
      document.getElementById("timeEarlierButton").disabled = granularity.months === null || windowInfo.start <= extent.min;
      document.getElementById("timeLaterButton").disabled = granularity.months === null || windowInfo.start >= maxWindowStart;
      document.getElementById("zoomInButton").disabled = state.timeGranularityIndex <= 0;
      document.getElementById("zoomOutButton").disabled = state.timeGranularityIndex >= TIME_GRANULARITIES.length - 1;
      const allComponentIds = graphComponents(nodes, edges);
      let componentIds = allComponentIds.slice(0, 8);
      if (allComponentIds.length > 8) {
        componentIds = allComponentIds.slice(0, 7);
        componentIds.push(allComponentIds.slice(7).flat());
      }
      const componentByNode = new Map();
      componentIds.forEach((component, index) => component.forEach(id => componentByNode.set(id, index)));
      const componentCount = Math.max(1, componentIds.length || 1);
      const laneW = innerW / componentCount;
      function yFromMonth(month) {
        if (month === null || month === undefined) return top + innerH / 2;
        if (windowInfo.end <= windowInfo.start + 1) return top + innerH / 2;
        return top + (Math.max(windowInfo.start, Math.min(windowInfo.end - 1, month)) - windowInfo.start) / Math.max(1, windowInfo.end - windowInfo.start - 1) * innerH;
      }
      const groupSlots = new Map();
      const groupInfo = new Map();
      for (const node of nodes) {
        const key = `${node.type}|${graphTimeMonthForNode(node) ?? "unknown"}`;
        if (!groupSlots.has(key)) groupSlots.set(key, []);
        groupSlots.get(key).push(node);
      }
      for (const group of groupSlots.values()) {
        group.sort((a, b) => nodeDisplayScore(b) - nodeDisplayScore(a));
        group.forEach((node, index) => groupInfo.set(node.id, { index, count: group.length }));
      }
      function yFor(node) {
        const base = yFromMonth(graphTimeMonthForNode(node));
        const info = groupInfo.get(node.id) || { index: 0, count: 1 };
        if (info.count <= 1) return base + hashOffset(node.id, 8);
        const step = Math.min(11, 52 / Math.max(1, info.count - 1));
        const offset = (info.index - (info.count - 1) / 2) * step;
        return Math.max(top + 6, Math.min(top + innerH - 6, base + offset));
      }
      function xFor(node) {
        const idx = componentByNode.has(node.id) ? componentByNode.get(node.id) : componentCount - 1;
        const center = left + idx * laneW + laneW / 2;
        const component = componentIds[idx] || [node.id];
        const ordered = [...component].sort((a, b) => {
          const an = entityById.get(a) || {};
          const bn = entityById.get(b) || {};
          return (graphTimeMonthForNode(an) || 0) - (graphTimeMonthForNode(bn) || 0) || a.localeCompare(b);
        });
        const localIndex = Math.max(0, ordered.indexOf(node.id));
        const localCount = Math.max(1, ordered.length);
        const spread = Math.min(laneW * 0.42, Math.max(16, localCount * 7));
        const centered = localCount <= 1 ? 0 : (localIndex - (localCount - 1) / 2) / Math.max(1, localCount - 1) * spread;
        return center + centered + hashOffset(node.id, Math.min(8, laneW * 0.08));
      }
      for (const node of nodes) {
        nodePositions.set(node.id, { x: xFor(node), y: yFor(node) });
      }
      const bands = Array.from({ length: componentCount }).map((_value, index) => {
        const x = left + index * laneW;
        const component = componentIds[index] || [];
        const edgeCount = edges.filter(edge => component.includes(edge.source) && component.includes(edge.target)).length;
        const label = component.length
          ? `${index === 7 && allComponentIds.length > 8 ? "其他链" : "链 " + (index + 1)} · ${component.length} 节点/${edgeCount} 边`
          : "当前窗口";
        return `<rect class="type-band" x="${x.toFixed(1)}" y="${top}" width="${laneW.toFixed(1)}" height="${innerH}"></rect>
          <text class="axis-label" x="${(x + laneW / 2).toFixed(1)}" y="${height - 16}" text-anchor="middle">${escapeHtml(label)}</text>`;
      }).join("");
      const timeTicks = [];
      const tickCount = granularity.months === null ? 8 : Math.min(8, Math.max(2, Math.ceil((windowInfo.end - windowInfo.start) / 3)));
      const tickStep = Math.max(1, Math.ceil((windowInfo.end - windowInfo.start) / tickCount));
      for (let month = windowInfo.start; month < windowInfo.end; month += tickStep) {
        const y = yFromMonth(month);
        timeTicks.push(`<line class="axis-line" x1="${left}" x2="${width - right}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}"></line>`);
        timeTicks.push(`<text class="axis-label" x="${left - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end">${escapeHtml(dateLabel(month))}</text>`);
      }
      const edgePaths = edges.map(edge => {
        const source = nodePositions.get(edge.source);
        const target = nodePositions.get(edge.target);
        if (!source || !target) return "";
        const midY = (source.y + target.y) / 2;
        const path = `M ${source.x.toFixed(1)} ${source.y.toFixed(1)} C ${source.x.toFixed(1)} ${midY.toFixed(1)}, ${target.x.toFixed(1)} ${midY.toFixed(1)}, ${target.x.toFixed(1)} ${target.y.toFixed(1)}`;
        const hit = psets.edges.has(edge.id);
        const dim = psets.pattern && !hit ? " dimmed" : "";
        const selectedClass = selected && selected.kind === "edge" && selected.id === edge.id ? " selected" : "";
        return `<defs><marker id="arrow-${escapeHtml(edge.id)}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="${edgeColor.get(edge.type) || "#475569"}"></path></marker></defs>
          <path class="edge-hit" d="${path}" data-edge="${escapeHtml(edge.id)}"></path>
          <path class="edge${hit ? " pattern-hit" : ""}${dim}${selectedClass}" d="${path}" stroke="${edgeColor.get(edge.type) || "#475569"}" marker-end="url(#arrow-${escapeHtml(edge.id)})"></path>`;
      }).join("");
      const labelLimit = state.selected || psets.pattern ? 20 : 12;
      const topLabels = new Set([...nodes].sort((a, b) => nodeDisplayScore(b) - nodeDisplayScore(a)).slice(0, labelLimit).map(node => node.id));
      if (state.selected && state.selected.kind === "entity") topLabels.add(state.selected.id);
      const nodeEls = nodes.map(node => {
        const pos = nodePositions.get(node.id);
        if (!pos) return "";
        const hit = psets.entities.has(node.id) || (psets.pattern && node.taxonomy_nodes.some(id => psets.taxonomy.has(id)));
        const dim = psets.pattern && !hit ? " dimmed" : "";
        const selectedClass = selected && selected.kind === "entity" && selected.id === node.id ? " selected" : "";
        const r = Math.max(5, Math.min(13, 4 + Math.log1p(node.support_count) + node.degree));
        const label = topLabels.has(node.id) || selectedClass ? `<text class="node-label${dim}" x="${(pos.x + r + 3).toFixed(1)}" y="${(pos.y + 4).toFixed(1)}">${escapeHtml(compact(node.name, 26))}</text>` : "";
        return `<circle class="node${hit ? " pattern-hit" : ""}${dim}${selectedClass}" cx="${pos.x.toFixed(1)}" cy="${pos.y.toFixed(1)}" r="${r.toFixed(1)}" fill="${entityColor.get(node.type) || "#475569"}" data-node="${escapeHtml(node.id)}"><title>${escapeHtml(node.name)}</title></circle>${label}`;
      }).join("");
      const emptyMessage = edgeEvidenceWindowCount === 0
        ? `<text x="${(left + innerW / 2).toFixed(1)}" y="${(top + innerH / 2).toFixed(1)}" text-anchor="middle" class="axis-label">当前时间片没有已接受演化边：可能尚未抽取、证据不足，或这些节点是新概念首现。</text>`
        : "";
      svg.innerHTML = `
        <rect x="0" y="0" width="${width}" height="${height}" fill="#ffffff"></rect>
        ${bands}
        ${timeTicks.join("")}
        <line class="axis-line" x1="${left}" x2="${left}" y1="${top}" y2="${top + innerH}"></line>
        ${edgePaths}
        ${nodeEls}
        ${emptyMessage}
        <text class="axis-label" x="${left}" y="18">${escapeHtml(mode)}：${escapeHtml(windowInfo.label)}，显示 ${nodes.length}/${totalNodes} 个节点 · ${edges.length}/${totalEdges} 条演化边。${escapeHtml(note)}</text>
      `;
      svg.querySelectorAll("[data-node]").forEach(el => {
        el.addEventListener("click", event => {
          event.stopPropagation();
          selectItem("entity", el.getAttribute("data-node"));
        });
      });
      svg.querySelectorAll("[data-edge]").forEach(el => {
        el.addEventListener("click", event => {
          event.stopPropagation();
          selectItem("edge", el.getAttribute("data-edge"));
        });
      });
      svg.onclick = () => {
        state.selected = state.patternId ? { kind: "pattern", id: state.patternId } : null;
        renderGraph();
        renderDetails();
      };
      renderGraphEdgeCards(edges, totalEdges, windowInfo);
    }

    function renderGraphEdgeCards(edges, totalEdges, windowInfo) {
      const target = document.getElementById("graphEdgeCards");
      const count = document.getElementById("graphEdgeCardCount");
      if (!target || !count) return;
      count.textContent = `${edges.length} / ${totalEdges} · ${windowInfo.label}`;
      target.innerHTML = edges.map(edgeCardHtml).join("") || `<div class="detail-empty">当前切片没有可展示的严格演化边。</div>`;
    }

    function renderTrajectories() {
      const psets = patternSets();
      const visibleEdges = new Set(visibleGraphData().edges.map(edge => edge.id));
      let rows = DATA.trajectories.filter(row => {
        if (state.graphEntityType !== "all") {
          const hasSelectedGroup = (row.edge_path || []).some(edgeId => {
            const edge = edgeById.get(edgeId) || {};
            return edgeSourceType(edge) === state.graphEntityType || edgeTargetType(edge) === state.graphEntityType;
          });
          if (!hasSelectedGroup) return false;
        }
        if (visibleEdges.size && !(row.edge_path || []).some(edgeId => visibleEdges.has(edgeId))) return false;
        const text = [row.id, row.entity_labels.join(" "), row.edge_path.join(" "), row.taxonomy_labels.join(" ")].join(" ").toLowerCase();
        return matches(text);
      });
      rows.sort((a, b) => {
        const ap = psets.trajectories.has(a.id) ? 1 : 0;
        const bp = psets.trajectories.has(b.id) ? 1 : 0;
        return bp - ap || b.score - a.score;
      });
      rows = rows.slice(0, 80);
      document.getElementById("trajectoryCount").textContent = `${rows.length} / ${DATA.trajectories.length}`;
      document.getElementById("trajectoryList").innerHTML = rows.map(row => {
        const active = state.selected && state.selected.kind === "trajectory" && state.selected.id === row.id ? " active" : "";
        const dim = psets.pattern && !psets.trajectories.has(row.id) ? " dimmed" : "";
        return `<button class="list-row${active}${dim}" type="button" data-trajectory-id="${escapeHtml(row.id)}">
          <div class="row-title"><span>${escapeHtml(row.id)}</span><span>${score(row.score)}</span></div>
          <div class="row-sub">${escapeHtml(compact(row.entity_labels.join(" → "), 150))}</div>
        </button>`;
      }).join("");
      document.querySelectorAll("[data-trajectory-id]").forEach(button => {
        button.addEventListener("click", () => selectItem("trajectory", button.getAttribute("data-trajectory-id")));
      });
    }

    function filteredNodesForBrowser() {
      const query = state.nodeQuery;
      return DATA.entities.filter(node => {
        if (state.nodeType !== "all" && node.type !== state.nodeType) return false;
        if (!query) return true;
        const text = [
          node.id,
          node.name,
          node.type,
          node.aliases.join(" "),
          node.taxonomy_labels.join(" "),
          node.support_documents.join(" ")
        ].join(" ").toLowerCase();
        return text.includes(query);
      }).sort((a, b) => {
        const aSelected = state.selected && state.selected.kind === "entity" && state.selected.id === a.id ? 1 : 0;
        const bSelected = state.selected && state.selected.kind === "entity" && state.selected.id === b.id ? 1 : 0;
        return bSelected - aSelected || b.degree - a.degree || b.support_count - a.support_count || a.name.localeCompare(b.name);
      });
    }

    async function loadBrowserNodes(start) {
      if (!window.EVOTAXA_DATA_API) {
        const rows = filteredNodesForBrowser();
        return { total: rows.length, items: rows.slice(start, start + state.nodePageSize) };
      }
      const params = new URLSearchParams({
        q: state.nodeQuery,
        type: state.nodeType,
        limit: String(state.nodePageSize),
        offset: String(start)
      });
      const response = await fetch(`/api/entities?${params.toString()}`);
      if (!response.ok) throw new Error(`entities API ${response.status}`);
      return await response.json();
    }

    async function renderNodeBrowser() {
      const select = document.getElementById("nodeTypeSelect");
      if (!select.dataset.ready) {
        select.innerHTML = `<option value="all">全部类型</option>` + DATA.entity_types.map(type => `<option value="${escapeHtml(type)}">${escapeHtml(DATA.entity_type_labels[type] || type)}</option>`).join("");
        select.dataset.ready = "1";
      }
      const requestId = ++nodeBrowserRequest;
      const start = state.nodePage * state.nodePageSize;
      const target = document.getElementById("nodeBrowserList");
      target.innerHTML = `<div class="detail-empty">正在加载节点...</div>`;
      let result;
      try {
        result = await loadBrowserNodes(start);
      } catch (error) {
        target.innerHTML = `<div class="detail-empty">节点加载失败：${escapeHtml(error.message)}</div>`;
        return;
      }
      if (requestId !== nodeBrowserRequest) return;
      const total = Number(result.total || 0);
      const rows = result.items || [];
      const pageCount = Math.max(1, Math.ceil(total / state.nodePageSize));
      if (state.nodePage >= pageCount) state.nodePage = pageCount - 1;
      document.getElementById("nodeBrowserCount").textContent = `${total} 个 · ${state.nodePage + 1}/${pageCount}`;
      target.innerHTML = rows.map(node => {
        const active = state.selected && state.selected.kind === "entity" && state.selected.id === node.id ? " active" : "";
        return `<button class="list-row${active}" type="button" data-browser-node-id="${escapeHtml(node.id)}">
          <div class="row-title"><span>${escapeHtml(compact(node.name, 42))}</span><span>${escapeHtml(DATA.entity_type_labels[node.type] || node.type)}</span></div>
          <div class="row-sub">${escapeHtml(node.first_seen || "未知")} · support ${node.support_count} · degree ${node.degree}</div>
          <div class="row-sub">${escapeHtml(compact(node.taxonomy_labels.join(" / "), 110))}</div>
        </button>`;
      }).join("") || `<div class="detail-empty">没有匹配节点。</div>`;
      document.getElementById("nodePrevButton").disabled = state.nodePage <= 0;
      document.getElementById("nodeNextButton").disabled = state.nodePage >= pageCount - 1;
      document.querySelectorAll("[data-browser-node-id]").forEach(button => {
        button.addEventListener("click", () => selectItem("entity", button.getAttribute("data-browser-node-id")));
      });
    }

    function renderWindows() {
      const psets = patternSets();
      let rows = DATA.windows.filter(row => {
        const text = [row.id, row.scope_label, row.scope_type, row.trigger, row.taxonomy_labels.join(" ")].join(" ").toLowerCase();
        return matches(text);
      });
      rows.sort((a, b) => {
        const ar = psets.pattern && (a.representative_edges.some(id => psets.edges.has(id)) || a.taxonomy_nodes.some(id => psets.taxonomy.has(id))) ? 1 : 0;
        const br = psets.pattern && (b.representative_edges.some(id => psets.edges.has(id)) || b.taxonomy_nodes.some(id => psets.taxonomy.has(id))) ? 1 : 0;
        return br - ar || String(a.start_date).localeCompare(String(b.start_date));
      });
      rows = rows.slice(0, 60);
      document.getElementById("windowCount").textContent = `${rows.length} / ${DATA.windows.length}`;
      document.getElementById("windowList").innerHTML = rows.map(row => {
        const hit = psets.pattern && (row.representative_edges.some(id => psets.edges.has(id)) || row.taxonomy_nodes.some(id => psets.taxonomy.has(id)));
        return `<button class="list-row${hit ? " active" : ""}" type="button" data-window-id="${escapeHtml(row.id)}">
          <div class="row-title"><span>${escapeHtml(compact(row.scope_label || row.scope_id, 42))}</span><span>${escapeHtml(row.scope_type)}</span></div>
          <div class="row-sub">${escapeHtml(row.start_date)} - ${escapeHtml(row.end_date)} · docs ${row.document_count}, mentions ${row.mention_count}, edges ${row.edge_count}</div>
        </button>`;
      }).join("");
      document.querySelectorAll("[data-window-id]").forEach(button => {
        button.addEventListener("click", () => selectItem("window", button.getAttribute("data-window-id")));
      });
    }

    function selectItem(kind, id) {
      state.selected = { kind, id };
      renderGraph();
      renderTrajectories();
      void renderNodeBrowser();
      renderDetails();
    }

    function renderDetails() {
      const label = document.getElementById("selectionLabel");
      const target = document.getElementById("detailsContent");
      const selected = state.selected;
      if (!selected) {
        label.textContent = "";
        target.innerHTML = `<div class="detail-empty">点击图中的节点、关系、轨迹或宏观模式查看完整证据卡。</div>`;
        return;
      }
      label.textContent = selected.kind;
      if (selected.kind === "entity") {
        void renderEntityDetails(selected.id, target);
        return;
      }
      if (selected.kind === "edge") return renderEdgeDetails(selected.id, target);
      if (selected.kind === "trajectory") return renderTrajectoryDetails(selected.id, target);
      if (selected.kind === "pattern") return renderPatternDetails(selected.id, target);
      if (selected.kind === "window") return renderWindowDetails(selected.id, target);
    }

    function edgeId(edge) {
      return edge.id || edge.edge_id || "";
    }

    function edgeType(edge) {
      return edge.type_label || edge.type || edge.edge_type || "";
    }

    function entityName(entityId) {
      const entity = entityById.get(entityId);
      if (entity && entity.name) return entity.name;
      return String(entityId || "").split("__").slice(1).join("__").replaceAll("_", " ") || entityId;
    }

    function edgeSource(edge) {
      return edge.source || edge.source_entity || "";
    }

    function edgeTarget(edge) {
      return edge.target || edge.target_entity || "";
    }

    function edgeYearLabel(edge) {
      return edge.target_year || edge.source_year || edge.year || "";
    }

    function edgeQuote(edge) {
      if (edge.quote) return edge.quote;
      const evidence = edge.evidence || {};
      for (const key of ["mechanism", "validation_evidence", "methodological_problem", "implementation_context", "data_basis"]) {
        const value = evidence[key];
        if (value && value.quote) return value.quote;
      }
      return "";
    }

    function edgeCardHtml(edge) {
      const id = edgeId(edge);
      const source = edgeSource(edge);
      const target = edgeTarget(edge);
      const quote = edgeQuote(edge);
      const conf = edge.confidence == null ? "" : ` · conf ${score(edge.confidence)}`;
      const year = edgeYearLabel(edge);
      return `<div class="edge-card">
        <div class="edge-card-title">
          <button class="inline-action" data-select-kind="edge" data-select-id="${escapeHtml(id)}">${escapeHtml(edgeType(edge) || "relation")}</button>
          <span class="muted">严格演化边 · ${escapeHtml(year)}${escapeHtml(conf)}</span>
        </div>
        <div class="edge-card-path">${escapeHtml(entityName(source))} → ${escapeHtml(entityName(target))}</div>
        ${quote ? `<div class="edge-card-quote">${escapeHtml(quote)}</div>` : ""}
      </div>`;
    }

    async function fetchEntityDetail(id) {
      if (!window.EVOTAXA_DATA_API) return null;
      const response = await fetch(`/api/entities/${encodeURIComponent(id)}`);
      if (!response.ok) throw new Error(`entity detail API ${response.status}`);
      return await response.json();
    }

    async function renderEntityDetails(id, target) {
      const row = entityById.get(id);
      if (!row && !window.EVOTAXA_DATA_API) return target.innerHTML = `<div class="detail-empty">未找到实体 ${escapeHtml(id)}</div>`;
      target.innerHTML = `<div class="detail-empty">正在加载节点卡片...</div>`;
      let detail = null;
      if (window.EVOTAXA_DATA_API) {
        try {
          detail = await fetchEntityDetail(id);
        } catch (error) {
          detail = { error: error.message };
        }
      }
      const card = detail && detail.entity ? detail.entity : row;
      if (!card) return target.innerHTML = `<div class="detail-empty">未找到实体 ${escapeHtml(id)}</div>`;
      const supportDocuments = detail && detail.support_documents ? detail.support_documents : row.support_documents.map(docId => DATA.documents[docId] || { doc_id: docId, title: docId, published_at: "" });
      const mentions = detail && detail.mentions ? detail.mentions : [];
      const incidentEdges = detail && detail.incident_edges ? detail.incident_edges : DATA.edges.filter(edge => edge.source === id || edge.target === id);
      const trajectories = detail && detail.trajectories ? detail.trajectories : DATA.trajectories.filter(trajectory => trajectory.entity_path.includes(id));
      const docs = supportDocuments.map(doc => `<li>${escapeHtml((doc.published_at || doc.year || "") + (doc.published_at || doc.year ? " · " : "") + (doc.title || doc.doc_id))} <span class="muted">${escapeHtml(doc.doc_id || "")}</span>${doc.text ? `<div class="row-sub">${escapeHtml(compact(doc.text, 260))}</div>` : ""}</li>`).join("");
      const mentionItems = mentions.slice(0, 12).map(mention => `<li><b>${escapeHtml(mention.name || card.name)}</b> <span class="muted">${escapeHtml(mention.doc_id || "")}${mention.confidence ? " · conf " + escapeHtml(score(mention.confidence)) : ""}</span><div class="quote">${escapeHtml(mention.quote || "")}</div></li>`).join("");
      target.innerHTML = `
        <h3>${escapeHtml(card.name)}</h3>
        <dl class="kv">
          <dt>ID</dt><dd>${escapeHtml(card.id)}</dd>
          <dt>演化组</dt><dd>${escapeHtml(card.type_label || DATA.entity_type_labels[card.type] || card.type)}</dd>
          <dt>原始类型</dt><dd>${escapeHtml(card.entity_type_label || DATA.raw_entity_type_labels?.[card.entity_type] || card.entity_type || "unknown")}</dd>
          <dt>原始名</dt><dd>${escapeHtml(card.canonical_name || card.name)}</dd>
          <dt>领域上下文</dt><dd>${escapeHtml(card.domain_context || "未知")}</dd>
          <dt>方法角色</dt><dd>${escapeHtml(card.method_role || "未知")}</dd>
          <dt>领域落地分</dt><dd>${card.domain_grounding_score == null ? "n/a" : score(card.domain_grounding_score)}${card.generic_technology_name ? " · 通用技术名" : ""}</dd>
          <dt>首现</dt><dd>${escapeHtml(card.first_seen || "未知")}</dd>
          <dt>支撑文献</dt><dd>${card.support_count}</dd>
          <dt>图度数</dt><dd>${card.degree}</dd>
        </dl>
        ${card.definition ? `<h4>类型定义</h4><div class="quote">${escapeHtml(card.definition)}</div>` : ""}
        <h4>Aliases</h4>${pillRow(card.aliases)}
        <h4>分类体系位置</h4>${pillRow(card.taxonomy_labels)}
        <h4>代表性提及</h4><ul class="evidence-list">${mentionItems || "<li>无</li>"}</ul>
        <h4>支撑文献</h4><ul class="doc-list">${docs || "<li>无</li>"}</ul>
        <h4>演化边</h4><div class="edge-card-list">${incidentEdges.slice(0, 18).map(edgeCardHtml).join("") || "<div class='muted'>无</div>"}</div>
        <h4>演化轨迹</h4><ul class="evidence-list">${trajectories.slice(0, 24).map(trajectory => `<li><button class="inline-action" data-select-kind="trajectory" data-select-id="${escapeHtml(trajectory.id || trajectory.trajectory_id)}">${escapeHtml(trajectory.id || trajectory.trajectory_id)}</button></li>`).join("") || "<li>无</li>"}</ul>
        ${detail && detail.raw_entity ? `<details><summary>原始节点记录</summary><pre class="raw-json">${escapeHtml(JSON.stringify(detail.raw_entity, null, 2))}</pre></details>` : ""}
        ${detail && detail.error ? `<div class="row-sub warn">后端详情加载失败：${escapeHtml(detail.error)}</div>` : ""}
      `;
    }

    function renderEdgeDetails(id, target) {
      const row = edgeById.get(id);
      if (!row) return target.innerHTML = `<div class="detail-empty">未找到关系 ${escapeHtml(id)}</div>`;
      const source = entityById.get(row.source);
      const targetEntity = entityById.get(row.target);
      target.innerHTML = `
        <h3>${escapeHtml((source || {}).name || row.source)} → ${escapeHtml((targetEntity || {}).name || row.target)}</h3>
        <dl class="kv">
          <dt>关系</dt><dd>${escapeHtml(row.type_label || row.type)}</dd>
          <dt>图层</dt><dd>严格演化边</dd>
          <dt>演化组</dt><dd>${escapeHtml(row.schema_group || row.source_schema_group || "unknown")}</dd>
          <dt>原始类型</dt><dd>${escapeHtml([row.source_entity_type, row.target_entity_type].filter(Boolean).join(" → ") || "unknown")}</dd>
          <dt>置信度</dt><dd>${score(row.confidence)}</dd>
          <dt>时间差</dt><dd>${row.time_delta_days == null ? "未知" : escapeHtml(row.time_delta_days + " 天")}</dd>
          <dt>审计</dt><dd>${escapeHtml(row.audit_status || "n/a")} ${row.substring_verified ? "· quote verified" : ""}</dd>
        </dl>
        ${row.definition ? `<h4>关系定义</h4><div class="quote">${escapeHtml(row.definition)}</div>` : ""}
        <h4>证据摘录</h4><div class="quote">${escapeHtml(row.quote || "无证据摘录")}</div>
        <h4>证据字段</h4><ul class="evidence-list">${row.evidence_fields.map(field => `<li><b>${escapeHtml(field.field)}</b>: ${escapeHtml(field.description || field.quote)}</li>`).join("") || "<li>无</li>"}</ul>
        <h4>文献</h4>
        <ul class="doc-list">
          <li>source: ${docLine(row.source_document, false)}</li>
          <li>target: ${docLine(row.target_document, false)}</li>
        </ul>
        <h4>分类体系位置</h4>${pillRow(row.taxonomy_labels)}
      `;
    }

    function renderTrajectoryDetails(id, target) {
      const row = trajectoryById.get(id);
      if (!row) return target.innerHTML = `<div class="detail-empty">未找到轨迹 ${escapeHtml(id)}</div>`;
      target.innerHTML = `
        <h3>${escapeHtml(row.id)}</h3>
        <dl class="kv">
          <dt>轨迹分</dt><dd>${score(row.score)}</dd>
          <dt>路径长度</dt><dd>${row.path_length}</dd>
          <dt>平均边置信度</dt><dd>${score(row.mean_edge_confidence)}</dd>
          <dt>时间一致性</dt><dd>${score(row.temporal_coherence)}</dd>
          <dt>证据落地</dt><dd>${score(row.quote_grounding)}</dd>
          <dt>schema 一致性</dt><dd>${score(row.schema_coherence)}</dd>
        </dl>
        <h4>实体路径</h4><div class="quote">${escapeHtml(row.entity_labels.join(" → "))}</div>
        <h4>关系证据</h4><div class="edge-card-list">${row.edge_path.map(edgeId => edgeById.get(edgeId)).filter(Boolean).map(edgeCardHtml).join("") || "<div class='muted'>无</div>"}</div>
        <h4>分类体系位置</h4>${pillRow(row.taxonomy_labels)}
      `;
    }

    function renderPatternDetails(id, target) {
      const row = patternById.get(id);
      if (!row) return target.innerHTML = `<div class="detail-empty">未找到模式 ${escapeHtml(id)}</div>`;
      const timeline = row.timeline.map(item => `${escapeHtml(item.time_slice || "unspecified")} (${score(item.score)}, ${item.evidence_count} evidence)`).join("<br>");
      const linkedEdges = (row.edge_ids || []).map(edgeId => edgeById.get(edgeId)).filter(Boolean);
      target.innerHTML = `
        <h3>${escapeHtml(row.label)}</h3>
        <dl class="kv">
          <dt>模式分</dt><dd>${score(row.score)}</dd>
          <dt>证据数</dt><dd>${row.evidence_count}</dd>
          <dt>信号数</dt><dd>${row.supporting_signal_count}</dd>
          <dt>时间跨度</dt><dd>${escapeHtml(row.time_span || "未知")}</dd>
          <dt>LLM 总结</dt><dd>${row.llm_summary_used ? "yes" : "no"}</dd>
        </dl>
        ${row.insight ? `<h4>语料洞察</h4><div class="insight-box">${escapeHtml(row.insight)}</div>` : ""}
        ${row.analytic_note ? `<h4>检测器读法</h4><div class="quote">${escapeHtml(row.analytic_note)}</div>` : ""}
        ${row.interpretation_caveat ? `<h4>解释边界</h4><div class="caveat-box">${escapeHtml(row.interpretation_caveat)}</div>` : ""}
        <h4>定义</h4><div class="quote">${escapeHtml(row.definition)}</div>
        <h4>主导信号</h4>${metricTable(row.dominant_signals, "signal")}
        <h4>关系构成</h4>${metricTable(row.dominant_relations, "relation")}
        <h4>类型迁移</h4>${metricTable(row.dominant_type_transitions, "transition")}
        <h4>时间热点</h4>${hotspotTable(row.temporal_hotspots)}
        <h4>代表分类节点</h4>${pillRow(row.representative_nodes)}
        <h4>代表证据</h4>${representativeEvidenceList(row.representative_evidence)}
        <h4>关联演化边</h4><div class="edge-card-list">${linkedEdges.slice(0, 10).map(edgeCardHtml).join("") || "<div class='muted'>无</div>"}</div>
        <h4>代表轨迹</h4><ul class="evidence-list">${row.representative_trajectories.slice(0, 12).map(trajId => `<li><button class="inline-action" data-select-kind="trajectory" data-select-id="${escapeHtml(trajId)}">${escapeHtml(trajId)}</button></li>`).join("") || "<li>无</li>"}</ul>
        <h4>时间线</h4><div class="row-sub">${timeline || "无"}</div>
      `;
    }

    function metricTable(rows, label) {
      const items = (rows || []).filter(Boolean);
      if (!items.length) return `<div class="muted">无</div>`;
      return `<table class="mini-table"><thead><tr><th>${escapeHtml(label)}</th><th>count</th><th>share</th></tr></thead><tbody>${
        items.slice(0, 8).map(item => `<tr><td>${escapeHtml(item.value || "")}</td><td>${escapeHtml(item.count ?? "")}</td><td>${escapeHtml(item.share == null ? "" : score(item.share))}</td></tr>`).join("")
      }</tbody></table>`;
    }

    function hotspotTable(rows) {
      const items = (rows || []).filter(Boolean);
      if (!items.length) return `<div class="muted">无</div>`;
      return `<table class="mini-table"><thead><tr><th>time</th><th>count</th><th>mean score</th></tr></thead><tbody>${
        items.slice(0, 8).map(item => `<tr><td>${escapeHtml(item.time_slice || "")}</td><td>${escapeHtml(item.count ?? "")}</td><td>${escapeHtml(item.mean_score == null ? "" : score(item.mean_score))}</td></tr>`).join("")
      }</tbody></table>`;
    }

    function representativeEvidenceList(rows) {
      const items = (rows || []).filter(Boolean);
      if (!items.length) return `<div class="muted">无</div>`;
      return `<div class="edge-card-list">${items.slice(0, 8).map(item => {
        const edgeId = (item.edge_ids || [])[0];
        const trajectoryId = (item.trajectory_ids || [])[0];
        const action = edgeId
          ? `<button class="inline-action" data-select-kind="edge" data-select-id="${escapeHtml(edgeId)}">打开边</button>`
          : (trajectoryId ? `<button class="inline-action" data-select-kind="trajectory" data-select-id="${escapeHtml(trajectoryId)}">打开轨迹</button>` : "");
        return `<div class="edge-card">
          <div class="edge-card-title"><span>${escapeHtml(item.signal_type || item.artifact_type || "evidence")}</span><span class="muted">${escapeHtml(item.time_slice || "")} · ${score(item.score)}</span></div>
          <div class="edge-card-path">${escapeHtml(item.path || item.artifact_id || "")}</div>
          ${item.relation ? `<div class="row-sub">${escapeHtml(item.relation)}</div>` : ""}
          ${item.type_transition ? `<div class="row-sub">type: ${escapeHtml(item.type_transition)}</div>` : ""}
          ${item.context_shift ? `<div class="row-sub">context: ${escapeHtml(item.context_shift)}</div>` : ""}
          ${item.quote ? `<div class="edge-card-quote">${escapeHtml(item.quote)}</div>` : ""}
          ${action ? `<div style="margin-top:6px">${action}</div>` : ""}
        </div>`;
      }).join("")}</div>`;
    }

    function renderWindowDetails(id, target) {
      const row = DATA.windows.find(item => item.id === id);
      if (!row) return target.innerHTML = `<div class="detail-empty">未找到窗口 ${escapeHtml(id)}</div>`;
      target.innerHTML = `
        <h3>${escapeHtml(row.scope_label || row.id)}</h3>
        <dl class="kv">
          <dt>范围</dt><dd>${escapeHtml(row.scope_type)} · ${escapeHtml(row.id)}</dd>
          <dt>时间</dt><dd>${escapeHtml(row.start_date)} - ${escapeHtml(row.end_date)}</dd>
          <dt>触发</dt><dd>${escapeHtml(row.trigger)}</dd>
          <dt>文献</dt><dd>${row.document_count}</dd>
          <dt>mentions</dt><dd>${row.mention_count}</dd>
          <dt>edges</dt><dd>${row.edge_count}</dd>
        </dl>
        <h4>代表实体</h4>${pillRow(row.representative_entities)}
        <h4>代表边</h4><ul class="evidence-list">${row.representative_edges.map(edgeId => `<li><button class="inline-action" data-select-kind="edge" data-select-id="${escapeHtml(edgeId)}">${escapeHtml(edgeId)}</button></li>`).join("") || "<li>无</li>"}</ul>
        <h4>代表文献</h4><ul class="doc-list">${row.representative_documents.map(docId => docLine(docId)).join("") || "<li>无</li>"}</ul>
        <h4>分类体系位置</h4>${pillRow(row.taxonomy_labels)}
      `;
    }

    function pillRow(items) {
      const rows = (items || []).filter(Boolean);
      if (!rows.length) return `<div class="muted">无</div>`;
      return `<div class="pill-row">${rows.map(item => `<span class="pill">${escapeHtml(item)}</span>`).join("")}</div>`;
    }
    function docLine(docId, wrap = true) {
      const doc = DATA.documents[docId] || { title: docId, year: "" };
      const text = `${doc.year ? doc.year + " · " : ""}${doc.title || docId}`;
      const html = `${escapeHtml(text)} <span class="muted">${escapeHtml(docId)}</span>`;
      return wrap ? `<li>${html}</li>` : html;
    }

    boot().catch(error => {
      document.getElementById("loadingView").textContent = `加载失败：${error.message}`;
      console.error(error);
    });
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
