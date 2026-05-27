from __future__ import annotations

from collections import defaultdict
from typing import Any

from evotaxa.config import GraphConfig
from evotaxa.models import EntityMention, EvolutionEntity
from evotaxa.taxonomy import tokenize


def filter_entities_by_quality(
    entities: list[EvolutionEntity],
    mentions: list[EntityMention],
    config: GraphConfig,
) -> tuple[list[EvolutionEntity], list[EntityMention], list[dict[str, Any]]]:
    allow = {_norm_text(value) for value in config.entity_allowlist}
    deny = {_norm_text(value) for value in config.entity_denylist}
    generic = {_norm_text(value) for value in config.generic_entity_phrases}
    mention_count_by_entity: dict[str, int] = defaultdict(int)
    for mention in mentions:
        mention_count_by_entity[mention.entity_id] += 1

    kept_ids: set[str] = set()
    report: list[dict[str, Any]] = []
    for entity in entities:
        quality, reasons = score_entity_quality(
            entity,
            mention_count=mention_count_by_entity.get(entity.entity_id, 0),
            allowlist=allow,
            denylist=deny,
            generic_phrases=generic,
        )
        status = "kept" if quality >= config.min_entity_quality else "filtered"
        if _norm_text(entity.canonical_name) in allow:
            status = "kept"
        if _norm_text(entity.canonical_name) in deny:
            status = "filtered"
        if status == "kept":
            kept_ids.add(entity.entity_id)
        report.append(
            {
                "entity_id": entity.entity_id,
                "canonical_name": entity.canonical_name,
                "entity_type": entity.entity_type,
                "quality": round(quality, 3),
                "status": status,
                "reasons": reasons,
                "mention_count": mention_count_by_entity.get(entity.entity_id, 0),
                "support_document_count": len(entity.support_documents),
            }
        )
    kept_entities = [entity for entity in entities if entity.entity_id in kept_ids]
    kept_mentions = [mention for mention in mentions if mention.entity_id in kept_ids]
    return kept_entities, kept_mentions, sorted(report, key=lambda row: (row["status"], -row["quality"], row["entity_id"]))


def score_entity_quality(
    entity: EvolutionEntity,
    *,
    mention_count: int,
    allowlist: set[str],
    denylist: set[str],
    generic_phrases: set[str],
) -> tuple[float, list[str]]:
    name = entity.canonical_name.strip()
    norm = _norm_text(name)
    tokens = tokenize(name)
    reasons: list[str] = []
    score = 0.45

    if norm in allowlist:
        return 1.0, ["allowlist"]
    if norm in denylist:
        return 0.0, ["denylist"]

    if not tokens:
        reasons.append("no_content_tokens")
        score -= 0.5
    token_count = len(tokens)
    if 1 <= token_count <= 4:
        score += 0.18
    elif token_count > 6:
        reasons.append("too_many_tokens")
        score -= 0.28

    if any(_norm_text(token) in generic_phrases for token in tokens):
        reasons.append("contains_generic_token")
        score -= 0.18
    if norm in generic_phrases:
        reasons.append("generic_phrase")
        score -= 0.4

    lower_name = name.lower()
    if any(marker in lower_name for marker in [" and ", " the ", " of ", " for "]):
        reasons.append("sentence_like_connector")
        score -= 0.18 if token_count <= 4 else 0.28
    if token_count >= 4 and not (entity.aliases or len(entity.support_documents) >= 2 or mention_count >= 2):
        reasons.append("unsupported_long_phrase")
        score -= 0.12
    if name[:1].isupper() and token_count <= 4:
        score += 0.08
    if any(ch.isdigit() for ch in name):
        score += 0.04
    if "-" in name or "_" in name:
        score += 0.04
    if mention_count >= 2:
        score += 0.12
    if len(entity.support_documents) >= 2:
        score += 0.1
    if entity.aliases:
        score += 0.08
    if len(name) > 80:
        reasons.append("too_long")
        score -= 0.35
    if _looks_like_title_fragment(name):
        reasons.append("title_fragment")
        score -= 0.28

    return max(0.0, min(1.0, score)), reasons or ["passed_heuristics"]


def _looks_like_title_fragment(name: str) -> bool:
    tokens = name.split()
    if len(tokens) < 5:
        return False
    title_case = sum(1 for token in tokens if token[:1].isupper())
    return title_case >= max(3, len(tokens) - 1)


def _norm_text(value: str) -> str:
    return " ".join(tokenize(value)).lower()
