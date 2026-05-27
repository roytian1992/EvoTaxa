from __future__ import annotations

from typing import Any


def score_forecast_hooks(hooks: list[dict[str, Any]], edge_index: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for hook in hooks:
        support_edges = [edge_index[edge_id] for edge_id in hook.get("support_edges", []) if edge_id in edge_index]
        evidence_strength = _mean([float(edge.get("confidence") or 0.0) for edge in support_edges])
        verified_rate = _mean([1.0 if edge.get("substring_verified") else 0.0 for edge in support_edges])
        chain_len = len(hook.get("evolution_chain") or [])
        bottleneck_openness = 1.0 if hook.get("root_bottleneck") else 0.4
        branch_maturity = min(1.0, len(support_edges) / 5.0)
        tradeoff_risk = 0.7 if hook.get("risk_or_tradeoff") else 0.3
        score = (
            0.28 * evidence_strength
            + 0.22 * verified_rate
            + 0.18 * min(1.0, chain_len / 4.0)
            + 0.14 * bottleneck_openness
            + 0.12 * branch_maturity
            - 0.06 * tradeoff_risk
        )
        row = dict(hook)
        row["scores"] = {
            "evidence_strength": round(evidence_strength, 3),
            "verified_rate": round(verified_rate, 3),
            "lineage_depth": round(min(1.0, chain_len / 4.0), 3),
            "bottleneck_openness": round(bottleneck_openness, 3),
            "branch_maturity": round(branch_maturity, 3),
            "tradeoff_risk": round(tradeoff_risk, 3),
            "hook_score": round(max(0.0, min(1.0, score)), 3),
        }
        row["confidence"] = max(float(row.get("confidence") or 0.0), row["scores"]["hook_score"])
        scored.append(row)
    return sorted(scored, key=lambda item: (-item["scores"]["hook_score"], item["hook_id"]))


def build_hook_score_report(scored_hooks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "hook_count": len(scored_hooks),
        "top_hooks": [
            {
                "hook_id": hook["hook_id"],
                "hook_type": hook["hook_type"],
                "hook_score": hook["scores"]["hook_score"],
                "taxonomy_node": hook.get("taxonomy_node", ""),
            }
            for hook in scored_hooks[:20]
        ],
        "mean_hook_score": round(_mean([hook["scores"]["hook_score"] for hook in scored_hooks]), 3),
    }


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)

