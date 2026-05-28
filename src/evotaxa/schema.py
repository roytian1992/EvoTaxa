from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evotaxa.config import EvoTaxaConfig
from evotaxa.io import read_json_or_jsonl, slugify
from evotaxa.llm import LLMClient, infer_entity_evidence_schema, infer_relation_schema
from evotaxa.models import Document, TaxonomyNode
from evotaxa.relation_schema import (
    apply_relation_schema_revisions,
    fixed_relation_schema,
    normalize_relation_schema,
    propose_relation_schema_revisions,
)


DEFAULT_EVIDENCE_SCHEMA: dict[str, dict[str, Any]] = {
    "bottleneck": {
        "definition": "Problem, limitation, unresolved need, or pressure that motivates a successor.",
        "required": False,
        "quote_required": True,
        "allowed_source": "either",
        "validation": "substring",
        "schema_source": "fixed",
    },
    "mechanism": {
        "definition": "Mechanism, design, intervention, or process connecting source and target.",
        "required": True,
        "quote_required": True,
        "allowed_source": "either",
        "validation": "substring",
        "schema_source": "fixed",
    },
    "tradeoff": {
        "definition": "Cost, limitation, risk, side effect, or comparison caveat.",
        "required": False,
        "quote_required": True,
        "allowed_source": "either",
        "validation": "substring",
        "schema_source": "fixed",
    },
}


SOCIAL_EVIDENCE_SLOTS: dict[str, dict[str, Any]] = {
    "problem_definition": {
        "definition": "How the social issue or governance problem is framed.",
        "required": False,
        "quote_required": True,
        "allowed_source": "either",
        "validation": "substring",
        "schema_source": "inferred",
    },
    "actor": {
        "definition": "Institution, platform, community, public group, or authority involved.",
        "required": False,
        "quote_required": True,
        "allowed_source": "either",
        "validation": "substring",
        "schema_source": "inferred",
    },
    "intervention_mechanism": {
        "definition": "How an intervention, policy, measurement, or frame is expected to work.",
        "required": True,
        "quote_required": True,
        "allowed_source": "either",
        "validation": "substring",
        "schema_source": "inferred",
    },
    "implementation_context": {
        "definition": "Population, platform, institution, geography, or implementation setting.",
        "required": False,
        "quote_required": True,
        "allowed_source": "either",
        "validation": "substring",
        "schema_source": "inferred",
    },
    "observed_outcome": {
        "definition": "Observed outcome, metric shift, institutional response, or behavioral result.",
        "required": False,
        "quote_required": True,
        "allowed_source": "either",
        "validation": "substring",
        "schema_source": "inferred",
    },
}


class SchemaBundle(dict):
    @property
    def entity_schema(self) -> dict[str, dict[str, Any]]:
        return self["entity_schema"]

    @property
    def relation_schema(self) -> dict[str, dict[str, Any]]:
        return self["relation_schema"]

    @property
    def evidence_schema(self) -> dict[str, dict[str, Any]]:
        return self["evidence_schema"]

    @property
    def reports(self) -> list[dict[str, Any]]:
        return self["reports"]

    @property
    def llm_records(self) -> list[Any]:
        return self["llm_records"]

    @property
    def fixed_entity_schema(self) -> dict[str, dict[str, Any]]:
        return self["fixed_entity_schema"]

    @property
    def fixed_relation_schema(self) -> dict[str, dict[str, Any]]:
        return self["fixed_relation_schema"]

    @property
    def fixed_evidence_schema(self) -> dict[str, dict[str, Any]]:
        return self["fixed_evidence_schema"]

    @property
    def inferred_entity_schema(self) -> dict[str, dict[str, Any]]:
        return self["inferred_entity_schema"]

    @property
    def inferred_relation_schema(self) -> dict[str, dict[str, Any]]:
        return self["inferred_relation_schema"]

    @property
    def inferred_evidence_schema(self) -> dict[str, dict[str, Any]]:
        return self["inferred_evidence_schema"]

    @property
    def revision_candidates(self) -> list[dict[str, Any]]:
        return self["revision_candidates"]


def resolve_initial_schema(
    config: EvoTaxaConfig,
    docs: list[Document],
    nodes: list[TaxonomyNode],
    llm_client: LLMClient,
) -> SchemaBundle:
    seed = _load_seed(config.schema.schema_seed_path)
    fixed_entities = fixed_entity_schema(config, nodes, seed.get("entity_schema"))
    fixed_relations = fixed_relation_schema(config.graph)
    fixed_evidence = fixed_evidence_schema(config, seed.get("evidence_schema"))
    reports: list[dict[str, Any]] = []
    llm_records: list[Any] = []

    relation_schema = fixed_relations
    entity_schema = fixed_entities
    evidence_schema = fixed_evidence
    inferred_entity_schema: dict[str, dict[str, Any]] = {}
    inferred_relation_schema: dict[str, dict[str, Any]] = {}
    inferred_evidence_schema: dict[str, dict[str, Any]] = {}

    relation_seed = seed.get("relation_schema") if isinstance(seed.get("relation_schema"), dict) else {}
    if relation_seed:
        relation_schema, relation_report = normalize_relation_schema({"relation_types": _schema_rows(relation_seed)}, config.graph)
        reports.extend(_report_rows("relation_schema", "seed", relation_report))

    if config.schema.relation_schema_mode in {"inferred", "adaptive"}:
        record = infer_relation_schema(
            llm_client,
            domain_id=config.project.domain_id,
            entity_types=list(entity_schema),
            strong_edge_types=config.graph.strong_edge_types,
            sample_documents=_sample_documents(docs, config.schema.schema_inference_sample_size),
            fixed_schema=relation_schema,
            max_relation_types=config.graph.max_relation_types,
        )
        llm_records.append(record)
        relation_schema, relation_report = normalize_relation_schema(record.output, config.graph)
        inferred_relation_schema = relation_schema
        reports.extend(_report_rows("relation_schema", config.schema.relation_schema_mode, relation_report))

    if config.schema.entity_schema_mode in {"inferred", "adaptive"} or config.schema.evidence_schema_mode in {"inferred", "adaptive"}:
        record = infer_entity_evidence_schema(
            llm_client,
            domain_id=config.project.domain_id,
            taxonomy_dimensions=sorted({node.dimension for node in nodes if node.dimension}),
            configured_entity_types=config.graph.entity_types,
            fixed_entity_schema=entity_schema,
            fixed_evidence_schema=evidence_schema,
            sample_documents=_sample_documents(docs, config.schema.schema_inference_sample_size),
        )
        llm_records.append(record)
        entity_schema, evidence_schema, schema_report = normalize_entity_evidence_schema(
            record.output,
            config,
            fixed_entity_schema=entity_schema,
            fixed_evidence_schema=evidence_schema,
        )
        inferred_entity_schema = entity_schema
        inferred_evidence_schema = evidence_schema
        reports.extend(schema_report)

    return SchemaBundle(
        entity_schema=entity_schema,
        relation_schema=relation_schema,
        evidence_schema=evidence_schema,
        reports=reports,
        llm_records=llm_records,
        fixed_entity_schema=fixed_entities,
        fixed_relation_schema=fixed_relations,
        fixed_evidence_schema=fixed_evidence,
        inferred_entity_schema=inferred_entity_schema,
        inferred_relation_schema=inferred_relation_schema,
        inferred_evidence_schema=inferred_evidence_schema,
        revision_candidates=[],
    )


def adapt_schema_after_graph(
    bundle: SchemaBundle,
    *,
    edge_evidence_audit: list[dict[str, Any]],
    entity_quality_report: list[dict[str, Any]],
    config: EvoTaxaConfig,
    judgements: dict[str, dict[str, Any]] | None = None,
) -> tuple[SchemaBundle, list[dict[str, Any]]]:
    adapted = SchemaBundle(
        entity_schema=deepcopy(bundle.entity_schema),
        relation_schema=deepcopy(bundle.relation_schema),
        evidence_schema=deepcopy(bundle.evidence_schema),
        reports=list(bundle.reports),
        llm_records=list(bundle.llm_records),
        fixed_entity_schema=deepcopy(bundle.fixed_entity_schema),
        fixed_relation_schema=deepcopy(bundle.fixed_relation_schema),
        fixed_evidence_schema=deepcopy(bundle.fixed_evidence_schema),
        inferred_entity_schema=deepcopy(bundle.inferred_entity_schema),
        inferred_relation_schema=deepcopy(bundle.inferred_relation_schema),
        inferred_evidence_schema=deepcopy(bundle.inferred_evidence_schema),
        revision_candidates=list(bundle.revision_candidates),
    )
    candidates = propose_schema_revision_candidates(
        adapted,
        edge_evidence_audit=edge_evidence_audit,
        entity_quality_report=entity_quality_report,
        config=config,
    )
    judged_candidates = _apply_revision_judgements(candidates, judgements or {})
    revisions = promote_schema_revisions(adapted, judged_candidates, config)
    adapted["revision_candidates"].extend(judged_candidates)
    adapted.reports.extend(revisions)
    return adapted, revisions


def propose_schema_revision_candidates(
    bundle: SchemaBundle,
    *,
    edge_evidence_audit: list[dict[str, Any]],
    entity_quality_report: list[dict[str, Any]],
    config: EvoTaxaConfig,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    if config.schema.relation_schema_mode == "adaptive":
        candidates.extend(propose_relation_schema_revisions(bundle.relation_schema, edge_evidence_audit, config.graph))

    if config.schema.entity_schema_mode == "adaptive":
        candidates.extend(propose_entity_schema_revisions(bundle.entity_schema, entity_quality_report, config.schema.schema_revision_min_support))

    if config.schema.evidence_schema_mode == "adaptive":
        candidates.extend(propose_evidence_schema_revisions(bundle.evidence_schema, edge_evidence_audit, config.schema.schema_revision_min_support))

    for row in candidates:
        row.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
        row.setdefault("decision", "candidate")
    return sorted(candidates, key=lambda row: (-float(row.get("confidence") or 0.0), row.get("candidate_id", "")))


def promote_schema_revisions(
    bundle: SchemaBundle,
    candidates: list[dict[str, Any]],
    config: EvoTaxaConfig,
    judgements: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    candidates = _apply_revision_judgements(candidates, judgements or {})
    held_by_judge = [row for row in candidates if row.get("decision") in {"rejected", "needs_human_review"}]
    candidates = [row for row in candidates if row.get("decision") not in {"rejected", "needs_human_review"}]
    if config.schema.max_schema_revisions > 0:
        promotable = candidates[: config.schema.max_schema_revisions]
        overflow = candidates[config.schema.max_schema_revisions :]
    else:
        promotable = list(candidates)
        overflow = []

    relation_candidates = [row for row in promotable if row.get("schema_family") == "relation_schema"]
    relation_schema, relation_report = apply_relation_schema_revisions(
        bundle.relation_schema,
        relation_candidates,
        max_revisions=0,
        max_relation_types=config.graph.max_relation_types,
    )
    bundle["relation_schema"] = relation_schema

    revisions: list[dict[str, Any]] = list(relation_report)
    for candidate in promotable:
        family = candidate.get("schema_family")
        if family == "entity_schema":
            revisions.append(_apply_entity_schema_revision(bundle.entity_schema, candidate))
        elif family == "evidence_schema":
            revisions.append(_apply_evidence_schema_revision(bundle.evidence_schema, candidate))
        elif family != "relation_schema":
            revisions.append({**candidate, "status": "rejected", "decision": "rejected", "reason": "unsupported_schema_family"})

    for candidate in overflow:
        revisions.append({**candidate, "status": "rejected", "decision": "rejected", "reason": "max_schema_revisions_reached"})
    revisions.extend(held_by_judge)
    for row in revisions:
        row.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
        row.setdefault("decision", "promoted" if row.get("status") == "applied" else row.get("decision", "rejected"))
    return revisions


def _apply_revision_judgements(
    candidates: list[dict[str, Any]],
    judgements: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "")
        judgement = judgements.get(candidate_id) or {}
        decision = str(judgement.get("decision") or "promote")
        row = dict(candidate)
        if judgement:
            row["judge_decision"] = decision
            row["judge_confidence"] = judgement.get("confidence")
            row["judge_rationale"] = judgement.get("rationale")
            row["judge_risk"] = judgement.get("risk")
        if decision == "reject":
            row["status"] = "rejected"
            row["decision"] = "rejected"
            row["reason"] = judgement.get("rationale") or row.get("reason") or "schema_revision_judge_rejected"
            rows.append(row)
        elif decision == "needs_human_review":
            row["status"] = "needs_human_review"
            row["decision"] = "needs_human_review"
            rows.append(row)
        else:
            rows.append(row)
    promotable = [row for row in rows if row.get("decision") not in {"rejected", "needs_human_review"}]
    held = [row for row in rows if row.get("decision") in {"rejected", "needs_human_review"}]
    return [*promotable, *held]


def fixed_entity_schema(
    config: EvoTaxaConfig,
    nodes: list[TaxonomyNode],
    seed_schema: Any = None,
) -> dict[str, dict[str, Any]]:
    dimensions_by_entity = _entity_dimensions(config, nodes)
    schema: dict[str, dict[str, Any]] = {}
    for entity_type in config.graph.entity_types or ["entity"]:
        schema[entity_type] = {
            "entity_type": entity_type,
            "definition": _default_entity_definition(entity_type),
            "inclusion_criteria": f"Mentions of {entity_type.replace('_', ' ')} that participate in field evolution.",
            "exclusion_criteria": "Generic references, isolated topic names, or unsupported phrases.",
            "aliases": [],
            "allowed_dimensions": dimensions_by_entity.get(entity_type, config.graph.entity_dimensions),
            "example_mentions": list(config.graph.entity_patterns.get(entity_type, []))[:10],
            "negative_examples": list(config.graph.generic_entity_phrases)[:8],
            "quality_rules": ["quote_required", "canonical_name_required", "reject_generic_phrases"],
            "schema_source": "fixed",
        }
    for entity_type, spec in ((seed_schema or {}).items() if isinstance(seed_schema, dict) else []):
        key = str(entity_type)
        schema[key] = {**schema.get(key, _minimal_entity_schema(key)), **dict(spec), "schema_source": "fixed"}
    return schema


def fixed_evidence_schema(config: EvoTaxaConfig, seed_schema: Any = None) -> dict[str, dict[str, Any]]:
    schema = deepcopy(DEFAULT_EVIDENCE_SCHEMA)
    if _looks_social(config.project.domain_id, config.graph.entity_types):
        schema.update(deepcopy(SOCIAL_EVIDENCE_SLOTS))
    for slot, spec in config.schema.evidence_schema.items():
        schema[slot] = {**schema.get(slot, {}), **spec, "schema_source": "fixed"}
    for slot, spec in ((seed_schema or {}).items() if isinstance(seed_schema, dict) else []):
        schema[str(slot)] = {**schema.get(str(slot), {}), **dict(spec), "schema_source": "fixed"}
    return schema


def normalize_entity_evidence_schema(
    raw_schema: dict[str, Any],
    config: EvoTaxaConfig,
    *,
    fixed_entity_schema: dict[str, dict[str, Any]],
    fixed_evidence_schema: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    entity_schema = deepcopy(fixed_entity_schema)
    evidence_schema = deepcopy(fixed_evidence_schema)
    report: list[dict[str, Any]] = []

    rows = raw_schema.get("entity_types") if isinstance(raw_schema, dict) else None
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            entity_type = slugify(str(row.get("entity_type") or row.get("name") or ""))
            if not entity_type:
                continue
            entity_schema[entity_type] = {
                **entity_schema.get(entity_type, _minimal_entity_schema(entity_type)),
                "entity_type": entity_type,
                "definition": str(row.get("definition") or entity_schema.get(entity_type, {}).get("definition") or ""),
                "inclusion_criteria": str(row.get("inclusion_criteria") or ""),
                "exclusion_criteria": str(row.get("exclusion_criteria") or ""),
                "aliases": _str_list(row.get("aliases")),
                "allowed_dimensions": _str_list(row.get("allowed_dimensions")),
                "example_mentions": _str_list(row.get("example_mentions")),
                "negative_examples": _str_list(row.get("negative_examples")),
                "quality_rules": _str_list(row.get("quality_rules")),
                "schema_source": "inferred",
            }
            report.append({"schema_family": "entity_schema", "status": "accepted", "entity_type": entity_type})

    slots = raw_schema.get("evidence_slots") if isinstance(raw_schema, dict) else None
    if isinstance(slots, list):
        for row in slots:
            if not isinstance(row, dict):
                continue
            slot = slugify(str(row.get("slot") or row.get("name") or ""))
            if not slot:
                continue
            evidence_schema[slot] = {
                **evidence_schema.get(slot, {}),
                "definition": str(row.get("definition") or ""),
                "required": bool(row.get("required", False)),
                "quote_required": bool(row.get("quote_required", True)),
                "allowed_source": str(row.get("allowed_source") or "either"),
                "validation": str(row.get("validation") or "substring"),
                "schema_source": "inferred",
            }
            report.append({"schema_family": "evidence_schema", "status": "accepted", "slot": slot})

    if not report:
        report.append({"schema_family": "entity_evidence_schema", "status": "fallback", "reason": "missing_or_invalid_rows"})
    return entity_schema, evidence_schema, report


def adapt_entity_schema(
    entity_schema: dict[str, dict[str, Any]],
    entity_quality_report: list[dict[str, Any]],
    min_support: int,
) -> list[dict[str, Any]]:
    return [_apply_entity_schema_revision(entity_schema, candidate) for candidate in propose_entity_schema_revisions(entity_schema, entity_quality_report, min_support)]


def propose_entity_schema_revisions(
    entity_schema: dict[str, dict[str, Any]],
    entity_quality_report: list[dict[str, Any]],
    min_support: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in entity_quality_report:
        by_type[str(row.get("entity_type") or "entity")].append(row)
    for entity_type, rows in sorted(by_type.items()):
        filtered = [row for row in rows if row.get("status") == "filtered"]
        if len(filtered) < min_support:
            continue
        reasons = Counter(reason for row in filtered for reason in row.get("reasons", []))
        candidates.append(
            {
                "candidate_id": f"entity_boundary__{slugify(entity_type)}",
                "schema_family": "entity_schema",
                "schema_name": entity_type,
                "revision_type": "tighten_boundary",
                "support": len(filtered),
                "negative_examples": [str(row.get("canonical_name") or "") for row in filtered[:5] if row.get("canonical_name")],
                "confidence": round(min(0.9, 0.45 + 0.08 * len(filtered)), 3),
                "reason": f"Filtered entity mentions suggest boundary issues: {dict(reasons)}",
            }
        )
    return candidates


def adapt_evidence_schema(
    evidence_schema: dict[str, dict[str, Any]],
    edge_evidence_audit: list[dict[str, Any]],
    min_support: int,
) -> list[dict[str, Any]]:
    return [_apply_evidence_schema_revision(evidence_schema, candidate) for candidate in propose_evidence_schema_revisions(evidence_schema, edge_evidence_audit, min_support)]


def propose_evidence_schema_revisions(
    evidence_schema: dict[str, dict[str, Any]],
    edge_evidence_audit: list[dict[str, Any]],
    min_support: int,
) -> list[dict[str, Any]]:
    missing = Counter()
    unverified = Counter()
    for row in edge_evidence_audit:
        for field in row.get("missing_quote_fields") or []:
            missing[str(field)] += 1
        for check in row.get("quote_checks") or []:
            if not check.get("verified"):
                unverified[str(check.get("field") or "")] += 1
    candidates: list[dict[str, Any]] = []
    for slot, count in sorted((missing + unverified).items()):
        if not slot or count < min_support or slot not in evidence_schema:
            continue
        candidates.append(
            {
                "candidate_id": f"evidence_review__{slugify(slot)}",
                "schema_family": "evidence_schema",
                "schema_name": slot,
                "revision_type": "mark_needs_review",
                "support": count,
                "confidence": round(min(0.9, 0.45 + 0.06 * count), 3),
                "reason": "Evidence slot repeatedly missing or failed quote validation.",
            }
        )
    return candidates


def _apply_entity_schema_revision(entity_schema: dict[str, dict[str, Any]], candidate: dict[str, Any]) -> dict[str, Any]:
    entity_type = str(candidate.get("schema_name") or "")
    if not entity_type:
        return {**candidate, "status": "rejected", "decision": "rejected", "reason": "missing_entity_type"}
    spec = entity_schema.setdefault(entity_type, _minimal_entity_schema(entity_type))
    if candidate.get("revision_type") != "tighten_boundary":
        return {**candidate, "status": "rejected", "decision": "rejected", "reason": "unsupported_revision_type"}
    negative_examples = set(spec.get("negative_examples") or [])
    negative_examples.update(str(item) for item in candidate.get("negative_examples") or [] if str(item).strip())
    spec["negative_examples"] = sorted(negative_examples)
    spec["schema_source"] = "adaptive"
    return {**candidate, "status": "applied", "decision": "promoted"}


def _apply_evidence_schema_revision(evidence_schema: dict[str, dict[str, Any]], candidate: dict[str, Any]) -> dict[str, Any]:
    slot = str(candidate.get("schema_name") or "")
    if not slot or slot not in evidence_schema:
        return {**candidate, "status": "rejected", "decision": "rejected", "reason": "missing_evidence_slot"}
    if candidate.get("revision_type") != "mark_needs_review":
        return {**candidate, "status": "rejected", "decision": "rejected", "reason": "unsupported_revision_type"}
    evidence_schema[slot]["needs_review"] = True
    evidence_schema[slot]["schema_source"] = "adaptive"
    return {**candidate, "status": "applied", "decision": "promoted"}


def _load_seed(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    value = read_json_or_jsonl(path)
    return value if isinstance(value, dict) else {}


def _sample_documents(docs: list[Document], limit: int) -> list[dict[str, Any]]:
    rows = []
    for doc in docs[: max(0, limit)]:
        rows.append(
            {
                "doc_id": doc.doc_id,
                "title": doc.title,
                "chronology_slice": doc.chronology_slice,
                "source_type": doc.source_type,
                "text": doc.text[:1200],
            }
        )
    return rows


def _schema_rows(schema: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"edge_type": key, **value} for key, value in schema.items()]


def _report_rows(schema_family: str, mode: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**row, "schema_family": schema_family, "mode": mode} for row in rows]


def _revision_rows(schema_family: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**row, "schema_family": schema_family, "revision_type": row.get("status", "updated")} for row in rows]


def _entity_dimensions(config: EvoTaxaConfig, nodes: list[TaxonomyNode]) -> dict[str, list[str]]:
    configured = list(config.graph.entity_dimensions)
    if configured:
        return {entity_type: configured for entity_type in config.graph.entity_types}
    dims = sorted({node.dimension for node in nodes if node.dimension})
    return {entity_type: dims for entity_type in config.graph.entity_types}


def _default_entity_definition(entity_type: str) -> str:
    return f"Domain entity of type {entity_type.replace('_', ' ')} relevant to evolution modeling."


def _minimal_entity_schema(entity_type: str) -> dict[str, Any]:
    return {
        "entity_type": entity_type,
        "definition": _default_entity_definition(entity_type),
        "inclusion_criteria": "",
        "exclusion_criteria": "",
        "aliases": [],
        "allowed_dimensions": [],
        "example_mentions": [],
        "negative_examples": [],
        "quality_rules": ["quote_required"],
        "schema_source": "fixed",
    }


def _looks_social(domain_id: str, entity_types: list[str]) -> bool:
    value = " ".join([domain_id, *entity_types]).lower()
    return any(term in value for term in ["policy", "intervention", "governance", "social", "public_frame"])


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
