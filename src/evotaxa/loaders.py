from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from evotaxa.config import EvoTaxaConfig
from evotaxa.io import as_str_list, first_value, listify, normalize_space, parse_date, read_json_or_jsonl, slugify
from evotaxa.models import Document, TaxonomyNode


def load_documents(config: EvoTaxaConfig) -> tuple[list[Document], dict[str, Any]]:
    if config.corpus.path is None:
        raise ValueError("corpus.path is required")
    raw_rows = read_json_or_jsonl(config.corpus.path)
    if not isinstance(raw_rows, list):
        raise ValueError(f"Corpus must be a JSONL file or JSON list: {config.corpus.path}")

    cutoff = parse_date(config.corpus.cutoff_date)
    accepted = set(config.corpus.accepted_roles)
    docs: list[Document] = []
    skipped = defaultdict(int)

    for index, row in enumerate(raw_rows, start=1):
        if not isinstance(row, dict):
            skipped["non_object"] += 1
            continue
        doc_id = normalize_space(first_value(row, config.corpus.id_fields))
        if not doc_id:
            doc_id = f"doc_{index:06d}"
        title = normalize_space(first_value(row, config.corpus.title_fields))
        text_parts = [
            normalize_space(value)
            for field in config.corpus.text_fields
            if (value := first_value(row, [field])) not in (None, "", [], {})
        ]
        text = "\n".join(part for part in text_parts if part)
        if not title and not text:
            skipped["missing_text"] += 1
            continue

        role = normalize_space(first_value(row, config.corpus.role_fields))
        if accepted and role not in accepted:
            skipped["role_filtered"] += 1
            continue

        published_at = parse_date(first_value(row, config.corpus.date_fields))
        if published_at is None and config.corpus.missing_date_policy == "drop":
            skipped["missing_date"] += 1
            continue
        if cutoff is not None and published_at is not None and published_at > cutoff:
            skipped["post_cutoff"] += 1
            continue
        chronology_slice = normalize_space(first_value(row, config.corpus.slice_fields))
        if not chronology_slice and published_at is not None:
            chronology_slice = published_at.isoformat()[:7]

        docs.append(
            Document(
                doc_id=doc_id,
                title=title,
                text=text,
                published_at=published_at,
                chronology_slice=chronology_slice,
                role=role,
                source_type=config.corpus.source_type,
                raw=row,
            )
        )

    docs.sort(key=lambda doc: (doc.published_at is None, doc.published_at or "", doc.doc_id))
    return docs, {
        "path": str(config.corpus.path),
        "raw_rows": len(raw_rows),
        "loaded_documents": len(docs),
        "skipped": dict(skipped),
        "cutoff_date": config.corpus.cutoff_date,
        "accepted_roles": config.corpus.accepted_roles,
    }


def _flatten_nested_taxonomy(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def visit(node: dict[str, Any], parent_id: str = "", dimension: str = "") -> None:
        current = dict(node)
        current.setdefault("parent_id", parent_id)
        current.setdefault("dimension", dimension or current.get("dimension_id") or "")
        rows.append(current)
        node_id = str(current.get("node_id") or current.get("id") or "")
        current_dimension = str(current.get("dimension") or current.get("dimension_id") or dimension or "")
        for child in current.get("children") or []:
            if isinstance(child, dict):
                visit(child, node_id, current_dimension)

    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                if "children" in item:
                    visit(item)
                else:
                    rows.append(dict(item))
    elif isinstance(value, dict):
        if all(isinstance(item, dict) for item in value.values()):
            for dimension, root in value.items():
                current = dict(root)
                current.setdefault("dimension", str(dimension))
                visit(current, dimension=str(dimension))
        else:
            visit(value)
    else:
        raise ValueError("Taxonomy nodes must be a JSON list, nested object, or JSONL")
    return rows


def load_taxonomy_nodes(config: EvoTaxaConfig, *, previous: bool = False) -> tuple[list[TaxonomyNode], dict[str, Any]]:
    path = config.taxonomy.previous_nodes_path if previous else config.taxonomy.nodes_path
    if path is None:
        if previous:
            return [], {"path": None, "loaded_nodes": 0}
        raise ValueError("taxonomy.nodes_path is required")

    raw = read_json_or_jsonl(path)
    raw_rows = _flatten_nested_taxonomy(raw)
    nodes: list[TaxonomyNode] = []
    skipped = defaultdict(int)
    seen: set[str] = set()
    dimensions = {dim.dimension_id for dim in config.taxonomy.dimensions}

    for index, row in enumerate(raw_rows, start=1):
        node_id = normalize_space(first_value(row, config.taxonomy.node_id_fields))
        label = normalize_space(first_value(row, config.taxonomy.node_label_fields))
        dimension = normalize_space(first_value(row, config.taxonomy.node_dimension_fields))
        if not dimension and dimensions:
            dimension = sorted(dimensions)[0]
        if not label:
            skipped["missing_label"] += 1
            continue
        if not node_id:
            node_id = f"{slugify(dimension)}__{slugify(label)}_{index:04d}"
        if node_id in seen:
            node_id = f"{node_id}_{index:04d}"
        seen.add(node_id)
        nodes.append(
            TaxonomyNode(
                node_id=node_id,
                dimension=dimension,
                canonical_label=label,
                parent_id=normalize_space(first_value(row, config.taxonomy.node_parent_fields)),
                definition=normalize_space(first_value(row, config.taxonomy.node_definition_fields)),
                created_time_slice=normalize_space(first_value(row, config.taxonomy.node_created_slice_fields)),
                aliases=as_str_list(first_value(row, config.taxonomy.node_alias_fields)),
                support_documents=as_str_list(row.get("support_documents") or row.get("support_papers")),
                representative_documents=as_str_list(row.get("representative_documents") or row.get("representative_papers")),
                counterexample_documents=as_str_list(row.get("counterexample_documents") or row.get("counterexample_papers")),
                raw=row,
            )
        )
    return nodes, {"path": str(path), "raw_nodes": len(raw_rows), "loaded_nodes": len(nodes), "skipped": dict(skipped)}


def load_assignments(config: EvoTaxaConfig) -> tuple[dict[str, list[str]], dict[str, Any]]:
    path = config.taxonomy.assignments_path
    if path is None:
        return {}, {"path": None, "loaded_assignments": 0}
    raw_rows = read_json_or_jsonl(path)
    if not isinstance(raw_rows, list):
        raise ValueError(f"Assignments must be a JSONL file or JSON list: {path}")

    mapping: dict[str, set[str]] = defaultdict(set)
    skipped = defaultdict(int)
    for row in raw_rows:
        if not isinstance(row, dict):
            skipped["non_object"] += 1
            continue
        doc_id = normalize_space(first_value(row, config.taxonomy.assignment_doc_id_fields))
        if not doc_id:
            skipped["missing_doc_id"] += 1
            continue

        direct_node_ids: list[str] = []
        for field in config.taxonomy.assignment_node_id_fields:
            value = first_value(row, [field])
            direct_node_ids.extend(as_str_list(value))

        for field in config.taxonomy.assignment_dimension_map_fields:
            value = first_value(row, [field])
            if isinstance(value, dict):
                for item in value.values():
                    direct_node_ids.extend(_extract_node_ids_from_assignment_value(item))

        for node_id in direct_node_ids:
            mapping[doc_id].add(node_id)

    normalized = {doc_id: sorted(node_ids) for doc_id, node_ids in mapping.items()}
    return normalized, {"path": str(path), "raw_rows": len(raw_rows), "loaded_assignments": len(normalized), "skipped": dict(skipped)}


def _extract_node_ids_from_assignment_value(value: Any) -> list[str]:
    node_ids: list[str] = []
    for item in listify(value):
        if isinstance(item, dict):
            for key in ["node_id", "id", "leaf_node_id"]:
                if item.get(key):
                    node_ids.append(str(item[key]))
        else:
            node_ids.append(str(item))
    return [node_id.strip() for node_id in node_ids if node_id and node_id.strip()]


def infer_assignments_from_text(docs: list[Document], nodes: list[TaxonomyNode]) -> dict[str, list[str]]:
    by_doc: dict[str, set[str]] = defaultdict(set)
    for doc in docs:
        text = doc.full_text.lower()
        for node in nodes:
            candidates = [node.canonical_label, *node.aliases]
            if any(candidate and candidate.lower() in text for candidate in candidates):
                by_doc[doc.doc_id].add(node.node_id)
    return {doc_id: sorted(node_ids) for doc_id, node_ids in by_doc.items()}


def attach_node_support(
    docs: list[Document],
    nodes: list[TaxonomyNode],
    assignments: dict[str, list[str]],
) -> list[TaxonomyNode]:
    doc_ids = {doc.doc_id for doc in docs}
    support_by_node: dict[str, set[str]] = defaultdict(set)
    for doc_id, node_ids in assignments.items():
        if doc_id not in doc_ids:
            continue
        for node_id in node_ids:
            support_by_node[node_id].add(doc_id)

    output: list[TaxonomyNode] = []
    for node in nodes:
        support = set(node.support_documents)
        support.update(support_by_node.get(node.node_id, set()))
        representatives = set(node.representative_documents)
        representatives.update(sorted(support)[:5])
        output.append(
            TaxonomyNode(
                node_id=node.node_id,
                dimension=node.dimension,
                canonical_label=node.canonical_label,
                parent_id=node.parent_id,
                definition=node.definition,
                created_time_slice=node.created_time_slice,
                aliases=node.aliases,
                support_documents=sorted(support),
                representative_documents=sorted(representatives)[:10],
                counterexample_documents=node.counterexample_documents,
                raw=node.raw,
            )
        )
    return output

