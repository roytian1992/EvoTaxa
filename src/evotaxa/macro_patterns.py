from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from evotaxa.config import MacroPatternConfig
from evotaxa.models import EvolutionEdge, TaxonomyNode


PATTERN_SPECS: dict[str, dict[str, str]] = {
    "differentiation": {
        "label": "Differentiation",
        "definition": "A broad category splits into finer subnodes or specialized trajectories.",
    },
    "convergence": {
        "label": "Convergence",
        "definition": "Previously separate nodes, entity lines, or relation families increasingly connect around shared mechanisms.",
    },
    "hybridization": {
        "label": "Hybridization",
        "definition": "A node or trajectory combines multiple domains, methods, mechanisms, or relation types.",
    },
    "recontextualization": {
        "label": "Recontextualization",
        "definition": "A method, frame, or mechanism moves into a new domain, actor setting, platform, or evidence context.",
    },
    "cyclical_return": {
        "label": "Cyclical Return",
        "definition": "Earlier ideas reappear after a gap through repeated nodes, labels, or trajectories.",
    },
    "institutionalization": {
        "label": "Institutionalization",
        "definition": "An initially local pattern becomes stabilized through governance, standards, audits, benchmarks, or schema support.",
    },
    "substitution": {
        "label": "Substitution",
        "definition": "A newer entity, node, or trajectory replaces an older one.",
    },
    "fragmentation": {
        "label": "Fragmentation",
        "definition": "The field disperses into weakly connected subareas with many branches and rejected or low-quality relations.",
    },
    "stabilization": {
        "label": "Stabilization",
        "definition": "States, relations, and trajectories remain coherent with limited revision pressure.",
    },
}


def synthesize_macro_patterns(
    *,
    docs: list[Any],
    nodes: list[TaxonomyNode],
    taxonomy_events: list[dict[str, Any]],
    state_snapshot: dict[str, Any],
    state_transitions: list[dict[str, Any]],
    trajectory_rows: list[dict[str, Any]],
    edges: list[EvolutionEdge],
    edge_score_rows: list[dict[str, Any]],
    schema_revisions: list[dict[str, Any]],
    relation_rejections: list[dict[str, Any]],
    config: MacroPatternConfig,
    llm_summaries: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Estimate optional macro-level evolution patterns from existing EvoTaxa artifacts."""
    feature_rows = _feature_rows(
        docs=docs,
        nodes=nodes,
        taxonomy_events=taxonomy_events,
        state_snapshot=state_snapshot,
        state_transitions=state_transitions,
        trajectory_rows=trajectory_rows,
        edges=edges,
        edge_score_rows=edge_score_rows,
        schema_revisions=schema_revisions,
        relation_rejections=relation_rejections,
        config=config,
    )
    raw_profiles = [
        _pattern_profile(
            pattern_id=pattern_id,
            features=feature_rows,
            config=config,
            llm_summaries=llm_summaries or {},
        )
        for pattern_id in PATTERN_SPECS
    ]
    profiles = [
        profile
        for profile in raw_profiles
        if float(profile.get("pattern_score") or 0.0) >= config.min_pattern_score
    ]
    profiles.sort(key=lambda row: (-float(row.get("pattern_score") or 0.0), row.get("pattern_id", "")))
    if config.max_patterns > 0:
        profiles = profiles[: config.max_patterns]

    profile_ids = {str(row.get("pattern_id") or "") for row in profiles}
    evidence_records = [
        row
        for row in _evidence_records(feature_rows)
        if any(pattern_id in profile_ids for pattern_id in row.get("pattern_ids", []))
    ]
    timeline = _timeline_rows(feature_rows, profile_ids)
    return {
        "profiles": profiles,
        "evidence_records": evidence_records,
        "timeline": timeline,
        "summary": {
            "enabled": True,
            "candidate_pattern_count": len(raw_profiles),
            "reported_pattern_count": len(profiles),
            "evidence_record_count": len(evidence_records),
            "timeline_rows": len(timeline),
            "min_pattern_score": config.min_pattern_score,
        },
    }


def _feature_rows(
    *,
    docs: list[Any],
    nodes: list[TaxonomyNode],
    taxonomy_events: list[dict[str, Any]],
    state_snapshot: dict[str, Any],
    state_transitions: list[dict[str, Any]],
    trajectory_rows: list[dict[str, Any]],
    edges: list[EvolutionEdge],
    edge_score_rows: list[dict[str, Any]],
    schema_revisions: list[dict[str, Any]],
    relation_rejections: list[dict[str, Any]],
    config: MacroPatternConfig,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    node_map = {node.node_id: node for node in nodes}
    edge_by_id = {edge.edge_id: edge for edge in edges}
    score_by_edge_id = {str(row.get("edge_id") or ""): row for row in edge_score_rows}
    rows.extend(_taxonomy_features(taxonomy_events, node_map))
    rows.extend(_state_features(state_snapshot, state_transitions, node_map))
    rows.extend(_trajectory_features(trajectory_rows, edge_by_id, score_by_edge_id, node_map))
    rows.extend(_edge_features(edges, score_by_edge_id, node_map))
    rows.extend(_schema_features(schema_revisions))
    if config.use_negative_evidence:
        rows.extend(_negative_relation_features(relation_rejections))
    rows.extend(_temporal_recurrence_features(docs, nodes))
    return rows


def _taxonomy_features(events: list[dict[str, Any]], node_map: dict[str, TaxonomyNode]) -> list[dict[str, Any]]:
    rows = []
    for event in events:
        event_type = str(event.get("event_type") or "unknown")
        target_nodes = [str(node_id) for node_id in event.get("target_node_ids") or [] if str(node_id)]
        source_nodes = [str(node_id) for node_id in event.get("source_node_ids") or [] if str(node_id)]
        patterns: dict[str, float] = {}
        if event_type in {"birth", "split"}:
            patterns["differentiation"] = 0.72 if event_type == "split" else 0.48
        if event_type == "cross_link":
            patterns["convergence"] = 0.65
            patterns["hybridization"] = 0.45
        if event_type == "state_update":
            patterns["stabilization"] = 0.35
        if event_type == "revision":
            patterns["recontextualization"] = 0.36
        if not patterns:
            continue
        rows.append(
            _feature(
                artifact_type="taxonomy_event",
                artifact_id=str(event.get("event_id") or f"taxonomy_event__{len(rows) + 1}"),
                signal_type=event_type,
                patterns=patterns,
                time_slice=str(event.get("time_slice") or ""),
                nodes=sorted(set(source_nodes + target_nodes)),
                representative_nodes=_node_labels(sorted(set(source_nodes + target_nodes)), node_map),
                score=float(event.get("confidence") or 0.0),
                evidence_ids=[str(event.get("event_id") or "")],
                source=event,
                explanation=str(event.get("reason") or ""),
            )
        )
    return rows


def _state_features(
    state_snapshot: dict[str, Any],
    transitions: list[dict[str, Any]],
    node_map: dict[str, TaxonomyNode],
) -> list[dict[str, Any]]:
    rows = []
    node_states = ((state_snapshot.get("taxonomy") or {}).get("node_states") or [])
    active_nodes = [row for row in node_states if row.get("state") == "active"]
    bridging_nodes = [row for row in node_states if row.get("state") == "bridging"]
    stable_nodes = [row for row in node_states if row.get("state") == "stable"]
    emerging_nodes = [row for row in node_states if row.get("state") == "emerging"]
    if bridging_nodes:
        nodes = [str(row.get("node_id") or "") for row in bridging_nodes if row.get("node_id")]
        rows.append(
            _feature(
                artifact_type="state_snapshot",
                artifact_id="state__bridging_nodes",
                signal_type="bridging_node_state",
                patterns={"convergence": 0.5, "hybridization": 0.4},
                time_slice="",
                nodes=nodes,
                representative_nodes=_node_labels(nodes, node_map),
                score=min(1.0, len(bridging_nodes) / max(1, len(node_states))),
                evidence_ids=["state__current"],
                source={"node_states": bridging_nodes[:8]},
                explanation="Nodes marked as bridging connect otherwise separate taxonomy areas.",
            )
        )
    if active_nodes and len(active_nodes) >= len(stable_nodes):
        nodes = [str(row.get("node_id") or "") for row in active_nodes[:10] if row.get("node_id")]
        rows.append(
            _feature(
                artifact_type="state_snapshot",
                artifact_id="state__active_nodes",
                signal_type="active_node_state",
                patterns={"fragmentation": 0.3, "differentiation": 0.24},
                time_slice="",
                nodes=nodes,
                representative_nodes=_node_labels(nodes, node_map),
                score=min(1.0, len(active_nodes) / max(1, len(node_states))),
                evidence_ids=["state__current"],
                source={"active_node_count": len(active_nodes), "emerging_node_count": len(emerging_nodes)},
                explanation="Many active or emerging nodes indicate ongoing structural movement.",
            )
        )
    if stable_nodes and len(stable_nodes) >= len(emerging_nodes):
        nodes = [str(row.get("node_id") or "") for row in stable_nodes[:10] if row.get("node_id")]
        rows.append(
            _feature(
                artifact_type="state_snapshot",
                artifact_id="state__stable_nodes",
                signal_type="stable_node_state",
                patterns={"stabilization": 0.54},
                time_slice="",
                nodes=nodes,
                representative_nodes=_node_labels(nodes, node_map),
                score=min(1.0, len(stable_nodes) / max(1, len(node_states))),
                evidence_ids=["state__current"],
                source={"stable_node_count": len(stable_nodes), "node_state_count": len(node_states)},
                explanation="Stable node states support a stabilization pattern.",
            )
        )
    rejection_transitions = [row for row in transitions if row.get("transition_family") == "negative_relation"]
    if rejection_transitions:
        rows.append(
            _feature(
                artifact_type="state_transition",
                artifact_id="state__negative_relation_constraints",
                signal_type="negative_relation_constraints",
                patterns={"fragmentation": 0.4, "stabilization": 0.18},
                time_slice="",
                nodes=[],
                representative_nodes=[],
                score=min(1.0, sum(int(row.get("support") or 0) for row in rejection_transitions) / 10.0),
                evidence_ids=[str(row.get("transition_id") or "") for row in rejection_transitions],
                source={"transitions": rejection_transitions},
                explanation="Rejected relation pairs constrain weak links and can expose fragmented or stabilized boundaries.",
            )
        )
    return rows


def _trajectory_features(
    trajectory_rows: list[dict[str, Any]],
    edge_by_id: dict[str, EvolutionEdge],
    score_by_edge_id: dict[str, dict[str, Any]],
    node_map: dict[str, TaxonomyNode],
) -> list[dict[str, Any]]:
    rows = []
    for row in trajectory_rows:
        edge_ids = [str(edge_id) for edge_id in row.get("edge_path") or []]
        edges = [edge_by_id[edge_id] for edge_id in edge_ids if edge_id in edge_by_id]
        edge_types = [edge.edge_type for edge in edges]
        nodes = sorted({str(node_id) for node_id in row.get("taxonomy_nodes") or [] if str(node_id)})
        patterns: dict[str, float] = {}
        if len(nodes) >= 2:
            patterns["convergence"] = max(patterns.get("convergence", 0.0), 0.44)
            patterns["hybridization"] = max(patterns.get("hybridization", 0.0), 0.5)
        if any(edge_type == "adapts" for edge_type in edge_types):
            patterns["recontextualization"] = max(patterns.get("recontextualization", 0.0), 0.62)
        if any(edge_type == "replaces" for edge_type in edge_types):
            patterns["substitution"] = max(patterns.get("substitution", 0.0), 0.72)
        if _has_repeated_entity(row.get("entity_path") or []):
            patterns["cyclical_return"] = max(patterns.get("cyclical_return", 0.0), 0.62)
        if int(row.get("branching_factor") or 0) >= 3:
            patterns["fragmentation"] = max(patterns.get("fragmentation", 0.0), 0.42)
        if float(row.get("temporal_coherence") or 0.0) >= 0.85 and float(row.get("schema_coherence") or 0.0) >= 0.75:
            patterns["stabilization"] = max(patterns.get("stabilization", 0.0), 0.32)
        if not patterns:
            continue
        score = float(row.get("trajectory_score") or 0.0)
        rows.append(
            _feature(
                artifact_type="trajectory",
                artifact_id=str(row.get("trajectory_id") or f"trajectory__{len(rows) + 1}"),
                signal_type="trajectory_shape",
                patterns=patterns,
                time_slice="",
                nodes=nodes,
                representative_nodes=_node_labels(nodes, node_map),
                trajectories=[str(row.get("trajectory_id") or "")],
                score=score,
                evidence_ids=[str(row.get("trajectory_id") or ""), *edge_ids],
                source={
                    "trajectory_id": row.get("trajectory_id"),
                    "entity_path": row.get("entity_path") or [],
                    "edge_path": edge_ids,
                    "edge_types": edge_types,
                    "edge_scores": [score_by_edge_id.get(edge_id, {}) for edge_id in edge_ids],
                },
                explanation="Trajectory topology and relation types indicate candidate macro evolution patterns.",
            )
        )
    return rows


def _edge_features(
    edges: list[EvolutionEdge],
    score_by_edge_id: dict[str, dict[str, Any]],
    node_map: dict[str, TaxonomyNode],
) -> list[dict[str, Any]]:
    rows = []
    for edge in edges:
        score_row = score_by_edge_id.get(edge.edge_id, {})
        patterns: dict[str, float] = {}
        if edge.edge_type == "adapts":
            patterns["recontextualization"] = 0.56
        elif edge.edge_type == "replaces":
            patterns["substitution"] = 0.72
        elif edge.edge_type in {"uses_component", "compares"}:
            patterns["hybridization"] = 0.32
        if len(edge.taxonomy_nodes or []) >= 2:
            patterns["convergence"] = max(patterns.get("convergence", 0.0), 0.36)
            patterns["hybridization"] = max(patterns.get("hybridization", 0.0), 0.38)
        if _institutional_terms(edge):
            patterns["institutionalization"] = max(patterns.get("institutionalization", 0.0), 0.56)
        if float(score_row.get("edge_score") or edge.confidence or 0.0) >= 0.75 and edge.substring_verified:
            patterns["stabilization"] = max(patterns.get("stabilization", 0.0), 0.26)
        if not patterns:
            continue
        nodes = [str(node_id) for node_id in edge.taxonomy_nodes or [] if str(node_id)]
        rows.append(
            _feature(
                artifact_type="edge",
                artifact_id=edge.edge_id,
                signal_type=f"edge_type__{edge.edge_type}",
                patterns=patterns,
                time_slice="",
                nodes=nodes,
                representative_nodes=_node_labels(nodes, node_map),
                score=float(score_row.get("edge_score") or edge.confidence or 0.0),
                evidence_ids=[edge.edge_id],
                source=edge.to_record() | {"edge_score": score_row},
                explanation=f"Relation edge type {edge.edge_type!r} contributes to macro-pattern evidence.",
            )
        )
    return rows


def _schema_features(schema_revisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for revision in schema_revisions:
        status = str(revision.get("status") or revision.get("decision") or "")
        if status and status not in {"applied", "promote"}:
            continue
        revision_type = str(revision.get("revision_type") or "")
        patterns: dict[str, float] = {}
        if revision_type in {"add_relation_type", "add_entity_type", "add_evidence_slot"}:
            patterns["differentiation"] = 0.4
            patterns["recontextualization"] = 0.22
        if revision_type == "update_negative_prior":
            patterns["stabilization"] = 0.34
            patterns["fragmentation"] = 0.22
        if not patterns:
            continue
        rows.append(
            _feature(
                artifact_type="schema_revision",
                artifact_id=str(revision.get("candidate_id") or f"schema_revision__{len(rows) + 1}"),
                signal_type=revision_type,
                patterns=patterns,
                time_slice="",
                nodes=[],
                representative_nodes=[],
                score=float(revision.get("confidence") or revision.get("judge_confidence") or 0.0),
                evidence_ids=[str(revision.get("candidate_id") or "")],
                source=revision,
                explanation="Applied schema revisions alter the interpretation space for macro patterns.",
            )
        )
    return rows


def _negative_relation_features(rejections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rejection in rejections:
        grouped[str(rejection.get("rejection_reason") or "unknown")].append(rejection)
    for reason, reason_rows in sorted(grouped.items()):
        patterns = {"fragmentation": 0.42}
        if reason in {"temporal_violation", "unsupported_by_quotes", "no_mechanism_evidence", "schema_mismatch"}:
            patterns["stabilization"] = 0.2
        rows.append(
            _feature(
                artifact_type="relation_rejection",
                artifact_id=f"relation_rejection__{reason}",
                signal_type=reason,
                patterns=patterns,
                time_slice="",
                nodes=[],
                representative_nodes=[],
                score=min(1.0, len(reason_rows) / 8.0),
                evidence_ids=[f"relation_rejection__{reason}__{index}" for index, _ in enumerate(reason_rows[:20], start=1)],
                source={"reason": reason, "count": len(reason_rows), "examples": reason_rows[:5]},
                explanation="Negative relation evidence prevents weak co-mentions from becoming macro links.",
            )
        )
    return rows


def _temporal_recurrence_features(docs: list[Any], nodes: list[TaxonomyNode]) -> list[dict[str, Any]]:
    rows = []
    doc_years = {
        getattr(doc, "doc_id", ""): getattr(getattr(doc, "published_at", None), "year", None)
        for doc in docs
    }
    for node in nodes:
        years = sorted({int(year) for doc_id in node.support_documents if (year := doc_years.get(doc_id))})
        if len(years) >= 2 and years[-1] - years[0] >= 6:
            rows.append(
                _feature(
                    artifact_type="temporal_support",
                    artifact_id=f"temporal_support__{node.node_id}",
                    signal_type="long_span_node_support",
                    patterns={"cyclical_return": 0.34, "stabilization": 0.22},
                    time_slice=f"{years[0]}-{years[-1]}",
                    nodes=[node.node_id],
                    representative_nodes=[node.canonical_label],
                    score=min(1.0, (years[-1] - years[0]) / 20.0),
                    evidence_ids=[f"temporal_support__{node.node_id}"],
                    source={"node_id": node.node_id, "support_years": years, "support_documents": node.support_documents},
                    explanation="Long-span node support can indicate recurrence or stabilization across time.",
                )
            )
    return rows


def _pattern_profile(
    *,
    pattern_id: str,
    features: list[dict[str, Any]],
    config: MacroPatternConfig,
    llm_summaries: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    pattern_features = [row for row in features if pattern_id in row.get("pattern_scores", {})]
    weighted_scores = [
        float(row.get("score") or 0.0) * float(row.get("pattern_scores", {}).get(pattern_id) or 0.0)
        for row in pattern_features
    ]
    score = _clamp(_mean(weighted_scores) + min(0.35, 0.035 * len(pattern_features)))
    top_features = sorted(
        pattern_features,
        key=lambda row: (
            -float(row.get("score") or 0.0) * float(row.get("pattern_scores", {}).get(pattern_id) or 0.0),
            row.get("artifact_id", ""),
        ),
    )[: max(1, config.max_evidence_per_pattern)]
    evidence_ids = _dedupe(
        evidence_id
        for row in top_features
        for evidence_id in row.get("evidence_ids", [])
        if str(evidence_id)
    )
    representative_nodes = _dedupe(node for row in top_features for node in row.get("representative_nodes", []) if str(node))[:8]
    representative_node_ids = _dedupe(node for row in top_features for node in row.get("nodes", []) if str(node))[:8]
    representative_trajectories = _dedupe(
        trajectory_id for row in top_features for trajectory_id in row.get("trajectories", []) if str(trajectory_id)
    )[:8]
    time_span = _time_span(top_features)
    explanation = _explanation(pattern_id, score, top_features)
    llm_summary = llm_summaries.get(pattern_id, {}) if llm_summaries else {}
    if isinstance(llm_summary, dict) and llm_summary.get("summary"):
        explanation = str(llm_summary.get("summary") or explanation)
    return {
        "pattern_id": pattern_id,
        "pattern_label": PATTERN_SPECS[pattern_id]["label"],
        "definition": PATTERN_SPECS[pattern_id]["definition"],
        "pattern_score": round(score, 3),
        "time_span": time_span,
        "representative_node_ids": representative_node_ids,
        "representative_nodes": representative_nodes,
        "representative_trajectories": representative_trajectories,
        "evidence_ids": evidence_ids,
        "evidence_count": len(evidence_ids),
        "supporting_signal_count": len(pattern_features),
        "explanation": explanation,
        "llm_summary_used": bool(llm_summary.get("summary")) if isinstance(llm_summary, dict) else False,
    }


def _evidence_records(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for row in features:
        pattern_scores = {
            pattern_id: round(float(score) * float(row.get("score") or 0.0), 3)
            for pattern_id, score in row.get("pattern_scores", {}).items()
        }
        records.append(
            {
                "evidence_id": row["feature_id"],
                "artifact_type": row["artifact_type"],
                "artifact_id": row["artifact_id"],
                "signal_type": row["signal_type"],
                "pattern_ids": sorted(pattern_scores),
                "pattern_scores": pattern_scores,
                "time_slice": row.get("time_slice", ""),
                "node_ids": row.get("nodes", []),
                "representative_nodes": row.get("representative_nodes", []),
                "trajectory_ids": row.get("trajectories", []),
                "source_evidence_ids": row.get("evidence_ids", []),
                "explanation": row.get("explanation", ""),
                "source": row.get("source", {}),
            }
        )
    return records


def _timeline_rows(features: list[dict[str, Any]], profile_ids: set[str]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in features:
        time_slice = str(row.get("time_slice") or "unspecified")
        for pattern_id in row.get("pattern_scores", {}):
            if pattern_id in profile_ids:
                buckets[(pattern_id, time_slice)].append(row)
    timeline = []
    for (pattern_id, time_slice), rows in sorted(buckets.items()):
        scores = [
            float(row.get("score") or 0.0) * float(row.get("pattern_scores", {}).get(pattern_id) or 0.0)
            for row in rows
        ]
        timeline.append(
            {
                "pattern_id": pattern_id,
                "pattern_label": PATTERN_SPECS[pattern_id]["label"],
                "time_slice": time_slice,
                "pattern_score": round(_clamp(_mean(scores) + min(0.2, 0.03 * len(rows))), 3),
                "evidence_ids": [row["feature_id"] for row in rows],
                "representative_node_ids": _dedupe(node for row in rows for node in row.get("nodes", []) if str(node))[:8],
                "representative_trajectories": _dedupe(
                    trajectory for row in rows for trajectory in row.get("trajectories", []) if str(trajectory)
                )[:8],
            }
        )
    return timeline


def _feature(
    *,
    artifact_type: str,
    artifact_id: str,
    signal_type: str,
    patterns: dict[str, float],
    time_slice: str,
    nodes: list[str],
    representative_nodes: list[str],
    score: float,
    evidence_ids: list[str],
    source: dict[str, Any],
    explanation: str,
    trajectories: list[str] | None = None,
) -> dict[str, Any]:
    feature_id = f"macro_evidence__{artifact_type}__{_safe_id(artifact_id)}"
    return {
        "feature_id": feature_id,
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "signal_type": signal_type,
        "pattern_scores": {pattern_id: _clamp(value) for pattern_id, value in patterns.items()},
        "time_slice": time_slice,
        "nodes": nodes,
        "representative_nodes": representative_nodes,
        "trajectories": trajectories or [],
        "score": _clamp(score),
        "evidence_ids": _dedupe(evidence_ids),
        "source": source,
        "explanation": explanation,
    }


def _node_labels(node_ids: list[str], node_map: dict[str, TaxonomyNode]) -> list[str]:
    return [node_map[node_id].canonical_label for node_id in node_ids if node_id in node_map]


def _institutional_terms(edge: EvolutionEdge) -> bool:
    text = " ".join(
        [
            edge.source_entity,
            edge.target_entity,
            edge.edge_type,
            str((edge.evidence or {}).get("mechanism") or ""),
            str((edge.evidence or {}).get("bottleneck") or ""),
            str((edge.evidence or {}).get("implementation_context") or ""),
        ]
    ).lower()
    terms = ["governance", "institution", "standard", "benchmark", "audit", "policy", "regulation", "mandate"]
    return any(term in text for term in terms)


def _has_repeated_entity(entity_path: list[Any]) -> bool:
    values = [str(item) for item in entity_path if str(item)]
    return len(set(values)) < len(values)


def _time_span(rows: list[dict[str, Any]]) -> str:
    values = [str(row.get("time_slice") or "") for row in rows if str(row.get("time_slice") or "")]
    if not values:
        return ""
    years = []
    for value in values:
        for part in value.replace("-", " ").split():
            if part.isdigit() and len(part) == 4:
                years.append(int(part))
    if years:
        return f"{min(years)}-{max(years)}" if min(years) != max(years) else str(min(years))
    unique = sorted(set(values))
    return unique[0] if len(unique) == 1 else f"{unique[0]} -> {unique[-1]}"


def _explanation(pattern_id: str, score: float, features: list[dict[str, Any]]) -> str:
    if not features:
        return "No detector-backed evidence exceeded the current threshold."
    signal_counts = Counter(str(row.get("signal_type") or "unknown") for row in features)
    top_signals = ", ".join(signal for signal, _ in signal_counts.most_common(3))
    artifact_counts = Counter(str(row.get("artifact_type") or "unknown") for row in features)
    top_artifacts = ", ".join(artifact for artifact, _ in artifact_counts.most_common(3))
    label = PATTERN_SPECS[pattern_id]["label"]
    return (
        f"{label} is estimated from {len(features)} detector-backed signals "
        f"(score {score:.3f}), led by {top_signals} evidence in {top_artifacts} artifacts."
    )


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(value or "unknown"))[:120]


def _dedupe(values: Any) -> list[str]:
    seen = set()
    output = []
    for value in values:
        item = str(value or "")
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value or 0.0)))
