#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from build_evolution_visualization import build_edge_payload, build_payload, read_json, read_jsonl, render_html  # noqa: E402
from evotaxa.io import normalize_space  # noqa: E402
from schema_groups import schema_group_for_type, schema_group_label  # noqa: E402


class DashboardStore:
    def __init__(self, run_root: Path, *, max_nodes: int, max_edges: int, max_trajectories: int, max_windows: int) -> None:
        self.run_root = run_root.expanduser().resolve()
        self.payload = build_payload(
            run_root=self.run_root,
            max_nodes=max_nodes,
            max_edges=max_edges,
            max_trajectories=max_trajectories,
            max_windows=max_windows,
            support_doc_limit=12,
        )
        self.html = render_html(api_mode=True, data_api="/api/data")
        self.documents = read_jsonl(self.run_root / "corpus" / "documents.normalized.jsonl")
        self.entities_raw = {str(row.get("entity_id") or ""): row for row in read_jsonl(self.run_root / "graph" / "method_registry.jsonl") if row.get("entity_id")}
        self.entity_cards_raw = {str(row.get("entity_id") or ""): row for row in read_jsonl(self.run_root / "graph" / "entity_cards.jsonl") if row.get("entity_id")}
        self.mentions_by_entity = self._load_mentions_by_entity()
        edge_path = self.run_root / "graph" / "successor_edges.accepted.jsonl"
        if not edge_path.exists():
            edge_path = self.run_root / "graph" / "method_edges.trusted.jsonl"
        self.edges_raw = {str(row.get("edge_id") or ""): row for row in read_jsonl(edge_path) if row.get("edge_id")}
        self.edge_source = str(edge_path.relative_to(self.run_root)) if edge_path.exists() else ""
        trajectory_path = self.run_root / "trajectory" / "successor_trajectories.jsonl"
        if not trajectory_path.exists():
            trajectory_path = self.run_root / "trajectory" / "evolution_trajectories.jsonl"
        self.trajectories_raw = {
            str(row.get("trajectory_id") or ""): row
            for row in read_jsonl(trajectory_path)
            if row.get("trajectory_id")
        }
        self.trajectory_source = str(trajectory_path.relative_to(self.run_root)) if trajectory_path.exists() else ""
        self.taxonomy = self.payload.get("taxonomy", {})
        self.docs_by_id = {str(row.get("doc_id") or ""): row for row in self.documents if row.get("doc_id")}
        self.entity_schema = read_json(self.run_root / "schema" / "entity_schema.final.json", default={})
        self.relation_schema = read_json(self.run_root / "schema" / "relation_schema.final.json", default={})
        self.payload_entities = {row["id"]: row for row in self.payload.get("entities", [])}
        self.payload_edges = {row["id"]: row for row in self.payload.get("edges", [])}
        self.payload_trajectories = {row["id"]: row for row in self.payload.get("trajectories", [])}

    def entity_index(self, *, query: str = "", entity_type: str = "all", limit: int = 50, offset: int = 0) -> dict[str, Any]:
        query_lower = query.lower().strip()
        rows = []
        for entity_id, raw in self.entities_raw.items():
            card = self.payload_entities.get(entity_id) or self._fallback_entity_card(entity_id, raw)
            if entity_type != "all" and card.get("type") != entity_type and card.get("entity_type") != entity_type:
                continue
            text = " ".join(
                [
                    entity_id,
                    str(card.get("name") or ""),
                    str(card.get("type") or ""),
                    str(card.get("entity_type") or ""),
                    " ".join(card.get("aliases") or []),
                    " ".join(card.get("taxonomy_labels") or []),
                    " ".join(card.get("support_documents") or []),
                ]
            ).lower()
            if query_lower and query_lower not in text:
                continue
            rows.append(card)
        rows.sort(key=lambda row: (-int(row.get("degree") or 0), -int(row.get("support_count") or 0), str(row.get("name") or "")))
        return {
            "total": len(rows),
            "limit": limit,
            "offset": offset,
            "items": rows[offset : offset + limit],
        }

    def entity_detail(self, entity_id: str) -> dict[str, Any] | None:
        raw = self.entities_raw.get(entity_id)
        materialized = self.entity_cards_raw.get(entity_id)
        card = self.payload_entities.get(entity_id) or (self._payload_from_materialized_card(materialized) if materialized else None) or (self._fallback_entity_card(entity_id, raw) if raw else None)
        if not card:
            return None
        incident_edges = self._incident_edges(entity_id)
        incident_edges.sort(key=lambda row: float(row.get("confidence") or 0), reverse=True)
        trajectories = []
        for trajectory_id, trajectory in self.trajectories_raw.items():
            if entity_id in (trajectory.get("entity_path") or []):
                trajectories.append(self.payload_trajectories.get(trajectory_id) or trajectory)
        trajectories.sort(key=lambda row: float(row.get("score") or row.get("trajectory_score") or 0), reverse=True)
        support_docs = self._support_documents(entity_id, card)
        mentions = (materialized or {}).get("representative_mentions") if isinstance(materialized, dict) else None
        if not isinstance(mentions, list):
            mentions = self.mentions_by_entity.get(entity_id, [])
        return {
            "entity": card,
            "raw_entity": (materialized or {}).get("raw_entity") if isinstance(materialized, dict) and materialized.get("raw_entity") else raw,
            "materialized_card": materialized,
            "support_documents": support_docs,
            "mentions": mentions[:24],
            "incident_edges": incident_edges,
            "trajectories": trajectories,
            "card": {
                "display_name": card.get("name") or entity_id,
                "entity_id": entity_id,
                "entity_type": card.get("type") or "",
                "raw_entity_type": card.get("entity_type") or "",
                "first_seen": card.get("first_seen") or "",
                "support_count": card.get("support_count") or 0,
                "taxonomy_labels": card.get("taxonomy_labels") or [],
                "aliases": card.get("aliases") or [],
                "representative_mentions": mentions[:8],
                "support_documents": support_docs,
                "incoming_edges": [edge for edge in incident_edges if edge.get("target") == entity_id or edge.get("target_entity") == entity_id],
                "outgoing_edges": [edge for edge in incident_edges if edge.get("source") == entity_id or edge.get("source_entity") == entity_id],
            },
        }

    def _load_mentions_by_entity(self) -> dict[str, list[dict[str, Any]]]:
        rows: dict[str, list[dict[str, Any]]] = {}
        for path_name in ["graph/llm_entity_mentions.jsonl", "graph/paper_method_mentions.jsonl"]:
            path = self.run_root / path_name
            for row in read_jsonl(path):
                entity_id = str(row.get("entity_id") or "")
                if not entity_id:
                    continue
                quote = normalize_space(row.get("quote") or row.get("evidence") or "")
                if not quote:
                    continue
                rows.setdefault(entity_id, []).append(
                    {
                        "doc_id": str(row.get("doc_id") or ""),
                        "quote": quote[:800],
                        "name": normalize_space(row.get("name") or row.get("canonical_name") or ""),
                        "confidence": row.get("confidence"),
                        "status": str(row.get("status") or ""),
                        "reason": str(row.get("reason") or ""),
                        "source": path_name,
                    }
                )
        for entity_id, mentions in rows.items():
            seen = set()
            unique = []
            for mention in sorted(mentions, key=lambda item: (-len(str(item.get("quote") or "")), str(item.get("doc_id") or ""))):
                key = (mention.get("doc_id"), mention.get("quote"))
                if key in seen:
                    continue
                seen.add(key)
                unique.append(mention)
            rows[entity_id] = unique
        return rows

    def _incident_edges(self, entity_id: str) -> list[dict[str, Any]]:
        incident = []
        for edge_id, edge in self.payload_edges.items():
            if edge.get("source_entity") == entity_id or edge.get("target_entity") == entity_id:
                incident.append(edge)
            elif edge.get("source") == entity_id or edge.get("target") == entity_id:
                incident.append(edge)
        existing_ids = {str(edge.get("id") or edge.get("edge_id") or "") for edge in incident}
        for edge_id, edge in self.edges_raw.items():
            if edge_id in existing_ids:
                continue
            if edge.get("source_entity") != entity_id and edge.get("target_entity") != entity_id:
                continue
            incident.append(build_edge_payload(edge, docs=self._doc_payload_map(), taxonomy=self.taxonomy, relation_schema=self.relation_schema))
        return incident

    def _doc_payload_map(self) -> dict[str, dict[str, Any]]:
        docs = {}
        for doc_id, row in self.docs_by_id.items():
            published_at = str(row.get("published_at") or "")
            year = None
            if len(published_at) >= 4 and published_at[:4].isdigit():
                year = int(published_at[:4])
            docs[doc_id] = {
                "doc_id": doc_id,
                "title": normalize_space(row.get("title") or doc_id),
                "published_at": published_at,
                "year": year,
                "role": str(row.get("role") or ""),
            }
        return docs

    def _fallback_entity_card(self, entity_id: str, raw: dict[str, Any]) -> dict[str, Any]:
        taxonomy_nodes = [str(item) for item in raw.get("taxonomy_nodes") or []]
        support_docs = [str(item) for item in raw.get("support_documents") or []]
        degree = sum(
            1
            for edge in self.edges_raw.values()
            if edge.get("source_entity") == entity_id or edge.get("target_entity") == entity_id
        )
        raw_type = str(raw.get("entity_type") or "unknown")
        schema_group = str(raw.get("schema_group") or schema_group_for_type(raw_type))
        return {
            "id": entity_id,
            "name": normalize_space(raw.get("canonical_name") or entity_id),
            "aliases": [str(item) for item in raw.get("aliases") or []],
            "type": schema_group,
            "type_label": schema_group_label(schema_group),
            "definition": "",
            "entity_type": raw_type,
            "entity_type_label": normalize_space((self.entity_schema.get(raw_type) or {}).get("label") or raw_type) if isinstance(self.entity_schema, dict) else raw_type,
            "entity_type_definition": normalize_space((self.entity_schema.get(raw_type) or {}).get("definition") or "") if isinstance(self.entity_schema, dict) else "",
            "schema_group": schema_group,
            "schema_group_label": schema_group_label(schema_group),
            "first_seen": str(raw.get("first_seen_date") or ""),
            "support_count": len(support_docs),
            "support_documents": support_docs[:12],
            "taxonomy_nodes": taxonomy_nodes,
            "taxonomy_labels": [str((self.taxonomy.get(node_id) or {}).get("label") or node_id) for node_id in taxonomy_nodes],
            "degree": degree,
        }

    def _payload_from_materialized_card(self, raw: dict[str, Any] | None) -> dict[str, Any] | None:
        if not raw:
            return None
        support_docs = [
            str((doc or {}).get("doc_id") or "")
            for doc in raw.get("support_documents") or []
            if isinstance(doc, dict) and (doc or {}).get("doc_id")
        ]
        raw_type = str(raw.get("entity_type") or "unknown")
        schema_group = str(raw.get("schema_group") or schema_group_for_type(raw_type))
        return {
            "id": str(raw.get("entity_id") or ""),
            "name": normalize_space(raw.get("display_name") or raw.get("contextual_name") or raw.get("canonical_name") or raw.get("entity_id") or ""),
            "canonical_name": normalize_space(raw.get("canonical_name") or raw.get("entity_id") or ""),
            "contextual_name": normalize_space(raw.get("contextual_name") or ""),
            "domain_context": normalize_space(raw.get("domain_context") or ""),
            "method_role": normalize_space(raw.get("method_role") or ""),
            "domain_grounding_score": raw.get("domain_grounding_score"),
            "generic_technology_name": bool(raw.get("generic_technology_name")),
            "aliases": [str(item) for item in raw.get("aliases") or []],
            "type": schema_group,
            "type_label": normalize_space(raw.get("schema_group_label") or schema_group_label(schema_group)),
            "definition": normalize_space(raw.get("schema_group_definition") or ""),
            "entity_type": raw_type,
            "entity_type_label": normalize_space(raw.get("entity_type_label") or raw_type),
            "entity_type_definition": normalize_space(raw.get("entity_type_definition") or ""),
            "schema_group": schema_group,
            "schema_group_label": normalize_space(raw.get("schema_group_label") or schema_group_label(schema_group)),
            "first_seen": str(raw.get("first_seen_date") or ""),
            "support_count": int(raw.get("support_document_count") or len(support_docs)),
            "support_documents": support_docs[:12],
            "taxonomy_nodes": [str(item) for item in raw.get("taxonomy_nodes") or []],
            "taxonomy_labels": [str(item) for item in raw.get("taxonomy_labels") or []],
            "degree": int(raw.get("successor_degree") or 0),
        }

    def _support_documents(self, entity_id: str, card: dict[str, Any]) -> list[dict[str, Any]]:
        raw = self.entity_cards_raw.get(entity_id)
        docs = raw.get("support_documents") if isinstance(raw, dict) else None
        if isinstance(docs, list) and docs and isinstance(docs[0], dict):
            return docs[:24]
        return [self._doc_card(doc_id) for doc_id in card.get("support_documents") or []]

    def _doc_card(self, doc_id: str) -> dict[str, Any]:
        row = self.docs_by_id.get(doc_id) or {}
        return {
            "doc_id": doc_id,
            "title": normalize_space(row.get("title") or doc_id),
            "published_at": str(row.get("published_at") or ""),
            "role": str(row.get("role") or ""),
            "source_type": str(row.get("source_type") or ""),
            "text": normalize_space(row.get("text") or "")[:1200],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the EvoTaxa evolution dashboard with lightweight APIs.")
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--max-nodes", type=int, default=1200)
    parser.add_argument("--max-edges", type=int, default=1200)
    parser.add_argument("--max-trajectories", type=int, default=800)
    parser.add_argument("--max-windows", type=int, default=400)
    args = parser.parse_args()

    store = DashboardStore(
        args.run_root,
        max_nodes=args.max_nodes,
        max_edges=args.max_edges,
        max_trajectories=args.max_trajectories,
        max_windows=args.max_windows,
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            try:
                if parsed.path in {"/", "/dashboard"}:
                    return self.send_html(store.html)
                if parsed.path == "/api/data":
                    return self.send_json(store.payload)
                if parsed.path == "/api/runs":
                    return self.send_json({"run_root": str(store.run_root), "summary": store.payload.get("summary", {})})
                if parsed.path == "/api/entities":
                    return self.send_json(
                        store.entity_index(
                            query=first_query(query, "q"),
                            entity_type=first_query(query, "type") or "all",
                            limit=as_int(first_query(query, "limit"), 50),
                            offset=as_int(first_query(query, "offset"), 0),
                        )
                    )
                if parsed.path.startswith("/api/entities/"):
                    entity_id = parsed.path.removeprefix("/api/entities/")
                    detail = store.entity_detail(entity_id)
                    if detail is None:
                        return self.send_json({"error": "entity_not_found", "entity_id": entity_id}, status=HTTPStatus.NOT_FOUND)
                    return self.send_json(detail)
                return self.send_json({"error": "not_found", "path": parsed.path}, status=HTTPStatus.NOT_FOUND)
            except Exception as exc:  # pragma: no cover - diagnostic server path
                return self.send_json({"error": "server_error", "message": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write("[dashboard] " + fmt % args + "\n")

        def send_html(self, text: str, *, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, value: Any, *, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Serving EvoTaxa dashboard at http://{args.host}:{args.port}/")
    print(f"Run root: {store.run_root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()
    return 0


def first_query(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key) or []
    return values[0] if values else ""


def as_int(value: str, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    raise SystemExit(main())
