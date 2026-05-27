from __future__ import annotations

from collections import Counter
from typing import Any


def build_quality_report(
    *,
    node_quality: list[Any],
    entity_quality_report: list[dict[str, Any]],
    edge_evidence_audit: list[dict[str, Any]],
    hook_score_report: dict[str, Any],
    feedback_rows: list[dict[str, Any]],
    expansion_application_report: list[dict[str, Any]],
    revision_application_report: list[dict[str, Any]],
    llm_records: list[Any],
) -> dict[str, Any]:
    taxonomy_scores = _taxonomy_scores(node_quality)
    entity_scores = _entity_scores(entity_quality_report)
    edge_scores = _edge_scores(edge_evidence_audit)
    coevolution_scores = _coevolution_scores(feedback_rows, expansion_application_report, revision_application_report)
    llm_scores = _llm_scores(llm_records)
    hook_scores = _hook_scores(hook_score_report)
    dimensions = {
        "taxonomy": taxonomy_scores["score"],
        "entity_layer": entity_scores["score"],
        "edge_evidence": edge_scores["score"],
        "coevolution": coevolution_scores["score"],
        "forecast_hooks": hook_scores["score"],
        "llm_reliability": llm_scores["score"],
    }
    overall = round(sum(dimensions.values()) / max(1, len(dimensions)), 3)
    return {
        "overall_quality_score": overall,
        "dimension_scores": dimensions,
        "taxonomy": taxonomy_scores,
        "entity_layer": entity_scores,
        "edge_evidence": edge_scores,
        "coevolution": coevolution_scores,
        "forecast_hooks": hook_scores,
        "llm_reliability": llm_scores,
        "recommendations": _recommendations(taxonomy_scores, entity_scores, edge_scores, coevolution_scores, hook_scores, llm_scores),
    }


def _taxonomy_scores(rows: list[Any]) -> dict[str, Any]:
    metric_names = [
        "dimension_alignment",
        "granularity",
        "sibling_coherence",
        "uniqueness",
        "paper_relevance",
        "coverage",
        "temporal_stability",
        "boundary_clarity",
    ]
    metrics = {
        metric: round(_mean([float(getattr(row, metric, 0.0)) for row in rows]), 3)
        for metric in metric_names
    }
    notes = Counter(getattr(row, "judge_notes", "") for row in rows if getattr(row, "judge_notes", ""))
    return {
        "score": round(_mean(list(metrics.values())), 3),
        "node_count": len(rows),
        "metrics": metrics,
        "notes": dict(notes),
    }


def _entity_scores(rows: list[dict[str, Any]]) -> dict[str, Any]:
    kept = [row for row in rows if row.get("status") == "kept"]
    filtered = [row for row in rows if row.get("status") == "filtered"]
    qualities = [float(row.get("quality") or 0.0) for row in kept]
    kept_rate = len(kept) / max(1, len(rows))
    score = 0.6 * _mean(qualities) + 0.4 * kept_rate
    return {
        "score": round(score, 3),
        "kept_entities": len(kept),
        "filtered_entities": len(filtered),
        "kept_rate": round(kept_rate, 3),
        "mean_kept_quality": round(_mean(qualities), 3),
        "top_filter_reasons": dict(Counter(reason for row in filtered for reason in row.get("reasons", [])).most_common(10)),
    }


def _edge_scores(rows: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("status") or "unknown") for row in rows)
    trusted_rate = statuses.get("trusted", 0) / max(1, len(rows))
    candidate_rate = statuses.get("candidate", 0) / max(1, len(rows))
    unverified_rate = statuses.get("unverified", 0) / max(1, len(rows))
    quote_rate = _mean([min(1.0, float(row.get("verified_quote_count") or 0.0) / 3.0) for row in rows])
    confidence = _mean([float(row.get("confidence") or 0.0) for row in rows])
    score = 0.45 * trusted_rate + 0.25 * quote_rate + 0.2 * confidence + 0.1 * (1.0 - unverified_rate)
    return {
        "score": round(score, 3),
        "edge_count": len(rows),
        "status_counts": dict(statuses),
        "trusted_rate": round(trusted_rate, 3),
        "candidate_rate": round(candidate_rate, 3),
        "unverified_rate": round(unverified_rate, 3),
        "mean_quote_field_coverage": round(quote_rate, 3),
        "mean_confidence": round(confidence, 3),
    }


def _coevolution_scores(
    feedback_rows: list[dict[str, Any]],
    expansion_application_report: list[dict[str, Any]],
    revision_application_report: list[dict[str, Any]],
) -> dict[str, Any]:
    expansions_applied = sum(1 for row in expansion_application_report if row.get("status") == "applied")
    revisions_applied = sum(1 for row in revision_application_report if row.get("status") == "applied")
    actionable_feedback = sum(1 for row in feedback_rows if row.get("recommendations") and row.get("recommendations") != ["monitor"])
    action_rate = actionable_feedback / max(1, len(feedback_rows))
    revision_yield = revisions_applied / max(1, len(revision_application_report))
    expansion_yield = expansions_applied / max(1, len(expansion_application_report))
    score = 0.35 * action_rate + 0.35 * revision_yield + 0.3 * expansion_yield
    return {
        "score": round(score, 3),
        "feedback_rows": len(feedback_rows),
        "actionable_feedback_rows": actionable_feedback,
        "action_rate": round(action_rate, 3),
        "expansions_applied": expansions_applied,
        "expansion_yield": round(expansion_yield, 3),
        "revisions_applied": revisions_applied,
        "revision_yield": round(revision_yield, 3),
    }


def _hook_scores(report: dict[str, Any]) -> dict[str, Any]:
    hook_count = int(report.get("hook_count") or 0)
    mean_score = float(report.get("mean_hook_score") or 0.0)
    score = mean_score if hook_count else 0.0
    return {
        "score": round(score, 3),
        "hook_count": hook_count,
        "mean_hook_score": round(mean_score, 3),
        "top_hook_count": len(report.get("top_hooks") or []),
    }


def _llm_scores(records: list[Any]) -> dict[str, Any]:
    if not records:
        return {
            "score": 1.0,
            "record_count": 0,
            "used_model_count": 0,
            "schema_valid_rate": 1.0,
            "error_count": 0,
            "cache_hit_rate": 0.0,
        }
    schema_valid_rate = _mean([1.0 if getattr(record, "schema_valid", False) else 0.0 for record in records])
    error_count = sum(1 for record in records if _blocking_error(record))
    error_rate = error_count / max(1, len(records))
    cache_hit_rate = _mean([1.0 if getattr(record, "cache_hit", False) else 0.0 for record in records])
    used_model_count = sum(1 for record in records if getattr(record, "used_model", False))
    score = 0.7 * schema_valid_rate + 0.3 * (1.0 - error_rate)
    return {
        "score": round(score, 3),
        "record_count": len(records),
        "used_model_count": used_model_count,
        "schema_valid_rate": round(schema_valid_rate, 3),
        "error_count": error_count,
        "cache_hit_rate": round(cache_hit_rate, 3),
    }


def _blocking_error(record: Any) -> bool:
    error = str(getattr(record, "error", "") or "")
    if not error:
        return False
    return error != "No LLM tasks enabled."


def _recommendations(*sections: dict[str, Any]) -> list[str]:
    recommendations: list[str] = []
    section_names = ["taxonomy", "entity_layer", "edge_evidence", "coevolution", "forecast_hooks", "llm_reliability"]
    for name, section in zip(section_names, sections):
        if float(section.get("score") or 0.0) < 0.55:
            recommendations.append(f"review_{name}")
    if not recommendations:
        recommendations.append("ready_for_larger_corpus_or_gold_evaluation")
    return recommendations


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
