#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from evotaxa.io import iter_jsonl, write_json, write_jsonl  # noqa: E402


CORE_MAIN_EDGE_TYPES = {"extends", "improves", "replaces", "adapts", "operationalizes", "enables", "validates", "combines"}
AUDIT_COLUMNS = [
    "sample_id",
    "edge_id",
    "edge_status",
    "stratum",
    "role_pair",
    "edge_type",
    "confidence",
    "source_entity",
    "target_entity",
    "source_role",
    "target_role",
    "source_document",
    "target_document",
    "source_title",
    "target_title",
    "time_delta_days",
    "taxonomy_nodes",
    "cue",
    "verified_quote_count",
    "verified_quote_fields",
    "quote",
    "quote_document",
    "auto_flags",
    "auto_recommendation",
    "manual_entity_ok",
    "manual_relation_ok",
    "manual_quote_supports_edge",
    "manual_taxonomy_ok",
    "manual_primary_evidence_layer",
    "manual_notes",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a role-aware stratified audit sample for EvoTaxa edges.")
    parser.add_argument("--run-root", type=Path, required=True, help="Completed EvoTaxa run output root.")
    parser.add_argument("--output-root", type=Path, required=True, help="Audit output directory.")
    parser.add_argument("--seed", type=int, default=20260530)
    parser.add_argument("--per-role-pair", type=int, default=8)
    parser.add_argument("--per-edge-type", type=int, default=4)
    parser.add_argument("--per-status", type=int, default=24)
    parser.add_argument("--max-samples", type=int, default=120)
    args = parser.parse_args()

    run_root = args.run_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    documents = load_documents(run_root / "corpus" / "documents.normalized.jsonl")
    nodes = load_taxonomy_nodes(run_root / "taxonomy" / "taxonomy_nodes.enriched.json")
    entities = load_entities(run_root / "graph" / "method_registry.jsonl")
    edges = load_edges(run_root)
    audit_by_edge = load_edge_evidence_audit(run_root / "graph" / "edge_evidence_audit.jsonl")

    rng = random.Random(args.seed)
    selected = select_edges(
        edges,
        documents=documents,
        seed_rng=rng,
        per_role_pair=args.per_role_pair,
        per_edge_type=args.per_edge_type,
        per_status=args.per_status,
        max_samples=args.max_samples,
    )
    sample_rows = [
        build_sample_row(
            index=index,
            edge=edge,
            documents=documents,
            entities=entities,
            nodes=nodes,
            audit=audit_by_edge.get(str(edge.get("edge_id") or ""), {}),
        )
        for index, edge in enumerate(selected, start=1)
    ]

    write_jsonl(output_root / "edge_audit_sample.jsonl", sample_rows)
    write_csv(output_root / "edge_audit_sheet.csv", sample_rows)
    summary = build_summary(
        run_root=run_root,
        output_root=output_root,
        seed=args.seed,
        edges=edges,
        selected=sample_rows,
        documents=documents,
        params={
            "per_role_pair": args.per_role_pair,
            "per_edge_type": args.per_edge_type,
            "per_status": args.per_status,
            "max_samples": args.max_samples,
        },
    )
    write_json(output_root / "edge_audit_summary.json", summary)
    write_markdown_report(output_root / "edge_audit_readme.md", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def load_documents(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row.get("doc_id") or ""): row for row in iter_jsonl(path)}


def load_entities(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row.get("entity_id") or ""): row for row in iter_jsonl(path)}


def load_taxonomy_nodes(path: Path) -> dict[str, dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, list):
        return {}
    return {str(row.get("node_id") or row.get("id") or ""): row for row in raw if isinstance(row, dict)}


def load_edges(run_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for status, filename in [
        ("trusted", "method_edges.trusted.jsonl"),
        ("candidate", "method_edges.candidate.jsonl"),
    ]:
        path = run_root / "graph" / filename
        for row in iter_jsonl(path):
            item = dict(row)
            item["edge_status"] = status
            rows.append(item)
    return rows


def load_edge_evidence_audit(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row.get("edge_id") or ""): row for row in iter_jsonl(path)}


def select_edges(
    edges: list[dict[str, Any]],
    *,
    documents: dict[str, dict[str, Any]],
    seed_rng: random.Random,
    per_role_pair: int,
    per_edge_type: int,
    per_status: int,
    max_samples: int,
) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}

    def add_sample(rows: list[dict[str, Any]], limit: int) -> None:
        if limit <= 0 or not rows:
            return
        shuffled = list(rows)
        seed_rng.shuffle(shuffled)
        for row in shuffled[:limit]:
            selected.setdefault(str(row.get("edge_id") or ""), row)

    by_status: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_role_pair: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_edge_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_status_role_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_status_edge_type: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for edge in edges:
        status = str(edge.get("edge_status") or "unknown")
        edge_type = str(edge.get("edge_type") or "unknown")
        role_pair = edge_role_pair(edge, documents)
        by_status[status].append(edge)
        by_role_pair[role_pair].append(edge)
        by_edge_type[edge_type].append(edge)
        by_status_role_pair[(status, role_pair)].append(edge)
        by_status_edge_type[(status, edge_type)].append(edge)

    for status in sorted(by_status):
        add_sample(by_status[status], per_status)
    for key in sorted(by_status_role_pair):
        add_sample(by_status_role_pair[key], per_role_pair)
    for key in sorted(by_status_edge_type):
        add_sample(by_status_edge_type[key], per_edge_type)

    ranked = sorted(
        selected.values(),
        key=lambda row: (
            str(row.get("edge_status") or ""),
            edge_role_pair(row, documents),
            str(row.get("edge_type") or ""),
            str(row.get("edge_id") or ""),
        ),
    )
    if max_samples > 0 and len(ranked) > max_samples:
        keep = set()
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in ranked:
            grouped[str(row.get("edge_status") or "unknown")].append(row)
        status_quota = max(1, max_samples // max(1, len(grouped)))
        for status in sorted(grouped):
            subset = list(grouped[status])
            seed_rng.shuffle(subset)
            keep.update(str(row.get("edge_id") or "") for row in subset[:status_quota])
        remaining = [row for row in ranked if str(row.get("edge_id") or "") not in keep]
        seed_rng.shuffle(remaining)
        for row in remaining[: max(0, max_samples - len(keep))]:
            keep.add(str(row.get("edge_id") or ""))
        ranked = [row for row in ranked if str(row.get("edge_id") or "") in keep]
    return ranked


def build_sample_row(
    *,
    index: int,
    edge: dict[str, Any],
    documents: dict[str, dict[str, Any]],
    entities: dict[str, dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
    audit: dict[str, Any],
) -> dict[str, Any]:
    source_doc = documents.get(str(edge.get("source_document") or ""), {})
    target_doc = documents.get(str(edge.get("target_document") or ""), {})
    source_role = str(source_doc.get("role") or "missing")
    target_role = str(target_doc.get("role") or "missing")
    source_entity_id = str(edge.get("source_entity") or "")
    target_entity_id = str(edge.get("target_entity") or "")
    source_entity = entities.get(source_entity_id, {})
    target_entity = entities.get(target_entity_id, {})
    edge_type = str(edge.get("edge_type") or "")
    quote_info = best_quote(edge=edge, audit=audit)
    taxonomy_nodes = [str(node_id) for node_id in edge.get("taxonomy_nodes") or []]
    flags = auto_flags(
        edge=edge,
        source_doc=source_doc,
        target_doc=target_doc,
        source_entity=source_entity,
        target_entity=target_entity,
        taxonomy_nodes=[nodes.get(node_id, {}) for node_id in taxonomy_nodes],
        quote_info=quote_info,
    )
    return {
        "sample_id": f"edge_audit_{index:04d}",
        "edge_id": str(edge.get("edge_id") or ""),
        "edge_status": str(edge.get("edge_status") or ""),
        "stratum": f"{edge.get('edge_status')}|{source_role}->{target_role}|{edge_type}",
        "role_pair": f"{source_role}->{target_role}",
        "edge_type": edge_type,
        "confidence": edge.get("confidence"),
        "source_entity": source_entity_display(edge, "source", source_entity),
        "target_entity": source_entity_display(edge, "target", target_entity),
        "source_entity_id": source_entity_id,
        "target_entity_id": target_entity_id,
        "source_entity_type": source_entity.get("entity_type") or entity_type_from_id(source_entity_id),
        "target_entity_type": target_entity.get("entity_type") or entity_type_from_id(target_entity_id),
        "source_role": source_role,
        "target_role": target_role,
        "source_document": str(edge.get("source_document") or ""),
        "target_document": str(edge.get("target_document") or ""),
        "source_title": source_doc.get("title") or "",
        "target_title": target_doc.get("title") or "",
        "source_screening_decision": ((source_doc.get("raw") or {}).get("screening") or {}).get("screening_decision", ""),
        "target_screening_decision": ((target_doc.get("raw") or {}).get("screening") or {}).get("screening_decision", ""),
        "time_delta_days": edge.get("time_delta_days"),
        "taxonomy_nodes": taxonomy_nodes,
        "taxonomy_node_labels": [nodes.get(node_id, {}).get("canonical_label", node_id) for node_id in taxonomy_nodes],
        "cue": ((edge.get("evidence") or {}).get("cue") or ""),
        "verified_quote_count": audit.get("verified_quote_count")
        or (((edge.get("evidence") or {}).get("evidence_audit") or {}).get("verified_quote_count") or 0),
        "verified_quote_fields": audit.get("verified_quote_fields")
        or (((edge.get("evidence") or {}).get("evidence_audit") or {}).get("verified_quote_fields") or []),
        "quote_field": quote_info["field"],
        "quote": quote_info["quote"],
        "quote_document": quote_info["matched_document"],
        "quote_reason": quote_info["reason"],
        "auto_flags": flags,
        "auto_recommendation": auto_recommendation(edge=edge, flags=flags, role_pair=f"{source_role}->{target_role}"),
        "source_doc_excerpt": excerpt(source_doc.get("text") or "", quote_info["quote"]),
        "target_doc_excerpt": excerpt(target_doc.get("text") or "", quote_info["quote"]),
        "manual_entity_ok": "",
        "manual_relation_ok": "",
        "manual_quote_supports_edge": "",
        "manual_taxonomy_ok": "",
        "manual_primary_evidence_layer": "",
        "manual_notes": "",
    }


def source_entity_display(edge: dict[str, Any], side: str, entity: dict[str, Any]) -> str:
    key = f"{side}_entity"
    return str(entity.get("canonical_name") or edge.get(key) or "")


def entity_type_from_id(entity_id: str) -> str:
    return entity_id.split("__", 1)[0] if "__" in entity_id else ""


def edge_role_pair(edge: dict[str, Any], documents: dict[str, dict[str, Any]]) -> str:
    source_role = str(documents.get(str(edge.get("source_document") or ""), {}).get("role") or "missing")
    target_role = str(documents.get(str(edge.get("target_document") or ""), {}).get("role") or "missing")
    return f"{source_role}->{target_role}"


def best_quote(*, edge: dict[str, Any], audit: dict[str, Any]) -> dict[str, str]:
    checks = audit.get("quote_checks") if isinstance(audit, dict) else None
    if isinstance(checks, list):
        verified = [row for row in checks if isinstance(row, dict) and row.get("verified") and str(row.get("quote") or "").strip()]
        if verified:
            row = max(verified, key=lambda item: len(str(item.get("quote") or "")))
            return {
                "field": str(row.get("field") or ""),
                "quote": compact(str(row.get("quote") or "")),
                "matched_document": str(row.get("matched_document") or ""),
                "reason": str(row.get("reason") or ""),
            }
    evidence = edge.get("evidence") or {}
    best = {"field": "", "quote": "", "matched_document": "", "reason": "missing_quote"}
    for field, value in evidence.items():
        if not isinstance(value, dict):
            continue
        quote = compact(str(value.get("quote") or ""))
        if len(quote) > len(best["quote"]):
            best = {"field": str(field), "quote": quote, "matched_document": "", "reason": "edge_evidence_quote"}
    return best


def auto_flags(
    *,
    edge: dict[str, Any],
    source_doc: dict[str, Any],
    target_doc: dict[str, Any],
    source_entity: dict[str, Any],
    target_entity: dict[str, Any],
    taxonomy_nodes: list[dict[str, Any]],
    quote_info: dict[str, str],
) -> list[str]:
    flags: list[str] = []
    edge_type = str(edge.get("edge_type") or "")
    if edge_type not in CORE_MAIN_EDGE_TYPES:
        flags.append("weak_edge_type_for_primary_claim")
    if int(edge.get("time_delta_days") or 0) < 0:
        flags.append("negative_time_delta")
    if not quote_info.get("quote"):
        flags.append("missing_quote")
    if quote_info.get("quote") and not quote_mentions_entities(
        quote_info["quote"],
        [source_entity.get("canonical_name"), target_entity.get("canonical_name")],
    ):
        flags.append("quote_does_not_name_both_entities")
    for side, entity in [("source", source_entity), ("target", target_entity)]:
        name = str(entity.get("canonical_name") or "")
        if entity_is_taxonomy_label(name, taxonomy_nodes):
            flags.append(f"{side}_entity_matches_taxonomy_label")
        if entity_is_generic(name):
            flags.append(f"{side}_entity_generic_or_broad")
        if entity_looks_like_title_fragment(name, [source_doc.get("title") or "", target_doc.get("title") or ""]):
            flags.append(f"{side}_entity_title_fragment")
    source_role = str(source_doc.get("role") or "missing")
    target_role = str(target_doc.get("role") or "missing")
    if source_role == "support" or target_role == "support":
        flags.append("support_involved")
    if source_role == "support" and target_role == "support":
        flags.append("support_only_edge")
    return sorted(set(flags))


def quote_mentions_entities(quote: str, names: list[Any]) -> bool:
    quote_norm = compact(quote).lower()
    hits = 0
    for name in names:
        raw = compact(str(name or "")).lower()
        if not raw:
            continue
        tokens = [token for token in re.findall(r"[a-z0-9]+", raw) if len(token) > 2]
        if raw in quote_norm or sum(1 for token in tokens if token in quote_norm) >= min(2, len(tokens)):
            hits += 1
    return hits >= 2


def entity_is_taxonomy_label(name: str, nodes: list[dict[str, Any]]) -> bool:
    norm = normalize_name(name)
    labels = {normalize_name(node.get("canonical_label") or node.get("label") or "") for node in nodes}
    labels.update(normalize_name(alias) for node in nodes for alias in (node.get("aliases") or []))
    return bool(norm and norm in labels)


def entity_is_generic(name: str) -> bool:
    norm = normalize_name(name)
    generic = {
        "computational social science",
        "data source evidence base",
        "computational infrastructure algorithms",
        "reproducibility ethics governance",
        "machine learning ai classification",
        "modeling simulation strategy",
        "measurement annotation strategy",
        "evaluation validation practice",
        "network analysis",
        "text as data computational text analysis",
        "digital trace data",
        "online interaction social media",
    }
    tokens = norm.split()
    return norm in generic or len(tokens) == 1 or len(tokens) >= 8


def entity_looks_like_title_fragment(name: str, titles: list[str]) -> bool:
    norm = normalize_name(name)
    if not norm or len(norm.split()) < 4:
        return False
    return any(norm in normalize_name(title) for title in titles)


def normalize_name(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def auto_recommendation(*, edge: dict[str, Any], flags: list[str], role_pair: str) -> str:
    flag_set = set(flags)
    if "missing_quote" in flag_set or "negative_time_delta" in flag_set:
        return "reject_or_reinspect"
    if any(flag.endswith("_entity_title_fragment") or flag.endswith("_entity_generic_or_broad") for flag in flag_set):
        return "entity_repair_needed"
    if "quote_does_not_name_both_entities" in flag_set:
        return "quote_relation_reinspect"
    if role_pair == "core->core" and edge.get("edge_type") in CORE_MAIN_EDGE_TYPES:
        return "primary_candidate"
    if "support_only_edge" in flag_set:
        return "discovery_only"
    if "support_involved" in flag_set:
        return "auxiliary_candidate"
    return "manual_review"


def excerpt(text: str, quote: str, *, radius: int = 260) -> str:
    text = compact(text)
    quote = compact(quote)
    if not text:
        return ""
    if not quote:
        return text[: radius * 2]
    idx = text.lower().find(quote[:80].lower())
    if idx < 0:
        return text[: radius * 2]
    start = max(0, idx - radius)
    end = min(len(text), idx + len(quote) + radius)
    return text[start:end]


def compact(value: str) -> str:
    return " ".join(str(value or "").split())


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            csv_row = dict(row)
            for key, value in list(csv_row.items()):
                if isinstance(value, (list, dict)):
                    csv_row[key] = json.dumps(value, ensure_ascii=False)
            writer.writerow(csv_row)


def build_summary(
    *,
    run_root: Path,
    output_root: Path,
    seed: int,
    edges: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    params: dict[str, Any],
) -> dict[str, Any]:
    edge_counts = Counter(str(edge.get("edge_status") or "unknown") for edge in edges)
    sample_counts = Counter(str(row.get("edge_status") or "unknown") for row in selected)
    role_pairs_all = Counter(edge_role_pair(edge, documents) for edge in edges)
    role_pairs_sample = Counter(str(row.get("role_pair") or "unknown") for row in selected)
    edge_types_sample = Counter(str(row.get("edge_type") or "unknown") for row in selected)
    recommendations = Counter(str(row.get("auto_recommendation") or "unknown") for row in selected)
    flags = Counter(flag for row in selected for flag in row.get("auto_flags") or [])
    return {
        "script": "audit_edges_role_aware.py",
        "run_root": str(run_root),
        "output_root": str(output_root),
        "seed": seed,
        "parameters": params,
        "input_edge_count": len(edges),
        "input_edge_counts_by_status": dict(sorted(edge_counts.items())),
        "input_role_pairs": dict(sorted(role_pairs_all.items())),
        "sample_count": len(selected),
        "sample_counts_by_status": dict(sorted(sample_counts.items())),
        "sample_role_pairs": dict(sorted(role_pairs_sample.items())),
        "sample_edge_types": dict(sorted(edge_types_sample.items())),
        "auto_recommendations": dict(sorted(recommendations.items())),
        "auto_flags": dict(sorted(flags.items())),
        "outputs": {
            "sample_jsonl": str(output_root / "edge_audit_sample.jsonl"),
            "audit_sheet_csv": str(output_root / "edge_audit_sheet.csv"),
            "summary": str(output_root / "edge_audit_summary.json"),
            "readme": str(output_root / "edge_audit_readme.md"),
        },
    }


def write_markdown_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Role-Aware Edge Audit",
        "",
        f"- Run root: `{summary['run_root']}`",
        f"- Seed: `{summary['seed']}`",
        f"- Input edges: `{summary['input_edge_count']}`",
        f"- Sample edges: `{summary['sample_count']}`",
        "",
        "## Sample Status Counts",
        "",
    ]
    for key, value in summary["sample_counts_by_status"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Role Pairs", ""])
    for key, value in summary["sample_role_pairs"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Auto Recommendations", ""])
    for key, value in summary["auto_recommendations"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(
        [
            "",
            "## Manual Audit Columns",
            "",
            "- `manual_entity_ok`: yes/no/partial",
            "- `manual_relation_ok`: yes/no/partial",
            "- `manual_quote_supports_edge`: yes/no/partial",
            "- `manual_taxonomy_ok`: yes/no/partial",
            "- `manual_primary_evidence_layer`: primary/auxiliary/discovery/reject",
            "- `manual_notes`: short rationale",
            "",
            "The CSV is meant for manual or LLM-assisted annotation. The JSONL preserves full excerpts and machine diagnostics.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
