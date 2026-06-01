from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from evotaxa.config import GraphConfig
from evotaxa.graph import validate_evidence_quote
from evotaxa.io import normalize_space
from evotaxa.models import Document, EvolutionEdge


EVIDENCE_FIELDS = ["bottleneck", "mechanism", "tradeoff"]


def stratify_edges_by_evidence(
    edges: list[EvolutionEdge],
    docs: list[Document],
    config: GraphConfig,
) -> tuple[list[EvolutionEdge], list[EvolutionEdge], list[EvolutionEdge], list[dict[str, Any]]]:
    doc_map = {doc.doc_id: doc for doc in docs}
    trusted: list[EvolutionEdge] = []
    candidates: list[EvolutionEdge] = []
    unverified: list[EvolutionEdge] = []
    audit_rows: list[dict[str, Any]] = []

    for edge in edges:
        audit = audit_edge_evidence(edge, doc_map, config)
        edge.evidence = _evidence_with_audit(edge.evidence, audit)
        edge.substring_verified = bool(audit["verified_quote_count"] > 0)
        status = audit["status"]
        if status == "trusted":
            trusted.append(edge)
        elif status == "candidate":
            candidates.append(edge)
        else:
            unverified.append(edge)
        audit_rows.append(audit)

    return trusted, candidates, unverified, audit_rows


def audit_edge_evidence(
    edge: EvolutionEdge,
    doc_map: dict[str, Document],
    config: GraphConfig,
) -> dict[str, Any]:
    source_text = _doc_text(doc_map.get(edge.source_document))
    target_text = _doc_text(doc_map.get(edge.target_document))
    quote_checks: list[dict[str, Any]] = []
    verified_fields: list[str] = []
    missing_fields: list[str] = []

    for field in _audit_fields(edge):
        value = (edge.evidence or {}).get(field) or {}
        quote = normalize_space(value.get("quote") if isinstance(value, dict) else "")
        description = normalize_space(value.get("description") if isinstance(value, dict) else "")
        if not quote:
            missing_fields.append(field)
            quote_checks.append(
                {
                    "field": field,
                    "quote": "",
                    "description": description,
                    "verified": False,
                    "matched_document": "",
                    "reason": "missing_quote",
                }
            )
            continue
        source_verified = validate_evidence_quote(quote, source_text)
        target_verified = validate_evidence_quote(quote, target_text)
        substring_verified = source_verified or target_verified
        grounding = _quote_relation_grounding(quote, edge, config)
        verified = substring_verified and grounding["relation_supported"]
        matched_document = ""
        if target_verified:
            matched_document = edge.target_document
        elif source_verified:
            matched_document = edge.source_document
        if verified:
            verified_fields.append(field)
        quote_checks.append(
            {
                "field": field,
                "quote": quote,
                "description": description,
                "verified": verified,
                "substring_verified": substring_verified,
                "relation_supported": grounding["relation_supported"],
                "entity_token_hits": grounding["entity_token_hits"],
                "relation_cue_hit": grounding["relation_cue_hit"],
                "matched_document": matched_document,
                "reason": _quote_check_reason(substring_verified, grounding["relation_supported"]),
            }
        )

    verified_quote_count = len(verified_fields)
    status, reason = _edge_status(edge, verified_quote_count, config)
    return {
        "edge_id": edge.edge_id,
        "source_entity": edge.source_entity,
        "target_entity": edge.target_entity,
        "edge_type": edge.edge_type,
        "source_document": edge.source_document,
        "target_document": edge.target_document,
        "confidence": edge.confidence,
        "status": status,
        "reason": reason,
        "verified_quote_fields": verified_fields,
        "missing_quote_fields": missing_fields,
        "verified_quote_count": verified_quote_count,
        "quote_checks": quote_checks,
    }


def _edge_status(edge: EvolutionEdge, verified_quote_count: int, config: GraphConfig) -> tuple[str, str]:
    if edge.edge_type not in set(config.strong_edge_types):
        if edge.confidence >= config.candidate_edge_confidence_threshold:
            return "candidate", "weak_or_non_strong_edge_type"
        return "unverified", "low_confidence_non_strong_edge_type"

    has_verified_evidence = verified_quote_count > 0
    if edge.confidence >= config.trusted_edge_confidence_threshold:
        if has_verified_evidence or not config.require_verified_evidence_for_trusted:
            return "trusted", "strong_edge_with_verified_evidence"
        return "candidate", "strong_edge_needs_relation_grounding"

    if edge.confidence >= config.candidate_edge_confidence_threshold:
        return "candidate", "below_trusted_confidence_threshold"
    return "unverified", "below_candidate_confidence_threshold"


def _evidence_with_audit(evidence: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    updated = deepcopy(evidence or {})
    updated["evidence_audit"] = {
        "status": audit["status"],
        "reason": audit["reason"],
        "verified_quote_fields": audit["verified_quote_fields"],
        "verified_quote_count": audit["verified_quote_count"],
    }
    return updated


def _doc_text(doc: Document | None) -> str:
    return doc.full_text if doc else ""


def _audit_fields(edge: EvolutionEdge) -> list[str]:
    fields = list((edge.evidence or {}).get("schema_slots") or [])
    for field in EVIDENCE_FIELDS:
        if field not in fields:
            fields.append(field)
    return fields


def _quote_check_reason(substring_verified: bool, relation_supported: bool) -> str:
    if substring_verified and relation_supported:
        return "quote_verified_relation_supported"
    if substring_verified:
        return "quote_found_but_relation_not_supported"
    return "quote_not_found_in_source_or_target"


def _quote_relation_grounding(quote: str, edge: EvolutionEdge, config: GraphConfig) -> dict[str, Any]:
    quote_tokens = set(_tokens(quote))
    if not quote_tokens:
        return {"relation_supported": False, "entity_token_hits": [], "relation_cue_hit": False}

    source_hits = _entity_token_hits(edge.source_entity, quote_tokens)
    target_hits = _entity_token_hits(edge.target_entity, quote_tokens)
    entity_hits = []
    if source_hits:
        entity_hits.append("source")
    if target_hits:
        entity_hits.append("target")

    cue = str((edge.evidence or {}).get("cue") or "")
    relation_cue_hit = bool(_relation_cue_hit(quote_tokens, edge.edge_type, cue))
    relation_supported = _relation_supported_by_mode(
        mode=config.quote_relation_grounding_mode,
        entity_hit_count=len(entity_hits),
        relation_cue_hit=relation_cue_hit,
    )
    return {
        "relation_supported": relation_supported,
        "entity_token_hits": entity_hits,
        "relation_cue_hit": relation_cue_hit,
    }


def _relation_supported_by_mode(*, mode: str, entity_hit_count: int, relation_cue_hit: bool) -> bool:
    if mode == "substring":
        return True
    if mode == "two_sided_cue":
        return entity_hit_count >= 2 and relation_cue_hit
    return entity_hit_count >= 1 and relation_cue_hit


def _entity_token_hits(entity_id: str, quote_tokens: set[str]) -> list[str]:
    entity_tokens = [token for token in _tokens(_entity_name_from_id(entity_id)) if token not in _weak_entity_tokens()]
    if not entity_tokens:
        return []
    hits = [token for token in entity_tokens if token in quote_tokens]
    if len(entity_tokens) == 1:
        return hits if hits else []
    needed = min(2, len(set(entity_tokens)))
    return hits if len(set(hits)) >= needed else []


def _entity_name_from_id(entity_id: str) -> str:
    value = str(entity_id or "")
    if "__" in value:
        value = value.split("__", 1)[1]
    return value.replace("_", " ")


def _relation_cue_hit(quote_tokens: set[str], edge_type: str, cue: str) -> bool:
    relation_terms = set(_tokens(cue))
    relation_terms.update(_edge_type_terms(edge_type))
    if not relation_terms:
        return False
    return bool(quote_tokens & relation_terms)


def _edge_type_terms(edge_type: str) -> set[str]:
    return {
        "adapts": {"adapt", "adapts", "adapted", "apply", "applies", "applied", "application", "transfer", "port", "ports", "specializ", "specialize", "specializes", "specialized"},
        "combines": {"combine", "combines", "combined", "integrate", "integrates", "integrated", "hybrid", "joint"},
        "compares": {"compare", "compares", "compared", "versus", "vs", "baseline", "contrast"},
        "enables": {"enable", "enables", "enabled", "support", "supports", "provide", "provides", "allow", "allows"},
        "extends": {"extend", "extends", "extended", "augment", "augments", "build", "builds", "incorporate", "incorporates"},
        "improves": {"advantage", "advantages", "compared", "efficient", "efficiency", "feasible", "faster", "better", "improve", "improves", "improved", "outperform", "outperforms", "enhance", "enhances"},
        "operationalizes": {"operationalize", "operationalizes", "measure", "measures", "code", "codes", "annotate", "annotates", "detect", "detects", "extract", "extracts"},
        "replaces": {"replace", "replaces", "replaced", "instead", "substitute", "substitutes", "supersede", "supersedes"},
        "uses_component": {"use", "uses", "using", "based", "component", "module", "integrate", "integrates"},
        "validates": {"assess", "assesses", "benchmark", "benchmarks", "evaluate", "evaluates", "finite", "performance", "replicate", "replicates", "study", "test", "tests", "validate", "validates", "validated"},
    }.get(str(edge_type or ""), set())


def _tokens(value: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", str(value or "").lower())
    return [_normalize_token(token) for token in tokens if len(token) > 2]


def _normalize_token(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("s") and len(token) > 3:
        return token[:-1]
    if token.endswith("ed") and len(token) > 4:
        return token[:-2]
    if token.endswith("ing") and len(token) > 5:
        return token[:-3]
    return token


def _weak_entity_tokens() -> set[str]:
    return {
        "analysis",
        "base",
        "data",
        "evidence",
        "method",
        "model",
        "practice",
        "research",
        "science",
        "social",
        "strategy",
        "system",
        "tooling",
        "validation",
    }
