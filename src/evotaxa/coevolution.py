from __future__ import annotations

from collections import defaultdict
from typing import Any

from evotaxa.config import TaxonomyConfig
from evotaxa.io import slugify
from evotaxa.models import EvolutionEdge, EvolutionEntity, TaxonomyNode
from evotaxa.taxonomy import tokenize


def propose_taxonomy_revisions(
    nodes: list[TaxonomyNode],
    entities: list[EvolutionEntity],
    edges: list[EvolutionEdge],
    feedback_rows: list[dict[str, Any]],
    config: TaxonomyConfig,
) -> list[dict[str, Any]]:
    node_map = {node.node_id: node for node in nodes}
    entity_map = {entity.entity_id: entity for entity in entities}
    edges_by_node: dict[str, list[EvolutionEdge]] = defaultdict(list)
    for edge in edges:
        for node_id in edge.taxonomy_nodes:
            edges_by_node[node_id].append(edge)

    candidates: list[dict[str, Any]] = []
    for row in feedback_rows:
        node_id = str(row.get("node_id") or "")
        node = node_map.get(node_id)
        if node is None:
            continue
        recommendations = set(row.get("recommendations") or [])
        local_edges = edges_by_node.get(node_id, [])
        if "split_review" in recommendations:
            candidates.extend(_split_candidates(node, local_edges, entity_map, row))
            state_candidate = _state_annotation_candidate(node, local_edges, row)
            if state_candidate:
                candidates.append(state_candidate)
        if "cross_link_review" in recommendations:
            candidate = _cross_link_candidate(node, local_edges, row, entity_map)
            if candidate:
                candidates.append(candidate)
        mismatch_candidate = _cross_link_candidate(node, local_edges, row, entity_map)
        if mismatch_candidate:
            candidates.append(mismatch_candidate)
        if "mark_fragmenting_or_growing" in recommendations:
            candidate = _state_annotation_candidate(node, local_edges, row)
            if candidate:
                candidates.append(candidate)

    candidates = _deduplicate_candidates(candidates)
    candidates.sort(key=lambda item: (-float(item.get("confidence") or 0.0), item.get("candidate_id", "")))
    return candidates[: config.max_revision_candidates]


def apply_taxonomy_revisions(
    nodes: list[TaxonomyNode],
    assignments: dict[str, list[str]],
    candidates: list[dict[str, Any]],
    config: TaxonomyConfig,
) -> tuple[list[TaxonomyNode], dict[str, list[str]], list[dict[str, Any]]]:
    revised_nodes = list(nodes)
    node_ids = {node.node_id for node in revised_nodes}
    node_index = {node.node_id: index for index, node in enumerate(revised_nodes)}
    sibling_labels = {(node.parent_id, node.canonical_label.lower()) for node in revised_nodes}
    existing_labels = {node.canonical_label.lower() for node in revised_nodes}
    revised_assignments: dict[str, set[str]] = {doc_id: set(node_ids_) for doc_id, node_ids_ in assignments.items()}
    report: list[dict[str, Any]] = []
    applied = 0

    for candidate in candidates:
        if applied >= config.max_applied_revisions:
            report.append(_skipped_report(candidate, "max_applied_revisions_reached"))
            continue
        confidence = float(candidate.get("confidence") or 0.0)
        if confidence < config.revision_acceptance_threshold:
            report.append(_skipped_report(candidate, "below_revision_acceptance_threshold"))
            continue
        revision_type = str(candidate.get("revision_type") or "")
        if revision_type == "split_child":
            status = _apply_split_child(
                revised_nodes,
                node_ids,
                sibling_labels,
                existing_labels,
                revised_assignments,
                candidate,
            )
        elif revision_type in {"cross_link", "state_annotation"}:
            status = _apply_annotation(revised_nodes, node_index, candidate)
        else:
            status = {"status": "rejected", "reason": f"Unknown revision_type: {revision_type}"}
        report.append({**_base_report(candidate), **status})
        if status.get("status") == "applied":
            applied += 1

    return revised_nodes, {doc_id: sorted(node_ids_) for doc_id, node_ids_ in sorted(revised_assignments.items())}, report


def _split_candidates(
    node: TaxonomyNode,
    edges: list[EvolutionEdge],
    entity_map: dict[str, EvolutionEntity],
    feedback_row: dict[str, Any],
) -> list[dict[str, Any]]:
    target_counts: dict[str, set[str]] = defaultdict(set)
    target_docs: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if not edge.substring_verified:
            continue
        target_counts[edge.target_entity].add(edge.edge_id)
        target_docs[edge.target_entity].update([edge.source_document, edge.target_document])

    candidates: list[dict[str, Any]] = []
    for target_id, support_edges in sorted(target_counts.items(), key=lambda item: (-len(item[1]), item[0]))[:3]:
        entity = entity_map.get(target_id)
        label = entity.canonical_name if entity else target_id.split("__", 1)[-1].replace("_", " ")
        if not _valid_revision_label(label):
            continue
        if entity and not _dimension_matches_entity(node.dimension, entity.entity_type):
            continue
        confidence = min(0.9, 0.55 + 0.08 * len(support_edges) + 0.04 * int(feedback_row.get("entity_count") or 0))
        candidates.append(
            {
                "candidate_id": f"revision_split__{slugify(node.node_id)}__{slugify(label)}",
                "revision_type": "split_child",
                "source_node_id": node.node_id,
                "parent_node_id": node.node_id,
                "dimension": node.dimension,
                "proposed_label": label,
                "support_edges": sorted(support_edges),
                "support_documents": sorted(doc_id for doc_id in target_docs[target_id] if doc_id),
                "confidence": round(confidence, 3),
                "reason": "Trusted graph edges suggest a successor-specific child under this taxonomy node.",
            }
        )
    return candidates


def _cross_link_candidate(
    node: TaxonomyNode,
    edges: list[EvolutionEdge],
    feedback_row: dict[str, Any],
    entity_map: dict[str, EvolutionEntity],
) -> dict[str, Any] | None:
    other_nodes = sorted({edge_node for edge in edges for edge_node in edge.taxonomy_nodes if edge_node != node.node_id})
    linked_entities = sorted(
        {
            entity_id
            for edge in edges
            for entity_id in [edge.source_entity, edge.target_entity]
            if entity_id in entity_map and not _dimension_matches_entity(node.dimension, entity_map[entity_id].entity_type)
        }
    )
    if not other_nodes and not linked_entities:
        return None
    confidence = min(0.86, 0.5 + 0.04 * len(other_nodes) + 0.04 * len(linked_entities) + 0.02 * int(feedback_row.get("edge_count") or 0))
    return {
        "candidate_id": f"revision_cross_link__{slugify(node.node_id)}",
        "revision_type": "cross_link",
        "source_node_id": node.node_id,
        "linked_node_ids": other_nodes[:8],
        "linked_entity_ids": linked_entities[:12],
        "linked_entity_types": sorted({entity_map[entity_id].entity_type for entity_id in linked_entities if entity_id in entity_map}),
        "support_edges": [edge.edge_id for edge in edges[:20]],
        "support_documents": sorted({edge.source_document for edge in edges} | {edge.target_document for edge in edges}),
        "confidence": round(confidence, 3),
        "reason": "Graph edges connect this taxonomy node to other nodes through shared entities or mechanisms.",
    }


def _state_annotation_candidate(
    node: TaxonomyNode,
    edges: list[EvolutionEdge],
    feedback_row: dict[str, Any],
) -> dict[str, Any] | None:
    if not edges:
        return None
    successors = sorted({edge.target_entity for edge in edges if edge.substring_verified})
    state = "fragmenting" if len(successors) >= 2 else "growing"
    confidence = min(0.88, 0.54 + 0.05 * len(successors) + 0.02 * int(feedback_row.get("verified_strong_edge_count") or 0))
    return {
        "candidate_id": f"revision_state__{slugify(node.node_id)}__{state}",
        "revision_type": "state_annotation",
        "source_node_id": node.node_id,
        "state": state,
        "support_edges": [edge.edge_id for edge in edges[:20]],
        "support_documents": sorted({edge.source_document for edge in edges} | {edge.target_document for edge in edges}),
        "confidence": round(confidence, 3),
        "reason": f"Trusted graph structure suggests the taxonomy node is {state}.",
    }


def _apply_split_child(
    nodes: list[TaxonomyNode],
    node_ids: set[str],
    sibling_labels: set[tuple[str, str]],
    existing_labels: set[str],
    assignments: dict[str, set[str]],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    label = str(candidate.get("proposed_label") or "").strip()
    parent_id = str(candidate.get("parent_node_id") or "")
    if not label or not parent_id:
        return {"status": "rejected", "reason": "missing_label_or_parent"}
    if not _valid_revision_label(label):
        return {"status": "rejected", "reason": "low_quality_label"}
    if label.lower() in existing_labels:
        return {"status": "deduplicated", "reason": "label_already_exists_in_taxonomy"}
    if (parent_id, label.lower()) in sibling_labels:
        return {"status": "deduplicated", "reason": "sibling_label_already_exists"}
    base_node_id = f"{slugify(candidate.get('dimension') or 'taxonomy')}__{slugify(label)}"
    node_id = base_node_id
    suffix = 2
    while node_id in node_ids:
        node_id = f"{base_node_id}_{suffix}"
        suffix += 1
    support_docs = sorted({str(doc_id) for doc_id in candidate.get("support_documents", []) if str(doc_id)})
    nodes.append(
        TaxonomyNode(
            node_id=node_id,
            dimension=str(candidate.get("dimension") or ""),
            canonical_label=label,
            parent_id=parent_id,
            definition=f"Graph-derived child for successor mechanism {label}.",
            support_documents=support_docs,
            representative_documents=support_docs[:5],
            raw={
                "source": "taxonomy_graph_coevolution",
                "revision_candidate_id": candidate.get("candidate_id"),
                "revision_type": candidate.get("revision_type"),
                "support_edges": candidate.get("support_edges") or [],
                "confidence": candidate.get("confidence"),
            },
        )
    )
    node_ids.add(node_id)
    sibling_labels.add((parent_id, label.lower()))
    existing_labels.add(label.lower())
    for doc_id in support_docs:
        assignments.setdefault(doc_id, set()).add(node_id)
    return {"status": "applied", "new_node_id": node_id, "reason": "created_graph_derived_child"}


def _apply_annotation(
    nodes: list[TaxonomyNode],
    node_index: dict[str, int],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    source_node_id = str(candidate.get("source_node_id") or "")
    index = node_index.get(source_node_id)
    if index is None:
        return {"status": "rejected", "reason": "source_node_missing"}
    node = nodes[index]
    raw = dict(node.raw or {})
    revisions = list(raw.get("graph_revisions") or [])
    revisions.append(
        {
            "candidate_id": candidate.get("candidate_id"),
            "revision_type": candidate.get("revision_type"),
            "confidence": candidate.get("confidence"),
            "reason": candidate.get("reason"),
            "linked_node_ids": candidate.get("linked_node_ids") or [],
            "linked_entity_ids": candidate.get("linked_entity_ids") or [],
            "linked_entity_types": candidate.get("linked_entity_types") or [],
            "state": candidate.get("state") or "",
            "support_edges": candidate.get("support_edges") or [],
        }
    )
    raw["graph_revisions"] = revisions
    if candidate.get("revision_type") == "state_annotation":
        raw["graph_state"] = candidate.get("state") or ""
    if candidate.get("revision_type") == "cross_link":
        raw["cross_linked_node_ids"] = sorted(set(raw.get("cross_linked_node_ids") or []) | set(candidate.get("linked_node_ids") or []))
        raw["cross_linked_entity_ids"] = sorted(set(raw.get("cross_linked_entity_ids") or []) | set(candidate.get("linked_entity_ids") or []))
    nodes[index] = TaxonomyNode(
        node_id=node.node_id,
        dimension=node.dimension,
        canonical_label=node.canonical_label,
        parent_id=node.parent_id,
        definition=node.definition,
        created_time_slice=node.created_time_slice,
        aliases=node.aliases,
        support_documents=node.support_documents,
        representative_documents=node.representative_documents,
        counterexample_documents=node.counterexample_documents,
        raw=raw,
    )
    return {"status": "applied", "reason": "annotated_existing_node"}


def _deduplicate_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = str(candidate.get("candidate_id") or "")
        if not key:
            continue
        if key not in deduped or float(candidate.get("confidence") or 0.0) > float(deduped[key].get("confidence") or 0.0):
            deduped[key] = candidate
    return list(deduped.values())


def _valid_revision_label(label: str) -> bool:
    tokens = tokenize(label)
    if not tokens or len(tokens) > 4:
        return False
    low = label.lower()
    blocked_fragments = [" the", " this", " that", " it ", " improves ", " extends ", " adapts ", " replaces "]
    return not any(fragment in f" {low} " for fragment in blocked_fragments)


def _dimension_matches_entity(dimension: str, entity_type: str) -> bool:
    dim_tokens = {_singularize(token) for token in tokenize(dimension.replace("_", " "))}
    type_tokens = {_singularize(token) for token in tokenize(entity_type.replace("_", " "))}
    if not dim_tokens or not type_tokens:
        return True
    if dim_tokens & type_tokens:
        return True
    compatibility = {
        "intervention": {"policy", "instrument", "governance", "program"},
        "policy": {"intervention", "governance", "instrument"},
        "instrument": {"intervention", "policy", "governance"},
        "mechanism": {"explanatory"},
        "explanatory": {"mechanism"},
        "measurement": {"evaluation", "protocol", "strategy", "audit"},
        "strategy": {"measurement", "evaluation", "protocol"},
        "evaluation": {"measurement", "strategy", "protocol"},
        "frame": {"public", "framing"},
        "public": {"frame", "framing"},
    }
    for token in dim_tokens:
        if compatibility.get(token, set()) & type_tokens:
            return True
    for token in type_tokens:
        if compatibility.get(token, set()) & dim_tokens:
            return True
    return False


def _singularize(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return f"{token[:-3]}y"
    if token.endswith("s") and len(token) > 3:
        return token[:-1]
    return token


def _base_report(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": candidate.get("candidate_id"),
        "revision_type": candidate.get("revision_type"),
        "source_node_id": candidate.get("source_node_id"),
        "confidence": candidate.get("confidence"),
        "support_edges": candidate.get("support_edges") or [],
        "support_documents": candidate.get("support_documents") or [],
    }


def _skipped_report(candidate: dict[str, Any], reason: str) -> dict[str, Any]:
    return {**_base_report(candidate), "status": "rejected", "reason": reason}
