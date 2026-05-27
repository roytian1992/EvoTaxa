from __future__ import annotations

from copy import deepcopy
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
        verified = source_verified or target_verified
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
                "matched_document": matched_document,
                "reason": "quote_verified" if verified else "quote_not_found_in_source_or_target",
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
        return "candidate", "strong_edge_needs_quote_verification"

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
