from __future__ import annotations

from collections import Counter
from typing import Any


def build_case_study_report(
    *,
    manifest: dict[str, Any],
    schema_revisions: list[dict[str, Any]],
    relation_rejections: list[dict[str, Any]],
    forecast_hooks: list[dict[str, Any]],
) -> str:
    counts = manifest.get("counts") or {}
    rejection_reasons = Counter(str(row.get("rejection_reason") or "unknown") for row in relation_rejections)
    revision_types = Counter(str(row.get("revision_type") or "unknown") for row in schema_revisions)
    hook_types = Counter(str(row.get("hook_type") or "unknown") for row in forecast_hooks)
    lines = [
        "# EvoTaxa Social Science Case Study",
        "",
        "## Run Summary",
        "",
        f"- Domain: `{(manifest.get('project') or {}).get('domain_id', '')}`",
        f"- Mode: `{manifest.get('mode', '')}`",
        f"- Documents: {counts.get('documents', 0)}",
        f"- Taxonomy nodes: {counts.get('taxonomy_nodes', 0)}",
        f"- Entities: {counts.get('entities', 0)}",
        f"- Trusted edges: {counts.get('trusted_edges', 0)}",
        f"- Forecast/social hooks: {counts.get('forecast_hooks', 0)} / {counts.get('social_analysis_hooks', 0)}",
        "",
        "## Adaptive Schema",
        "",
        f"- Entity schema types: {counts.get('entity_schema_types', 0)}",
        f"- Relation schema types: {counts.get('relation_schema_types', 0)}",
        f"- Evidence slots: {counts.get('evidence_schema_slots', 0)}",
        f"- Revision candidates: {counts.get('schema_revision_candidates', 0)}",
        f"- Promoted/reported revisions: {counts.get('schema_revisions', 0)}",
        f"- Revision types: {_format_counter(revision_types)}",
        "",
        "## Relation Extraction Audit",
        "",
        f"- Schema-guided relation pairs: {counts.get('llm_relation_pairs', 0)}",
        f"- Schema-guided accepted edges: {counts.get('llm_relation_edges', 0)}",
        f"- Rejected pairs: {counts.get('relation_rejections', len(relation_rejections))}",
        f"- Rejection reasons: {_format_counter(rejection_reasons)}",
        "",
        "## Hook Distribution",
        "",
        f"- Hook types: {_format_counter(hook_types)}",
        "",
        "## Artifact Pointers",
        "",
        "- `schema/schema_revision_candidates.jsonl`",
        "- `schema/*_schema.revisions.jsonl`",
        "- `graph/relation_extraction_report.jsonl`",
        "- `graph/relation_rejections.jsonl`",
        "- `graph/edge_scores.jsonl`",
        "- `hooks/social_analysis_hooks.jsonl`",
        "",
    ]
    return "\n".join(lines)


def _format_counter(counter: Counter[str]) -> str:
    if not counter:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in sorted(counter.items()))
