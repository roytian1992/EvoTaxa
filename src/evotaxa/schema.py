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
from evotaxa.relation_schema import adapt_relation_schema, fixed_relation_schema, normalize_relation_schema


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
    )


def adapt_schema_after_graph(
    bundle: SchemaBundle,
    *,
    edge_evidence_audit: list[dict[str, Any]],
    entity_quality_report: list[dict[str, Any]],
    config: EvoTaxaConfig,
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
    )
    revisions: list[dict[str, Any]] = []

    if config.schema.relation_schema_mode == "adaptive":
        relation_schema, relation_report = adapt_relation_schema(adapted.relation_schema, edge_evidence_audit, config.graph)
        adapted["relation_schema"] = relation_schema
        revisions.extend(_revision_rows("relation_schema", relation_report))

    if config.schema.entity_schema_mode == "adaptive":
        entity_revisions = adapt_entity_schema(adapted.entity_schema, entity_quality_report, config.schema.schema_revision_min_support)
        revisions.extend(entity_revisions)

    if config.schema.evidence_schema_mode == "adaptive":
        evidence_revisions = adapt_evidence_schema(adapted.evidence_schema, edge_evidence_audit, config.schema.schema_revision_min_support)
        revisions.extend(evidence_revisions)

    if config.schema.max_schema_revisions > 0:
        revisions = revisions[: config.schema.max_schema_revisions]
    for row in revisions:
        row.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
        row.setdefault("decision", "promoted")
    adapted.reports.extend(revisions)
    return adapted, revisions


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
    revisions: list[dict[str, Any]] = []
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in entity_quality_report:
        by_type[str(row.get("entity_type") or "entity")].append(row)
    for entity_type, rows in sorted(by_type.items()):
        filtered = [row for row in rows if row.get("status") == "filtered"]
        if len(filtered) < min_support:
            continue
        reasons = Counter(reason for row in filtered for reason in row.get("reasons", []))
        spec = entity_schema.setdefault(entity_type, _minimal_entity_schema(entity_type))
        negative_examples = set(spec.get("negative_examples") or [])
        negative_examples.update(str(row.get("canonical_name") or "") for row in filtered[:5] if row.get("canonical_name"))
        spec["negative_examples"] = sorted(negative_examples)
        spec["schema_source"] = "adaptive"
        revisions.append(
            {
                "schema_family": "entity_schema",
                "schema_name": entity_type,
                "revision_type": "tighten_boundary",
                "support": len(filtered),
                "reason": f"Filtered entity mentions suggest boundary issues: {dict(reasons)}",
            }
        )
    return revisions


def adapt_evidence_schema(
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
    revisions: list[dict[str, Any]] = []
    for slot, count in sorted((missing + unverified).items()):
        if not slot or count < min_support or slot not in evidence_schema:
            continue
        evidence_schema[slot]["needs_review"] = True
        evidence_schema[slot]["schema_source"] = "adaptive"
        revisions.append(
            {
                "schema_family": "evidence_schema",
                "schema_name": slot,
                "revision_type": "mark_needs_review",
                "support": count,
                "reason": "Evidence slot repeatedly missing or failed quote validation.",
            }
        )
    return revisions


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
