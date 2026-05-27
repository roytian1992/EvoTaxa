from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any

from evotaxa.config import GraphConfig
from evotaxa.io import slugify
from evotaxa.models import EntityMention, EvolutionEdge, EvolutionEntity
from evotaxa.taxonomy import tokenize


def canonicalize_entities(
    entities: list[EvolutionEntity],
    mentions: list[EntityMention],
    config: GraphConfig,
) -> tuple[list[EvolutionEntity], list[EntityMention], list[dict[str, Any]]]:
    alias_lookup = _alias_lookup(config)
    canonical_by_old_id: dict[str, str] = {}
    link_rows: list[dict[str, Any]] = []

    grouped_by_type: dict[str, list[EvolutionEntity]] = defaultdict(list)
    for entity in entities:
        grouped_by_type[entity.entity_type].append(entity)

    for entity_type, rows in grouped_by_type.items():
        canonical_keys: dict[str, str] = {}
        canonical_names: dict[str, str] = {}
        for entity in sorted(rows, key=lambda item: (item.canonical_name.lower(), item.entity_id)):
            configured_name = alias_lookup.get(_norm(entity.canonical_name))
            target_name = configured_name or _find_near_duplicate(entity.canonical_name, canonical_names, config.alias_similarity_threshold)
            if target_name:
                canonical_id = f"{slugify(entity_type)}__{slugify(target_name)}"
                reason = "configured_alias" if configured_name else "near_duplicate"
            else:
                target_name = entity.canonical_name
                canonical_id = f"{slugify(entity_type)}__{slugify(target_name)}"
                reason = "canonical"
                canonical_names[_norm(target_name)] = target_name
            canonical_keys[entity.entity_id] = canonical_id
            canonical_by_old_id[entity.entity_id] = canonical_id
            link_rows.append(
                {
                    "source_entity_id": entity.entity_id,
                    "canonical_entity_id": canonical_id,
                    "source_name": entity.canonical_name,
                    "canonical_name": target_name,
                    "entity_type": entity_type,
                    "reason": reason,
                }
            )

    remapped_mentions = [
        EntityMention(
            doc_id=mention.doc_id,
            entity_id=canonical_by_old_id.get(mention.entity_id, mention.entity_id),
            canonical_name=_name_from_id(canonical_by_old_id.get(mention.entity_id, mention.entity_id), mention.canonical_name),
            taxonomy_nodes=mention.taxonomy_nodes,
            evidence=mention.evidence,
        )
        for mention in mentions
    ]
    merged_entities = _merge_entities(entities, remapped_mentions, canonical_by_old_id)
    alias_rows = _build_alias_rows(entities, merged_entities, canonical_by_old_id)
    return merged_entities, remapped_mentions, [*link_rows, *alias_rows]


def remap_edges_to_canonical_entities(
    edges: list[EvolutionEdge],
    entity_link_rows: list[dict[str, Any]],
) -> list[EvolutionEdge]:
    mapping = {
        str(row["source_entity_id"]): str(row["canonical_entity_id"])
        for row in entity_link_rows
        if row.get("source_entity_id") and row.get("canonical_entity_id")
    }
    deduped: dict[str, EvolutionEdge] = {}
    for edge in edges:
        source = mapping.get(edge.source_entity, edge.source_entity)
        target = mapping.get(edge.target_entity, edge.target_entity)
        if source == target:
            continue
        edge.source_entity = source
        edge.target_entity = target
        edge.edge_id = f"{slugify(edge.edge_type)}__{slugify(source)}__{slugify(target)}__{slugify(edge.target_document)}"
        existing = deduped.get(edge.edge_id)
        if existing is None or edge.confidence > existing.confidence:
            deduped[edge.edge_id] = edge
    return sorted(deduped.values(), key=lambda row: (-row.confidence, row.edge_id))


def _alias_lookup(config: GraphConfig) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for canonical_name, aliases in config.entity_aliases.items():
        lookup[_norm(canonical_name)] = canonical_name
        for alias in aliases:
            lookup[_norm(alias)] = canonical_name
    return lookup


def _norm(value: str) -> str:
    tokens = tokenize(value)
    normalized = []
    for token in tokens:
        if token.endswith("ies") and len(token) > 4:
            token = token[:-3] + "y"
        elif token.endswith("s") and len(token) > 3:
            token = token[:-1]
        normalized.append(token)
    return " ".join(normalized)


def _find_near_duplicate(name: str, canonical_names: dict[str, str], threshold: float) -> str:
    normalized = _norm(name)
    for key, canonical in canonical_names.items():
        if not key or not normalized:
            continue
        if key == normalized:
            return canonical
        if _token_jaccard(key, normalized) >= threshold:
            return canonical
        if SequenceMatcher(None, key, normalized).ratio() >= threshold:
            return canonical
    return ""


def _token_jaccard(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _name_from_id(entity_id: str, fallback: str) -> str:
    if "__" not in entity_id:
        return fallback
    return entity_id.split("__", 1)[1].replace("_", " ")


def _merge_entities(
    entities: list[EvolutionEntity],
    mentions: list[EntityMention],
    mapping: dict[str, str],
) -> list[EvolutionEntity]:
    original_by_id = {entity.entity_id: entity for entity in entities}
    mentions_by_entity: dict[str, list[EntityMention]] = defaultdict(list)
    for mention in mentions:
        mentions_by_entity[mention.entity_id].append(mention)

    aliases_by_canonical: dict[str, set[str]] = defaultdict(set)
    support_by_canonical: dict[str, set[str]] = defaultdict(set)
    nodes_by_canonical: dict[str, set[str]] = defaultdict(set)
    types_by_canonical: dict[str, str] = {}
    names_by_canonical: dict[str, str] = {}
    first_seen_by_canonical: dict[str, str] = {}

    for old_id, canonical_id in mapping.items():
        original = original_by_id[old_id]
        aliases_by_canonical[canonical_id].add(original.canonical_name)
        aliases_by_canonical[canonical_id].update(original.aliases)
        support_by_canonical[canonical_id].update(original.support_documents)
        nodes_by_canonical[canonical_id].update(original.taxonomy_nodes)
        types_by_canonical[canonical_id] = original.entity_type
        names_by_canonical.setdefault(canonical_id, _name_from_id(canonical_id, original.canonical_name))
        first_seen = original.first_seen_date
        if first_seen and (not first_seen_by_canonical.get(canonical_id) or first_seen < first_seen_by_canonical[canonical_id]):
            first_seen_by_canonical[canonical_id] = first_seen

    for canonical_id, rows in mentions_by_entity.items():
        support_by_canonical[canonical_id].update(row.doc_id for row in rows)
        nodes_by_canonical[canonical_id].update(node_id for row in rows for node_id in row.taxonomy_nodes)

    merged: list[EvolutionEntity] = []
    for canonical_id in sorted(support_by_canonical):
        canonical_name = names_by_canonical.get(canonical_id) or _name_from_id(canonical_id, canonical_id)
        aliases = sorted(alias for alias in aliases_by_canonical[canonical_id] if alias and alias.lower() != canonical_name.lower())
        merged.append(
            EvolutionEntity(
                entity_id=canonical_id,
                canonical_name=canonical_name,
                aliases=aliases,
                first_seen_date=first_seen_by_canonical.get(canonical_id, ""),
                support_documents=sorted(support_by_canonical[canonical_id]),
                taxonomy_nodes=sorted(nodes_by_canonical[canonical_id]),
                entity_type=types_by_canonical.get(canonical_id, canonical_id.split("__", 1)[0]),
            )
        )
    return merged


def _build_alias_rows(
    original_entities: list[EvolutionEntity],
    merged_entities: list[EvolutionEntity],
    mapping: dict[str, str],
) -> list[dict[str, Any]]:
    original_by_id = {entity.entity_id: entity for entity in original_entities}
    rows: list[dict[str, Any]] = []
    for entity in merged_entities:
        source_ids = sorted(old_id for old_id, canonical_id in mapping.items() if canonical_id == entity.entity_id)
        rows.append(
            {
                "alias_record_type": "canonical_alias_set",
                "canonical_entity_id": entity.entity_id,
                "canonical_name": entity.canonical_name,
                "aliases": entity.aliases,
                "source_entity_ids": source_ids,
                "source_names": [original_by_id[old_id].canonical_name for old_id in source_ids if old_id in original_by_id],
            }
        )
    return rows

