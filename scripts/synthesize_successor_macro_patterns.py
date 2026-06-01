#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from evotaxa.io import iter_jsonl, normalize_space, parse_date, write_json, write_jsonl  # noqa: E402


PATTERN_SPECS: dict[str, dict[str, str]] = {
    "differentiation": {
        "label": "Differentiation",
        "definition": "An existing method, evidence object, or practice branches into multiple more specific successor lines; useful for finding where a broad technique becomes a family of domain- or task-specific variants.",
    },
    "convergence": {
        "label": "Convergence",
        "definition": "Multiple predecessor lines feed into a shared successor, method family, or evidential target; useful for seeing where formerly separate techniques become consolidated into one framing.",
    },
    "hybridization": {
        "label": "Hybridization",
        "definition": "Evolution crosses original node types or combines multiple method, measurement, data, and governance roles within a schema group; useful for seeing method changes that are coupled to measurement, data, or modeling changes.",
    },
    "recontextualization": {
        "label": "Recontextualization",
        "definition": "A method or measurement practice is adapted into a new domain, platform, data context, or social-science use setting; useful for seeing when the same tool gains a new empirical meaning.",
    },
    "cyclical_return": {
        "label": "Cyclical Return",
        "definition": "Earlier concepts recur after a long gap through renewed successor edges or long-span trajectories; useful for identifying older ideas revived by new data, models, or problem settings.",
    },
    "institutionalization": {
        "label": "Institutionalization",
        "definition": "Methods become stabilized through benchmarks, validation protocols, governance practices, reproducibility, or standardization signals; useful for seeing when a method becomes an accepted evaluative or operational routine.",
    },
    "substitution": {
        "label": "Substitution",
        "definition": "Newer methods or practices explicitly replace older ones; useful for finding points where the literature frames a new practice as displacing manual, older, or less capable approaches.",
    },
    "fragmentation": {
        "label": "Fragmentation",
        "definition": "A node or local area splits into many weakly connected specialized successor branches; useful for finding local areas where a common ancestor no longer has one dominant successor line.",
    },
    "stabilization": {
        "label": "Stabilization",
        "definition": "A relation or trajectory is supported by high-confidence, quote-grounded, temporally coherent strict successor evidence; useful for separating stable micro-evolution from isolated candidate links.",
    },
}

PATTERN_LABEL_ZH = {
    "differentiation": "分化",
    "convergence": "汇聚",
    "hybridization": "混合",
    "recontextualization": "重新语境化",
    "cyclical_return": "循环回归",
    "institutionalization": "制度化",
    "substitution": "替代",
    "fragmentation": "碎片化",
    "stabilization": "稳定化",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Synthesize detector-backed macro patterns from strict successor EvoTaxa artifacts."
    )
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--min-pattern-score", type=float, default=0.2)
    parser.add_argument("--max-patterns", type=int, default=20)
    parser.add_argument("--max-evidence-per-pattern", type=int, default=12)
    args = parser.parse_args()

    run_root = args.run_root.expanduser().resolve()
    result = synthesize_successor_macro_patterns(
        run_root,
        min_pattern_score=args.min_pattern_score,
        max_patterns=args.max_patterns,
        max_evidence_per_pattern=args.max_evidence_per_pattern,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


def synthesize_successor_macro_patterns(
    run_root: Path,
    *,
    min_pattern_score: float,
    max_patterns: int,
    max_evidence_per_pattern: int,
) -> dict[str, Any]:
    cards = {str(row.get("entity_id") or ""): row for row in read_jsonl(run_root / "graph" / "entity_cards.jsonl") if row.get("entity_id")}
    edges = read_jsonl(run_root / "graph" / "successor_edges.accepted.jsonl")
    trajectories = read_jsonl(run_root / "trajectory" / "successor_trajectories.jsonl")
    docs = {str(row.get("doc_id") or ""): row for row in read_jsonl(run_root / "corpus" / "documents.normalized.jsonl") if row.get("doc_id")}
    features = build_features(edges=edges, trajectories=trajectories, cards=cards, docs=docs)
    profiles = build_profiles(
        features,
        min_pattern_score=min_pattern_score,
        max_patterns=max_patterns,
        max_evidence_per_pattern=max_evidence_per_pattern,
    )
    profile_ids = {str(row.get("pattern_id") or "") for row in profiles}
    evidence_records = [
        feature_to_evidence(row)
        for row in features
        if any(pattern_id in profile_ids for pattern_id in row.get("pattern_scores", {}))
    ]
    timeline = build_timeline(features, profile_ids)
    output_root = run_root / "macro_patterns"
    output_root.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_root / "pattern_profiles.jsonl", profiles)
    write_jsonl(output_root / "pattern_evidence.jsonl", evidence_records)
    write_jsonl(output_root / "pattern_timeline.jsonl", timeline)
    summary = {
        "enabled": True,
        "source": "strict_successor_artifacts",
        "candidate_pattern_count": len(PATTERN_SPECS),
        "reported_pattern_count": len(profiles),
        "evidence_record_count": len(evidence_records),
        "timeline_rows": len(timeline),
        "min_pattern_score": min_pattern_score,
        "successor_edges": len(edges),
        "successor_trajectories": len(trajectories),
        "entity_cards": len(cards),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": "Detector-backed macro synthesis from strict successor edges, materialized node cards, and successor trajectories. No LLM-generated patterns.",
    }
    write_json(output_root / "pattern_summary.json", summary)
    update_manifest_counts(run_root, summary)
    return {"profiles": profiles, "evidence_records": evidence_records, "timeline": timeline, "summary": summary}


def build_features(
    *,
    edges: list[dict[str, Any]],
    trajectories: list[dict[str, Any]],
    cards: dict[str, dict[str, Any]],
    docs: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    edge_by_id = {str(edge.get("edge_id") or ""): edge for edge in edges if edge.get("edge_id")}
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        outgoing[str(edge.get("source_entity") or "")].append(edge)
        incoming[str(edge.get("target_entity") or "")].append(edge)
        features.extend(edge_features(edge, cards, docs))
    for entity_id, rows in outgoing.items():
        if len(rows) >= 3:
            features.append(branching_feature(entity_id, rows, cards, docs))
    for entity_id, rows in incoming.items():
        if len(rows) >= 3:
            features.append(convergence_feature(entity_id, rows, cards, docs))
    for trajectory in trajectories:
        features.extend(trajectory_features(trajectory, edge_by_id, cards, docs))
    return [row for row in features if row]


def edge_features(edge: dict[str, Any], cards: dict[str, dict[str, Any]], docs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    edge_id = str(edge.get("edge_id") or edge.get("id") or "")
    if not edge_id:
        return []
    relation = str(edge.get("edge_type") or edge.get("type") or "")
    confidence = safe_float(edge.get("confidence"))
    source_id = str(edge.get("source_entity") or edge.get("source") or "")
    target_id = str(edge.get("target_entity") or edge.get("target") or "")
    source_card = cards.get(source_id) or {}
    target_card = cards.get(target_id) or {}
    patterns: dict[str, float] = {}
    if relation == "adapts":
        patterns["recontextualization"] = 0.68
    if relation == "replaces":
        patterns["substitution"] = 0.84
    if relation == "specializes":
        patterns["differentiation"] = 0.5
    if relation == "generalizes":
        patterns["convergence"] = 0.42
    if relation in {"extends", "improves", "specializes", "generalizes"} and confidence >= 0.88:
        patterns["stabilization"] = max(patterns.get("stabilization", 0.0), 0.34)
    if source_card.get("entity_type") and target_card.get("entity_type") and source_card.get("entity_type") != target_card.get("entity_type"):
        patterns["hybridization"] = max(patterns.get("hybridization", 0.0), 0.52)
    if cross_context(source_card, target_card):
        patterns["recontextualization"] = max(patterns.get("recontextualization", 0.0), 0.44)
    if institutional_signal(edge, source_card, target_card):
        patterns["institutionalization"] = max(patterns.get("institutionalization", 0.0), 0.58)
    delta_days = safe_int(edge.get("time_delta_days"))
    if delta_days >= 365 * 6:
        patterns["cyclical_return"] = max(patterns.get("cyclical_return", 0.0), 0.38)
    if not patterns:
        return []
    score = min(1.0, confidence + (0.05 if edge.get("substring_verified") else 0.0))
    return [
        feature(
            artifact_type="successor_edge",
            artifact_id=edge_id,
            signal_type=f"edge_type__{relation}",
            patterns=patterns,
            score=score,
            time_slice=edge_year(edge, docs),
            entity_ids=[source_id, target_id],
            entity_labels=[entity_name(source_id, cards), entity_name(target_id, cards)],
            trajectory_ids=[],
            evidence_ids=[edge_id],
            source={
                "edge_id": edge_id,
                "source_entity": source_id,
                "target_entity": target_id,
                "source_label": entity_name(source_id, cards),
                "target_label": entity_name(target_id, cards),
                "source_type": str(source_card.get("entity_type") or edge.get("source_entity_type") or ""),
                "target_type": str(target_card.get("entity_type") or edge.get("target_entity_type") or ""),
                "source_schema_group": str(source_card.get("schema_group") or edge.get("source_schema_group") or edge.get("schema_group") or ""),
                "target_schema_group": str(target_card.get("schema_group") or edge.get("target_schema_group") or edge.get("schema_group") or ""),
                "source_context": normalize_space(source_card.get("domain_context") or ""),
                "target_context": normalize_space(target_card.get("domain_context") or ""),
                "edge_type": relation,
                "confidence": confidence,
                "time_delta_days": delta_days,
                "quote": first_quote(edge),
            },
            explanation=f"Strict successor edge {relation!r} links {entity_name(source_id, cards)} to {entity_name(target_id, cards)}.",
        )
    ]


def branching_feature(
    entity_id: str,
    rows: list[dict[str, Any]],
    cards: dict[str, dict[str, Any]],
    docs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    edge_ids = [str(row.get("edge_id") or "") for row in rows if row.get("edge_id")]
    targets = [str(row.get("target_entity") or "") for row in rows if row.get("target_entity")]
    relation_counts = Counter(str(row.get("edge_type") or "") for row in rows)
    patterns = {"differentiation": 0.74, "fragmentation": 0.42 if len(rows) >= 5 else 0.24}
    return feature(
        artifact_type="successor_branch",
        artifact_id=f"successor_branch__{safe_id(entity_id)}",
        signal_type="outgoing_successor_branching",
        patterns=patterns,
        score=min(1.0, len(rows) / 8.0),
        time_slice=time_span([edge_year(row, docs) for row in rows]),
        entity_ids=[entity_id, *targets[:8]],
        entity_labels=[entity_name(entity_id, cards), *[entity_name(target, cards) for target in targets[:8]]],
        trajectory_ids=[],
        evidence_ids=edge_ids[:16],
        source={"source_entity": entity_id, "outgoing_count": len(rows), "relation_counts": dict(relation_counts), "edge_ids": edge_ids[:16]},
        explanation=f"{entity_name(entity_id, cards)} has {len(rows)} strict successor branches.",
    )


def convergence_feature(
    entity_id: str,
    rows: list[dict[str, Any]],
    cards: dict[str, dict[str, Any]],
    docs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    edge_ids = [str(row.get("edge_id") or "") for row in rows if row.get("edge_id")]
    sources = [str(row.get("source_entity") or "") for row in rows if row.get("source_entity")]
    relation_counts = Counter(str(row.get("edge_type") or "") for row in rows)
    return feature(
        artifact_type="successor_convergence",
        artifact_id=f"successor_convergence__{safe_id(entity_id)}",
        signal_type="incoming_successor_convergence",
        patterns={"convergence": 0.78, "hybridization": 0.34 if cross_type_edges(rows, cards) else 0.0},
        score=min(1.0, len(rows) / 8.0),
        time_slice=time_span([edge_year(row, docs) for row in rows]),
        entity_ids=[*sources[:8], entity_id],
        entity_labels=[*[entity_name(source, cards) for source in sources[:8]], entity_name(entity_id, cards)],
        trajectory_ids=[],
        evidence_ids=edge_ids[:16],
        source={"target_entity": entity_id, "incoming_count": len(rows), "relation_counts": dict(relation_counts), "edge_ids": edge_ids[:16]},
        explanation=f"{len(rows)} predecessor lines converge on {entity_name(entity_id, cards)}.",
    )


def trajectory_features(
    trajectory: dict[str, Any],
    edge_by_id: dict[str, dict[str, Any]],
    cards: dict[str, dict[str, Any]],
    docs: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    edge_ids = [str(edge_id) for edge_id in trajectory.get("edge_path") or [] if str(edge_id)]
    trajectory_edges = [edge_by_id[edge_id] for edge_id in edge_ids if edge_id in edge_by_id]
    if not trajectory_edges:
        return []
    relation_types = [str(edge.get("edge_type") or "") for edge in trajectory_edges]
    entity_path = [str(entity_id) for entity_id in trajectory.get("entity_path") or [] if str(entity_id)]
    patterns: dict[str, float] = {}
    if len(set(relation_types)) >= 2:
        patterns["hybridization"] = 0.48
    if any(relation == "adapts" for relation in relation_types):
        patterns["recontextualization"] = max(patterns.get("recontextualization", 0.0), 0.62)
    if any(relation == "replaces" for relation in relation_types):
        patterns["substitution"] = max(patterns.get("substitution", 0.0), 0.72)
    entity_types = {str((cards.get(entity_id) or {}).get("entity_type") or "") for entity_id in entity_path}
    entity_types.discard("")
    schema_groups = {str((cards.get(entity_id) or {}).get("schema_group") or "") for entity_id in entity_path}
    schema_groups.discard("")
    if len(entity_types) >= 2:
        patterns["hybridization"] = max(patterns.get("hybridization", 0.0), 0.56)
    if int(trajectory.get("path_length") or len(edge_ids)) >= 2 and safe_float(trajectory.get("temporal_coherence")) >= 0.9:
        patterns["stabilization"] = max(patterns.get("stabilization", 0.0), 0.32)
    if not patterns:
        return []
    trajectory_id = str(trajectory.get("trajectory_id") or "")
    return [
        feature(
            artifact_type="successor_trajectory",
            artifact_id=trajectory_id,
            signal_type="trajectory_shape",
            patterns=patterns,
            score=safe_float(trajectory.get("trajectory_score")),
            time_slice=time_span([edge_year(edge, docs) for edge in trajectory_edges]),
            entity_ids=entity_path,
            entity_labels=[entity_name(entity_id, cards) for entity_id in entity_path],
            trajectory_ids=[trajectory_id],
            evidence_ids=[trajectory_id, *edge_ids],
            source={
                "trajectory_id": trajectory_id,
                "entity_path": entity_path,
                "entity_labels": [entity_name(entity_id, cards) for entity_id in entity_path],
                "edge_path": edge_ids,
                "edge_types": relation_types,
                "entity_types": sorted(entity_types),
                "schema_groups": sorted(schema_groups),
            },
            explanation="Successor trajectory shape and relation sequence support macro-pattern evidence.",
        )
    ]


def build_profiles(
    features: list[dict[str, Any]],
    *,
    min_pattern_score: float,
    max_patterns: int,
    max_evidence_per_pattern: int,
) -> list[dict[str, Any]]:
    profiles = []
    for pattern_id, spec in PATTERN_SPECS.items():
        rows = [row for row in features if pattern_id in row.get("pattern_scores", {})]
        weighted = [safe_float(row.get("score")) * safe_float(row.get("pattern_scores", {}).get(pattern_id)) for row in rows]
        score = clamp(mean(weighted) + min(0.35, 0.035 * len(rows)))
        if score < min_pattern_score:
            continue
        top_rows = sorted(
            rows,
            key=lambda row: (
                -safe_float(row.get("score")) * safe_float(row.get("pattern_scores", {}).get(pattern_id)),
                str(row.get("artifact_id") or ""),
            ),
        )[: max(1, max_evidence_per_pattern)]
        trajectory_rows = [
            row
            for row in sorted(
                rows,
                key=lambda row: (
                    -safe_float(row.get("score")) * safe_float(row.get("pattern_scores", {}).get(pattern_id)),
                    str(row.get("artifact_id") or ""),
                ),
            )
            if row.get("trajectory_ids")
        ]
        representative_trajectory_ids = dedupe(
            traj for row in trajectory_rows for traj in row.get("trajectory_ids", [])
        )[:10]
        representative_node_ids = dedupe(entity_id for row in top_rows for entity_id in row.get("entity_ids", []))
        for row in trajectory_rows[: max_evidence_per_pattern]:
            representative_node_ids.extend(
                entity_id
                for entity_id in row.get("entity_ids", [])
                if entity_id not in representative_node_ids
            )
        representative_node_labels = dedupe(label for row in top_rows for label in row.get("entity_labels", []))
        for row in trajectory_rows[: max_evidence_per_pattern]:
            representative_node_labels.extend(
                label
                for label in row.get("entity_labels", [])
                if label not in representative_node_labels
            )
        evidence_ids = dedupe(evidence_id for row in top_rows for evidence_id in row.get("evidence_ids", []))
        for trajectory_id in representative_trajectory_ids:
            if trajectory_id not in evidence_ids:
                evidence_ids.append(trajectory_id)
        insight = profile_insight(
            pattern_id=pattern_id,
            score=score,
            rows=rows,
            top_rows=top_rows,
            representative_nodes=representative_node_labels,
            representative_trajectories=representative_trajectory_ids,
        )
        profiles.append(
            {
                "pattern_id": pattern_id,
                "pattern_label": spec["label"],
                "definition": spec["definition"],
                "insight": insight["insight"],
                "analytic_note": insight["analytic_note"],
                "interpretation_caveat": insight["interpretation_caveat"],
                "dominant_signals": insight["dominant_signals"],
                "dominant_artifacts": insight["dominant_artifacts"],
                "dominant_relations": insight["dominant_relations"],
                "dominant_type_transitions": insight["dominant_type_transitions"],
                "dominant_schema_groups": insight["dominant_schema_groups"],
                "temporal_hotspots": insight["temporal_hotspots"],
                "representative_evidence": insight["representative_evidence"],
                "pattern_score": round(score, 3),
                "time_span": time_span([str(row.get("time_slice") or "") for row in rows]),
                "representative_node_ids": representative_node_ids[:10],
                "representative_nodes": representative_node_labels[:10],
                "representative_trajectories": representative_trajectory_ids,
                "evidence_ids": evidence_ids[:24],
                "evidence_count": len(dedupe(evidence_id for row in rows for evidence_id in row.get("evidence_ids", []))),
                "supporting_signal_count": len(rows),
                "explanation": explanation(pattern_id, score, rows),
                "llm_summary_used": False,
            }
        )
    profiles.sort(key=lambda row: (-safe_float(row.get("pattern_score")), str(row.get("pattern_id") or "")))
    return profiles[:max_patterns] if max_patterns > 0 else profiles


def profile_insight(
    *,
    pattern_id: str,
    score: float,
    rows: list[dict[str, Any]],
    top_rows: list[dict[str, Any]],
    representative_nodes: list[str],
    representative_trajectories: list[str],
) -> dict[str, Any]:
    total = max(1, len(rows))
    signal_counter = Counter(str(row.get("signal_type") or "unknown") for row in rows)
    artifact_counter = Counter(str(row.get("artifact_type") or "unknown") for row in rows)
    relation_counter: Counter[str] = Counter()
    type_transition_counter: Counter[str] = Counter()
    schema_group_counter: Counter[str] = Counter()
    hotspot_scores: dict[str, list[float]] = defaultdict(list)

    for row in rows:
        source = row.get("source") if isinstance(row.get("source"), dict) else {}
        for relation in relation_values(source):
            relation_counter[relation] += 1
        type_transition = type_transition_value(source)
        if type_transition:
            type_transition_counter[type_transition] += 1
        schema_group = schema_group_value(source)
        if schema_group:
            schema_group_counter[schema_group] += 1
        time_slice = str(row.get("time_slice") or "unspecified")
        hotspot_scores[time_slice].append(safe_float(row.get("score")) * safe_float(row.get("pattern_scores", {}).get(pattern_id)))

    top_signal = top_count_rows(signal_counter, total, limit=5)
    top_artifact = top_count_rows(artifact_counter, total, limit=4)
    top_relation = top_count_rows(relation_counter, sum(relation_counter.values()) or total, limit=6)
    top_transition = top_count_rows(type_transition_counter, sum(type_transition_counter.values()) or total, limit=6)
    top_schema_group = top_count_rows(schema_group_counter, sum(schema_group_counter.values()) or total, limit=4)
    hotspots = sorted(
        (
            {
                "time_slice": time_slice,
                "count": len(scores),
                "mean_score": round(mean(scores), 3),
            }
            for time_slice, scores in hotspot_scores.items()
        ),
        key=lambda row: (-int(row["count"]), -safe_float(row["mean_score"]), str(row["time_slice"])),
    )[:6]
    representative_evidence = [representative_evidence_record(row, pattern_id) for row in top_rows[:8]]
    representative_evidence = [row for row in representative_evidence if row]
    node_phrase = natural_join(representative_nodes[:4])
    relation_phrase = natural_join([row["value"] for row in top_relation[:3]])
    signal_phrase = natural_join([row["value"] for row in top_signal[:3]])
    transition_phrase = natural_join([row["value"] for row in top_transition[:3]])
    hotspot_phrase = natural_join([row["time_slice"] for row in hotspots[:3]])
    insight = pattern_specific_insight(
        pattern_id=pattern_id,
        score=score,
        total=total,
        node_phrase=node_phrase,
        relation_phrase=relation_phrase,
        signal_phrase=signal_phrase,
        transition_phrase=transition_phrase,
        hotspot_phrase=hotspot_phrase,
        trajectory_count=len(representative_trajectories),
    )
    caveat = pattern_caveat(pattern_id, top_signal, top_transition)
    analytic_note = (
        f"检测器证据主要来自 {signal_phrase or '未指定信号'}"
        f"{f'；主导关系类型为 {relation_phrase}' if relation_phrase else ''}。"
        f"{f' 主要类型迁移为 {transition_phrase}。' if transition_phrase else ''}"
        f"{f' 证据最密集时间切片为 {hotspot_phrase}。' if hotspot_phrase else ''}"
    )
    return {
        "insight": insight,
        "analytic_note": analytic_note,
        "interpretation_caveat": caveat,
        "dominant_signals": top_signal,
        "dominant_artifacts": top_artifact,
        "dominant_relations": top_relation,
        "dominant_type_transitions": top_transition,
        "dominant_schema_groups": top_schema_group,
        "temporal_hotspots": hotspots,
        "representative_evidence": representative_evidence,
    }


def pattern_specific_insight(
    *,
    pattern_id: str,
    score: float,
    total: int,
    node_phrase: str,
    relation_phrase: str,
    signal_phrase: str,
    transition_phrase: str,
    hotspot_phrase: str,
    trajectory_count: int,
) -> str:
    label = PATTERN_LABEL_ZH.get(pattern_id, PATTERN_SPECS[pattern_id]["label"])
    prefix = f"{label}由 {total} 条检测器支持的严格演化信号支撑，模式分为 {score:.3f}。"
    nodes = f" 代表节点包括 {node_phrase}。" if node_phrase else ""
    times = f" 证据最密集的时间切片是 {hotspot_phrase}。" if hotspot_phrase else ""
    trajectories = f" 当前绑定了 {trajectory_count} 条代表性 successor trajectory。" if trajectory_count else ""
    if pattern_id == "substitution":
        return (
            f"{prefix} 主要信号是显式替代：较新的标注、建模、数据或验证实践被文献表述为取代旧做法，"
            f"主导关系包括 {relation_phrase or signal_phrase}。{nodes}{times}{trajectories}"
        )
    if pattern_id == "institutionalization":
        return (
            f"{prefix} 它不是单纯的新方法发明，而是方法逐渐变得可评价、可基准化、可审计或协议化。{nodes}{times}"
        )
    if pattern_id == "recontextualization":
        return (
            f"{prefix} 核心运动是方法在新经验语境中的复用：相似方法对象跨领域、平台或数据场景被重新使用，"
            f"常见关系包括 {relation_phrase or signal_phrase}。{nodes}{times}{trajectories}"
        )
    if pattern_id == "hybridization":
        return (
            f"{prefix} 有用信号是跨角色耦合：方法、建模、测量、数据或评估节点不是各自独立演化，而是一起变化。"
            f"主要类型迁移包括 {transition_phrase or '混合节点角色'}。{nodes}{times}{trajectories}"
        )
    if pattern_id == "differentiation":
        return (
            f"{prefix} 宽泛前身分出更具体的 successor，说明局部方法族正在围绕特定任务、工具或经验场景形成。{nodes}{times}"
        )
    if pattern_id == "convergence":
        return (
            f"{prefix} 多条前身线索指向共同 successor，说明若干方法族、标签或验证目标出现了综合和收束。{nodes}{times}"
        )
    if pattern_id == "cyclical_return":
        return (
            f"{prefix} 信号来自长时间间隔后的再出现：旧概念在新数据或新建模环境中重新变得有用。{nodes}{times}"
        )
    if pattern_id == "fragmentation":
        return (
            f"{prefix} 同一前身区域扇出到多条分支，局部文献呈现多元分裂，而不是收束到单一主导 successor。{nodes}{times}"
        )
    if pattern_id == "stabilization":
        return (
            f"{prefix} 信号来自高置信度、quote-grounded 的 successor 关系和时间一致轨迹，表示这些微观演化目前更适合解释。{nodes}{times}{trajectories}"
        )
    return f"{prefix}{nodes}{times}{trajectories}"


def pattern_caveat(pattern_id: str, top_signals: list[dict[str, Any]], top_transitions: list[dict[str, Any]]) -> str:
    signal_values = {str(row.get("value") or "") for row in top_signals}
    if pattern_id in {"hybridization", "recontextualization"}:
        return (
            "这是偏宽的检测器信号。需要点开关联边确认跨类型或跨语境变化是否有实质含义，而不只是 schema 标签变化。"
        )
    if pattern_id in {"differentiation", "fragmentation"} and "outgoing_successor_branching" in signal_values:
        return "这是分支局部模式：即使没有长链条 trajectory，只要一个前身扇出多条 successor，也可以成立。"
    if pattern_id == "convergence" and "incoming_successor_convergence" in signal_values:
        return "这是汇聚局部模式：需要检查多条 incoming predecessor edge，判断共同 successor 是真实综合还是宽泛标签。"
    if pattern_id == "institutionalization":
        return "制度化由 strict successor evidence 中的 benchmark、evaluation、governance、reproducibility、policy 或 protocol 信号推断。"
    if pattern_id == "cyclical_return":
        return "循环回归由长时间间隔推断；在声称思想复兴前，需要检查 source 和 target 文献的实际语义。"
    if top_transitions:
        return "解释应以关联演化边为准；这些字段只是汇总检测器信号，不能替代微观证据审计。"
    return "解释应以关联演化边为准；这个画像只是汇总检测器信号，不能替代微观证据审计。"


def representative_evidence_record(row: dict[str, Any], pattern_id: str) -> dict[str, Any]:
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    artifact_type = str(row.get("artifact_type") or "")
    artifact_id = str(row.get("artifact_id") or "")
    score = round(safe_float(row.get("score")) * safe_float(row.get("pattern_scores", {}).get(pattern_id)), 3)
    labels = [str(label) for label in row.get("entity_labels", []) if str(label)]
    record = {
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "signal_type": str(row.get("signal_type") or ""),
        "score": score,
        "time_slice": str(row.get("time_slice") or ""),
        "path": "",
        "relation": "",
        "type_transition": type_transition_value(source),
        "context_shift": context_shift_value(source),
        "quote": normalize_space(source.get("quote") or ""),
        "edge_ids": [edge_id for edge_id in row.get("evidence_ids", []) if str(edge_id).startswith(("extends__", "specializes__", "adapts__", "improves__", "generalizes__", "replaces__"))][:6],
        "trajectory_ids": row.get("trajectory_ids", [])[:6],
    }
    if artifact_type == "successor_edge":
        record["path"] = f"{source.get('source_label') or (labels[0] if labels else '')} -> {source.get('target_label') or (labels[-1] if labels else '')}"
        record["relation"] = str(source.get("edge_type") or "")
    elif artifact_type == "successor_trajectory":
        record["path"] = " -> ".join(source.get("entity_labels") or labels)
        record["relation"] = " -> ".join(source.get("edge_types") or [])
        record["trajectory_ids"] = [artifact_id]
    elif artifact_type == "successor_branch":
        record["path"] = f"{labels[0]} -> {', '.join(labels[1:5])}" if labels else artifact_id
        record["relation"] = relation_count_phrase(source.get("relation_counts"))
    elif artifact_type == "successor_convergence":
        record["path"] = f"{', '.join(labels[:4])} -> {labels[-1]}" if labels else artifact_id
        record["relation"] = relation_count_phrase(source.get("relation_counts"))
    else:
        record["path"] = " -> ".join(labels)
    return record


def relation_values(source: dict[str, Any]) -> list[str]:
    values: list[str] = []
    if source.get("edge_type"):
        values.append(str(source.get("edge_type")))
    values.extend(str(value) for value in source.get("edge_types") or [] if str(value))
    relation_counts = source.get("relation_counts")
    if isinstance(relation_counts, dict):
        values.extend(str(key) for key, value in relation_counts.items() for _ in range(max(0, safe_int(value))))
    return values


def type_transition_value(source: dict[str, Any]) -> str:
    source_type = normalize_space(source.get("source_type") or "")
    target_type = normalize_space(source.get("target_type") or "")
    if source_type and target_type:
        return f"{source_type} -> {target_type}"
    entity_types = [normalize_space(value) for value in source.get("entity_types") or [] if normalize_space(value)]
    if len(entity_types) >= 2:
        return " + ".join(entity_types)
    return ""


def schema_group_value(source: dict[str, Any]) -> str:
    source_group = normalize_space(source.get("source_schema_group") or "")
    target_group = normalize_space(source.get("target_schema_group") or "")
    if source_group and target_group:
        return source_group if source_group == target_group else f"{source_group} -> {target_group}"
    schema_groups = [normalize_space(value) for value in source.get("schema_groups") or [] if normalize_space(value)]
    if len(schema_groups) == 1:
        return schema_groups[0]
    if len(schema_groups) > 1:
        return " + ".join(schema_groups)
    return ""


def context_shift_value(source: dict[str, Any]) -> str:
    source_context = normalize_space(source.get("source_context") or "")
    target_context = normalize_space(source.get("target_context") or "")
    if source_context and target_context and source_context != target_context:
        return f"{source_context} -> {target_context}"
    return ""


def relation_count_phrase(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return ", ".join(f"{key}:{count}" for key, count in Counter({str(k): safe_int(v) for k, v in value.items()}).most_common(4))


def top_count_rows(counter: Counter[str], total: int, *, limit: int) -> list[dict[str, Any]]:
    return [
        {"value": key, "count": int(count), "share": round(count / max(1, total), 3)}
        for key, count in counter.most_common(limit)
        if key
    ]


def natural_join(items: list[str], *, limit: int = 4) -> str:
    values = [normalize_space(item) for item in items if normalize_space(item)]
    if not values:
        return ""
    values = values[:limit]
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + f", and {values[-1]}"


def build_timeline(features: list[dict[str, Any]], profile_ids: set[str]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in features:
        time_slice = str(row.get("time_slice") or "unspecified")
        for pattern_id in row.get("pattern_scores", {}):
            if pattern_id in profile_ids:
                buckets[(pattern_id, time_slice)].append(row)
    rows = []
    for (pattern_id, time_slice), items in sorted(buckets.items()):
        scores = [safe_float(row.get("score")) * safe_float(row.get("pattern_scores", {}).get(pattern_id)) for row in items]
        rows.append(
            {
                "pattern_id": pattern_id,
                "pattern_label": PATTERN_SPECS[pattern_id]["label"],
                "time_slice": time_slice,
                "pattern_score": round(clamp(mean(scores) + min(0.2, 0.03 * len(items))), 3),
                "evidence_ids": [str(row.get("feature_id") or "") for row in items],
                "representative_node_ids": dedupe(entity_id for row in items for entity_id in row.get("entity_ids", []))[:8],
                "representative_trajectories": dedupe(traj for row in items for traj in row.get("trajectory_ids", []))[:8],
            }
        )
    return rows


def feature_to_evidence(row: dict[str, Any]) -> dict[str, Any]:
    pattern_scores = {
        pattern_id: round(safe_float(row.get("score")) * safe_float(score), 3)
        for pattern_id, score in row.get("pattern_scores", {}).items()
    }
    return {
        "evidence_id": row["feature_id"],
        "artifact_type": row["artifact_type"],
        "artifact_id": row["artifact_id"],
        "signal_type": row["signal_type"],
        "pattern_ids": sorted(pattern_scores),
        "pattern_scores": pattern_scores,
        "time_slice": row.get("time_slice", ""),
        "node_ids": row.get("entity_ids", []),
        "representative_nodes": row.get("entity_labels", []),
        "trajectory_ids": row.get("trajectory_ids", []),
        "source_evidence_ids": row.get("evidence_ids", []),
        "explanation": row.get("explanation", ""),
        "source": row.get("source", {}),
    }


def feature(
    *,
    artifact_type: str,
    artifact_id: str,
    signal_type: str,
    patterns: dict[str, float],
    score: float,
    time_slice: str,
    entity_ids: list[str],
    entity_labels: list[str],
    trajectory_ids: list[str],
    evidence_ids: list[str],
    source: dict[str, Any],
    explanation: str,
) -> dict[str, Any]:
    return {
        "feature_id": f"macro_evidence__{artifact_type}__{safe_id(artifact_id)}",
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "signal_type": signal_type,
        "pattern_scores": {pattern_id: clamp(score) for pattern_id, score in patterns.items() if safe_float(score) > 0},
        "score": clamp(score),
        "time_slice": time_slice,
        "entity_ids": dedupe(entity_ids),
        "entity_labels": dedupe(entity_labels),
        "trajectory_ids": dedupe(trajectory_ids),
        "evidence_ids": dedupe(evidence_ids),
        "source": source,
        "explanation": explanation,
    }


def update_manifest_counts(run_root: Path, summary: dict[str, Any]) -> None:
    manifest_path = run_root / "manifest.json"
    if not manifest_path.exists():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    counts = manifest.setdefault("counts", {})
    counts["macro_patterns"] = int(summary.get("reported_pattern_count") or 0)
    counts["macro_pattern_evidence"] = int(summary.get("evidence_record_count") or 0)
    counts["macro_pattern_timeline_rows"] = int(summary.get("timeline_rows") or 0)
    layout = manifest.setdefault("artifact_layout", {})
    layout["macro_pattern_profiles"] = "macro_patterns/pattern_profiles.jsonl"
    layout["macro_pattern_evidence"] = "macro_patterns/pattern_evidence.jsonl"
    layout["macro_pattern_timeline"] = "macro_patterns/pattern_timeline.jsonl"
    layout["macro_pattern_summary"] = "macro_patterns/pattern_summary.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return list(iter_jsonl(path))


def cross_context(source_card: dict[str, Any], target_card: dict[str, Any]) -> bool:
    source_context = normalize_space(source_card.get("domain_context") or "").lower()
    target_context = normalize_space(target_card.get("domain_context") or "").lower()
    if not source_context or not target_context:
        return False
    return source_context != target_context


def cross_type_edges(rows: list[dict[str, Any]], cards: dict[str, dict[str, Any]]) -> bool:
    for row in rows:
        source_type = (cards.get(str(row.get("source_entity") or "")) or {}).get("entity_type")
        target_type = (cards.get(str(row.get("target_entity") or "")) or {}).get("entity_type")
        if source_type and target_type and source_type != target_type:
            return True
    return False


def institutional_signal(edge: dict[str, Any], source_card: dict[str, Any], target_card: dict[str, Any]) -> bool:
    text = " ".join(
        [
            str(edge.get("edge_type") or ""),
            entity_name(str(edge.get("source_entity") or ""), {str(edge.get("source_entity") or ""): source_card}),
            entity_name(str(edge.get("target_entity") or ""), {str(edge.get("target_entity") or ""): target_card}),
            str(source_card.get("method_role") or ""),
            str(target_card.get("method_role") or ""),
            str(first_quote(edge)),
            json.dumps(edge.get("evidence") or {}, ensure_ascii=False),
        ]
    ).lower()
    terms = ["benchmark", "validation", "evaluation", "governance", "audit", "standard", "protocol", "reproduc", "policy"]
    return any(term in text for term in terms)


def first_quote(edge: dict[str, Any]) -> str:
    evidence = edge.get("evidence") if isinstance(edge.get("evidence"), dict) else {}
    for key in ["mechanism", "validation_evidence", "methodological_problem", "implementation_context", "data_basis", "tradeoff"]:
        value = evidence.get(key)
        if isinstance(value, dict) and value.get("quote"):
            return normalize_space(value.get("quote") or "")
    return ""


def edge_year(edge: dict[str, Any], docs: dict[str, dict[str, Any]]) -> str:
    for key in ["target_date", "source_date"]:
        parsed = parse_date(edge.get(key))
        if parsed:
            return str(parsed.year)
    for key in ["target_document", "source_document"]:
        doc = docs.get(str(edge.get(key) or "")) or {}
        parsed = parse_date(doc.get("published_at"))
        if parsed:
            return str(parsed.year)
        if doc.get("year"):
            return str(doc.get("year"))
    return ""


def entity_name(entity_id: str, cards: dict[str, dict[str, Any]]) -> str:
    card = cards.get(entity_id) or {}
    return normalize_space(
        card.get("display_name")
        or card.get("contextual_name")
        or card.get("canonical_name")
        or entity_id.split("__", 1)[-1].replace("_", " ")
    )


def explanation(pattern_id: str, score: float, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No detector-backed evidence exceeded the current threshold."
    signals = ", ".join(signal for signal, _ in Counter(str(row.get("signal_type") or "unknown") for row in rows).most_common(3))
    artifacts = ", ".join(kind for kind, _ in Counter(str(row.get("artifact_type") or "unknown") for row in rows).most_common(3))
    return (
        f"{PATTERN_SPECS[pattern_id]['label']} is estimated from {len(rows)} strict-successor signals "
        f"(score {score:.3f}), led by {signals} evidence in {artifacts} artifacts."
    )


def time_span(values: list[str]) -> str:
    years = []
    for value in values:
        for part in str(value or "").replace("-", " ").split():
            if part.isdigit() and len(part) == 4:
                years.append(int(part))
    if years:
        return f"{min(years)}-{max(years)}" if min(years) != max(years) else str(min(years))
    unique = sorted({str(value) for value in values if str(value)})
    return unique[0] if len(unique) == 1 else (f"{unique[0]} -> {unique[-1]}" if unique else "")


def dedupe(values: Any) -> list[str]:
    seen = set()
    output = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(value or "unknown"))[:140]


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def clamp(value: float) -> float:
    return max(0.0, min(1.0, safe_float(value)))


if __name__ == "__main__":
    raise SystemExit(main())
