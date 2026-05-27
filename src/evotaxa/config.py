from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evotaxa.io import as_str_list, parse_date
from evotaxa.models import DimensionSpec


DEFAULT_EDGE_CUES: dict[str, list[str]] = {
    "extends": ["extend", "build on", "build upon", "augment", "add", "incorporate"],
    "improves": ["improve", "outperform", "better", "enhance", "reduce error", "increase"],
    "replaces": ["replace", "instead of", "substitute", "supersede"],
    "adapts": ["adapt", "transfer", "port", "apply to", "generalize to"],
    "uses_component": ["use", "based on", "component", "module", "integrate"],
    "compares": ["compare", "baseline", "versus", "vs.", "benchmark against"],
    "background": ["related work", "prior work"],
}


@dataclass
class CorpusConfig:
    path: Path | None
    id_fields: list[str] = field(default_factory=lambda: ["doc_id", "paper_id", "id"])
    title_fields: list[str] = field(default_factory=lambda: ["title", "name"])
    text_fields: list[str] = field(default_factory=lambda: ["abstract", "body_text", "full_text", "text"])
    date_fields: list[str] = field(default_factory=lambda: ["published_at", "published", "date", "year"])
    slice_fields: list[str] = field(default_factory=lambda: ["chronology_slice", "time_slice", "slice", "year"])
    role_fields: list[str] = field(default_factory=lambda: ["role", "benchmark_role", "screen_decision"])
    accepted_roles: list[str] = field(default_factory=list)
    cutoff_date: str = ""
    missing_date_policy: str = "keep"
    source_type: str = "document"


@dataclass
class TaxonomyConfig:
    nodes_path: Path | None
    assignments_path: Path | None = None
    previous_nodes_path: Path | None = None
    dimensions: list[DimensionSpec] = field(default_factory=list)
    node_id_fields: list[str] = field(default_factory=lambda: ["node_id", "id"])
    node_label_fields: list[str] = field(default_factory=lambda: ["canonical_label", "label", "display_name", "name"])
    node_dimension_fields: list[str] = field(default_factory=lambda: ["dimension", "dimension_id"])
    node_parent_fields: list[str] = field(default_factory=lambda: ["parent_id", "parent_node_id"])
    node_definition_fields: list[str] = field(default_factory=lambda: ["definition", "description"])
    node_created_slice_fields: list[str] = field(default_factory=lambda: ["created_time_slice", "time_slice", "created_year"])
    node_alias_fields: list[str] = field(default_factory=lambda: ["aliases", "alias"])
    assignment_doc_id_fields: list[str] = field(default_factory=lambda: ["doc_id", "paper_id", "id"])
    assignment_node_id_fields: list[str] = field(default_factory=lambda: ["node_ids", "taxonomy_nodes", "assigned_node_ids"])
    assignment_dimension_map_fields: list[str] = field(default_factory=lambda: ["dimension_assignments"])
    induction_enabled: bool = False
    expansion_enabled: bool = True
    max_induced_nodes_per_dimension: int = 8
    min_cluster_documents: int = 2
    expansion_threshold: float = 0.55
    expansion_acceptance_threshold: float = 0.6
    width_threshold: float = 0.65
    depth_threshold: float = 0.65
    max_expansion_candidates: int = 50
    max_applied_expansions: int = 20


@dataclass
class GraphConfig:
    entity_dimensions: list[str] = field(default_factory=list)
    entity_types: list[str] = field(default_factory=lambda: ["method", "mechanism", "intervention", "evaluation_protocol"])
    strong_edge_types: list[str] = field(default_factory=lambda: ["extends", "improves", "replaces", "adapts"])
    entity_patterns: dict[str, list[str]] = field(default_factory=dict)
    entity_aliases: dict[str, list[str]] = field(default_factory=dict)
    edge_cues: dict[str, list[str]] = field(default_factory=lambda: dict(DEFAULT_EDGE_CUES))
    method_cue_terms: list[str] = field(default_factory=lambda: [
        "agent",
        "architecture",
        "audit",
        "benchmark",
        "evaluation",
        "framework",
        "intervention",
        "mechanism",
        "method",
        "model",
        "policy",
        "protocol",
        "retrieval",
        "system",
        "training",
    ])
    min_entity_mentions: int = 1
    max_entities_per_document: int = 12
    max_edge_candidates_per_entity: int = 24
    llm_entity_extraction_limit: int = 12
    alias_similarity_threshold: float = 0.86
    min_entity_quality: float = 0.42
    entity_allowlist: list[str] = field(default_factory=list)
    entity_denylist: list[str] = field(default_factory=list)
    generic_entity_phrases: list[str] = field(default_factory=lambda: [
        "this",
        "that",
        "these",
        "those",
        "it",
        "we",
        "paper",
        "study",
        "approach",
        "method",
        "system",
        "framework",
        "problem",
        "challenge",
        "result",
        "section",
        "figure",
        "table",
    ])


@dataclass
class OutputConfig:
    root: Path = Path("data/evotaxa/run_lite")


@dataclass
class ProjectConfig:
    name: str = "evotaxa"
    domain_id: str = "default"
    run_id: str = "run_lite"


@dataclass
class LLMConfig:
    provider: str = "deterministic"
    model: str = ""
    api_key: str = ""
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str = ""
    enabled_tasks: list[str] = field(default_factory=list)
    cache_path: Path | None = None
    max_retries: int = 1
    timeout_seconds: int = 120
    temperature: float = 0.0


@dataclass
class EvoTaxaConfig:
    path: Path
    project: ProjectConfig
    corpus: CorpusConfig
    taxonomy: TaxonomyConfig
    graph: GraphConfig
    llm: LLMConfig
    output: OutputConfig


def _resolve_path(base: Path, value: Any) -> Path | None:
    if value in (None, ""):
        return None
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = base / path
    return path


def _list(data: dict[str, Any], key: str, default: list[str]) -> list[str]:
    if key not in data:
        return list(default)
    return as_str_list(data.get(key))


def _dimensions(raw: dict[str, Any]) -> list[DimensionSpec]:
    table = raw.get("dimensions") or {}
    dims: list[DimensionSpec] = []
    if isinstance(table, dict):
        for dim_id, spec in table.items():
            if isinstance(spec, dict):
                dims.append(
                    DimensionSpec(
                        dimension_id=str(dim_id),
                        display_name=str(spec.get("display_name") or dim_id),
                        definition=str(spec.get("definition") or ""),
                    )
                )
            else:
                dims.append(DimensionSpec(str(dim_id), str(dim_id), str(spec or "")))
    elif isinstance(table, list):
        for item in table:
            if isinstance(item, dict):
                dim_id = str(item.get("id") or item.get("dimension_id") or item.get("name"))
                dims.append(
                    DimensionSpec(
                        dimension_id=dim_id,
                        display_name=str(item.get("display_name") or dim_id),
                        definition=str(item.get("definition") or ""),
                    )
                )
    return dims


def _merge_edge_cues(raw: dict[str, Any]) -> dict[str, list[str]]:
    cues = {key: list(value) for key, value in DEFAULT_EDGE_CUES.items()}
    for edge_type, patterns in (raw.get("edge_cues") or {}).items():
        cues[str(edge_type)] = as_str_list(patterns)
    return cues


def load_config(path: str | Path) -> EvoTaxaConfig:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("rb") as handle:
        if config_path.suffix.lower() == ".json":
            raw = json.loads(handle.read().decode("utf-8"))
        else:
            raw = tomllib.load(handle)
    base = config_path.parent

    project_raw = raw.get("project") or {}
    corpus_raw = raw.get("corpus") or {}
    taxonomy_raw = raw.get("taxonomy") or {}
    graph_raw = raw.get("graph") or {}
    llm_raw = raw.get("llm") or {}
    output_raw = raw.get("output") or {}

    corpus = CorpusConfig(
        path=_resolve_path(base, corpus_raw.get("path")),
        id_fields=_list(corpus_raw, "id_fields", CorpusConfig(None).id_fields),
        title_fields=_list(corpus_raw, "title_fields", CorpusConfig(None).title_fields),
        text_fields=_list(corpus_raw, "text_fields", CorpusConfig(None).text_fields),
        date_fields=_list(corpus_raw, "date_fields", CorpusConfig(None).date_fields),
        slice_fields=_list(corpus_raw, "slice_fields", CorpusConfig(None).slice_fields),
        role_fields=_list(corpus_raw, "role_fields", CorpusConfig(None).role_fields),
        accepted_roles=_list(corpus_raw, "accepted_roles", []),
        cutoff_date=str(corpus_raw.get("cutoff_date") or ""),
        missing_date_policy=str(corpus_raw.get("missing_date_policy") or "keep"),
        source_type=str(corpus_raw.get("source_type") or "document"),
    )
    if corpus.cutoff_date and parse_date(corpus.cutoff_date) is None:
        raise ValueError(f"Invalid cutoff_date: {corpus.cutoff_date}")

    taxonomy = TaxonomyConfig(
        nodes_path=_resolve_path(base, taxonomy_raw.get("nodes_path")),
        assignments_path=_resolve_path(base, taxonomy_raw.get("assignments_path")),
        previous_nodes_path=_resolve_path(base, taxonomy_raw.get("previous_nodes_path")),
        dimensions=_dimensions(taxonomy_raw),
        node_id_fields=_list(taxonomy_raw, "node_id_fields", TaxonomyConfig(None).node_id_fields),
        node_label_fields=_list(taxonomy_raw, "node_label_fields", TaxonomyConfig(None).node_label_fields),
        node_dimension_fields=_list(taxonomy_raw, "node_dimension_fields", TaxonomyConfig(None).node_dimension_fields),
        node_parent_fields=_list(taxonomy_raw, "node_parent_fields", TaxonomyConfig(None).node_parent_fields),
        node_definition_fields=_list(taxonomy_raw, "node_definition_fields", TaxonomyConfig(None).node_definition_fields),
        node_created_slice_fields=_list(taxonomy_raw, "node_created_slice_fields", TaxonomyConfig(None).node_created_slice_fields),
        node_alias_fields=_list(taxonomy_raw, "node_alias_fields", TaxonomyConfig(None).node_alias_fields),
        assignment_doc_id_fields=_list(taxonomy_raw, "assignment_doc_id_fields", TaxonomyConfig(None).assignment_doc_id_fields),
        assignment_node_id_fields=_list(taxonomy_raw, "assignment_node_id_fields", TaxonomyConfig(None).assignment_node_id_fields),
        assignment_dimension_map_fields=_list(taxonomy_raw, "assignment_dimension_map_fields", TaxonomyConfig(None).assignment_dimension_map_fields),
        induction_enabled=bool(taxonomy_raw.get("induction_enabled") or False),
        expansion_enabled=bool(taxonomy_raw.get("expansion_enabled", True)),
        max_induced_nodes_per_dimension=int(taxonomy_raw.get("max_induced_nodes_per_dimension") or 8),
        min_cluster_documents=int(taxonomy_raw.get("min_cluster_documents") or 2),
        expansion_threshold=float(taxonomy_raw.get("expansion_threshold") or 0.55),
        expansion_acceptance_threshold=float(taxonomy_raw.get("expansion_acceptance_threshold") or 0.6),
        width_threshold=float(taxonomy_raw.get("width_threshold") or 0.65),
        depth_threshold=float(taxonomy_raw.get("depth_threshold") or 0.65),
        max_expansion_candidates=int(taxonomy_raw.get("max_expansion_candidates") or 50),
        max_applied_expansions=int(taxonomy_raw.get("max_applied_expansions") or 20),
    )

    graph = GraphConfig(
        entity_dimensions=_list(graph_raw, "entity_dimensions", []),
        entity_types=_list(graph_raw, "entity_types", GraphConfig().entity_types),
        strong_edge_types=_list(graph_raw, "strong_edge_types", GraphConfig().strong_edge_types),
        entity_patterns={
            str(key): as_str_list(value)
            for key, value in (graph_raw.get("entity_patterns") or {}).items()
        },
        entity_aliases={
            str(key): as_str_list(value)
            for key, value in (graph_raw.get("entity_aliases") or {}).items()
        },
        edge_cues=_merge_edge_cues(graph_raw),
        method_cue_terms=_list(graph_raw, "method_cue_terms", GraphConfig().method_cue_terms),
        min_entity_mentions=int(graph_raw.get("min_entity_mentions") or 1),
        max_entities_per_document=int(graph_raw.get("max_entities_per_document") or 12),
        max_edge_candidates_per_entity=int(graph_raw.get("max_edge_candidates_per_entity") or 24),
        llm_entity_extraction_limit=int(graph_raw.get("llm_entity_extraction_limit") or 12),
        alias_similarity_threshold=float(graph_raw.get("alias_similarity_threshold") or 0.86),
        min_entity_quality=float(graph_raw.get("min_entity_quality") or 0.42),
        entity_allowlist=_list(graph_raw, "entity_allowlist", []),
        entity_denylist=_list(graph_raw, "entity_denylist", []),
        generic_entity_phrases=_list(graph_raw, "generic_entity_phrases", GraphConfig().generic_entity_phrases),
    )

    return EvoTaxaConfig(
        path=config_path,
        project=ProjectConfig(
            name=str(project_raw.get("name") or "evotaxa"),
            domain_id=str(project_raw.get("domain_id") or "default"),
            run_id=str(project_raw.get("run_id") or "run_lite"),
        ),
        corpus=corpus,
        taxonomy=taxonomy,
        graph=graph,
        llm=LLMConfig(
            provider=str(llm_raw.get("provider") or ("openai_compat" if llm_raw.get("base_url") else "deterministic")),
            model=str(llm_raw.get("model") or llm_raw.get("model_name") or ""),
            api_key=str(llm_raw.get("api_key") or ""),
            api_key_env=str(llm_raw.get("api_key_env") or "OPENAI_API_KEY"),
            base_url=str(llm_raw.get("base_url") or ""),
            enabled_tasks=_list(llm_raw, "enabled_tasks", []),
            cache_path=_resolve_path(base, llm_raw.get("cache_path")),
            max_retries=int(llm_raw.get("max_retries") or 1),
            timeout_seconds=int(llm_raw.get("timeout_seconds") or 120),
            temperature=float(llm_raw.get("temperature") or 0.0),
        ),
        output=OutputConfig(root=_resolve_path(base, output_raw.get("root")) or Path("data/evotaxa/run_lite")),
    )
