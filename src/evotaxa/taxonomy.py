from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

from evotaxa.io import normalize_space, slugify
from evotaxa.models import Document, NodeQuality, TaxonomyNode


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into", "is", "it",
    "of", "on", "or", "that", "the", "their", "this", "to", "via", "with", "we",
}


def tokenize(text: str) -> list[str]:
    tokens = []
    for raw in normalize_space(text).lower().replace("-", " ").split():
        token = "".join(ch for ch in raw if ch.isalnum())
        if len(token) >= 3 and token not in STOPWORDS:
            tokens.append(token)
    return tokens


def top_phrases(texts: list[str], *, top_k: int = 8) -> list[str]:
    unigram_counts: Counter[str] = Counter()
    bigram_counts: Counter[str] = Counter()
    for text in texts:
        tokens = tokenize(text)
        unigram_counts.update(tokens)
        bigram_counts.update(" ".join(pair) for pair in zip(tokens, tokens[1:]))
    phrases = [phrase for phrase, _ in bigram_counts.most_common(top_k)]
    for phrase, _ in unigram_counts.most_common(top_k):
        if len(phrases) >= top_k:
            break
        phrases.append(phrase)
    return phrases


def enrich_taxonomy_nodes(docs: list[Document], nodes: list[TaxonomyNode]) -> list[dict[str, Any]]:
    doc_map = {doc.doc_id: doc for doc in docs}
    sibling_labels = _sibling_labels(nodes)
    enriched: list[dict[str, Any]] = []
    for node in nodes:
        support_docs = [doc_map[doc_id] for doc_id in node.support_documents if doc_id in doc_map]
        texts = [doc.full_text for doc in support_docs]
        phrases = top_phrases(texts + [node.canonical_label, node.definition], top_k=10)
        examples = [_sentence_with_phrase(doc.full_text, phrases) for doc in support_docs[:5]]
        examples = [example for example in examples if example]
        negative = [
            label for label in sibling_labels.get(node.parent_id or f"root:{node.dimension}", [])
            if label != node.canonical_label
        ][:8]
        uncertainty = _assignment_uncertainty(node)
        coherence = _semantic_coherence(texts, phrases)
        novelty = _temporal_novelty(support_docs)
        enriched.append(
            {
                "node_id": node.node_id,
                "dimension": node.dimension,
                "canonical_label": node.canonical_label,
                "aliases": node.aliases,
                "definition": node.definition or f"Documents centered on {node.canonical_label}.",
                "inclusion_criteria": f"Include documents that centrally discuss {node.canonical_label}.",
                "exclusion_criteria": "Exclude documents where the phrase appears only as background or unrelated context.",
                "distinctive_phrases": phrases,
                "sibling_negative_phrases": negative,
                "example_sentences": examples,
                "created_time_slice": node.created_time_slice,
                "node_status": _node_status(node, support_docs),
                "support_documents": node.support_documents,
                "representative_documents": node.representative_documents,
                "counterexample_documents": node.counterexample_documents,
                "assignment_uncertainty": uncertainty,
                "semantic_coherence": coherence,
                "temporal_novelty": novelty,
                "linked_method_entities": [],
                "dominant_bottlenecks": [],
                "dominant_mechanisms": [],
                "parent_id": node.parent_id,
            }
        )
    return enriched


def build_taxonomy_events(
    previous_nodes: list[TaxonomyNode],
    current_nodes: list[TaxonomyNode],
) -> list[dict[str, Any]]:
    previous_by_id = {node.node_id: node for node in previous_nodes}
    current_by_id = {node.node_id: node for node in current_nodes}
    events: list[dict[str, Any]] = []
    for node_id, node in sorted(current_by_id.items()):
        if node_id not in previous_by_id:
            events.append(
                {
                    "event_id": f"birth__{slugify(node_id)}",
                    "event_type": "birth",
                    "time_slice": node.created_time_slice,
                    "source_node_ids": [],
                    "target_node_ids": [node_id],
                    "support_documents": node.support_documents,
                    "reason": "Node exists in current taxonomy but not in previous taxonomy.",
                    "confidence": 0.85 if node.support_documents else 0.6,
                }
            )
            continue
        old = previous_by_id[node_id]
        if old.canonical_label != node.canonical_label:
            events.append(
                {
                    "event_id": f"rename__{slugify(node_id)}",
                    "event_type": "rename",
                    "time_slice": node.created_time_slice,
                    "source_node_ids": [node_id],
                    "target_node_ids": [node_id],
                    "support_documents": node.support_documents,
                    "reason": f"Label changed from {old.canonical_label!r} to {node.canonical_label!r}.",
                    "confidence": 0.7,
                }
            )

    previous_children = _children_by_parent(previous_nodes)
    current_children = _children_by_parent(current_nodes)
    for parent_id, children in current_children.items():
        previous_count = len(previous_children.get(parent_id, []))
        if previous_count < 2 and len(children) >= 2:
            events.append(
                {
                    "event_id": f"split__{slugify(parent_id)}",
                    "event_type": "split",
                    "time_slice": "",
                    "source_node_ids": [parent_id] if parent_id else [],
                    "target_node_ids": sorted(children),
                    "support_documents": sorted({
                        doc_id for child_id in children for doc_id in current_by_id[child_id].support_documents
                    }),
                    "reason": "Parent now has multiple child directions.",
                    "confidence": 0.65,
                }
            )
    return events


def judge_taxonomy_quality(docs: list[Document], nodes: list[TaxonomyNode]) -> list[NodeQuality]:
    doc_map = {doc.doc_id: doc for doc in docs}
    by_label = Counter(node.canonical_label.lower() for node in nodes)
    children = _children_by_parent(nodes)
    results: list[NodeQuality] = []
    for node in nodes:
        support_docs = [doc_map[doc_id] for doc_id in node.support_documents if doc_id in doc_map]
        label_tokens = set(tokenize(node.canonical_label))
        text_tokens = set(tokenize(" ".join(doc.full_text for doc in support_docs[:20])))
        relevance = _overlap_score(label_tokens, text_tokens)
        uniqueness = 0.4 if by_label[node.canonical_label.lower()] > 1 else 1.0
        coverage = min(1.0, len(node.support_documents) / 5.0)
        child_count = len(children.get(node.node_id, []))
        granularity = 0.6 if child_count > 10 else 0.8 if child_count else 0.7
        boundary = 0.8 if node.definition or node.aliases else 0.55
        stability = _temporal_stability(support_docs)
        dimension_alignment = 1.0 if node.dimension else 0.3
        sibling_coherence = _sibling_coherence(node, nodes)
        notes = []
        if not node.dimension:
            notes.append("missing dimension")
        if not node.support_documents:
            notes.append("no support documents")
        if by_label[node.canonical_label.lower()] > 1:
            notes.append("duplicate label")
        results.append(
            NodeQuality(
                node_id=node.node_id,
                dimension_alignment=round(dimension_alignment, 3),
                granularity=round(granularity, 3),
                sibling_coherence=round(sibling_coherence, 3),
                uniqueness=round(uniqueness, 3),
                paper_relevance=round(relevance, 3),
                coverage=round(coverage, 3),
                temporal_stability=round(stability, 3),
                boundary_clarity=round(boundary, 3),
                judge_notes="; ".join(notes),
            )
        )
    return results


def _sibling_labels(nodes: list[TaxonomyNode]) -> dict[str, list[str]]:
    labels: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        key = node.parent_id or f"root:{node.dimension}"
        labels[key].append(node.canonical_label)
    return labels


def _children_by_parent(nodes: list[TaxonomyNode]) -> dict[str, list[str]]:
    children: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        if node.parent_id:
            children[node.parent_id].append(node.node_id)
    return children


def _sentence_with_phrase(text: str, phrases: list[str]) -> str:
    sentences = [part.strip() for part in text.replace("\n", " ").split(".") if part.strip()]
    lowered_phrases = [phrase.lower() for phrase in phrases if phrase]
    for sentence in sentences:
        low = sentence.lower()
        if any(phrase in low for phrase in lowered_phrases):
            return sentence[:320]
    return sentences[0][:320] if sentences else ""


def _assignment_uncertainty(node: TaxonomyNode) -> float:
    support = len(node.support_documents)
    if support <= 0:
        return 1.0
    return round(1.0 / math.sqrt(support + 1), 3)


def _semantic_coherence(texts: list[str], phrases: list[str]) -> float:
    if not texts:
        return 0.0
    hits = 0
    for text in texts:
        low = text.lower()
        if any(phrase.lower() in low for phrase in phrases[:5]):
            hits += 1
    return round(hits / max(1, len(texts)), 3)


def _temporal_novelty(docs: list[Document]) -> float:
    dated = [doc.published_at for doc in docs if doc.published_at]
    if not dated:
        return 0.0
    years = [item.year for item in dated]
    newest = max(years)
    recent_share = sum(1 for year in years if year >= newest - 1) / len(years)
    return round(recent_share, 3)


def _node_status(node: TaxonomyNode, docs: list[Document]) -> str:
    support = len(docs)
    novelty = _temporal_novelty(docs)
    if support == 0:
        return "birth"
    if support < 3:
        return "emerging"
    if novelty >= 0.75 and support >= 3:
        return "growing"
    if support >= 10:
        return "mature"
    return "emerging"


def _overlap_score(left: set[str], right: set[str]) -> float:
    if not left:
        return 0.5
    return min(1.0, len(left & right) / len(left))


def _temporal_stability(docs: list[Document]) -> float:
    slices = {doc.chronology_slice for doc in docs if doc.chronology_slice}
    if not docs:
        return 0.0
    return min(1.0, len(slices) / 4.0) if slices else 0.5


def _sibling_coherence(node: TaxonomyNode, nodes: list[TaxonomyNode]) -> float:
    siblings = [item for item in nodes if item.parent_id == node.parent_id and item.node_id != node.node_id]
    if not siblings:
        return 0.8
    label_lengths = [len(tokenize(item.canonical_label)) for item in siblings + [node]]
    if max(label_lengths) - min(label_lengths) <= 3:
        return 0.85
    return 0.6

