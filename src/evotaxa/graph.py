from __future__ import annotations

import itertools
import re
from collections import Counter, defaultdict
from datetime import date
from typing import Any

from evotaxa.config import GraphConfig
from evotaxa.io import normalize_space, slugify
from evotaxa.models import Document, EntityMention, EvolutionEdge, EvolutionEntity
from evotaxa.taxonomy import tokenize


CAPITALIZED_PHRASE = re.compile(r"\b(?:[A-Z][A-Za-z0-9]+|[A-Z]{2,})(?:[-\s](?:[A-Z][A-Za-z0-9]+|[A-Z]{2,}|[a-z]+)){0,4}\b")


def extract_entities(
    docs: list[Document],
    assignments: dict[str, list[str]],
    config: GraphConfig,
) -> tuple[list[EvolutionEntity], list[EntityMention]]:
    mention_map: dict[str, list[EntityMention]] = defaultdict(list)
    entity_names_by_type = _configured_entity_names(config)

    for doc in docs:
        text = doc.full_text
        candidates: list[tuple[str, str, str]] = []
        for entity_type, names in entity_names_by_type.items():
            for name in names:
                evidence = _sentence_containing(text, name)
                if evidence:
                    candidates.append((name, entity_type, evidence))
        candidates.extend(_heuristic_entity_candidates(doc, config))

        seen_names: set[str] = set()
        for name, entity_type, evidence in candidates[: config.max_entities_per_document * 2]:
            canonical = normalize_entity_name(name)
            if not canonical or canonical.lower() in seen_names:
                continue
            seen_names.add(canonical.lower())
            entity_id = f"{slugify(entity_type)}__{slugify(canonical)}"
            mention_map[entity_id].append(
                EntityMention(
                    doc_id=doc.doc_id,
                    entity_id=entity_id,
                    canonical_name=canonical,
                    taxonomy_nodes=assignments.get(doc.doc_id, []),
                    evidence=evidence[:500],
                )
            )
            if len(seen_names) >= config.max_entities_per_document:
                break

    entities: list[EvolutionEntity] = []
    mentions: list[EntityMention] = []
    doc_map = {doc.doc_id: doc for doc in docs}
    for entity_id, rows in sorted(mention_map.items()):
        if len({row.doc_id for row in rows}) < config.min_entity_mentions:
            continue
        mentions.extend(rows)
        entity_type = entity_id.split("__", 1)[0]
        support_docs = sorted({row.doc_id for row in rows})
        first_seen = _first_seen_date([doc_map[doc_id] for doc_id in support_docs if doc_id in doc_map])
        taxonomy_nodes = sorted({node_id for row in rows for node_id in row.taxonomy_nodes})
        entities.append(
            EvolutionEntity(
                entity_id=entity_id,
                canonical_name=rows[0].canonical_name,
                aliases=[],
                first_seen_date=first_seen,
                support_documents=support_docs,
                taxonomy_nodes=taxonomy_nodes,
                entity_type=entity_type,
            )
        )
    return entities, mentions


def build_edges(
    docs: list[Document],
    entities: list[EvolutionEntity],
    mentions: list[EntityMention],
    config: GraphConfig,
) -> list[EvolutionEdge]:
    doc_map = {doc.doc_id: doc for doc in docs}
    mention_by_entity: dict[str, list[EntityMention]] = defaultdict(list)
    for mention in mentions:
        mention_by_entity[mention.entity_id].append(mention)

    entities_by_node: dict[str, list[EvolutionEntity]] = defaultdict(list)
    for entity in entities:
        nodes = entity.taxonomy_nodes or ["__global__"]
        for node_id in nodes:
            entities_by_node[node_id].append(entity)

    edges: dict[str, EvolutionEdge] = {}
    for node_id, local_entities in entities_by_node.items():
        ordered = sorted(local_entities, key=lambda entity: (entity.first_seen_date or "9999", entity.entity_id))
        for source, target in itertools.permutations(ordered, 2):
            if source.entity_id == target.entity_id:
                continue
            pair_docs = _candidate_document_pairs(source, target, doc_map)
            for source_doc, target_doc in pair_docs[: config.max_edge_candidates_per_entity]:
                edge_type, cue, evidence_sentence = _infer_edge_type(source, target, source_doc, target_doc, config)
                if edge_type == "background":
                    confidence = 0.35
                else:
                    confidence = _edge_confidence(source, target, source_doc, target_doc, edge_type, cue)
                evidence = {
                    "cue": cue,
                    "bottleneck": {
                        "description": _infer_bottleneck(evidence_sentence),
                        "quote": evidence_sentence,
                        "dimension": "",
                    },
                    "mechanism": {
                        "description": f"{target.canonical_name} is connected to {source.canonical_name}.",
                        "quote": evidence_sentence,
                    },
                    "tradeoff": {
                        "description": "",
                        "quote": "",
                    },
                }
                substring_verified = validate_evidence_quote(evidence_sentence, target_doc.full_text) or validate_evidence_quote(
                    evidence_sentence, source_doc.full_text
                )
                edge_id = f"{slugify(edge_type)}__{slugify(source.entity_id)}__{slugify(target.entity_id)}__{slugify(target_doc.doc_id)}"
                existing = edges.get(edge_id)
                new_edge = EvolutionEdge(
                    edge_id=edge_id,
                    source_entity=source.entity_id,
                    target_entity=target.entity_id,
                    edge_type=edge_type,
                    source_document=source_doc.doc_id,
                    target_document=target_doc.doc_id,
                    time_delta_days=_time_delta(source_doc.published_at, target_doc.published_at),
                    taxonomy_nodes=[] if node_id == "__global__" else [node_id],
                    confidence=round(confidence, 3),
                    evidence=evidence,
                    substring_verified=substring_verified,
                )
                if existing is None or new_edge.confidence > existing.confidence:
                    edges[edge_id] = new_edge
    return sorted(edges.values(), key=lambda edge: (-edge.confidence, edge.edge_id))


def validate_evidence_quote(quote: str, text: str) -> bool:
    quote = normalize_space(quote).lower()
    text = normalize_space(text).lower()
    if not quote:
        return False
    if quote in text:
        return True
    quote_tokens = tokenize(quote)
    if len(quote_tokens) < 4:
        return False
    text_tokens = set(tokenize(text))
    return len(set(quote_tokens) & text_tokens) / len(set(quote_tokens)) >= 0.8


def aggregate_edges(edges: list[EvolutionEdge]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[EvolutionEdge]] = defaultdict(list)
    for edge in edges:
        grouped[(edge.source_entity, edge.target_entity, edge.edge_type)].append(edge)
    rows: list[dict[str, Any]] = []
    for (source, target, edge_type), items in sorted(grouped.items()):
        rows.append(
            {
                "source_entity": source,
                "target_entity": target,
                "edge_type": edge_type,
                "support_edge_ids": [edge.edge_id for edge in items],
                "support_documents": sorted({edge.source_document for edge in items} | {edge.target_document for edge in items}),
                "taxonomy_nodes": sorted({node_id for edge in items for node_id in edge.taxonomy_nodes}),
                "mean_confidence": round(sum(edge.confidence for edge in items) / len(items), 3),
                "verified_edge_count": sum(1 for edge in items if edge.substring_verified),
            }
        )
    return rows


def _configured_entity_names(config: GraphConfig) -> dict[str, list[str]]:
    names: dict[str, list[str]] = defaultdict(list)
    for entity_type, patterns in config.entity_patterns.items():
        names[entity_type].extend(patterns)
    return names


def _heuristic_entity_candidates(doc: Document, config: GraphConfig) -> list[tuple[str, str, str]]:
    text = doc.full_text
    candidates: list[tuple[str, str, str]] = []
    cue_terms = [term.lower() for term in config.method_cue_terms]
    for match in CAPITALIZED_PHRASE.finditer(text):
        phrase = normalize_entity_name(match.group(0))
        if not phrase or len(phrase) < 4:
            continue
        window = text[max(0, match.start() - 80) : min(len(text), match.end() + 100)].lower()
        if not any(term in window for term in cue_terms):
            continue
        entity_type = _classify_entity_type(window, config)
        evidence = _sentence_containing(text, phrase) or normalize_space(window)
        candidates.append((phrase, entity_type, evidence))
    return candidates


def _classify_entity_type(window: str, config: GraphConfig) -> str:
    if "policy" in window or "regulation" in window or "governance" in window:
        return "policy_instrument" if "policy_instrument" in config.entity_types else config.entity_types[0]
    if "intervention" in window or "treatment" in window:
        return "intervention" if "intervention" in config.entity_types else config.entity_types[0]
    if "evaluation" in window or "benchmark" in window or "metric" in window:
        return "evaluation_protocol" if "evaluation_protocol" in config.entity_types else config.entity_types[0]
    if "mechanism" in window:
        return "mechanism" if "mechanism" in config.entity_types else config.entity_types[0]
    return config.entity_types[0] if config.entity_types else "method"


def normalize_entity_name(name: str) -> str:
    value = normalize_space(name)
    value = value.strip(" .,:;()[]{}")
    if len(value.split()) > 6:
        return ""
    blocked = {"This", "That", "These", "Those", "Figure", "Table", "Section", "Related Work"}
    if value in blocked:
        return ""
    return value


def _sentence_containing(text: str, phrase: str) -> str:
    if not phrase:
        return ""
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", normalize_space(text)) if part.strip()]
    phrase_low = phrase.lower()
    for sentence in sentences:
        if phrase_low in sentence.lower():
            return sentence
    return ""


def _first_seen_date(docs: list[Document]) -> str:
    dates = sorted(doc.published_at for doc in docs if doc.published_at)
    return dates[0].isoformat() if dates else ""


def _candidate_document_pairs(source: EvolutionEntity, target: EvolutionEntity, doc_map: dict[str, Document]) -> list[tuple[Document, Document]]:
    pairs: list[tuple[Document, Document]] = []
    for source_id in source.support_documents:
        for target_id in target.support_documents:
            source_doc = doc_map.get(source_id)
            target_doc = doc_map.get(target_id)
            if source_doc is None or target_doc is None:
                continue
            if source_doc.published_at and target_doc.published_at and source_doc.published_at > target_doc.published_at:
                continue
            pairs.append((source_doc, target_doc))
    return sorted(
        pairs,
        key=lambda pair: (
            pair[1].published_at or date.max,
            pair[0].published_at or date.max,
            pair[0].doc_id,
            pair[1].doc_id,
        ),
    )


def _infer_edge_type(
    source: EvolutionEntity,
    target: EvolutionEntity,
    source_doc: Document,
    target_doc: Document,
    config: GraphConfig,
) -> tuple[str, str, str]:
    text = target_doc.full_text
    source_name = source.canonical_name
    target_name = target.canonical_name
    candidate_sentences = [
        sentence for sentence in re.split(r"(?<=[.!?])\s+", normalize_space(text))
        if source_name.lower() in sentence.lower() or target_name.lower() in sentence.lower()
    ]
    if not candidate_sentences:
        candidate_sentences = [target_doc.full_text[:400]]

    best = ("background", "", candidate_sentences[0][:500])
    for sentence in candidate_sentences:
        low = sentence.lower()
        for edge_type, cues in config.edge_cues.items():
            for cue in cues:
                if cue.lower() in low:
                    return edge_type, cue, sentence[:500]
        if source_name.lower() in low and target_name.lower() in low:
            best = ("uses_component", "co-mention", sentence[:500])
    return best


def _edge_confidence(
    source: EvolutionEntity,
    target: EvolutionEntity,
    source_doc: Document,
    target_doc: Document,
    edge_type: str,
    cue: str,
) -> float:
    confidence = 0.45
    if edge_type in {"extends", "improves", "replaces", "adapts"}:
        confidence += 0.2
    if cue:
        confidence += 0.15
    if set(source.taxonomy_nodes) & set(target.taxonomy_nodes):
        confidence += 0.1
    delta = _time_delta(source_doc.published_at, target_doc.published_at)
    if delta is not None and delta >= 0:
        confidence += 0.1
    return min(0.95, confidence)


def _time_delta(source_date: date | None, target_date: date | None) -> int | None:
    if source_date is None or target_date is None:
        return None
    return (target_date - source_date).days


def _infer_bottleneck(sentence: str) -> str:
    low = sentence.lower()
    for cue in ["limitation", "bottleneck", "challenge", "issue", "problem", "fail", "lack", "gap"]:
        if cue in low:
            return sentence[:240]
    return ""


def entity_frequency_summary(entities: list[EvolutionEntity]) -> dict[str, Any]:
    return {
        "entity_count": len(entities),
        "entity_types": dict(Counter(entity.entity_type for entity in entities)),
        "top_entities": [
            {
                "entity_id": entity.entity_id,
                "canonical_name": entity.canonical_name,
                "support_document_count": len(entity.support_documents),
            }
            for entity in sorted(entities, key=lambda item: (-len(item.support_documents), item.entity_id))[:20]
        ],
    }

