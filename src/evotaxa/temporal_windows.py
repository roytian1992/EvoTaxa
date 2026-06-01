from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from typing import Any

from evotaxa.config import TemporalWindowConfig


def build_temporal_windows(
    *,
    docs: list[Any],
    nodes: list[Any],
    entities: list[Any],
    mentions: list[Any],
    edges: list[Any],
    trajectory_rows: list[dict[str, Any]],
    config: TemporalWindowConfig,
) -> dict[str, Any]:
    if not config.enabled:
        return {
            "windows": [],
            "assignments": [],
            "summary": _summary(enabled=False, config=config, events=[], windows=[], assignments=[]),
        }

    doc_map = {str(getattr(doc, "doc_id", "")): doc for doc in docs}
    entity_map = {str(getattr(entity, "entity_id", "")): entity for entity in entities}
    node_labels = {str(getattr(node, "node_id", "")): str(getattr(node, "canonical_label", "") or "") for node in nodes}
    events = _event_rows(
        docs=docs,
        doc_map=doc_map,
        entity_map=entity_map,
        mentions=mentions,
        edges=edges,
        scopes=set(config.scope_types),
    )
    windows, assignments = _build_windows(events, config, node_labels=node_labels)
    summary = _summary(enabled=True, config=config, events=events, windows=windows, assignments=assignments)
    summary["trajectory_window_links"] = _trajectory_window_links(trajectory_rows, assignments)
    return {
        "windows": windows,
        "assignments": assignments,
        "summary": summary,
    }


def _event_rows(
    *,
    docs: list[Any],
    doc_map: dict[str, Any],
    entity_map: dict[str, Any],
    mentions: list[Any],
    edges: list[Any],
    scopes: set[str],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if "global" in scopes:
        for doc in docs:
            doc_id = str(getattr(doc, "doc_id", "") or "")
            event = _doc_event(doc, scope_type="global", scope_id="global", scope_label="Global corpus")
            if event:
                events.append(event)
    if "taxonomy_node" in scopes:
        for mention in mentions:
            doc = doc_map.get(str(getattr(mention, "doc_id", "") or ""))
            if not doc:
                continue
            for node_id in getattr(mention, "taxonomy_nodes", []) or []:
                event = _mention_event(mention, doc, scope_type="taxonomy_node", scope_id=str(node_id), scope_label=str(node_id))
                if event:
                    events.append(event)
    if "entity_type" in scopes:
        for mention in mentions:
            entity = entity_map.get(str(getattr(mention, "entity_id", "") or ""))
            doc = doc_map.get(str(getattr(mention, "doc_id", "") or ""))
            if not entity or not doc:
                continue
            entity_type = str(getattr(entity, "entity_type", "") or "entity")
            event = _mention_event(mention, doc, scope_type="entity_type", scope_id=entity_type, scope_label=entity_type)
            if event:
                events.append(event)
    if "relation_type" in scopes:
        for edge in edges:
            target_doc = doc_map.get(str(getattr(edge, "target_document", "") or ""))
            source_doc = doc_map.get(str(getattr(edge, "source_document", "") or ""))
            doc = target_doc or source_doc
            edge_type = str(getattr(edge, "edge_type", "") or "background")
            event = _edge_event(edge, doc, scope_type="relation_type", scope_id=edge_type, scope_label=edge_type)
            if event:
                events.append(event)
    return sorted(events, key=lambda row: (row["event_date"], row["event_id"], row["scope_type"], row["scope_id"]))


def _doc_event(doc: Any, *, scope_type: str, scope_id: str, scope_label: str) -> dict[str, Any] | None:
    event_date = getattr(doc, "published_at", None)
    if not isinstance(event_date, date):
        return None
    doc_id = str(getattr(doc, "doc_id", "") or "")
    return {
        "event_id": f"document__{doc_id}",
        "event_type": "document",
        "event_date": event_date,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "scope_label": scope_label,
        "doc_id": doc_id,
        "mention_id": "",
        "edge_id": "",
        "entity_id": "",
        "taxonomy_nodes": [],
    }


def _mention_event(mention: Any, doc: Any, *, scope_type: str, scope_id: str, scope_label: str) -> dict[str, Any] | None:
    event_date = getattr(doc, "published_at", None)
    if not isinstance(event_date, date):
        return None
    doc_id = str(getattr(mention, "doc_id", "") or "")
    entity_id = str(getattr(mention, "entity_id", "") or "")
    taxonomy_nodes = [str(node_id) for node_id in getattr(mention, "taxonomy_nodes", []) or [] if str(node_id)]
    return {
        "event_id": f"mention__{doc_id}__{entity_id}__{scope_type}__{scope_id}",
        "event_type": "mention",
        "event_date": event_date,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "scope_label": scope_label,
        "doc_id": doc_id,
        "mention_id": f"{doc_id}::{entity_id}",
        "edge_id": "",
        "entity_id": entity_id,
        "taxonomy_nodes": taxonomy_nodes,
    }


def _edge_event(edge: Any, doc: Any, *, scope_type: str, scope_id: str, scope_label: str) -> dict[str, Any] | None:
    event_date = getattr(doc, "published_at", None) if doc else None
    if not isinstance(event_date, date):
        return None
    edge_id = str(getattr(edge, "edge_id", "") or "")
    return {
        "event_id": f"edge__{edge_id}",
        "event_type": "edge",
        "event_date": event_date,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "scope_label": scope_label,
        "doc_id": str(getattr(edge, "target_document", "") or getattr(edge, "source_document", "") or ""),
        "mention_id": "",
        "edge_id": edge_id,
        "entity_id": str(getattr(edge, "target_entity", "") or ""),
        "taxonomy_nodes": [str(node_id) for node_id in getattr(edge, "taxonomy_nodes", []) or [] if str(node_id)],
    }


def _build_windows(
    events: list[dict[str, Any]],
    config: TemporalWindowConfig,
    *,
    node_labels: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_scope: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_scope[(event["scope_type"], event["scope_id"])].append(event)

    windows: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []
    for (scope_type, scope_id), scope_events in sorted(by_scope.items()):
        scope_windows, scope_assignments = _windows_for_scope(
            scope_type=scope_type,
            scope_id=scope_id,
            scope_label=node_labels.get(scope_id) or scope_events[0].get("scope_label") or scope_id,
            events=scope_events,
            config=config,
        )
        windows.extend(scope_windows)
        assignments.extend(scope_assignments)
    return windows, assignments


def _windows_for_scope(
    *,
    scope_type: str,
    scope_id: str,
    scope_label: str,
    events: list[dict[str, Any]],
    config: TemporalWindowConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    windows: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    for event in events:
        current.append(event)
        if _should_close(current, config, is_last=False):
            window, rows = _close_window(current, scope_type, scope_id, scope_label, len(windows) + 1)
            windows.append(window)
            assignments.extend(rows)
            current = []
            if config.max_windows_per_scope > 0 and len(windows) >= config.max_windows_per_scope:
                break
    if current and (config.max_windows_per_scope <= 0 or len(windows) < config.max_windows_per_scope):
        window, rows = _close_window(current, scope_type, scope_id, scope_label, len(windows) + 1)
        windows.append(window)
        assignments.extend(rows)
    return windows, assignments


def _should_close(events: list[dict[str, Any]], config: TemporalWindowConfig, *, is_last: bool) -> bool:
    if not events:
        return False
    counts = Counter(row["event_type"] for row in events)
    duration = _duration_days(events)
    threshold_hit = (
        counts.get("document", 0) >= config.min_documents_per_window
        or counts.get("mention", 0) >= config.min_mentions_per_window
        or counts.get("edge", 0) >= config.min_edges_per_window
    )
    if is_last:
        return True
    if duration >= config.max_duration_days:
        return True
    return threshold_hit and duration >= config.min_duration_days


def _close_window(
    events: list[dict[str, Any]],
    scope_type: str,
    scope_id: str,
    scope_label: str,
    index: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    start_date = events[0]["event_date"]
    end_date = events[-1]["event_date"]
    counts = Counter(row["event_type"] for row in events)
    doc_ids = sorted({row["doc_id"] for row in events if row.get("doc_id")})
    entity_ids = sorted({row["entity_id"] for row in events if row.get("entity_id")})
    edge_ids = sorted({row["edge_id"] for row in events if row.get("edge_id")})
    node_ids = sorted({node_id for row in events for node_id in row.get("taxonomy_nodes", []) if str(node_id)})
    trigger = _trigger(counts)
    window_id = f"{scope_type}__{_safe_id(scope_id)}__w{index:04d}"
    window = {
        "window_id": window_id,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "scope_label": scope_label,
        "window_index": index,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "duration_days": (end_date - start_date).days,
        "trigger": trigger,
        "document_count": len(doc_ids),
        "mention_count": counts.get("mention", 0),
        "edge_count": counts.get("edge", 0),
        "event_count": len(events),
        "representative_documents": doc_ids[:10],
        "representative_entities": entity_ids[:10],
        "representative_edges": edge_ids[:10],
        "taxonomy_nodes": node_ids[:10],
    }
    rows = [
        {
            "window_id": window_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "event_date": row["event_date"].isoformat(),
            "doc_id": row.get("doc_id", ""),
            "entity_id": row.get("entity_id", ""),
            "edge_id": row.get("edge_id", ""),
        }
        for row in events
    ]
    return window, rows


def _trigger(counts: Counter[str]) -> str:
    if counts.get("edge", 0):
        return "edge_count"
    if counts.get("mention", 0):
        return "mention_count"
    return "document_count"


def _duration_days(events: list[dict[str, Any]]) -> int:
    if len(events) < 2:
        return 0
    return (events[-1]["event_date"] - events[0]["event_date"]).days


def _trajectory_window_links(trajectory_rows: list[dict[str, Any]], assignments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edge_to_windows: dict[str, set[str]] = defaultdict(set)
    for row in assignments:
        edge_id = str(row.get("edge_id") or "")
        if edge_id:
            edge_to_windows[edge_id].add(str(row.get("window_id") or ""))
    links = []
    for trajectory in trajectory_rows:
        edge_path = [str(edge_id) for edge_id in trajectory.get("edge_path", []) if str(edge_id)]
        window_ids = sorted({window_id for edge_id in edge_path for window_id in edge_to_windows.get(edge_id, set()) if window_id})
        if window_ids:
            links.append(
                {
                    "trajectory_id": trajectory.get("trajectory_id") or trajectory.get("chain_id") or "",
                    "window_ids": window_ids,
                    "edge_count": len(edge_path),
                    "linked_edge_count": sum(1 for edge_id in edge_path if edge_to_windows.get(edge_id)),
                }
            )
    return links


def _summary(
    *,
    enabled: bool,
    config: TemporalWindowConfig,
    events: list[dict[str, Any]],
    windows: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
) -> dict[str, Any]:
    by_scope_type = Counter(row.get("scope_type", "unknown") for row in windows)
    events_by_type = Counter(row.get("event_type", "unknown") for row in events)
    durations = [int(row.get("duration_days") or 0) for row in windows]
    return {
        "enabled": enabled,
        "scope_types": list(config.scope_types),
        "event_count": len(events),
        "events_by_type": dict(sorted(events_by_type.items())),
        "window_count": len(windows),
        "windows_by_scope_type": dict(sorted(by_scope_type.items())),
        "assignment_count": len(assignments),
        "min_documents_per_window": config.min_documents_per_window,
        "min_mentions_per_window": config.min_mentions_per_window,
        "min_edges_per_window": config.min_edges_per_window,
        "min_duration_days": config.min_duration_days,
        "max_duration_days": config.max_duration_days,
        "mean_duration_days": round(sum(durations) / len(durations), 2) if durations else 0.0,
    }


def _safe_id(value: str) -> str:
    safe = "".join(char.lower() if char.isalnum() else "_" for char in str(value))
    safe = "_".join(part for part in safe.split("_") if part)
    return safe[:80] or "unknown"
