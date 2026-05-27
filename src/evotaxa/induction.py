from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from evotaxa.config import TaxonomyConfig
from evotaxa.io import slugify
from evotaxa.models import DimensionSpec, Document, EvolutionEntity, TaxonomyNode
from evotaxa.taxonomy import tokenize, top_phrases


@dataclass
class ExpansionSignal:
    node_id: str
    dimension: str
    paper_density: float
    unassigned_mass: float
    semantic_heterogeneity: float
    assignment_uncertainty: float
    temporal_burst: float
    method_entity_burst: float
    bottleneck_concentration: float
    evaluation_shift_signal: float
    expansion_score: float
    recommended_action: str
    reason: str

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


def induce_initial_taxonomy(
    docs: list[Document],
    dimensions: list[DimensionSpec],
    config: TaxonomyConfig,
) -> tuple[list[TaxonomyNode], dict[str, list[str]], list[dict[str, Any]]]:
    """Build a deterministic first taxonomy when no node file is provided."""
    if not dimensions:
        dimensions = [DimensionSpec("topics", "Topics", "Induced topical structure.")]
    nodes: list[TaxonomyNode] = []
    assignments: dict[str, set[str]] = defaultdict(set)
    audit: list[dict[str, Any]] = []

    corpus_texts = [doc.full_text for doc in docs]
    global_phrases = top_phrases(corpus_texts, top_k=max(12, config.max_induced_nodes_per_dimension * 2))
    for dim in dimensions:
        root_id = f"{slugify(dim.dimension_id)}__root"
        nodes.append(
            TaxonomyNode(
                node_id=root_id,
                dimension=dim.dimension_id,
                canonical_label=dim.display_name or dim.dimension_id,
                definition=dim.definition,
            )
        )
        selected = _dimension_phrases(dim, global_phrases, docs, config.max_induced_nodes_per_dimension)
        for phrase in selected:
            node_id = f"{slugify(dim.dimension_id)}__{slugify(phrase)}"
            support = [doc.doc_id for doc in docs if _phrase_matches_doc(phrase, doc)]
            if len(support) < config.min_cluster_documents and len(docs) >= config.min_cluster_documents:
                continue
            nodes.append(
                TaxonomyNode(
                    node_id=node_id,
                    dimension=dim.dimension_id,
                    canonical_label=phrase,
                    parent_id=root_id,
                    definition=f"Induced node for documents emphasizing {phrase}.",
                    support_documents=sorted(support),
                    representative_documents=sorted(support)[:5],
                )
            )
            for doc_id in support:
                assignments[doc_id].add(node_id)
            audit.append(
                {
                    "node_id": node_id,
                    "dimension": dim.dimension_id,
                    "source": "deterministic_phrase_cluster",
                    "support_documents": sorted(support),
                    "phrase": phrase,
                }
            )
    return nodes, {doc_id: sorted(node_ids) for doc_id, node_ids in assignments.items()}, audit


def score_expansion_triggers(
    docs: list[Document],
    nodes: list[TaxonomyNode],
    assignments: dict[str, list[str]],
    entities: list[EvolutionEntity],
) -> list[ExpansionSignal]:
    doc_map = {doc.doc_id: doc for doc in docs}
    assigned_docs = {doc_id for doc_id, node_ids in assignments.items() if node_ids}
    unassigned_mass = max(0.0, (len(docs) - len(assigned_docs)) / max(1, len(docs)))
    entities_by_node: dict[str, list[EvolutionEntity]] = defaultdict(list)
    for entity in entities:
        for node_id in entity.taxonomy_nodes:
            entities_by_node[node_id].append(entity)

    signals: list[ExpansionSignal] = []
    for node in nodes:
        support_docs = [doc_map[doc_id] for doc_id in node.support_documents if doc_id in doc_map]
        density = min(1.0, len(support_docs) / 10.0)
        heterogeneity = _semantic_heterogeneity(support_docs)
        uncertainty = 1.0 if not support_docs else min(1.0, 1.0 / (len(support_docs) ** 0.5))
        burst = _temporal_burst(support_docs)
        entity_burst = min(1.0, len(entities_by_node.get(node.node_id, [])) / 6.0)
        bottleneck = _bottleneck_concentration(support_docs)
        evaluation_shift = _evaluation_shift(support_docs)
        score = _weighted_sum(
            [
                density,
                unassigned_mass,
                heterogeneity,
                uncertainty,
                burst,
                entity_burst,
                bottleneck,
                evaluation_shift,
            ]
        )
        action, reason = _recommend_action(
            density=density,
            unassigned_mass=unassigned_mass,
            heterogeneity=heterogeneity,
            uncertainty=uncertainty,
            burst=burst,
            entity_burst=entity_burst,
            bottleneck=bottleneck,
            evaluation_shift=evaluation_shift,
        )
        signals.append(
            ExpansionSignal(
                node_id=node.node_id,
                dimension=node.dimension,
                paper_density=round(density, 3),
                unassigned_mass=round(unassigned_mass, 3),
                semantic_heterogeneity=round(heterogeneity, 3),
                assignment_uncertainty=round(uncertainty, 3),
                temporal_burst=round(burst, 3),
                method_entity_burst=round(entity_burst, 3),
                bottleneck_concentration=round(bottleneck, 3),
                evaluation_shift_signal=round(evaluation_shift, 3),
                expansion_score=round(score, 3),
                recommended_action=action,
                reason=reason,
            )
        )
    return sorted(signals, key=lambda row: (-row.expansion_score, row.node_id))


def propose_expansion_candidates(
    docs: list[Document],
    nodes: list[TaxonomyNode],
    signals: list[ExpansionSignal],
    config: TaxonomyConfig,
) -> list[dict[str, Any]]:
    doc_map = {doc.doc_id: doc for doc in docs}
    node_map = {node.node_id: node for node in nodes}
    candidates: list[dict[str, Any]] = []
    for signal in signals:
        if signal.expansion_score < config.expansion_threshold:
            continue
        node = node_map.get(signal.node_id)
        if node is None:
            continue
        support_docs = [doc_map[doc_id] for doc_id in node.support_documents if doc_id in doc_map]
        phrases = top_phrases([doc.full_text for doc in support_docs] or [node.canonical_label], top_k=8)
        action = signal.recommended_action
        for phrase in phrases[:3]:
            candidate_type = "depth" if action in {"depth_expansion", "fragmentation_review"} else "width"
            candidates.append(
                {
                    "candidate_id": f"{candidate_type}__{slugify(node.node_id)}__{slugify(phrase)}",
                    "candidate_type": candidate_type,
                    "parent_node_id": node.node_id if candidate_type == "depth" else node.parent_id,
                    "dimension": node.dimension,
                    "proposed_label": phrase,
                    "support_documents": [doc.doc_id for doc in support_docs if phrase.lower() in doc.full_text.lower()],
                    "trigger_node_id": signal.node_id,
                    "trigger_score": signal.expansion_score,
                    "recommended_action": signal.recommended_action,
                    "reason": signal.reason,
                    "status": "candidate",
                }
            )
        if len(candidates) >= config.max_expansion_candidates:
            break
    return candidates


def build_induction_assignments(
    docs: list[Document],
    nodes: list[TaxonomyNode],
    existing_assignments: dict[str, list[str]],
) -> dict[str, list[str]]:
    merged: dict[str, set[str]] = {doc_id: set(node_ids) for doc_id, node_ids in existing_assignments.items()}
    for doc in docs:
        for node in nodes:
            if node.parent_id and _phrase_matches_doc(node.canonical_label, doc):
                merged.setdefault(doc.doc_id, set()).add(node.node_id)
    return {doc_id: sorted(node_ids) for doc_id, node_ids in sorted(merged.items())}


def _dimension_phrases(
    dim: DimensionSpec,
    global_phrases: list[str],
    docs: list[Document],
    limit: int,
) -> list[str]:
    dim_tokens = set(tokenize(f"{dim.dimension_id} {dim.display_name} {dim.definition}"))
    scored: list[tuple[float, str]] = []
    for phrase in global_phrases:
        phrase_tokens = set(tokenize(phrase))
        overlap = len(dim_tokens & phrase_tokens)
        support = sum(1 for doc in docs if _phrase_matches_doc(phrase, doc))
        score = support + 0.5 * overlap
        scored.append((score, phrase))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [phrase for _, phrase in scored[:limit]]


def _phrase_matches_doc(phrase: str, doc: Document) -> bool:
    phrase_low = phrase.lower()
    if phrase_low in doc.full_text.lower():
        return True
    phrase_tokens = set(tokenize(phrase))
    doc_tokens = set(tokenize(doc.full_text))
    return bool(phrase_tokens) and len(phrase_tokens & doc_tokens) / len(phrase_tokens) >= 0.67


def _semantic_heterogeneity(docs: list[Document]) -> float:
    if len(docs) <= 1:
        return 0.0
    doc_token_sets = [set(tokenize(doc.full_text)) for doc in docs[:30]]
    similarities: list[float] = []
    for index, left in enumerate(doc_token_sets):
        for right in doc_token_sets[index + 1 :]:
            union = left | right
            if union:
                similarities.append(len(left & right) / len(union))
    if not similarities:
        return 0.0
    return max(0.0, 1.0 - sum(similarities) / len(similarities))


def _temporal_burst(docs: list[Document]) -> float:
    slices = Counter(doc.chronology_slice or (doc.published_at.isoformat()[:4] if doc.published_at else "") for doc in docs)
    if not slices:
        return 0.0
    return max(slices.values()) / max(1, sum(slices.values()))


def _bottleneck_concentration(docs: list[Document]) -> float:
    cues = ["limitation", "bottleneck", "challenge", "problem", "fail", "gap", "barrier", "constraint"]
    if not docs:
        return 0.0
    hits = sum(1 for doc in docs if any(cue in doc.full_text.lower() for cue in cues))
    return hits / len(docs)


def _evaluation_shift(docs: list[Document]) -> float:
    cues = ["benchmark", "evaluation", "metric", "measure", "audit", "survey", "experiment", "protocol"]
    if not docs:
        return 0.0
    hits = sum(1 for doc in docs if any(cue in doc.full_text.lower() for cue in cues))
    return hits / len(docs)


def _weighted_sum(values: list[float]) -> float:
    weights = [0.15, 0.12, 0.18, 0.12, 0.12, 0.13, 0.1, 0.08]
    return sum(weight * value for weight, value in zip(weights, values))


def _recommend_action(
    *,
    density: float,
    unassigned_mass: float,
    heterogeneity: float,
    uncertainty: float,
    burst: float,
    entity_burst: float,
    bottleneck: float,
    evaluation_shift: float,
) -> tuple[str, str]:
    if unassigned_mass >= 0.4 and burst >= 0.5:
        return "width_expansion", "High unassigned mass with temporal concentration."
    if density >= 0.5 and heterogeneity >= 0.55:
        return "depth_expansion", "Dense node with heterogeneous support documents."
    if bottleneck >= 0.5 and entity_burst >= 0.3:
        return "handoff_to_evolution_graph", "Bottleneck concentration and entity burst are both visible."
    if evaluation_shift >= 0.6:
        return "cross_dimension_link", "Evaluation or measurement vocabulary is concentrated."
    if uncertainty >= 0.7:
        return "assignment_review", "High assignment uncertainty."
    return "monitor", "No dominant expansion trigger."

