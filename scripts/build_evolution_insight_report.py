#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build an evidence-grounded Markdown insight report from macro patterns and micro successor artifacts."
    )
    parser.add_argument("--run-root", type=Path, required=True, help="Completed EvoTaxa run root.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Report path. Defaults to <run-root>/reports/evolution_insight_report.md.",
    )
    parser.add_argument("--max-patterns", type=int, default=9)
    parser.add_argument("--max-evidence-per-pattern", type=int, default=5)
    parser.add_argument("--max-micro-examples", type=int, default=8)
    parser.add_argument("--quote-chars", type=int, default=220)
    parser.add_argument("--no-manifest-update", action="store_true")
    args = parser.parse_args()

    run_root = args.run_root.expanduser().resolve()
    output = args.output.expanduser().resolve() if args.output else run_root / "reports" / "evolution_insight_report.md"
    report = build_evolution_insight_report(
        run_root=run_root,
        max_patterns=max(1, args.max_patterns),
        max_evidence_per_pattern=max(1, args.max_evidence_per_pattern),
        max_micro_examples=max(1, args.max_micro_examples),
        quote_chars=max(80, args.quote_chars),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report["markdown"], encoding="utf-8")
    summary_path = output.with_suffix(".summary.json")
    write_json(summary_path, report["summary"])
    if not args.no_manifest_update:
        update_manifest(run_root, output, summary_path, report["summary"])
    print(
        json.dumps(
            {
                "report": str(output),
                "summary": str(summary_path),
                "patterns": report["summary"]["macro_patterns"],
                "strict_successor_edges": report["summary"]["strict_successor_edges"],
                "successor_trajectories": report["summary"]["successor_trajectories"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_evolution_insight_report(
    *,
    run_root: Path,
    max_patterns: int = 9,
    max_evidence_per_pattern: int = 5,
    max_micro_examples: int = 8,
    quote_chars: int = 220,
) -> dict[str, Any]:
    manifest = read_json(run_root / "manifest.json", default={})
    docs = {str(row.get("doc_id") or ""): row for row in read_jsonl(run_root / "corpus" / "documents.normalized.jsonl") if row.get("doc_id")}
    cards = {str(row.get("entity_id") or ""): row for row in read_jsonl(run_root / "graph" / "entity_cards.jsonl") if row.get("entity_id")}
    edges = read_jsonl(run_root / "graph" / "successor_edges.accepted.jsonl")
    trajectories = read_jsonl(run_root / "trajectory" / "successor_trajectories.jsonl")
    patterns = sorted(
        read_jsonl(run_root / "macro_patterns" / "pattern_profiles.jsonl"),
        key=lambda row: (-safe_float(row.get("pattern_score")), str(row.get("pattern_id") or "")),
    )
    timeline = read_jsonl(run_root / "macro_patterns" / "pattern_timeline.jsonl")
    edge_by_id = {str(row.get("edge_id") or ""): row for row in edges if row.get("edge_id")}
    trajectory_by_id = {str(row.get("trajectory_id") or ""): row for row in trajectories if row.get("trajectory_id")}
    micro = summarize_micro_regularities(edges=edges, trajectories=trajectories, cards=cards, docs=docs)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_root": str(run_root),
        "project_name": ((manifest.get("project") or {}).get("name") or "EvoTaxa"),
        "run_id": ((manifest.get("project") or {}).get("run_id") or run_root.name),
        "documents": int((manifest.get("counts") or {}).get("documents") or len(docs)),
        "entity_cards": len(cards),
        "strict_successor_edges": len(edges),
        "successor_trajectories": len(trajectories),
        "macro_patterns": len(patterns),
        "timeline_rows": len(timeline),
        "top_patterns": [str(row.get("pattern_id") or "") for row in patterns[:max_patterns]],
        "top_relation_types": micro["relation_distribution"][:6],
        "top_type_transitions": micro["type_transitions"][:6],
        "top_target_years": micro["target_years"][:8],
    }
    lines: list[str] = []
    lines.extend(report_header(summary))
    lines.extend(executive_findings(summary, patterns, micro))
    lines.extend(macro_pattern_section(patterns[:max_patterns], edge_by_id, trajectory_by_id, cards, max_evidence_per_pattern, quote_chars))
    lines.extend(micro_regularities_section(micro, edge_by_id, cards, max_micro_examples, quote_chars))
    lines.extend(cross_scale_section(patterns[:max_patterns], micro, max_patterns=max_patterns))
    lines.extend(appendix_section(summary, run_root))
    markdown = "\n".join(lines).rstrip() + "\n"
    return {"markdown": markdown, "summary": summary}


def summarize_micro_regularities(
    *,
    edges: list[dict[str, Any]],
    trajectories: list[dict[str, Any]],
    cards: dict[str, dict[str, Any]],
    docs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    relation_counter = Counter(str(edge.get("edge_type") or "unknown") for edge in edges)
    schema_counter = Counter(str(edge.get("schema_group") or "unknown") for edge in edges)
    type_counter = Counter(type_transition(edge) for edge in edges)
    target_year_counter = Counter(edge_year(edge, docs, side="target") or "unknown" for edge in edges)
    source_year_counter = Counter(edge_year(edge, docs, side="source") or "unknown" for edge in edges)
    confidence_values = sorted(safe_float(edge.get("confidence")) for edge in edges)
    delta_values = sorted(safe_int(edge.get("time_delta_days")) for edge in edges if safe_int(edge.get("time_delta_days")) > 0)
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        outgoing[str(edge.get("source_entity") or "")].append(edge)
        incoming[str(edge.get("target_entity") or "")].append(edge)
    branch_rows = sorted(
        (
            branch_summary(entity_id, rows, cards, docs)
            for entity_id, rows in outgoing.items()
            if len(rows) >= 2
        ),
        key=lambda row: (-row["edge_count"], row["label"]),
    )
    convergence_rows = sorted(
        (
            convergence_summary(entity_id, rows, cards, docs)
            for entity_id, rows in incoming.items()
            if len(rows) >= 2
        ),
        key=lambda row: (-row["edge_count"], row["label"]),
    )
    cross_type_edges = [edge for edge in edges if str(edge.get("source_entity_type") or "") != str(edge.get("target_entity_type") or "")]
    replacement_edges = [edge for edge in edges if str(edge.get("edge_type") or "") == "replaces"]
    long_gap_edges = [edge for edge in edges if safe_int(edge.get("time_delta_days")) >= 365 * 6]
    high_confidence_edges = [edge for edge in edges if safe_float(edge.get("confidence")) >= 0.9]
    longest_trajectories = sorted(
        trajectories,
        key=lambda row: (safe_int(row.get("path_length")), safe_float(row.get("trajectory_score")), str(row.get("trajectory_id") or "")),
        reverse=True,
    )
    return {
        "edge_count": len(edges),
        "trajectory_count": len(trajectories),
        "relation_distribution": counter_rows(relation_counter, total=len(edges)),
        "schema_groups": counter_rows(schema_counter, total=len(edges)),
        "type_transitions": counter_rows(type_counter, total=len(edges)),
        "target_years": counter_rows(target_year_counter, total=len(edges), sort_numeric_label=True),
        "source_years": counter_rows(source_year_counter, total=len(edges), sort_numeric_label=True),
        "confidence": distribution_summary(confidence_values),
        "time_delta_days": distribution_summary(delta_values),
        "branching_sources": branch_rows,
        "convergence_targets": convergence_rows,
        "cross_type_edges": sorted(cross_type_edges, key=edge_rank, reverse=True),
        "replacement_edges": sorted(replacement_edges, key=edge_rank, reverse=True),
        "long_gap_edges": sorted(long_gap_edges, key=lambda edge: (safe_int(edge.get("time_delta_days")), safe_float(edge.get("confidence"))), reverse=True),
        "high_confidence_edges": sorted(high_confidence_edges, key=edge_rank, reverse=True),
        "longest_trajectories": longest_trajectories,
    }


def report_header(summary: dict[str, Any]) -> list[str]:
    return [
        "# EvoTaxa 演化洞察报告",
        "",
        f"- Project: `{summary['project_name']}`",
        f"- Run: `{summary['run_id']}`",
        f"- Generated: `{summary['generated_at']}`",
        f"- Documents: {summary['documents']}",
        f"- Entity cards: {summary['entity_cards']}",
        f"- Strict successor edges: {summary['strict_successor_edges']}",
        f"- Successor trajectories: {summary['successor_trajectories']}",
        f"- Macro patterns: {summary['macro_patterns']}",
        "",
        "## 读法和边界",
        "",
        "这份报告只使用已经物化的 EvoTaxa 产物：宏观模式画像、strict successor edges、successor trajectories、entity cards 和文献时间信息。",
        "报告中的 insight 是证据汇总和检测器解释，不是新的 LLM 自由发挥。宏观模式用于组织叙事，微观边和轨迹用于约束解释。",
        "没有 successor edge 的新概念不会被强行连到旧概念；因此本报告解释的是当前可证据化的演化线索，而不是整个语料的完整思想史。",
        "",
    ]


def executive_findings(summary: dict[str, Any], patterns: list[dict[str, Any]], micro: dict[str, Any]) -> list[str]:
    top_patterns = patterns[:3]
    top_relation = micro["relation_distribution"][0] if micro["relation_distribution"] else {}
    top_schema = micro["schema_groups"][0] if micro["schema_groups"] else {}
    top_transition = micro["type_transitions"][0] if micro["type_transitions"] else {}
    top_years = ", ".join(row["value"] for row in micro["target_years"][:4])
    cross_type_count = len(micro["cross_type_edges"])
    replacement_count = len(micro["replacement_edges"])
    long_gap_count = len(micro["long_gap_edges"])
    lines = [
        "## 主要发现",
        "",
        f"1. 当前可解释层建立在 {summary['strict_successor_edges']} 条 strict successor edges 和 {summary['successor_trajectories']} 条 successor trajectories 上；宏观层报告 {summary['macro_patterns']} 类模式。",
    ]
    if top_relation:
        lines.append(
            f"2. 微观演化关系以 `{top_relation['value']}` 最常见，占 {pct(top_relation.get('share'))}；这说明目前证据更多呈现为扩展/专门化/适配等渐进演化，而不是单一替代逻辑。"
        )
    if top_schema:
        lines.append(
            f"3. strict successor evidence 主要集中在 `{top_schema['value']}` schema group，占 {pct(top_schema.get('share'))}；其他图层更适合作为补充证据而非主叙事。"
        )
    if top_transition:
        lines.append(
            f"4. 最常见的节点类型迁移是 `{top_transition['value']}`，但跨类型演化边也有 {cross_type_count} 条，说明方法演化经常同时牵动 measurement、modeling、data 或 evaluation 角色。"
        )
    if top_years:
        lines.append(
            f"5. successor evidence 的目标文献集中在 {top_years}，报告中的近期模式应理解为当前语料和抽取范围下的证据密度，而不是领域历史中所有年份的真实强度。"
        )
    if top_patterns:
        lines.append(
            "6. 分数最高的宏观模式是 "
            + ", ".join(f"`{row.get('pattern_id')}` ({score(row.get('pattern_score'))})" for row in top_patterns)
            + "；这些模式的解释必须回到下面列出的代表性微观证据。"
        )
    lines.append(
        f"7. 当前有 {replacement_count} 条显式替代边、{long_gap_count} 条长时间间隔边。它们分别支撑“替代”和“循环回归”式解读，但需要逐条检查 source/target 文献语义。"
    )
    lines.extend(["", ""])
    return lines


def macro_pattern_section(
    patterns: list[dict[str, Any]],
    edge_by_id: dict[str, dict[str, Any]],
    trajectory_by_id: dict[str, dict[str, Any]],
    cards: dict[str, dict[str, Any]],
    max_evidence: int,
    quote_chars: int,
) -> list[str]:
    lines = ["## 宏观模式画像", ""]
    if not patterns:
        return [*lines, "当前 run 没有可用宏观模式画像。", ""]
    for pattern in patterns:
        pattern_id = str(pattern.get("pattern_id") or "")
        label = str(pattern.get("pattern_label") or pattern_id)
        lines.extend(
            [
                f"### {label} (`{pattern_id}`)",
                "",
                f"- Score: {score(pattern.get('pattern_score'))}",
                f"- Time span: {pattern.get('time_span') or 'unknown'}",
                f"- Evidence count: {pattern.get('evidence_count', 0)}",
                f"- Supporting signals: {pattern.get('supporting_signal_count', 0)}",
                "",
            ]
        )
        if pattern.get("insight"):
            lines.extend([f"**语料洞察**：{clean_sentence(pattern.get('insight'))}", ""])
        if pattern.get("analytic_note"):
            lines.extend([f"**检测器读法**：{clean_sentence(pattern.get('analytic_note'))}", ""])
        if pattern.get("interpretation_caveat"):
            lines.extend([f"**解释边界**：{clean_sentence(pattern.get('interpretation_caveat'))}", ""])
        lines.extend(metric_table("主导信号", pattern.get("dominant_signals") or []))
        lines.extend(metric_table("关系构成", pattern.get("dominant_relations") or []))
        lines.extend(metric_table("类型迁移", pattern.get("dominant_type_transitions") or []))
        lines.extend(hotspot_table(pattern.get("temporal_hotspots") or []))
        representative = pattern.get("representative_evidence") or []
        if representative:
            lines.extend(["**代表性微观证据**", ""])
            for index, row in enumerate(representative[:max_evidence], start=1):
                lines.extend(representative_evidence_lines(index, row, edge_by_id, trajectory_by_id, cards, quote_chars))
            lines.append("")
        else:
            evidence_ids = [str(item) for item in pattern.get("evidence_ids") or []]
            edge_ids = [edge_id for edge_id in evidence_ids if edge_id in edge_by_id]
            if edge_ids:
                lines.extend(["**代表性演化边**", ""])
                for index, edge_id in enumerate(edge_ids[:max_evidence], start=1):
                    lines.extend(edge_example_lines(index, edge_by_id[edge_id], cards, quote_chars))
                lines.append("")
    return lines


def micro_regularities_section(
    micro: dict[str, Any],
    edge_by_id: dict[str, dict[str, Any]],
    cards: dict[str, dict[str, Any]],
    max_examples: int,
    quote_chars: int,
) -> list[str]:
    lines = ["## 微观演化规律", ""]
    lines.extend(metric_table("关系类型分布", micro["relation_distribution"][:8]))
    lines.extend(metric_table("Schema group 分布", micro["schema_groups"][:8]))
    lines.extend(metric_table("节点类型迁移", micro["type_transitions"][:10]))
    lines.extend(metric_table("目标文献年份分布", micro["target_years"][:10]))
    lines.extend(
        [
            "### 分数与时间间隔",
            "",
            f"- Edge confidence: min={score(micro['confidence'].get('min'))}, median={score(micro['confidence'].get('median'))}, max={score(micro['confidence'].get('max'))}",
            f"- Time delta days: min={micro['time_delta_days'].get('min', 0)}, median={micro['time_delta_days'].get('median', 0)}, max={micro['time_delta_days'].get('max', 0)}",
            "",
        ]
    )
    lines.extend(branch_table("分化/碎片化的局部来源", micro["branching_sources"][:max_examples]))
    lines.extend(branch_table("汇聚的局部目标", micro["convergence_targets"][:max_examples], target=True))
    lines.extend(edge_group_section("显式替代边", micro["replacement_edges"][:max_examples], cards, quote_chars))
    lines.extend(edge_group_section("跨类型演化边", micro["cross_type_edges"][:max_examples], cards, quote_chars))
    lines.extend(edge_group_section("长时间间隔边", micro["long_gap_edges"][:max_examples], cards, quote_chars, include_delta=True))
    lines.extend(trajectory_section(micro["longest_trajectories"][:max_examples], edge_by_id, cards))
    return lines


def cross_scale_section(patterns: list[dict[str, Any]], micro: dict[str, Any], *, max_patterns: int) -> list[str]:
    lines = ["## 宏观-微观合成解读", ""]
    if not patterns:
        return [*lines, "没有宏观模式可用于合成。", ""]
    branch_names = ", ".join(row["label"] for row in micro["branching_sources"][:3])
    convergence_names = ", ".join(row["label"] for row in micro["convergence_targets"][:3])
    for pattern in patterns[:max_patterns]:
        pattern_id = str(pattern.get("pattern_id") or "")
        relation = first_metric_value(pattern.get("dominant_relations"))
        transition = first_metric_value(pattern.get("dominant_type_transitions"))
        hotspot = first_hotspot_value(pattern.get("temporal_hotspots"))
        evidence = first_representative_path(pattern.get("representative_evidence"))
        if pattern_id in {"differentiation", "fragmentation"} and branch_names:
            lines.append(f"- **{pattern_id}**：宏观上表现为局部分支；微观上主要可从 {branch_names} 这类高出度前身节点检查。")
        elif pattern_id == "convergence" and convergence_names:
            lines.append(f"- **{pattern_id}**：宏观上表现为多源汇聚；微观上可从 {convergence_names} 这类高入度目标节点检查。")
        elif pattern_id == "hybridization" and transition:
            lines.append(f"- **{pattern_id}**：宏观信号来自跨角色耦合；微观上最强类型迁移是 `{transition}`，代表证据为 {evidence or '见模式证据'}。")
        elif pattern_id == "recontextualization" and relation:
            lines.append(f"- **{pattern_id}**：宏观信号来自方法复用和语境转换；微观上由 `{relation}` 等关系支撑，热点时间片为 {hotspot or 'unknown'}。")
        elif pattern_id == "substitution":
            lines.append(f"- **{pattern_id}**：宏观信号来自替代话语；微观上应优先审计 `replaces` 边，例如 {evidence or '模式代表证据'}。")
        elif pattern_id == "institutionalization":
            lines.append(f"- **{pattern_id}**：宏观信号来自 evaluation、benchmark、governance、protocol 等证据槽；微观上需要检查这些词是否真的表示制度化，而不是普通评估描述。")
        elif pattern_id == "cyclical_return":
            lines.append(f"- **{pattern_id}**：宏观信号来自长时间间隔；微观上必须检查旧概念和新 target 是否有实质继承，而不只是共享名称。")
        else:
            lines.append(f"- **{pattern_id}**：主要由 `{relation or 'mixed'}` 关系和 `{transition or 'mixed'}` 类型迁移支撑，代表证据为 {evidence or '见模式证据'}。")
    lines.extend(["", "这些合成解读应被当作下一轮人工审计和可视化讲述的入口，而不是最终结论。", ""])
    return lines


def appendix_section(summary: dict[str, Any], run_root: Path) -> list[str]:
    return [
        "## 产物索引",
        "",
        f"- Run root: `{run_root}`",
        "- Macro profiles: `macro_patterns/pattern_profiles.jsonl`",
        "- Macro evidence: `macro_patterns/pattern_evidence.jsonl`",
        "- Macro timeline: `macro_patterns/pattern_timeline.jsonl`",
        "- Strict successor edges: `graph/successor_edges.accepted.jsonl`",
        "- Entity cards: `graph/entity_cards.jsonl`",
        "- Successor trajectories: `trajectory/successor_trajectories.jsonl`",
        "- Dashboard: `visualization/evolution_dashboard.html`",
        "",
        "## Reproducibility",
        "",
        "This report is generated deterministically from materialized artifacts. Re-run with:",
        "",
        "```bash",
        "PYTHONPATH=scripts:src python scripts/build_evolution_insight_report.py \\",
        f"  --run-root {run_root}",
        "```",
        "",
    ]


def metric_table(title: str, rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    lines = [f"**{title}**", "", "| value | count | share |", "|---|---:|---:|"]
    for row in rows:
        lines.append(f"| {md(row.get('value') or row.get('time_slice') or '')} | {int(row.get('count') or 0)} | {pct(row.get('share'))} |")
    lines.append("")
    return lines


def hotspot_table(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    lines = ["**时间热点**", "", "| time slice | count | mean score |", "|---|---:|---:|"]
    for row in rows[:8]:
        lines.append(f"| {md(row.get('time_slice') or '')} | {int(row.get('count') or 0)} | {score(row.get('mean_score'))} |")
    lines.append("")
    return lines


def branch_table(title: str, rows: list[dict[str, Any]], *, target: bool = False) -> list[str]:
    if not rows:
        return []
    column = "predecessors" if target else "successors"
    lines = [f"### {title}", "", f"| node | edges | relation mix | {column} |", "|---|---:|---|---|"]
    for row in rows:
        neighbors = ", ".join(row.get("neighbors") or [])
        lines.append(f"| {md(row['label'])} | {row['edge_count']} | {md(row['relation_mix'])} | {md(neighbors)} |")
    lines.append("")
    return lines


def edge_group_section(
    title: str,
    rows: list[dict[str, Any]],
    cards: dict[str, dict[str, Any]],
    quote_chars: int,
    *,
    include_delta: bool = False,
) -> list[str]:
    if not rows:
        return []
    lines = [f"### {title}", ""]
    for index, edge in enumerate(rows, start=1):
        lines.extend(edge_example_lines(index, edge, cards, quote_chars, include_delta=include_delta))
    lines.append("")
    return lines


def trajectory_section(rows: list[dict[str, Any]], edge_by_id: dict[str, dict[str, Any]], cards: dict[str, dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    lines = ["### 代表性 successor trajectories", ""]
    for row in rows:
        labels = row.get("entity_labels") or [entity_name(entity_id, cards) for entity_id in row.get("entity_path") or []]
        relations = row.get("edge_types") or [str((edge_by_id.get(edge_id) or {}).get("edge_type") or "") for edge_id in row.get("edge_path") or []]
        lines.append(
            f"- `{row.get('trajectory_id')}` score={score(row.get('trajectory_score'))}, length={row.get('path_length')}: "
            f"{md(' -> '.join(labels))} ({md(' -> '.join(relations))})"
        )
    lines.append("")
    return lines


def representative_evidence_lines(
    index: int,
    row: dict[str, Any],
    edge_by_id: dict[str, dict[str, Any]],
    trajectory_by_id: dict[str, dict[str, Any]],
    cards: dict[str, dict[str, Any]],
    quote_chars: int,
) -> list[str]:
    path = normalize_space(row.get("path") or row.get("artifact_id") or "")
    relation = normalize_space(row.get("relation") or row.get("signal_type") or "")
    line = f"{index}. `{row.get('artifact_type')}` score={score(row.get('score'))}, time={row.get('time_slice') or 'unknown'}: {md(path)}"
    if relation:
        line += f" ({md(relation)})"
    lines = [line]
    edge_ids = [edge_id for edge_id in row.get("edge_ids") or [] if edge_id in edge_by_id]
    if edge_ids:
        edge = edge_by_id[edge_ids[0]]
        quote = first_quote(edge)
        if quote:
            lines.append(f"   - Quote: {md(compact(quote, quote_chars))}")
        lines.append(f"   - Edge: `{edge_ids[0]}`")
    trajectory_ids = [trajectory_id for trajectory_id in row.get("trajectory_ids") or [] if trajectory_id in trajectory_by_id]
    if trajectory_ids:
        trajectory = trajectory_by_id[trajectory_ids[0]]
        labels = trajectory.get("entity_labels") or [entity_name(entity_id, cards) for entity_id in trajectory.get("entity_path") or []]
        lines.append(f"   - Trajectory: `{trajectory_ids[0]}` {md(' -> '.join(labels))}")
    return lines


def edge_example_lines(
    index: int,
    edge: dict[str, Any],
    cards: dict[str, dict[str, Any]],
    quote_chars: int,
    *,
    include_delta: bool = False,
) -> list[str]:
    source = entity_name(str(edge.get("source_entity") or ""), cards)
    target = entity_name(str(edge.get("target_entity") or ""), cards)
    relation = str(edge.get("edge_type") or "")
    suffix = f", delta={safe_int(edge.get('time_delta_days'))}d" if include_delta else ""
    lines = [
        f"{index}. `{relation}` conf={score(edge.get('confidence'))}{suffix}: {md(source)} -> {md(target)}",
        f"   - Edge: `{edge.get('edge_id')}`",
    ]
    quote = first_quote(edge)
    if quote:
        lines.append(f"   - Quote: {md(compact(quote, quote_chars))}")
    return lines


def branch_summary(entity_id: str, rows: list[dict[str, Any]], cards: dict[str, dict[str, Any]], docs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    relation_mix = Counter(str(row.get("edge_type") or "") for row in rows)
    targets = [entity_name(str(row.get("target_entity") or ""), cards) for row in sorted(rows, key=edge_rank, reverse=True)[:5]]
    years = sorted({edge_year(row, docs, side="target") for row in rows if edge_year(row, docs, side="target")})
    return {
        "entity_id": entity_id,
        "label": entity_name(entity_id, cards),
        "edge_count": len(rows),
        "relation_mix": counter_phrase(relation_mix),
        "neighbors": targets,
        "time_span": f"{years[0]}-{years[-1]}" if len(years) > 1 else (years[0] if years else ""),
    }


def convergence_summary(entity_id: str, rows: list[dict[str, Any]], cards: dict[str, dict[str, Any]], docs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    relation_mix = Counter(str(row.get("edge_type") or "") for row in rows)
    sources = [entity_name(str(row.get("source_entity") or ""), cards) for row in sorted(rows, key=edge_rank, reverse=True)[:5]]
    years = sorted({edge_year(row, docs, side="target") for row in rows if edge_year(row, docs, side="target")})
    return {
        "entity_id": entity_id,
        "label": entity_name(entity_id, cards),
        "edge_count": len(rows),
        "relation_mix": counter_phrase(relation_mix),
        "neighbors": sources,
        "time_span": f"{years[0]}-{years[-1]}" if len(years) > 1 else (years[0] if years else ""),
    }


def update_manifest(run_root: Path, output: Path, summary_path: Path, summary: dict[str, Any]) -> None:
    manifest_path = run_root / "manifest.json"
    if not manifest_path.exists():
        return
    manifest = read_json(manifest_path, default={})
    if not isinstance(manifest, dict):
        return
    layout = manifest.setdefault("artifact_layout", {})
    layout["evolution_insight_report"] = relative_path(output, run_root)
    layout["evolution_insight_report_summary"] = relative_path(summary_path, run_root)
    counts = manifest.setdefault("counts", {})
    counts["evolution_insight_reports"] = 1
    write_json(manifest_path, manifest)


def read_json(path: Path, *, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            rows.append(json.loads(text))
    return rows


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 4 and text.isdigit():
        return date(int(text), 1, 1)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y/%m"):
        try:
            parsed = datetime.strptime(text[: len(fmt)], fmt)
            return parsed.date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def normalize_space(value: Any) -> str:
    return " ".join(str(value or "").split())


def first_quote(edge: dict[str, Any]) -> str:
    evidence = edge.get("evidence") if isinstance(edge.get("evidence"), dict) else {}
    for key in ["mechanism", "validation_evidence", "methodological_problem", "implementation_context", "data_basis", "tradeoff"]:
        value = evidence.get(key)
        if isinstance(value, dict) and value.get("quote"):
            return normalize_space(value.get("quote") or "")
    return ""


def edge_year(edge: dict[str, Any], docs: dict[str, dict[str, Any]], *, side: str) -> str:
    doc_id = str(edge.get(f"{side}_document") or "")
    doc = docs.get(doc_id) or {}
    parsed = parse_date(doc.get("published_at"))
    if parsed:
        return str(parsed.year)
    value = doc.get("year") or doc.get("chronology_slice")
    if value:
        return str(value)[:4]
    parsed = parse_date(edge.get(f"{side}_date"))
    return str(parsed.year) if parsed else ""


def entity_name(entity_id: str, cards: dict[str, dict[str, Any]]) -> str:
    card = cards.get(entity_id) or {}
    return normalize_space(
        card.get("display_name")
        or card.get("contextual_name")
        or card.get("canonical_name")
        or entity_id.split("__", 1)[-1].replace("_", " ")
    )


def type_transition(edge: dict[str, Any]) -> str:
    source = str(edge.get("source_entity_type") or "")
    target = str(edge.get("target_entity_type") or "")
    if source and target:
        return f"{source} -> {target}"
    return "unknown"


def counter_rows(counter: Counter[str], *, total: int, sort_numeric_label: bool = False) -> list[dict[str, Any]]:
    rows = [
        {"value": key, "count": int(count), "share": round(count / max(1, total), 3)}
        for key, count in counter.items()
        if key
    ]
    if sort_numeric_label:
        rows.sort(key=lambda row: (-row["count"], str(row["value"])))
    else:
        rows.sort(key=lambda row: (-row["count"], str(row["value"])))
    return rows


def distribution_summary(values: list[float | int]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "min": 0, "median": 0, "max": 0}
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "median": ordered[len(ordered) // 2],
        "max": ordered[-1],
    }


def edge_rank(edge: dict[str, Any]) -> tuple[float, int, str]:
    return (
        safe_float(edge.get("confidence")),
        safe_int(edge.get("time_delta_days")),
        str(edge.get("edge_id") or ""),
    )


def counter_phrase(counter: Counter[str]) -> str:
    return ", ".join(f"{key}:{value}" for key, value in counter.most_common(4))


def first_metric_value(rows: Any) -> str:
    if isinstance(rows, list) and rows:
        return str((rows[0] or {}).get("value") or "")
    return ""


def first_hotspot_value(rows: Any) -> str:
    if isinstance(rows, list) and rows:
        return str((rows[0] or {}).get("time_slice") or "")
    return ""


def first_representative_path(rows: Any) -> str:
    if isinstance(rows, list) and rows:
        return normalize_space((rows[0] or {}).get("path") or "")
    return ""


def clean_sentence(value: Any) -> str:
    text = normalize_space(value)
    text = text.replace(", and ", " 和 ")
    text = text.replace(" and ", " 和 ")
    text = text.replace("trajectory。", "轨迹。")
    text = text.replace("successor trajectory", "successor 轨迹")
    text = text.replace("successor evidence", "successor 证据")
    text = text.replace("strict successor evidence", "strict successor 证据")
    return text


def compact(value: Any, max_chars: int) -> str:
    text = normalize_space(value)
    if len(text) <= max_chars:
        return text
    return text[: max(1, max_chars - 1)].rstrip() + "..."


def md(value: Any) -> str:
    text = normalize_space(value)
    return text.replace("|", "\\|")


def pct(value: Any) -> str:
    return f"{safe_float(value) * 100:.1f}%"


def score(value: Any) -> str:
    return f"{safe_float(value):.3f}".rstrip("0").rstrip(".") if safe_float(value) else "0"


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


def relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
