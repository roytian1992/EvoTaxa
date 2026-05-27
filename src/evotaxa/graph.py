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


def merge_llm_entity_mentions(
    docs: list[Document],
    assignments: dict[str, list[str]],
    entities: list[EvolutionEntity],
    mentions: list[EntityMention],
    extraction_records: list[Any],
    config: GraphConfig,
) -> tuple[list[EvolutionEntity], list[EntityMention], list[dict[str, Any]]]:
    doc_map = {doc.doc_id: doc for doc in docs}
    mention_map: dict[str, list[EntityMention]] = defaultdict(list)
    for mention in mentions:
        mention_map[mention.entity_id].append(mention)

    report: list[dict[str, Any]] = []
    for record in extraction_records:
        doc_id = _record_doc_id(record)
        doc = doc_map.get(doc_id)
        rows = ((record.output or {}).get("entities") or []) if hasattr(record, "output") else []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            name = normalize_entity_name(str(row.get("name") or ""))
            entity_type = str(row.get("entity_type") or "").strip() or _default_entity_type(config)
            quote = normalize_space(row.get("quote") or "")
            if entity_type not in set(config.entity_types):
                entity_type = _default_entity_type(config)
            verified = bool(doc and validate_evidence_quote(quote, doc.full_text))
            status = "accepted" if name and verified else "rejected"
            entity_id = f"{slugify(entity_type)}__{slugify(name)}" if name else ""
            report.append(
                {
                    "doc_id": doc_id,
                    "row_index": index,
                    "entity_id": entity_id,
                    "name": name,
                    "entity_type": entity_type,
                    "quote": quote,
                    "confidence": row.get("confidence"),
                    "status": status,
                    "reason": "quote_verified" if verified else "quote_not_verified_or_missing_name",
                }
            )
            if status != "accepted":
                continue
            mention_map[entity_id].append(
                EntityMention(
                    doc_id=doc_id,
                    entity_id=entity_id,
                    canonical_name=name,
                    taxonomy_nodes=assignments.get(doc_id, []),
                    evidence=quote[:500],
                )
            )

    merged_entities = _entities_from_mentions(docs, mention_map, config)
    return merged_entities, [mention for rows in mention_map.values() for mention in rows], report


def build_edges(
    docs: list[Document],
    entities: list[EvolutionEntity],
    mentions: list[EntityMention],
    config: GraphConfig,
    relation_schema: dict[str, dict[str, Any]] | None = None,
    evidence_schema: dict[str, dict[str, Any]] | None = None,
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
                edge_type, cue, evidence_sentence = _infer_edge_type(source, target, source_doc, target_doc, config, relation_schema)
                if edge_type == "background":
                    confidence = 0.35
                else:
                    confidence = _edge_confidence(source, target, source_doc, target_doc, edge_type, cue)
                evidence = _initial_edge_evidence(
                    source=source,
                    target=target,
                    evidence_sentence=evidence_sentence,
                    relation_schema=relation_schema,
                    evidence_schema=evidence_schema,
                    edge_type=edge_type,
                    cue=cue,
                )
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


def build_relation_extraction_pairs(
    docs: list[Document],
    entities: list[EvolutionEntity],
    config: GraphConfig,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    doc_map = {doc.doc_id: doc for doc in docs}
    entities_by_node: dict[str, list[EvolutionEntity]] = defaultdict(list)
    for entity in entities:
        for node_id in entity.taxonomy_nodes or ["__global__"]:
            entities_by_node[node_id].append(entity)

    pairs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for node_id, local_entities in entities_by_node.items():
        ordered = sorted(local_entities, key=lambda entity: (entity.first_seen_date or "9999", entity.entity_id))
        for source, target in itertools.permutations(ordered, 2):
            if source.entity_id == target.entity_id:
                continue
            for source_doc, target_doc in _candidate_document_pairs(source, target, doc_map)[: config.max_edge_candidates_per_entity]:
                key = (source.entity_id, target.entity_id, source_doc.doc_id, target_doc.doc_id, node_id)
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(
                    {
                        "source_entity": source.to_record(),
                        "target_entity": target.to_record(),
                        "source_document": source_doc.doc_id,
                        "target_document": target_doc.doc_id,
                        "taxonomy_nodes": [] if node_id == "__global__" else [node_id],
                        "time_delta_days": _time_delta(source_doc.published_at, target_doc.published_at),
                    }
                )
                if limit > 0 and len(pairs) >= limit:
                    return pairs
    return pairs


def edge_from_relation_extraction(
    pair: dict[str, Any],
    output: dict[str, Any],
    *,
    relation_schema: dict[str, dict[str, Any]] | None,
    evidence_schema: dict[str, dict[str, Any]] | None,
) -> EvolutionEdge | None:
    if not bool(output.get("accept")):
        return None
    edge_type = str(output.get("edge_type") or "background")
    if relation_schema and edge_type not in relation_schema:
        edge_type = "background"
    confidence = _safe_float(output.get("confidence"), default=0.0)
    if confidence <= 0.0:
        return None
    source = pair.get("source_entity") or {}
    target = pair.get("target_entity") or {}
    source_entity_id = str(source.get("entity_id") or "")
    target_entity_id = str(target.get("entity_id") or "")
    target_doc_id = str(pair.get("target_document") or "")
    if not source_entity_id or not target_entity_id or not target_doc_id:
        return None
    evidence = _extracted_evidence(output, relation_schema, evidence_schema, edge_type)
    if output.get("rationale"):
        evidence["extractor_rationale"] = str(output["rationale"])
    if output.get("negative_rationale"):
        evidence["negative_rationale"] = str(output["negative_rationale"])
    edge_id = f"{slugify(edge_type)}__{slugify(source_entity_id)}__{slugify(target_entity_id)}__{slugify(target_doc_id)}"
    return EvolutionEdge(
        edge_id=edge_id,
        source_entity=source_entity_id,
        target_entity=target_entity_id,
        edge_type=edge_type,
        source_document=str(pair.get("source_document") or ""),
        target_document=target_doc_id,
        time_delta_days=pair.get("time_delta_days") if isinstance(pair.get("time_delta_days"), int) else None,
        taxonomy_nodes=[str(node_id) for node_id in pair.get("taxonomy_nodes") or [] if str(node_id)],
        confidence=round(min(0.99, max(0.0, confidence)), 3),
        evidence=evidence,
        substring_verified=False,
    )


def merge_edges_by_confidence(edges: list[EvolutionEdge]) -> list[EvolutionEdge]:
    merged: dict[str, EvolutionEdge] = {}
    for edge in edges:
        existing = merged.get(edge.edge_id)
        if existing is None or edge.confidence > existing.confidence:
            merged[edge.edge_id] = edge
    return sorted(merged.values(), key=lambda edge: (-edge.confidence, edge.edge_id))


def _initial_edge_evidence(
    *,
    source: EvolutionEntity,
    target: EvolutionEntity,
    evidence_sentence: str,
    relation_schema: dict[str, dict[str, Any]] | None,
    evidence_schema: dict[str, dict[str, Any]] | None,
    edge_type: str,
    cue: str,
) -> dict[str, Any]:
    slots = list(((relation_schema or {}).get(edge_type) or {}).get("evidence_slots") or [])
    if not slots:
        slots = list((evidence_schema or {}).keys()) or ["bottleneck", "mechanism", "tradeoff"]
    evidence: dict[str, Any] = {
        "cue": cue,
        "schema_slots": slots,
    }
    for slot in slots:
        if slot == "bottleneck":
            evidence[slot] = {
                "description": _infer_bottleneck(evidence_sentence),
                "quote": evidence_sentence if _infer_bottleneck(evidence_sentence) else "",
                "dimension": "",
            }
        elif slot == "mechanism":
            evidence[slot] = {
                "description": f"{target.canonical_name} is connected to {source.canonical_name}.",
                "quote": evidence_sentence,
            }
        elif slot == "tradeoff":
            evidence[slot] = {
                "description": "",
                "quote": "",
            }
        else:
            spec = (evidence_schema or {}).get(slot) or {}
            evidence[slot] = {
                "description": spec.get("definition", ""),
                "quote": evidence_sentence if bool(spec.get("required", False)) else "",
            }
    for required in ["bottleneck", "mechanism", "tradeoff"]:
        evidence.setdefault(
            required,
            {
                "description": f"{target.canonical_name} is connected to {source.canonical_name}."
                if required == "mechanism"
                else "",
                "quote": evidence_sentence if required == "mechanism" else "",
            },
        )
    return evidence


def _extracted_evidence(
    output: dict[str, Any],
    relation_schema: dict[str, dict[str, Any]] | None,
    evidence_schema: dict[str, dict[str, Any]] | None,
    edge_type: str,
) -> dict[str, Any]:
    slots = list(((relation_schema or {}).get(edge_type) or {}).get("evidence_slots") or [])
    if not slots:
        slots = list((evidence_schema or {}).keys()) or ["mechanism"]
    evidence: dict[str, Any] = {"cue": "llm_schema_extractor", "schema_slots": slots}
    raw_evidence = output.get("evidence") if isinstance(output.get("evidence"), dict) else {}
    for slot in slots:
        value = raw_evidence.get(slot) if isinstance(raw_evidence.get(slot), dict) else output.get(slot)
        if isinstance(value, dict):
            evidence[slot] = value
        else:
            evidence[slot] = {"description": "", "quote": ""}
    for required in ["bottleneck", "mechanism", "tradeoff"]:
        evidence.setdefault(required, {"description": "", "quote": ""})
    return evidence


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
    relation_schema: dict[str, dict[str, Any]] | None = None,
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
        for edge_type, cues in _relation_cues(config, relation_schema).items():
            for cue in cues:
                if cue.lower() in low:
                    return edge_type, cue, sentence[:500]
        if source_name.lower() in low and target_name.lower() in low:
            best = ("uses_component", "co-mention", sentence[:500])
    return best


def _relation_cues(config: GraphConfig, relation_schema: dict[str, dict[str, Any]] | None) -> dict[str, list[str]]:
    cues = {edge_type: list(values) for edge_type, values in config.edge_cues.items()}
    for edge_type, spec in (relation_schema or {}).items():
        merged = set(cues.get(edge_type, []))
        merged.update(str(item) for item in spec.get("cues") or [] if str(item).strip())
        merged.update(str(item) for item in spec.get("positive_cues") or [] if str(item).strip())
        cues[edge_type] = sorted(merged)
    return cues


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


def _safe_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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


def _entities_from_mentions(
    docs: list[Document],
    mention_map: dict[str, list[EntityMention]],
    config: GraphConfig,
) -> list[EvolutionEntity]:
    doc_map = {doc.doc_id: doc for doc in docs}
    entities: list[EvolutionEntity] = []
    for entity_id, rows in sorted(mention_map.items()):
        if len({row.doc_id for row in rows}) < config.min_entity_mentions:
            continue
        entity_type = entity_id.split("__", 1)[0]
        support_docs = sorted({row.doc_id for row in rows})
        first_seen = _first_seen_date([doc_map[doc_id] for doc_id in support_docs if doc_id in doc_map])
        taxonomy_nodes = sorted({node_id for row in rows for node_id in row.taxonomy_nodes})
        canonical_name = rows[0].canonical_name
        entities.append(
            EvolutionEntity(
                entity_id=entity_id,
                canonical_name=canonical_name,
                aliases=[],
                first_seen_date=first_seen,
                support_documents=support_docs,
                taxonomy_nodes=taxonomy_nodes,
                entity_type=entity_type,
            )
        )
    return entities


def _record_doc_id(record: Any) -> str:
    output = getattr(record, "output", {}) or {}
    if output.get("doc_id"):
        return str(output["doc_id"])
    prompt = getattr(record, "prompt", "") or ""
    match = re.search(r"Document id:\s*(.+)", prompt)
    if match:
        return match.group(1).strip().splitlines()[0]
    return ""


def _default_entity_type(config: GraphConfig) -> str:
    return config.entity_types[0] if config.entity_types else "entity"
