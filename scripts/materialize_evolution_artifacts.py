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
from schema_groups import (
    SCHEMA_GROUPS,
    schema_group_definition,
    schema_group_for_type,
    schema_group_label,
    schema_group_records,
)  # noqa: E402


SUCCESSOR_EDGE_PATH = "graph/successor_edges.accepted.jsonl"
ENTITY_CARD_PATH = "graph/entity_cards.jsonl"
ENTITY_TYPE_DIAGNOSTIC_PATH = "schema/entity_type_diagnostics.json"
ENTITY_SCHEMA_GROUP_PATH = "schema/entity_schema_groups.json"
SUCCESSOR_TRAJECTORY_PATH = "trajectory/successor_trajectories.jsonl"
SUCCESSOR_TRAJECTORY_EVAL_PATH = "trajectory/successor_trajectory_eval.jsonl"
SOCIAL_CONTEXT_TERMS = {
    "annotation",
    "behavior",
    "behaviour",
    "bias",
    "classification",
    "coding",
    "community",
    "conversation",
    "discourse",
    "election",
    "emotion",
    "event",
    "gender",
    "governance",
    "hate",
    "ideology",
    "misinformation",
    "network",
    "online",
    "platform",
    "policy",
    "political",
    "population",
    "propaganda",
    "public",
    "sentiment",
    "sexism",
    "social",
    "survey",
    "text",
    "tweet",
    "twitter",
    "user",
}
GENERIC_TECH_TERMS = {
    "algorithm",
    "algorithms",
    "attention",
    "bayesian",
    "bert",
    "cnn",
    "convolutional",
    "deep",
    "embedding",
    "embeddings",
    "gcn",
    "gnn",
    "graph",
    "language",
    "learning",
    "logistic",
    "machine",
    "model",
    "models",
    "neural",
    "regression",
    "transformer",
    "transformers",
}
TYPE_MERGE_GROUPS = {
    "analytic_method": {"method", "modeling_strategy", "measurement_strategy"},
    "evidence_and_infrastructure": {"data_source", "infrastructure_tooling"},
    "validation_and_governance": {"evaluation_protocol", "governance_practice"},
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize first-class node cards and successor-edge trajectories for an EvoTaxa run."
    )
    parser.add_argument("--run-root", type=Path, required=True, help="Completed EvoTaxa run root.")
    parser.add_argument("--support-doc-limit", type=int, default=24)
    parser.add_argument("--mention-limit", type=int, default=24)
    parser.add_argument("--edge-limit", type=int, default=24)
    args = parser.parse_args()

    run_root = args.run_root.expanduser().resolve()
    if not run_root.exists():
        raise FileNotFoundError(f"Run root does not exist: {run_root}")

    result = materialize_evolution_artifacts(
        run_root,
        support_doc_limit=max(1, args.support_doc_limit),
        mention_limit=max(1, args.mention_limit),
        edge_limit=max(1, args.edge_limit),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def materialize_evolution_artifacts(
    run_root: Path,
    *,
    support_doc_limit: int,
    mention_limit: int,
    edge_limit: int,
) -> dict[str, Any]:
    docs = build_document_map(read_jsonl(run_root / "corpus" / "documents.normalized.jsonl"))
    taxonomy = build_taxonomy_map(
        read_json(run_root / "taxonomy" / "taxonomy_nodes.expanded.json", default=[])
        or read_json(run_root / "taxonomy" / "taxonomy_nodes.enriched.json", default=[])
    )
    entity_schema = read_json(run_root / "schema" / "entity_schema.final.json", default={})
    relation_schema = read_json(run_root / "schema" / "relation_schema.final.json", default={})
    entities = {
        str(row.get("entity_id") or ""): row
        for row in read_jsonl(run_root / "graph" / "method_registry.jsonl")
        if row.get("entity_id")
    }
    mentions_by_entity = load_mentions_by_entity(run_root)
    successor_edges = read_jsonl(run_root / SUCCESSOR_EDGE_PATH)
    successor_edges = [edge for edge in successor_edges if is_successor_edge(edge, entities)]
    edge_by_id = {str(edge.get("edge_id") or ""): edge for edge in successor_edges if edge.get("edge_id")}
    incoming, outgoing = incident_successor_edges(successor_edges)
    degree = Counter()
    for edge in successor_edges:
        source = str(edge.get("source_entity") or "")
        target = str(edge.get("target_entity") or "")
        if source:
            degree[source] += 1
        if target:
            degree[target] += 1

    entity_cards = [
        build_entity_card(
            entity_id,
            row,
            docs=docs,
            taxonomy=taxonomy,
            entity_schema=entity_schema,
            incoming=incoming,
            outgoing=outgoing,
            mentions=mentions_by_entity.get(entity_id, []),
            degree=degree,
            support_doc_limit=support_doc_limit,
            mention_limit=mention_limit,
            edge_limit=edge_limit,
        )
        for entity_id, row in sorted(entities.items())
    ]
    entity_cards_by_id = {str(card.get("entity_id") or ""): card for card in entity_cards if card.get("entity_id")}
    trajectories = build_successor_trajectories(successor_edges, entities, entity_cards_by_id=entity_cards_by_id)
    trajectory_eval = evaluate_successor_trajectories(trajectories, edge_by_id)

    cards_path = run_root / ENTITY_CARD_PATH
    trajectories_path = run_root / SUCCESSOR_TRAJECTORY_PATH
    trajectory_eval_path = run_root / SUCCESSOR_TRAJECTORY_EVAL_PATH
    write_jsonl(cards_path, entity_cards)
    write_jsonl(trajectories_path, trajectories)
    write_jsonl(trajectory_eval_path, trajectory_eval)
    type_diagnostic = build_entity_type_diagnostics(entity_cards, successor_edges, entity_schema)
    type_diagnostic_path = run_root / ENTITY_TYPE_DIAGNOSTIC_PATH
    write_json(type_diagnostic_path, type_diagnostic)
    schema_group_path = run_root / ENTITY_SCHEMA_GROUP_PATH
    write_json(schema_group_path, schema_group_records(entity_schema))
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_root": str(run_root),
        "entity_cards": len(entity_cards),
        "successor_edges": len(successor_edges),
        "successor_trajectories": len(trajectories),
        "entities_with_successor_predecessor": len(incoming),
        "entities_as_successor_predecessor": len(outgoing),
        "entity_cards_path": str(cards_path),
        "successor_trajectories_path": str(trajectories_path),
        "successor_trajectory_eval_path": str(trajectory_eval_path),
        "entity_type_diagnostic_path": str(type_diagnostic_path),
        "entity_schema_group_path": str(schema_group_path),
        "policy": "Node cards and trajectories are materialized from strict successor edges only; legacy trusted edges are not used here.",
    }
    write_json(run_root / "graph" / "entity_cards.summary.json", summary)
    update_manifest(run_root, summary)
    return summary


def read_json(path: Path, *, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        return default


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return list(iter_jsonl(path))


def build_document_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    docs: dict[str, dict[str, Any]] = {}
    for row in rows:
        doc_id = str(row.get("doc_id") or "")
        if not doc_id:
            continue
        published_at = str(row.get("published_at") or "")
        parsed = parse_date(published_at)
        docs[doc_id] = {
            "doc_id": doc_id,
            "title": normalize_space(row.get("title") or doc_id),
            "published_at": parsed.isoformat() if parsed else published_at,
            "year": parsed.year if parsed else year_from_value(row.get("chronology_slice") or published_at),
            "role": str(row.get("role") or ""),
            "source_type": str(row.get("source_type") or ""),
            "text": normalize_space(row.get("text") or "")[:1600],
        }
    return docs


def build_taxonomy_map(value: Any) -> dict[str, dict[str, Any]]:
    taxonomy: dict[str, dict[str, Any]] = {}
    rows = value if isinstance(value, list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        node_id = str(row.get("node_id") or "")
        if not node_id:
            continue
        taxonomy[node_id] = {
            "node_id": node_id,
            "label": normalize_space(row.get("canonical_label") or node_id),
            "dimension": str(row.get("dimension") or ""),
            "definition": normalize_space(row.get("definition") or ""),
        }
    return taxonomy


def load_mentions_by_entity(run_root: Path) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path_name in ["graph/llm_entity_mentions.jsonl", "graph/paper_method_mentions.jsonl"]:
        for row in read_jsonl(run_root / path_name):
            entity_id = str(row.get("entity_id") or "")
            quote = normalize_space(row.get("quote") or row.get("evidence") or "")
            if not entity_id or not quote:
                continue
            rows[entity_id].append(
                {
                    "doc_id": str(row.get("doc_id") or ""),
                    "name": normalize_space(row.get("name") or row.get("canonical_name") or ""),
                    "quote": quote[:1000],
                    "confidence": row.get("confidence"),
                    "status": str(row.get("status") or ""),
                    "reason": str(row.get("reason") or ""),
                    "source": path_name,
                }
            )
    for entity_id, mentions in list(rows.items()):
        seen = set()
        unique = []
        for mention in sorted(mentions, key=lambda item: (-len(str(item.get("quote") or "")), str(item.get("doc_id") or ""))):
            key = (mention.get("doc_id"), mention.get("quote"))
            if key in seen:
                continue
            seen.add(key)
            unique.append(mention)
        rows[entity_id] = unique
    return dict(rows)


def is_successor_edge(edge: dict[str, Any], entities: dict[str, dict[str, Any]]) -> bool:
    source = str(edge.get("source_entity") or "")
    target = str(edge.get("target_entity") or "")
    if not source or not target:
        return False
    source_type = str((entities.get(source) or {}).get("entity_type") or source.split("__", 1)[0])
    target_type = str((entities.get(target) or {}).get("entity_type") or target.split("__", 1)[0])
    source_group = str(edge.get("source_schema_group") or edge.get("schema_group") or schema_group_for_type(source_type))
    target_group = str(edge.get("target_schema_group") or edge.get("schema_group") or schema_group_for_type(target_type))
    if source_group != target_group:
        return False
    try:
        return int(edge.get("time_delta_days") or 0) > 0
    except (TypeError, ValueError):
        return False


def incident_successor_edges(
    edges: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        source = str(edge.get("source_entity") or "")
        target = str(edge.get("target_entity") or "")
        if source:
            outgoing[source].append(edge)
        if target:
            incoming[target].append(edge)
    for group in [incoming, outgoing]:
        for entity_id, rows in group.items():
            rows.sort(key=lambda edge: (-safe_float(edge.get("confidence")), str(edge.get("edge_id") or "")))
    return dict(incoming), dict(outgoing)


def build_entity_card(
    entity_id: str,
    row: dict[str, Any],
    *,
    docs: dict[str, dict[str, Any]],
    taxonomy: dict[str, dict[str, Any]],
    entity_schema: dict[str, Any],
    incoming: dict[str, list[dict[str, Any]]],
    outgoing: dict[str, list[dict[str, Any]]],
    mentions: list[dict[str, Any]],
    degree: Counter[str],
    support_doc_limit: int,
    mention_limit: int,
    edge_limit: int,
) -> dict[str, Any]:
    entity_type = str(row.get("entity_type") or "unknown")
    schema_group = schema_group_for_type(entity_type)
    schema = entity_schema.get(entity_type) if isinstance(entity_schema, dict) else {}
    support_doc_ids = as_str_list(row.get("support_documents"))
    support_documents = [docs.get(doc_id) or {"doc_id": doc_id, "title": doc_id} for doc_id in support_doc_ids[:support_doc_limit]]
    taxonomy_nodes = as_str_list(row.get("taxonomy_nodes"))
    first_seen = str(row.get("first_seen_date") or "")
    if not parse_date(first_seen):
        years = [doc.get("year") for doc in support_documents if doc.get("year")]
        if years:
            first_seen = f"{min(years)}-01-01"
    incoming_edges = [compact_edge(edge) for edge in incoming.get(entity_id, [])[:edge_limit]]
    outgoing_edges = [compact_edge(edge) for edge in outgoing.get(entity_id, [])[:edge_limit]]
    canonical_name = normalize_space(row.get("canonical_name") or entity_name_from_id(entity_id))
    surface_name = readable_surface_name(canonical_name, mentions)
    context = infer_domain_context(
        canonical_name=canonical_name,
        surface_name=surface_name,
        entity_type=entity_type,
        taxonomy_labels=[taxonomy_label(taxonomy, node_id) for node_id in taxonomy_nodes],
        mentions=mentions,
        support_documents=support_documents,
    )
    return {
        "card_schema_version": "1.0",
        "entity_id": entity_id,
        "canonical_name": canonical_name,
        "contextual_name": context["contextual_name"],
        "display_name": context["display_name"],
        "domain_context": context["domain_context"],
        "method_role": context["method_role"],
        "context_terms": context["context_terms"],
        "generic_technology_name": context["generic_technology_name"],
        "domain_grounding_score": context["domain_grounding_score"],
        "aliases": as_str_list(row.get("aliases"))[:16],
        "entity_type": entity_type,
        "entity_type_label": normalize_space((schema or {}).get("label") or entity_type),
        "entity_type_definition": normalize_space((schema or {}).get("definition") or ""),
        "schema_group": schema_group,
        "schema_group_label": schema_group_label(schema_group),
        "schema_group_definition": schema_group_definition(schema_group),
        "schema_group_members": list((SCHEMA_GROUPS.get(schema_group) or {}).get("member_types") or [entity_type]),
        "first_seen_date": first_seen,
        "support_document_count": len(support_doc_ids),
        "support_documents": support_documents,
        "taxonomy_nodes": taxonomy_nodes,
        "taxonomy_labels": [taxonomy_label(taxonomy, node_id) for node_id in taxonomy_nodes],
        "representative_mentions": mentions[:mention_limit],
        "successor_degree": int(degree[entity_id]),
        "incoming_successor_edges": incoming_edges,
        "outgoing_successor_edges": outgoing_edges,
        "has_accepted_predecessor": bool(incoming_edges),
        "as_accepted_predecessor": bool(outgoing_edges),
        "raw_entity": row,
    }


def infer_domain_context(
    *,
    canonical_name: str,
    surface_name: str,
    entity_type: str,
    taxonomy_labels: list[str],
    mentions: list[dict[str, Any]],
    support_documents: list[dict[str, Any]],
) -> dict[str, Any]:
    text_chunks = [canonical_name, " ".join(taxonomy_labels)]
    text_chunks.extend(str(mention.get("quote") or "") for mention in mentions[:8])
    text_chunks.extend(str(doc.get("title") or "") for doc in support_documents[:8])
    text = normalize_space(" ".join(text_chunks))
    tokens = content_tokens(text)
    name_tokens = content_tokens(canonical_name)
    context_terms = sorted((tokens & SOCIAL_CONTEXT_TERMS) - name_tokens)
    strong_social_name_terms = SOCIAL_CONTEXT_TERMS - {"classification", "event", "network", "text", "user"}
    generic_name = bool(name_tokens & GENERIC_TECH_TERMS) and not bool(name_tokens & strong_social_name_terms)
    role = infer_method_role(entity_type, text)
    context_phrase = context_phrase_from_terms(context_terms, taxonomy_labels)
    base_name = surface_name or canonical_name
    contextual_name = base_name
    if generic_name and context_phrase:
        contextual_name = f"{base_name} for {context_phrase}"
    elif context_phrase and context_phrase not in base_name.lower() and len(base_name.split()) <= 3:
        contextual_name = f"{base_name} in {context_phrase}"
    domain_context = context_phrase
    if not domain_context:
        domain_context = "; ".join(label for label in taxonomy_labels[:3] if label)
    score = min(1.0, 0.15 * len(context_terms) + (0.25 if taxonomy_labels else 0.0) + (0.25 if mentions else 0.0))
    return {
        "contextual_name": contextual_name,
        "display_name": contextual_name if generic_name else base_name,
        "domain_context": domain_context,
        "method_role": role,
        "context_terms": context_terms[:12],
        "generic_technology_name": generic_name,
        "domain_grounding_score": round(score, 3),
    }


def readable_surface_name(canonical_name: str, mentions: list[dict[str, Any]]) -> str:
    canonical_tokens = content_tokens(canonical_name)
    if not canonical_tokens:
        return canonical_name
    candidates: list[str] = []
    for mention in mentions[:12]:
        name = normalize_space(mention.get("name") or "")
        if not name:
            continue
        cleaned = repair_surface_name(name.strip(" .,:;"))
        if not cleaned:
            continue
        candidate_tokens = content_tokens(cleaned)
        if not canonical_tokens.issubset(candidate_tokens | abbreviation_tokens(cleaned)):
            continue
        if cleaned.lower() == canonical_name.lower():
            continue
        if len(cleaned) > 120:
            continue
        candidates.append(cleaned)
    if not candidates:
        return canonical_name
    candidates.sort(key=surface_name_score, reverse=True)
    return candidates[0]


def repair_surface_name(value: str) -> str:
    text = normalize_space(value)
    if text.count("(") > text.count(")"):
        text = f"{text})"
    if text.count("[") > text.count("]"):
        text = f"{text}]"
    return text


def abbreviation_tokens(text: str) -> set[str]:
    tokens = set()
    for chunk in str(text).replace(")", " ").replace("(", " ").split():
        cleaned = "".join(ch.lower() for ch in chunk if ch.isalnum())
        if 1 < len(cleaned) <= 8 and cleaned.isalpha():
            tokens.add(cleaned)
    return tokens


def surface_name_score(value: str) -> tuple[int, int, int, int]:
    text = str(value)
    has_upper = any(ch.isupper() for ch in text)
    has_paren = "(" in text or ")" in text
    has_hyphen = "-" in text or "/" in text
    return (int(has_upper), int(has_paren), int(has_hyphen), -abs(len(text) - 36))


def infer_method_role(entity_type: str, text: str) -> str:
    low = text.lower()
    if entity_type == "data_source":
        return "evidence_source"
    if entity_type == "infrastructure_tooling":
        return "tooling_or_platform"
    if entity_type == "evaluation_protocol":
        return "validation_or_benchmark"
    if entity_type == "governance_practice":
        return "governance_or_access_practice"
    if any(term in low for term in ["annotat", "coding", "classif", "detect", "measurement", "sentiment", "stance"]):
        return "measurement_or_annotation"
    if any(term in low for term in ["model", "simulation", "predict", "infer", "estimate"]):
        return "modeling_or_inference"
    if any(term in low for term in ["api", "dashboard", "software", "platform"]):
        return "tooling_or_platform"
    return "analytic_method"


def context_phrase_from_terms(context_terms: list[str], taxonomy_labels: list[str]) -> str:
    preferred = [
        ("social media text", {"social", "media", "text"}),
        ("social media", {"social", "tweet", "twitter", "platform", "online"}),
        ("political text", {"political", "text", "discourse", "ideology", "propaganda"}),
        ("hate speech or sexism detection", {"hate", "sexism"}),
        ("sentiment or emotion analysis", {"sentiment", "emotion"}),
        ("survey or population data", {"survey", "population"}),
        ("social network analysis", {"network", "community", "user"}),
        ("annotation and coding", {"annotation", "coding"}),
        ("public policy or governance analysis", {"policy", "governance", "public"}),
    ]
    term_set = set(context_terms)
    for phrase, required in preferred:
        if term_set & required:
            return phrase
    for label in taxonomy_labels:
        low = label.lower()
        if "online interaction" in low or "social media" in low:
            return "online interaction or social media"
        if "text-as-data" in low or "text analysis" in low:
            return "text-as-data social science"
        if "network analysis" in low:
            return "social network analysis"
        if "survey" in low or "population" in low:
            return "survey or population data"
    return " ".join(context_terms[:4])


def compact_edge(edge: dict[str, Any]) -> dict[str, Any]:
    evidence = edge.get("evidence") if isinstance(edge.get("evidence"), dict) else {}
    return {
        "edge_id": str(edge.get("edge_id") or ""),
        "source_entity": str(edge.get("source_entity") or ""),
        "target_entity": str(edge.get("target_entity") or ""),
        "edge_type": str(edge.get("edge_type") or ""),
        "confidence": edge.get("confidence"),
        "time_delta_days": edge.get("time_delta_days"),
        "source_document": str(edge.get("source_document") or ""),
        "target_document": str(edge.get("target_document") or ""),
        "quote": first_quote(evidence),
    }


def build_successor_trajectories(
    edges: list[dict[str, Any]],
    entities: dict[str, dict[str, Any]],
    *,
    entity_cards_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    entity_cards_by_id = entity_cards_by_id or {}
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    incoming_count = Counter()
    for edge in edges:
        outgoing[str(edge.get("source_entity") or "")].append(edge)
        incoming_count[str(edge.get("target_entity") or "")] += 1
    for rows in outgoing.values():
        rows.sort(key=lambda edge: (-safe_float(edge.get("confidence")), int(edge.get("time_delta_days") or 0), str(edge.get("target_entity") or "")))

    rows: list[dict[str, Any]] = []
    for edge in edges:
        source = str(edge.get("source_entity") or "")
        target = str(edge.get("target_entity") or "")
        edge_id = str(edge.get("edge_id") or "")
        if source and target and edge_id:
            rows.append(successor_trajectory_row([source, target], [edge_id], [edge]))
    starts = sorted({str(edge.get("source_entity") or "") for edge in edges if incoming_count[str(edge.get("source_entity") or "")] == 0})
    if not starts:
        starts = sorted(outgoing)
    for start in starts:
        extend_successor_path(
            rows,
            current=start,
            entity_path=[start],
            edge_path=[],
            chain_edges=[],
            outgoing=outgoing,
            max_depth=4,
        )
    if not rows:
        for edge in edges:
            source = str(edge.get("source_entity") or "")
            target = str(edge.get("target_entity") or "")
            rows.append(successor_trajectory_row([source, target], [str(edge.get("edge_id") or "")], [edge]))

    unique = unique_trajectory_rows(rows)
    edge_by_id = {str(edge.get("edge_id") or ""): edge for edge in edges}
    for index, row in enumerate(unique, start=1):
        row["trajectory_id"] = f"successor_trajectory__{index:06d}"
        row["trajectory_source"] = SUCCESSOR_EDGE_PATH
        row["entity_labels"] = [
            entity_display_name(entity_id, entities=entities, entity_cards_by_id=entity_cards_by_id)
            for entity_id in row.get("entity_path", [])
        ]
        row["canonical_entity_labels"] = [
            normalize_space((entities.get(entity_id) or {}).get("canonical_name") or entity_name_from_id(entity_id))
            for entity_id in row.get("entity_path", [])
        ]
        row["edge_types"] = [str((edge_by_id.get(edge_id) or {}).get("edge_type") or "") for edge_id in row.get("edge_path", [])]
    return unique


def entity_display_name(
    entity_id: str,
    *,
    entities: dict[str, dict[str, Any]],
    entity_cards_by_id: dict[str, dict[str, Any]],
) -> str:
    card = entity_cards_by_id.get(entity_id) or {}
    return normalize_space(
        card.get("display_name")
        or card.get("contextual_name")
        or card.get("canonical_name")
        or (entities.get(entity_id) or {}).get("canonical_name")
        or entity_name_from_id(entity_id)
    )


def extend_successor_path(
    rows: list[dict[str, Any]],
    *,
    current: str,
    entity_path: list[str],
    edge_path: list[str],
    chain_edges: list[dict[str, Any]],
    outgoing: dict[str, list[dict[str, Any]]],
    max_depth: int,
) -> None:
    if len(edge_path) >= max_depth:
        return
    next_edges = outgoing.get(current, [])
    if not next_edges:
        return
    for edge in next_edges[:4]:
        edge_id = str(edge.get("edge_id") or "")
        target = str(edge.get("target_entity") or "")
        if not edge_id or not target or target in entity_path:
            continue
        next_entity_path = [*entity_path, target]
        next_edge_path = [*edge_path, edge_id]
        next_chain_edges = [*chain_edges, edge]
        rows.append(successor_trajectory_row(next_entity_path, next_edge_path, next_chain_edges))
        extend_successor_path(
            rows,
            current=target,
            entity_path=next_entity_path,
            edge_path=next_edge_path,
            chain_edges=next_chain_edges,
            outgoing=outgoing,
            max_depth=max_depth,
        )


def successor_trajectory_row(entity_path: list[str], edge_path: list[str], chain_edges: list[dict[str, Any]]) -> dict[str, Any]:
    confidences = [safe_float(edge.get("confidence")) for edge in chain_edges]
    taxonomy_nodes = sorted({node_id for edge in chain_edges for node_id in as_str_list(edge.get("taxonomy_nodes"))})
    score = mean(confidences) if confidences else 0.0
    return {
        "trajectory_id": "",
        "entity_path": entity_path,
        "edge_path": edge_path,
        "taxonomy_nodes": taxonomy_nodes,
        "trajectory_score": round(score, 3),
        "path_length": len(edge_path),
        "mean_edge_confidence": round(score, 3),
        "temporal_coherence": 1.0,
        "quote_grounding": round(mean([1.0 if edge.get("substring_verified") else 0.75 for edge in chain_edges]), 3),
        "schema_coherence": 1.0,
        "branching_factor": 1,
    }


def unique_trajectory_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(row.get("edge_path") or [])
        existing = unique.get(key)
        if existing is None or trajectory_sort_key(row) < trajectory_sort_key(existing):
            unique[key] = row
    return sorted(unique.values(), key=trajectory_sort_key)


def trajectory_sort_key(row: dict[str, Any]) -> tuple[float, int, str]:
    return (-safe_float(row.get("trajectory_score")), -int(row.get("path_length") or 0), " ".join(row.get("entity_path") or []))


def evaluate_successor_trajectories(
    trajectories: list[dict[str, Any]],
    edge_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if not trajectories:
        return [{"metric": "successor_trajectory_count", "value": 0, "interpretation": "No strict successor trajectories were materialized."}]
    lengths = [int(row.get("path_length") or 0) for row in trajectories]
    scores = [safe_float(row.get("trajectory_score")) for row in trajectories]
    edge_ids = {edge_id for row in trajectories for edge_id in as_str_list(row.get("edge_path"))}
    relation_counts = Counter(str((edge_by_id.get(edge_id) or {}).get("edge_type") or "") for edge_id in edge_ids)
    return [
        {"metric": "successor_trajectory_count", "value": len(trajectories), "interpretation": "Number of trajectories inferred only from strict successor edges."},
        {"metric": "successor_edge_coverage", "value": len(edge_ids), "interpretation": "Strict successor edges covered by at least one successor trajectory."},
        {"metric": "mean_successor_trajectory_score", "value": round(mean(scores), 3), "interpretation": "Average score of strict successor trajectories."},
        {"metric": "mean_successor_path_length", "value": round(mean([float(value) for value in lengths]), 3), "interpretation": "Average number of successor edges per trajectory."},
        {"metric": "max_successor_path_length", "value": max(lengths), "interpretation": "Longest strict successor trajectory length."},
        {"metric": "successor_relation_types", "value": dict(relation_counts), "interpretation": "Relation-type distribution among strict successor trajectory edges."},
    ]


def build_entity_type_diagnostics(
    entity_cards: list[dict[str, Any]],
    successor_edges: list[dict[str, Any]],
    entity_schema: dict[str, Any],
) -> dict[str, Any]:
    type_counts = Counter(str(card.get("entity_type") or "unknown") for card in entity_cards)
    group_counts = Counter(str(card.get("schema_group") or schema_group_for_type(card.get("entity_type"))) for card in entity_cards)
    edge_type_counts = Counter()
    edge_group_counts = Counter()
    for edge in successor_edges:
        source_id = str(edge.get("source_entity") or "")
        target_id = str(edge.get("target_entity") or "")
        source_card = next((card for card in entity_cards if card.get("entity_id") == source_id), {})
        target_card = next((card for card in entity_cards if card.get("entity_id") == target_id), {})
        source_type = str(edge.get("source_entity_type") or source_card.get("entity_type") or source_id.split("__", 1)[0])
        target_type = str(edge.get("target_entity_type") or target_card.get("entity_type") or target_id.split("__", 1)[0])
        source_group = str(edge.get("source_schema_group") or edge.get("schema_group") or source_card.get("schema_group") or schema_group_for_type(source_type))
        target_group = str(edge.get("target_schema_group") or edge.get("schema_group") or target_card.get("schema_group") or schema_group_for_type(target_type))
        if source_type == target_type and source_type:
            edge_type_counts[source_type] += 1
        if source_group == target_group and source_group:
            edge_group_counts[source_group] += 1
    total = sum(type_counts.values()) or 1
    type_rows = []
    for entity_type, count in sorted(type_counts.items(), key=lambda item: (-item[1], item[0])):
        card_subset = [card for card in entity_cards if card.get("entity_type") == entity_type]
        generic_rate = mean([1.0 if card.get("generic_technology_name") else 0.0 for card in card_subset])
        grounding = mean([safe_float(card.get("domain_grounding_score")) for card in card_subset])
        type_rows.append(
            {
                "entity_type": entity_type,
                "count": count,
                "share": round(count / total, 4),
                "successor_edge_count": int(edge_type_counts[entity_type]),
                "generic_technology_rate": round(generic_rate, 3),
                "mean_domain_grounding_score": round(grounding, 3),
                "definition": normalize_space((entity_schema.get(entity_type) or {}).get("definition") or "") if isinstance(entity_schema, dict) else "",
            }
        )
    group_rows = []
    for group, count in sorted(group_counts.items(), key=lambda item: (-item[1], item[0])):
        card_subset = [
            card
            for card in entity_cards
            if str(card.get("schema_group") or schema_group_for_type(card.get("entity_type"))) == group
        ]
        group_rows.append(
            {
                "schema_group": group,
                "label": schema_group_label(group),
                "definition": schema_group_definition(group),
                "member_types": list((SCHEMA_GROUPS.get(group) or {}).get("member_types") or []),
                "count": count,
                "share": round(count / total, 4),
                "successor_edge_count": int(edge_group_counts[group]),
                "generic_technology_rate": round(mean([1.0 if card.get("generic_technology_name") else 0.0 for card in card_subset]), 3),
                "mean_domain_grounding_score": round(mean([safe_float(card.get("domain_grounding_score")) for card in card_subset]), 3),
            }
        )
    merge_suggestions = []
    for group_name, members in TYPE_MERGE_GROUPS.items():
        group_count = sum(type_counts[member] for member in members)
        group_edges = sum(edge_type_counts[member] for member in members)
        reasons = []
        for member in sorted(members):
            share = type_counts[member] / total
            if share < 0.04:
                reasons.append(f"{member} has low share ({share:.1%})")
            if edge_type_counts[member] < 5:
                reasons.append(f"{member} has sparse successor edges ({edge_type_counts[member]})")
        merge_suggestions.append(
            {
                "suggested_group": group_name,
                "member_types": sorted(members),
                "combined_entity_count": group_count,
                "combined_successor_edges": group_edges,
                "rationale": reasons or ["keep as grouping option for schema simplification"],
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entity_count": len(entity_cards),
        "successor_edge_count": len(successor_edges),
        "type_distribution": type_rows,
        "schema_group_distribution": group_rows,
        "merge_suggestions": merge_suggestions,
        "recommendation": "Treat entity types as an adaptive schema axis. Keep sparse types available for audit, but consider merged display/schema groups when a type has low share or few successor edges.",
    }


def first_quote(evidence: dict[str, Any]) -> str:
    for key in [
        "mechanism",
        "successor_rationale",
        "methodological_problem",
        "validation_evidence",
        "implementation_context",
        "tradeoff",
    ]:
        value = evidence.get(key)
        if isinstance(value, dict):
            quote = normalize_space(value.get("quote") or "")
            if quote:
                return quote[:500]
        elif isinstance(value, str):
            text = normalize_space(value)
            if text:
                return text[:500]
    return ""


def update_manifest(run_root: Path, summary: dict[str, Any]) -> None:
    manifest_path = run_root / "manifest.json"
    manifest = read_json(manifest_path, default={})
    if not isinstance(manifest, dict):
        return
    counts = manifest.setdefault("counts", {})
    if isinstance(counts, dict):
        counts["entity_cards"] = summary["entity_cards"]
        counts["successor_trajectories"] = summary["successor_trajectories"]
    layout = manifest.setdefault("artifact_layout", {})
    if isinstance(layout, dict):
        layout["entity_cards"] = ENTITY_CARD_PATH
        layout["entity_cards_summary"] = "graph/entity_cards.summary.json"
        layout["entity_type_diagnostics"] = ENTITY_TYPE_DIAGNOSTIC_PATH
        layout["entity_schema_groups"] = ENTITY_SCHEMA_GROUP_PATH
        layout["successor_trajectories"] = SUCCESSOR_TRAJECTORY_PATH
        layout["successor_trajectory_eval"] = SUCCESSOR_TRAJECTORY_EVAL_PATH
    write_json(manifest_path, manifest)


def as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def taxonomy_label(taxonomy: dict[str, dict[str, Any]], node_id: str) -> str:
    return normalize_space((taxonomy.get(node_id) or {}).get("label") or node_id)


def entity_name_from_id(entity_id: str) -> str:
    raw = entity_id.split("__", 1)[-1]
    return normalize_space(raw.replace("_", " "))


def year_from_value(value: Any) -> int | None:
    parsed = parse_date(value)
    if parsed:
        return parsed.year
    text = str(value or "")
    for token in text.replace("_", "-").split("-"):
        if token.isdigit() and len(token) == 4:
            year = int(token)
            if 1500 <= year <= 2100:
                return year
    return None


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def content_tokens(text: str) -> set[str]:
    return {
        token
        for token in "".join(ch.lower() if ch.isalnum() else " " for ch in str(text)).split()
        if len(token) > 2
    }


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


if __name__ == "__main__":
    raise SystemExit(main())
