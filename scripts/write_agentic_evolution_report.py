#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_evolution_insight_report import (  # noqa: E402
    build_evolution_insight_report,
    clean_sentence,
    compact,
    edge_year,
    entity_name,
    first_quote,
    md,
    read_json,
    read_jsonl,
    relative_path,
    safe_float,
    safe_int,
    score,
    update_manifest,
    write_json,
)


DEFAULT_SYSTEM_PROMPT = """你是一名严谨但有叙事能力的计算社会科学研究报告写作者。
你必须只使用用户提供的证据包写作，不能编造文献、节点、年份、趋势或因果关系。
你的任务不是复述统计表，而是提出有洞察的研究判断，并把每个判断锚定到读者可理解的证据标签、节点、关系、时间或引文。
最终报告面向研究合作者，不要暴露内部字段名、机器编号、下划线连接的机器串、运行路径或其他工程管线痕迹。
请直接输出中文 Markdown，不要输出思考过程。
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Use an LLM writing agent to produce an evidence-grounded narrative EvoTaxa report.")
    parser.add_argument("--run-root", type=Path, required=True, help="Completed EvoTaxa run root.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"), help="Local YAML/JSON config for OpenAI-compatible API.")
    parser.add_argument("--output", type=Path, default=None, help="Defaults to <run-root>/reports/evolution_insight_report.agent.md.")
    parser.add_argument("--evidence-output", type=Path, default=None, help="Defaults to <run-root>/reports/evolution_insight_report.evidence_pack.json.")
    parser.add_argument(
        "--reader-evidence-output",
        type=Path,
        default=None,
        help="Reader-facing evidence pack used by the writing agent. Defaults to <run-root>/reports/evolution_insight_report.reader_evidence_pack.json.",
    )
    parser.add_argument("--trace-output", type=Path, default=None, help="Defaults to <run-root>/reports/evolution_insight_report.agent_trace.json.")
    parser.add_argument("--deterministic-output", type=Path, default=None, help="Defaults to <run-root>/reports/evolution_insight_report.md.")
    parser.add_argument("--max-patterns", type=int, default=9)
    parser.add_argument("--max-evidence-per-pattern", type=int, default=8)
    parser.add_argument("--max-micro-examples", type=int, default=10)
    parser.add_argument("--quote-chars", type=int, default=260)
    parser.add_argument("--style", default="research_memo", choices=["research_memo", "presentation", "paper_outline"])
    parser.add_argument("--dry-run", action="store_true", help="Build evidence pack and prompts without calling the model.")
    parser.add_argument("--no-manifest-update", action="store_true")
    args = parser.parse_args()

    run_root = args.run_root.expanduser().resolve()
    output = args.output.expanduser().resolve() if args.output else run_root / "reports" / "evolution_insight_report.agent.md"
    default_evidence_name = "evolution_insight_report.dry_run.evidence_pack.json" if args.dry_run else "evolution_insight_report.evidence_pack.json"
    default_reader_evidence_name = (
        "evolution_insight_report.dry_run.reader_evidence_pack.json"
        if args.dry_run
        else "evolution_insight_report.reader_evidence_pack.json"
    )
    default_trace_name = "evolution_insight_report.dry_run.agent_trace.json" if args.dry_run else "evolution_insight_report.agent_trace.json"
    evidence_output = args.evidence_output.expanduser().resolve() if args.evidence_output else run_root / "reports" / default_evidence_name
    reader_evidence_output = (
        args.reader_evidence_output.expanduser().resolve()
        if args.reader_evidence_output
        else run_root / "reports" / default_reader_evidence_name
    )
    trace_output = args.trace_output.expanduser().resolve() if args.trace_output else run_root / "reports" / default_trace_name
    deterministic_output = (
        args.deterministic_output.expanduser().resolve()
        if args.deterministic_output
        else run_root / "reports" / "evolution_insight_report.md"
    )

    deterministic = build_evolution_insight_report(
        run_root=run_root,
        max_patterns=max(1, args.max_patterns),
        max_evidence_per_pattern=max(1, args.max_evidence_per_pattern),
        max_micro_examples=max(1, args.max_micro_examples),
        quote_chars=max(80, args.quote_chars),
    )
    deterministic_output.parent.mkdir(parents=True, exist_ok=True)
    deterministic_output.write_text(deterministic["markdown"], encoding="utf-8")
    deterministic_summary_path = deterministic_output.with_suffix(".summary.json")
    write_json(deterministic_summary_path, deterministic["summary"])

    evidence_pack = build_evidence_pack(
        run_root=run_root,
        deterministic_summary=deterministic["summary"],
        max_patterns=max(1, args.max_patterns),
        max_evidence_per_pattern=max(1, args.max_evidence_per_pattern),
        max_micro_examples=max(1, args.max_micro_examples),
        quote_chars=max(80, args.quote_chars),
    )
    write_json(evidence_output, evidence_pack)
    reader_evidence_pack = build_reader_evidence_pack(evidence_pack)
    write_json(reader_evidence_output, reader_evidence_pack)

    trace: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_root": str(run_root),
        "style": args.style,
        "dry_run": bool(args.dry_run),
        "evidence_output": str(evidence_output),
        "reader_evidence_output": str(reader_evidence_output),
        "deterministic_output": str(deterministic_output),
        "steps": [],
    }
    if args.dry_run:
        trace["planned_prompts"] = build_planned_prompts(evidence_pack=reader_evidence_pack, style=args.style)
        write_json(trace_output, trace)
        print(
            json.dumps(
                {
                    "evidence": str(evidence_output),
                    "reader_evidence": str(reader_evidence_output),
                    "trace": str(trace_output),
                    "dry_run": True,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    config = load_local_config(args.config)
    client = OpenAICompatTextClient(config)
    report_markdown = run_writing_agent(client=client, evidence_pack=reader_evidence_pack, style=args.style, trace=trace)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report_markdown, encoding="utf-8")
    summary_path = output.with_suffix(".summary.json")
    write_json(
        summary_path,
        {
            **deterministic["summary"],
            "agentic_report": str(output),
            "evidence_pack": str(evidence_output),
            "reader_evidence_pack": str(reader_evidence_output),
            "agent_trace": str(trace_output),
            "llm_model": client.model,
            "llm_base_url": client.base_url,
            "style": args.style,
            "agent_steps": [row["step"] for row in trace["steps"]],
        },
    )
    write_json(trace_output, trace)
    if not args.no_manifest_update:
        update_manifest(run_root, deterministic_output, deterministic_summary_path, deterministic["summary"])
        update_agent_manifest(run_root, output, summary_path, evidence_output, reader_evidence_output, trace_output)
    print(
        json.dumps(
            {
                "report": str(output),
                "summary": str(summary_path),
                "evidence": str(evidence_output),
                "reader_evidence": str(reader_evidence_output),
                "trace": str(trace_output),
                "model": client.model,
                "steps": len(trace["steps"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_evidence_pack(
    *,
    run_root: Path,
    deterministic_summary: dict[str, Any],
    max_patterns: int,
    max_evidence_per_pattern: int,
    max_micro_examples: int,
    quote_chars: int,
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
    edge_by_id = {str(row.get("edge_id") or ""): row for row in edges if row.get("edge_id")}
    trajectory_by_id = {str(row.get("trajectory_id") or ""): row for row in trajectories if row.get("trajectory_id")}
    micro = deterministic_summary
    selected_patterns = [
        pattern_evidence_pack(pattern, edge_by_id, trajectory_by_id, cards, docs, max_evidence_per_pattern, quote_chars)
        for pattern in patterns[:max_patterns]
    ]
    replacement_edges = sorted([edge for edge in edges if edge.get("edge_type") == "replaces"], key=edge_rank, reverse=True)
    cross_type_edges = sorted(
        [edge for edge in edges if str(edge.get("source_entity_type") or "") != str(edge.get("target_entity_type") or "")],
        key=edge_rank,
        reverse=True,
    )
    long_gap_edges = sorted(
        [edge for edge in edges if safe_int(edge.get("time_delta_days")) >= 365 * 6],
        key=lambda edge: (safe_int(edge.get("time_delta_days")), safe_float(edge.get("confidence"))),
        reverse=True,
    )
    long_trajectories = sorted(
        trajectories,
        key=lambda row: (safe_int(row.get("path_length")), safe_float(row.get("trajectory_score")), str(row.get("trajectory_id") or "")),
        reverse=True,
    )
    return {
        "report_contract": {
            "allowed_claims": [
                "Only make claims grounded in this evidence pack.",
                "Use counts as support, not as the main narrative.",
                "Name uncertainty and likely extraction artifacts when evidence is thin.",
                "Do not invent documents, nodes, years, or causal mechanisms.",
            ],
            "desired_output": "Chinese Markdown narrative report with vivid section titles, claims, evidence, caveats, and next audit questions.",
        },
        "run": {
            "project": (manifest.get("project") or {}).get("name") or deterministic_summary.get("project_name"),
            "run_id": (manifest.get("project") or {}).get("run_id") or deterministic_summary.get("run_id"),
            "run_root": str(run_root),
            "documents": deterministic_summary.get("documents"),
            "entity_cards": deterministic_summary.get("entity_cards"),
            "strict_successor_edges": deterministic_summary.get("strict_successor_edges"),
            "successor_trajectories": deterministic_summary.get("successor_trajectories"),
            "macro_patterns": deterministic_summary.get("macro_patterns"),
        },
        "macro_patterns": selected_patterns,
        "micro_evidence": {
            "top_relation_types": micro.get("top_relation_types", []),
            "top_type_transitions": micro.get("top_type_transitions", []),
            "top_target_years": micro.get("top_target_years", []),
            "replacement_edges": [edge_pack(edge, cards, docs, quote_chars) for edge in replacement_edges[:max_micro_examples]],
            "cross_type_edges": [edge_pack(edge, cards, docs, quote_chars) for edge in cross_type_edges[:max_micro_examples]],
            "long_gap_edges": [edge_pack(edge, cards, docs, quote_chars) for edge in long_gap_edges[:max_micro_examples]],
            "representative_trajectories": [trajectory_pack(row, edge_by_id, cards) for row in long_trajectories[:max_micro_examples]],
        },
    }


def pattern_evidence_pack(
    pattern: dict[str, Any],
    edge_by_id: dict[str, dict[str, Any]],
    trajectory_by_id: dict[str, dict[str, Any]],
    cards: dict[str, dict[str, Any]],
    docs: dict[str, dict[str, Any]],
    max_evidence: int,
    quote_chars: int,
) -> dict[str, Any]:
    evidence_rows = []
    for row in (pattern.get("representative_evidence") or [])[:max_evidence]:
        edge_ids = [str(edge_id) for edge_id in row.get("edge_ids") or [] if edge_id in edge_by_id]
        trajectory_ids = [str(item) for item in row.get("trajectory_ids") or [] if item in trajectory_by_id]
        evidence_rows.append(
            {
                "artifact_type": row.get("artifact_type"),
                "artifact_id": row.get("artifact_id"),
                "path": row.get("path"),
                "relation": row.get("relation"),
                "score": row.get("score"),
                "time_slice": row.get("time_slice"),
                "edge_ids": edge_ids,
                "edges": [edge_pack(edge_by_id[edge_id], cards, docs, quote_chars) for edge_id in edge_ids[:2]],
                "trajectory_ids": trajectory_ids,
                "trajectories": [trajectory_pack(trajectory_by_id[item], edge_by_id, cards) for item in trajectory_ids[:1]],
            }
        )
    return {
        "pattern_id": pattern.get("pattern_id"),
        "label": pattern.get("pattern_label") or pattern.get("pattern_id"),
        "score": pattern.get("pattern_score"),
        "time_span": pattern.get("time_span"),
        "detector_insight": clean_sentence(pattern.get("insight") or ""),
        "analytic_note": clean_sentence(pattern.get("analytic_note") or ""),
        "interpretation_caveat": clean_sentence(pattern.get("interpretation_caveat") or ""),
        "dominant_signals": pattern.get("dominant_signals") or [],
        "dominant_relations": pattern.get("dominant_relations") or [],
        "dominant_type_transitions": pattern.get("dominant_type_transitions") or [],
        "temporal_hotspots": pattern.get("temporal_hotspots") or [],
        "representative_evidence": evidence_rows,
    }


def edge_pack(edge: dict[str, Any], cards: dict[str, dict[str, Any]], docs: dict[str, dict[str, Any]], quote_chars: int) -> dict[str, Any]:
    source_doc = docs.get(str(edge.get("source_document") or "")) or {}
    target_doc = docs.get(str(edge.get("target_document") or "")) or {}
    return {
        "edge_id": edge.get("edge_id"),
        "relation": edge.get("edge_type"),
        "confidence": edge.get("confidence"),
        "source": entity_name(str(edge.get("source_entity") or ""), cards),
        "target": entity_name(str(edge.get("target_entity") or ""), cards),
        "source_type": edge.get("source_entity_type"),
        "target_type": edge.get("target_entity_type"),
        "schema_group": edge.get("schema_group"),
        "source_year": edge_year(edge, docs, side="source"),
        "target_year": edge_year(edge, docs, side="target"),
        "time_delta_days": edge.get("time_delta_days"),
        "source_title": compact(source_doc.get("title") or "", 160),
        "target_title": compact(target_doc.get("title") or "", 160),
        "quote": compact(first_quote(edge), quote_chars),
    }


def trajectory_pack(row: dict[str, Any], edge_by_id: dict[str, dict[str, Any]], cards: dict[str, dict[str, Any]]) -> dict[str, Any]:
    labels = row.get("entity_labels") or [entity_name(str(entity_id), cards) for entity_id in row.get("entity_path") or []]
    edge_types = row.get("edge_types") or [str((edge_by_id.get(edge_id) or {}).get("edge_type") or "") for edge_id in row.get("edge_path") or []]
    return {
        "trajectory_id": row.get("trajectory_id"),
        "score": row.get("trajectory_score"),
        "path_length": row.get("path_length"),
        "path": labels,
        "relations": edge_types,
        "edge_ids": row.get("edge_path") or [],
    }


def build_reader_evidence_pack(evidence_pack: dict[str, Any]) -> dict[str, Any]:
    edge_labels: dict[str, str] = {}
    trajectory_labels: dict[str, str] = {}

    def label_edge(edge: dict[str, Any]) -> dict[str, Any]:
        raw_id = str(edge.get("edge_id") or "")
        if raw_id:
            edge_labels.setdefault(raw_id, f"E{len(edge_labels) + 1}")
        label = edge_labels.get(raw_id, f"E{len(edge_labels) + 1}")
        return {
            "evidence_label": label,
            "relation": relation_label(edge.get("relation")),
            "source": edge.get("source"),
            "target": edge.get("target"),
            "source_role": role_label(edge.get("source_type")),
            "target_role": role_label(edge.get("target_type")),
            "year": edge.get("target_year") or edge.get("source_year"),
            "time_gap_years": gap_years(edge.get("time_delta_days")),
            "paper_title": edge.get("target_title") or edge.get("source_title"),
            "quote": edge.get("quote"),
        }

    def label_trajectory(row: dict[str, Any]) -> dict[str, Any]:
        raw_id = str(row.get("trajectory_id") or "")
        if raw_id:
            trajectory_labels.setdefault(raw_id, f"T{len(trajectory_labels) + 1}")
        label = trajectory_labels.get(raw_id, f"T{len(trajectory_labels) + 1}")
        return {
            "trajectory_label": label,
            "path": row.get("path") or [],
            "relations": [relation_label(item) for item in row.get("relations") or []],
            "path_length": row.get("path_length"),
        }

    patterns = []
    for index, pattern in enumerate(evidence_pack.get("macro_patterns") or [], start=1):
        evidence_rows = []
        for row in pattern.get("representative_evidence") or []:
            evidence_rows.append(
                {
                    "evidence_label": f"P{index}.{len(evidence_rows) + 1}",
                    "path": row.get("path"),
                    "relation": relation_label(row.get("relation")),
                    "time_slice": row.get("time_slice"),
                    "edges": [label_edge(edge) for edge in row.get("edges") or []],
                    "trajectories": [label_trajectory(item) for item in row.get("trajectories") or []],
                }
            )
        patterns.append(
            {
                "pattern_label": pattern_title(pattern.get("label") or pattern.get("pattern_id")),
                "short_name": pattern_short_name(pattern.get("pattern_id") or pattern.get("label")),
                "score": pattern.get("score"),
                "time_span": pattern.get("time_span"),
                "detector_interpretation": pattern.get("detector_insight"),
                "caveat": pattern.get("interpretation_caveat"),
                "dominant_relations": [
                    {"relation": relation_label(row.get("value")), "count": row.get("count"), "share": row.get("share")}
                    for row in pattern.get("dominant_relations") or []
                ],
                "dominant_type_transitions": [
                    {
                        "transition": readable_transition(row.get("value")),
                        "count": row.get("count"),
                        "share": row.get("share"),
                    }
                    for row in pattern.get("dominant_type_transitions") or []
                ],
                "temporal_hotspots": pattern.get("temporal_hotspots") or [],
                "representative_evidence": evidence_rows,
            }
        )

    micro = evidence_pack.get("micro_evidence") or {}
    reader_pack = {
        "writing_contract": {
            "audience": "research collaborators in computational social science",
            "style": "insightful research memo, not an engineering audit log",
            "must_do": [
                "Use natural-language evidence labels such as E1, P2.1, or T1.",
                "Use node names and paper titles when explaining evidence.",
                "Keep raw machine identifiers out of the final report body.",
                "Put uncertainty and audit needs in reader-friendly language.",
            ],
            "must_not_do": [
                "Do not mention internal field names, machine identifiers, JSON fields, run paths, evidence-group field names, or raw ids with double underscores.",
                "Do not use machine strings from the pipeline; cite reader-facing labels and node names instead.",
                "Do not turn the report into tables of counts.",
            ],
        },
        "run_context": {
            "project": (evidence_pack.get("run") or {}).get("project"),
            "documents": (evidence_pack.get("run") or {}).get("documents"),
            "strict_successor_edges": (evidence_pack.get("run") or {}).get("strict_successor_edges"),
            "successor_trajectories": (evidence_pack.get("run") or {}).get("successor_trajectories"),
            "macro_patterns": (evidence_pack.get("run") or {}).get("macro_patterns"),
        },
        "macro_patterns": patterns,
        "micro_evidence": {
            "relation_mix": [
                {"relation": relation_label(row.get("value")), "count": row.get("count"), "share": row.get("share")}
                for row in micro.get("top_relation_types") or []
            ],
            "type_transitions": [
                {"transition": readable_transition(row.get("value")), "count": row.get("count"), "share": row.get("share")}
                for row in micro.get("top_type_transitions") or []
            ],
            "active_years": micro.get("top_target_years") or [],
            "replacement_examples": [label_edge(edge) for edge in micro.get("replacement_edges") or []],
            "cross_role_examples": [label_edge(edge) for edge in micro.get("cross_type_edges") or []],
            "long_gap_examples": [label_edge(edge) for edge in micro.get("long_gap_edges") or []],
            "trajectory_examples": [label_trajectory(row) for row in micro.get("representative_trajectories") or []],
        },
        "audit_crosswalk": {
            "edge_labels": edge_labels,
            "trajectory_labels": trajectory_labels,
        },
    }
    return reader_pack


def run_writing_agent(
    *,
    client: "OpenAICompatTextClient",
    evidence_pack: dict[str, Any],
    style: str,
    trace: dict[str, Any],
) -> str:
    prompt_pack = prompt_evidence_pack(evidence_pack)
    scout = call_agent_step(
        client,
        trace,
        step="scout",
        prompt=render_prompt(
            "agentic_report_scout",
            {
                "style": style,
                "evidence_pack": compact_json(prompt_pack, 42000),
            },
        ),
        max_chars=8000,
    )
    outline = call_agent_step(
        client,
        trace,
        step="outline",
        prompt=render_prompt(
            "agentic_report_outline",
            {
                "style": style,
                "evidence_pack": compact_json(prompt_pack, 36000),
                "scout_notes": scout,
            },
        ),
        max_chars=8000,
    )
    draft = call_agent_step(
        client,
        trace,
        step="draft",
        prompt=render_prompt(
            "agentic_report_draft",
            {
                "style": style,
                "evidence_pack": compact_json(prompt_pack, 52000),
                "scout_notes": scout,
                "outline": outline,
            },
        ),
        max_chars=30000,
    )
    critique = call_agent_step(
        client,
        trace,
        step="critic",
        prompt=render_prompt(
            "agentic_report_critic",
            {
                "evidence_pack": compact_json(prompt_pack, 42000),
                "draft": draft,
            },
        ),
        max_chars=10000,
    )
    final = call_agent_step(
        client,
        trace,
        step="revise",
        prompt=render_prompt(
            "agentic_report_revise",
            {
                "style": style,
                "evidence_pack": compact_json(prompt_pack, 46000),
                "draft": draft,
                "critique": critique,
            },
        ),
        max_chars=36000,
    )
    return sanitize_final_report(final, evidence_pack).strip() + "\n"


def sanitize_final_report(text: str, evidence_pack: dict[str, Any]) -> str:
    crosswalk = evidence_pack.get("audit_crosswalk") if isinstance(evidence_pack.get("audit_crosswalk"), dict) else {}
    edge_labels = crosswalk.get("edge_labels") if isinstance(crosswalk.get("edge_labels"), dict) else {}
    trajectory_labels = crosswalk.get("trajectory_labels") if isinstance(crosswalk.get("trajectory_labels"), dict) else {}
    cleaned = str(text or "")
    for raw_id, label in sorted(edge_labels.items(), key=lambda item: len(str(item[0])), reverse=True):
        cleaned = cleaned.replace(str(raw_id), f"证据 {label}")
    for raw_id, label in sorted(trajectory_labels.items(), key=lambda item: len(str(item[0])), reverse=True):
        cleaned = cleaned.replace(str(raw_id), f"轨迹 {label}")
    replacements = {
        "pattern_id: ": "",
        "pattern_id": "模式",
        "edge_id": "证据编号",
        "trajectory_id": "轨迹编号",
        "schema_group": "证据分组",
        "successor edge": "演化证据",
        "successor Edge": "演化证据",
        "successor trajectory": "演化轨迹",
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    cleaned = re.sub(r"`?[\w]+(?:__[\w]+)+__w\d+`?", "证据", cleaned)
    cleaned = re.sub(r"\bw\d{8,}\b", "对应文献", cleaned)
    cleaned = re.sub(r"\b(pattern_id|edge_id|trajectory_id|schema_group)\b[:：]?\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned


def prompt_evidence_pack(evidence_pack: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in evidence_pack.items() if key != "audit_crosswalk"}


def call_agent_step(client: "OpenAICompatTextClient", trace: dict[str, Any], *, step: str, prompt: str, max_chars: int) -> str:
    started = time.time()
    output, raw = client.complete_text(task=f"agentic_evolution_report_{step}", prompt=prompt)
    if len(output) > max_chars:
        output = output[:max_chars].rstrip()
    trace["steps"].append(
        {
            "step": step,
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "prompt_chars": len(prompt),
            "output_chars": len(output),
            "elapsed_seconds": round(time.time() - started, 3),
            "finish_reason": raw.get("finish_reason"),
            "error": raw.get("error", ""),
        }
    )
    return output


def build_planned_prompts(*, evidence_pack: dict[str, Any], style: str) -> dict[str, str]:
    evidence = compact_json(prompt_evidence_pack(evidence_pack), 12000)
    return {
        "scout": render_prompt("agentic_report_scout", {"style": style, "evidence_pack": evidence}),
        "outline": render_prompt("agentic_report_outline", {"style": style, "evidence_pack": evidence, "scout_notes": "<scout_notes>"}),
        "draft": render_prompt(
            "agentic_report_draft",
            {"style": style, "evidence_pack": evidence, "scout_notes": "<scout_notes>", "outline": "<outline>"},
        ),
        "critic": render_prompt("agentic_report_critic", {"evidence_pack": evidence, "draft": "<draft>"}),
        "revise": render_prompt(
            "agentic_report_revise",
            {"style": style, "evidence_pack": evidence, "draft": "<draft>", "critique": "<critique>"},
        ),
    }


class OpenAICompatTextClient:
    def __init__(self, config: dict[str, Any]) -> None:
        llm = config.get("llm") if isinstance(config.get("llm"), dict) else config
        self.base_url = str(llm.get("base_url") or "https://api.openai.com/v1").rstrip("/")
        self.model = str(llm.get("model") or llm.get("model_name") or "")
        self.api_key = str(llm.get("api_key") or "")
        api_key_env = str(llm.get("api_key_env") or "")
        if not self.api_key and api_key_env:
            self.api_key = os.environ.get(api_key_env, "")
        self.temperature = float(llm.get("temperature", 0.2) or 0.0)
        self.top_p = float(llm.get("top_p", 0.8) or 0.8)
        self.timeout_seconds = int(llm.get("timeout_seconds", 180) or 180)
        self.max_retries = max(1, int(llm.get("max_retries", 2) or 2))
        self.extra_body = dict(llm.get("extra_body") or {})
        self.system_prompt = str(llm.get("system_prompt") or DEFAULT_SYSTEM_PROMPT)
        if not self.model:
            raise ValueError("LLM config must define llm.model or llm.model_name.")
        if not self.api_key:
            raise ValueError("LLM config must define llm.api_key or llm.api_key_env.")

    def complete_text(self, *, task: str, prompt: str) -> tuple[str, dict[str, Any]]:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
        }
        payload.update(self.extra_body)
        url = f"{self.base_url}/chat/completions"
        last_error = ""
        for attempt in range(1, self.max_retries + 1):
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = json.loads(response.read().decode("utf-8"))
                choice = raw["choices"][0]
                content = str((choice.get("message") or {}).get("content") or "")
                return content, {"finish_reason": choice.get("finish_reason"), "attempts": attempt, "task": task}
            except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
                last_error = str(exc)
                time.sleep(min(4, attempt))
        raise RuntimeError(f"LLM call failed for {task}: {last_error}")


def load_local_config(path: Path) -> dict[str, Any]:
    path = path.expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = parse_simple_yaml(text)
    if not isinstance(data, dict):
        raise ValueError(f"Config must be an object: {path}")
    return data


def parse_simple_yaml(text: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
        return data if isinstance(data, dict) else {}
    except ImportError:
        return parse_minimal_mapping(text)


def parse_minimal_mapping(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().strip("\"'")
        value = value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = parse_scalar(value)
    return root


def parse_scalar(value: str) -> Any:
    text = value.strip()
    if text in {"true", "True"}:
        return True
    if text in {"false", "False"}:
        return False
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def render_prompt(prompt_name: str, values: dict[str, Any]) -> str:
    path = REPO_ROOT / "task_specs" / "prompts" / "reports" / f"{prompt_name}.md"
    template = path.read_text(encoding="utf-8")
    for key, value in values.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def compact_json(data: Any, max_chars: int) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n... <truncated evidence pack>"


def edge_rank(edge: dict[str, Any]) -> tuple[float, int, str]:
    return (
        safe_float(edge.get("confidence")),
        safe_int(edge.get("time_delta_days")),
        str(edge.get("edge_id") or ""),
    )


def pattern_title(value: Any) -> str:
    key = str(value or "").strip().lower()
    labels = {
        "substitution": "替代模式",
        "institutionalization": "制度化模式",
        "recontextualization": "重新语境化模式",
        "hybridization": "混合化模式",
        "differentiation": "分化模式",
        "convergence": "汇聚模式",
        "cyclical_return": "循环回归模式",
        "stabilization": "稳定化模式",
        "fragmentation": "碎片化模式",
    }
    if key in labels:
        return labels[key]
    return str(value or "").replace("_", " ").strip().title()


def pattern_short_name(value: Any) -> str:
    key = str(value or "").strip().lower()
    labels = {
        "substitution": "替代",
        "institutionalization": "制度化",
        "recontextualization": "重新语境化",
        "hybridization": "混合化",
        "differentiation": "分化",
        "convergence": "汇聚",
        "cyclical_return": "循环回归",
        "stabilization": "稳定化",
        "fragmentation": "碎片化",
    }
    return labels.get(key, str(value or "").replace("_", " "))


def relation_label(value: Any) -> str:
    labels = {
        "replaces": "替代",
        "extends": "扩展",
        "adapts": "语境适配",
        "improves": "改进",
        "generalizes": "泛化",
        "specializes": "专门化",
    }
    return labels.get(str(value or ""), str(value or "").replace("_", " "))


def role_label(value: Any) -> str:
    labels = {
        "method": "方法",
        "measurement_strategy": "测量策略",
        "modeling_strategy": "建模策略",
        "evaluation_protocol": "评估协议",
        "infrastructure_tooling": "基础设施/工具",
        "data_source": "数据来源",
        "governance_practice": "治理实践",
    }
    return labels.get(str(value or ""), str(value or "").replace("_", " "))


def readable_transition(value: Any) -> str:
    text = str(value or "")
    for key in [
        "measurement_strategy",
        "modeling_strategy",
        "evaluation_protocol",
        "infrastructure_tooling",
        "data_source",
        "governance_practice",
        "method",
    ]:
        text = text.replace(key, role_label(key))
    return text.replace("->", "→")


def gap_years(value: Any) -> float | None:
    days = safe_float(value)
    if days <= 0:
        return None
    return round(days / 365.25, 1)


def update_agent_manifest(
    run_root: Path,
    output: Path,
    summary_path: Path,
    evidence_output: Path,
    reader_evidence_output: Path,
    trace_output: Path,
) -> None:
    manifest_path = run_root / "manifest.json"
    if not manifest_path.exists():
        return
    manifest = read_json(manifest_path, default={})
    if not isinstance(manifest, dict):
        return
    layout = manifest.setdefault("artifact_layout", {})
    layout["agentic_evolution_insight_report"] = relative_path(output, run_root)
    layout["agentic_evolution_insight_report_summary"] = relative_path(summary_path, run_root)
    layout["agentic_evolution_insight_evidence_pack"] = relative_path(evidence_output, run_root)
    layout["agentic_evolution_insight_reader_evidence_pack"] = relative_path(reader_evidence_output, run_root)
    layout["agentic_evolution_insight_trace"] = relative_path(trace_output, run_root)
    counts = manifest.setdefault("counts", {})
    counts["agentic_evolution_insight_reports"] = 1
    write_json(manifest_path, manifest)


if __name__ == "__main__":
    raise SystemExit(main())
