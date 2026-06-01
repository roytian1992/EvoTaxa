#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from evotaxa import toml_compat  # noqa: E402
from evotaxa.config import load_config  # noqa: E402
from evotaxa.io import iter_jsonl, slugify, write_json  # noqa: E402


ENTITY_TYPES = [
    "method",
    "data_source",
    "measurement_strategy",
    "modeling_strategy",
    "evaluation_protocol",
    "infrastructure_tooling",
    "governance_practice",
]


PRACTICE_DEFINITIONS = {
    "Data Source / Evidence Base": "Evidence bases and observed data sources used to support computational social-science claims, including platform traces, surveys, administrative records, web data, and curated datasets.",
    "Measurement / Annotation Strategy": "Ways of converting raw social data into measured constructs, labels, indicators, codes, or annotations.",
    "Modeling / Simulation Strategy": "Computational modeling choices, simulations, optimization procedures, statistical models, and generative representations of social processes.",
    "Evaluation / Validation Practice": "Validation, benchmarking, replication, robustness checks, gold standards, and other practices for assessing method quality.",
    "Computational Infrastructure / Tooling": "Software, algorithms, APIs, databases, parallel computing, information retrieval systems, and platforms that make computational social-science analysis possible.",
    "Access / Ethics / Governance": "Data access, privacy, consent, transparency, ethics, platform governance, and reproducibility practices that shape method use.",
}


METHOD_DEFINITIONS = {
    "Digital Trace Data": "Methods using platform logs, clickstreams, social media traces, mobility traces, call detail records, and other passively observed behavioral data.",
    "Text-as-Data / Computational Text Analysis": "Methods that transform text into computational social-science evidence, including NLP, text mining, topic models, content analysis, information retrieval, and frame or sentiment detection.",
    "Network Analysis": "Methods that model relational structure, graphs, communities, diffusion, interaction networks, and social network processes.",
    "Causal Inference & Experiments": "Designs and estimators for causal effects, including experiments, natural experiments, quasi-experiments, matching, and counterfactual methods.",
    "Agent-Based Modeling / Social Simulation": "Simulation methods representing agents, rules, interaction, formal models, artificial societies, and emergent social outcomes.",
    "LLM-Assisted Methods": "Methods using large language models or generative AI for annotation, coding, synthetic respondents, simulation, or research assistance.",
    "Reproducibility / Ethics / Governance": "Methods and practices for reproducibility, transparency, privacy, data access, ethics, and governance.",
    "Spatial / GIS / Geocomputation": "Spatial analysis, GIS, geocomputation, geographic information systems, mobility, and location-aware social-science methods.",
    "Survey / Administrative / Population Data Systems": "Survey, census, administrative, population, social accounts, and other large structured data systems used in social-science computation.",
    "Machine Learning / AI Classification": "Machine learning, artificial intelligence, supervised classification, data mining, predictive modeling, and pattern recognition for social-science evidence.",
    "Bibliometrics / Knowledge Mapping": "Citation analysis, co-citation, bibliometrics, scientometrics, knowledge graphs, and science mapping methods used to study research fields.",
    "Online Interaction / Social Media": "Methods for studying web, platform, social media, online community, forum, and digitally mediated interaction data.",
    "Computational Infrastructure / Algorithms": "Algorithms, optimization, parallel computation, databases, visualization, and computational infrastructure enabling large-scale social-science analysis.",
}


NODE_ALIAS_HINTS = {
    "Digital Trace Data": [
        "digital traces",
        "behavioral trace data",
        "call detail records",
        "mobility trace",
        "platform log",
        "clickstream",
    ],
    "Text-as-Data / Computational Text Analysis": [
        "information retrieval",
        "text mining",
        "automated content analysis",
        "computational content analysis",
        "frame analysis",
        "ALCESTE",
        "natural language processing",
    ],
    "Agent-Based Modeling / Social Simulation": [
        "computer simulation",
        "computer simulations",
        "formal model",
        "formal models",
        "artificial societies",
        "complex adaptive systems",
        "computational sociology",
    ],
    "Machine Learning / AI Classification": [
        "artificial intelligence",
        "AI",
        "data mining",
        "expert system",
        "neural network",
        "classification algorithm",
    ],
    "Online Interaction / Social Media": [
        "world wide web",
        "web data",
        "internet research",
        "online behavioral data",
        "web forum",
    ],
    "Causal Inference & Experiments": [
        "matching",
        "propensity score",
        "instrumental variables",
        "endogenous group effects",
        "exogenous group effects",
    ],
    "Survey / Administrative / Population Data Systems": [
        "input-output tables",
        "migration flows",
        "national accounts",
        "social accounts",
        "contingency tables",
        "survey data",
        "administrative records",
    ],
    "Bibliometrics / Knowledge Mapping": [
        "citation analysis",
        "co-citation",
        "co-mention analysis",
        "knowledge graph",
        "science mapping",
        "bibliographic coupling",
    ],
    "Computational Infrastructure / Algorithms": [
        "parallel computation",
        "parallel computing",
        "optimization",
        "algorithm",
        "database",
        "visualization",
        "e-social science",
        "collaboratory",
        "grid enabled",
    ],
    "Data Source / Evidence Base": [
        "digital trace data",
        "call detail records",
        "web data",
        "survey data",
        "administrative data",
        "census data",
        "platform data",
    ],
    "Measurement / Annotation Strategy": [
        "content analysis",
        "human annotation",
        "automated annotation",
        "machine coding",
        "psychometric methods",
        "construct measurement",
    ],
    "Modeling / Simulation Strategy": [
        "computational model",
        "formal model",
        "simulation model",
        "optimization",
        "matrix problem",
        "fuzzy MCDM",
        "artificial societies",
    ],
    "Evaluation / Validation Practice": [
        "validation",
        "benchmark",
        "gold standard",
        "replication",
        "reproducibility",
        "robustness check",
    ],
    "Computational Infrastructure / Tooling": [
        "parallel computation",
        "parallel computing",
        "grid enabled",
        "e-social science",
        "collaboratory",
        "API",
        "database",
        "information system",
        "programming language",
        "world wide web",
    ],
    "Access / Ethics / Governance": [
        "data access",
        "platform data access",
        "privacy",
        "consent",
        "research ethics",
        "data governance",
        "open science",
    ],
}


ENTITY_LABELS = {
    "method": "Computational method, named method family, algorithmic approach, or social-science method design.",
    "data_source": "Observed or curated data source used as evidence.",
    "measurement_strategy": "Coding, annotation, construct measurement, or transformation from raw material to social-science variable.",
    "modeling_strategy": "Model, simulation, optimization, or statistical/computational representation.",
    "evaluation_protocol": "Benchmarking, validation, replication, robustness, or quality-assessment protocol.",
    "infrastructure_tooling": "Software, API, database, platform, programming environment, or computational infrastructure.",
    "governance_practice": "Data access, ethics, privacy, transparency, reproducibility, or governance practice.",
}


RELATION_SCHEMA = {
    "extends": {
        "label": "Extends",
        "definition": "The target method or practice builds on, expands, or adds capability to the source.",
        "source_role": "prior method or practice",
        "target_role": "successor method or practice",
        "directionality": "directed",
        "temporal_constraint": "source_before_or_same_as_target",
        "evidence_slots": ["mechanism", "methodological_problem", "tradeoff"],
        "cues": ["extends", "builds on", "build upon", "expands", "adds", "incorporates", "generalizes"],
        "strong_edge": True,
    },
    "improves": {
        "label": "Improves",
        "definition": "The target improves accuracy, scale, robustness, validity, efficiency, or coverage over the source.",
        "source_role": "baseline or earlier method",
        "target_role": "improved method or practice",
        "directionality": "directed",
        "temporal_constraint": "source_before_or_same_as_target",
        "evidence_slots": ["mechanism", "validation_evidence", "tradeoff"],
        "cues": ["improves", "outperforms", "more accurate", "more robust", "increases", "reduces error", "enhances"],
        "strong_edge": True,
    },
    "adapts": {
        "label": "Adapts",
        "definition": "The target transfers or recontextualizes a source method, model, data practice, or infrastructure to a new domain, population, platform, or task.",
        "source_role": "source method or practice",
        "target_role": "adapted method or practice",
        "directionality": "directed",
        "temporal_constraint": "source_before_or_same_as_target",
        "evidence_slots": ["mechanism", "implementation_context", "tradeoff"],
        "cues": ["adapts", "applies", "transfers", "ports", "repurposes", "uses in", "applied to"],
        "strong_edge": True,
    },
    "replaces": {
        "label": "Replaces",
        "definition": "The target substitutes for, supersedes, or moves beyond the source method or practice.",
        "source_role": "displaced method or practice",
        "target_role": "replacement method or practice",
        "directionality": "directed",
        "temporal_constraint": "source_before_or_same_as_target",
        "evidence_slots": ["mechanism", "tradeoff"],
        "cues": ["replaces", "supersedes", "instead of", "moves beyond", "shifts from", "substitutes"],
        "strong_edge": True,
    },
    "operationalizes": {
        "label": "Operationalizes",
        "definition": "The target turns a construct, theory, source data, or qualitative material into measurable computational indicators or labels.",
        "source_role": "construct, theory, or raw material",
        "target_role": "measurement or annotation strategy",
        "directionality": "directed",
        "temporal_constraint": "none",
        "evidence_slots": ["measurement_design", "data_basis", "validation_evidence"],
        "cues": ["operationalizes", "measures", "codes", "annotates", "classifies", "detects", "extracts"],
        "strong_edge": True,
    },
    "enables": {
        "label": "Enables",
        "definition": "Infrastructure, data access, software, or tooling makes a downstream method or evidence practice feasible.",
        "source_role": "enabling infrastructure or data practice",
        "target_role": "enabled method or analysis",
        "directionality": "directed",
        "temporal_constraint": "none",
        "evidence_slots": ["infrastructure_context", "mechanism"],
        "cues": ["enables", "facilitates", "supports", "makes possible", "provides", "allows"],
        "strong_edge": True,
    },
    "validates": {
        "label": "Validates",
        "definition": "The target assesses, benchmarks, validates, replicates, or audits the source method or measurement.",
        "source_role": "method or measurement being assessed",
        "target_role": "validation or evaluation practice",
        "directionality": "directed",
        "temporal_constraint": "none",
        "evidence_slots": ["validation_evidence", "tradeoff"],
        "cues": ["validates", "evaluates", "benchmarks", "replicates", "audits", "tests", "compares"],
        "strong_edge": True,
    },
    "combines": {
        "label": "Combines",
        "definition": "The target combines two methods, data sources, models, or evidence practices into a hybrid approach.",
        "source_role": "component method or practice",
        "target_role": "hybrid method or practice",
        "directionality": "directed",
        "temporal_constraint": "none",
        "evidence_slots": ["mechanism", "data_basis"],
        "cues": ["combines", "integrates", "hybrid", "jointly", "fuses", "links"],
        "strong_edge": True,
    },
    "compares": {
        "label": "Compares",
        "definition": "The entities are compared, contrasted, or benchmarked without a confirmed successor relation.",
        "source_role": "comparison reference",
        "target_role": "compared method or practice",
        "directionality": "directed",
        "temporal_constraint": "none",
        "evidence_slots": ["validation_evidence", "tradeoff"],
        "cues": ["compares", "contrast", "relative to", "versus", "baseline"],
        "strong_edge": False,
    },
    "background": {
        "label": "Background",
        "definition": "The relation is weak context rather than a confirmed evolution edge.",
        "source_role": "background entity",
        "target_role": "background entity",
        "directionality": "undirected",
        "temporal_constraint": "none",
        "evidence_slots": ["mechanism"],
        "cues": ["related work", "prior work"],
        "strong_edge": False,
    },
}


EVIDENCE_SCHEMA = {
    "methodological_problem": {
        "definition": "Problem, limitation, social-science need, scaling pressure, validity concern, or unresolved task motivating a method change.",
        "required": False,
        "quote_required": True,
        "allowed_source": "either",
        "validation": "substring",
    },
    "mechanism": {
        "definition": "Mechanism, algorithmic design, modeling choice, measurement procedure, or infrastructure change linking source and target.",
        "required": True,
        "quote_required": True,
        "allowed_source": "either",
        "validation": "substring",
    },
    "data_basis": {
        "definition": "Data source, corpus, platform trace, administrative record, survey, web data, or linked evidence base supporting the method.",
        "required": False,
        "quote_required": True,
        "allowed_source": "either",
        "validation": "substring",
    },
    "measurement_design": {
        "definition": "Coding scheme, annotation design, construct operationalization, classifier label, or measurement strategy.",
        "required": False,
        "quote_required": True,
        "allowed_source": "either",
        "validation": "substring",
    },
    "validation_evidence": {
        "definition": "Benchmark, gold standard, replication, robustness check, accuracy estimate, or other validation evidence.",
        "required": False,
        "quote_required": True,
        "allowed_source": "either",
        "validation": "substring",
    },
    "infrastructure_context": {
        "definition": "Software, API, database, parallel computation, web platform, or other infrastructure enabling the method.",
        "required": False,
        "quote_required": True,
        "allowed_source": "either",
        "validation": "substring",
    },
    "implementation_context": {
        "definition": "Domain, population, platform, institution, geography, or task context where a method is applied.",
        "required": False,
        "quote_required": True,
        "allowed_source": "either",
        "validation": "substring",
    },
    "governance_constraint": {
        "definition": "Data access, privacy, ethics, consent, transparency, reproducibility, or governance constraint shaping method use.",
        "required": False,
        "quote_required": True,
        "allowed_source": "either",
        "validation": "substring",
    },
    "tradeoff": {
        "definition": "Cost, limitation, bias, validity caveat, coverage loss, interpretability issue, or other method tradeoff.",
        "required": False,
        "quote_required": True,
        "allowed_source": "either",
        "validation": "substring",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Turn schema probe artifacts into a proposed EvoTaxa taxonomy, schema seed, and config.")
    parser.add_argument("--base-config", type=Path, required=True, help="Existing EvoTaxa config to adapt.")
    parser.add_argument("--probe-root", type=Path, required=True, help="Directory produced by probe_schema_design.py.")
    parser.add_argument("--output-root", type=Path, required=True, help="Directory for proposal artifacts.")
    parser.add_argument("--run-id-suffix", default="schema_probe_proposed")
    args = parser.parse_args()

    base_config = load_config(args.base_config)
    raw_config = load_raw_config(args.base_config)
    probe_root = args.probe_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    reports = load_variant_reports(probe_root / "node_coverage_report.json")
    variants = load_variants(probe_root / "schema_variants.json")
    candidates = list(iter_jsonl(probe_root / "node_candidates.jsonl"))
    strategy = choose_strategy(reports)
    taxonomy_nodes = build_taxonomy_nodes(variants, candidates, strategy=strategy)
    schema_seed = build_schema_seed(taxonomy_nodes)
    proposed_config = build_proposed_config(
        raw_config,
        base_config_path=args.base_config,
        base_corpus_path=base_config.corpus.path,
        taxonomy_path=output_root / "taxonomy.proposed.json",
        schema_seed_path=output_root / "schema_seed.proposed.json",
        output_root=output_root,
        run_id_suffix=args.run_id_suffix,
        taxonomy_nodes=taxonomy_nodes,
    )
    summary = {
        "base_config": str(args.base_config),
        "probe_root": str(probe_root),
        "proposal_root": str(output_root),
        "strategy": strategy,
        "variant_scores": {
            report["variant_id"]: {
                "probe_score": report.get("probe_score"),
                "coverage": report.get("coverage"),
                "mean_nodes_per_document": report.get("mean_nodes_per_document"),
                "overloaded_documents": report.get("overloaded_documents"),
            }
            for report in reports
        },
        "taxonomy_node_count": len(taxonomy_nodes),
        "taxonomy_dimensions": sorted({node["dimension"] for node in taxonomy_nodes}),
        "entity_types": ENTITY_TYPES,
        "relation_types": list(RELATION_SCHEMA),
        "evidence_slots": list(EVIDENCE_SCHEMA),
        "outputs": {
            "taxonomy": str(output_root / "taxonomy.proposed.json"),
            "schema_seed": str(output_root / "schema_seed.proposed.json"),
            "config": str(output_root / "config.proposed.json"),
            "report": str(output_root / "schema_proposal_report.md"),
        },
    }

    write_json(output_root / "taxonomy.proposed.json", taxonomy_nodes)
    write_json(output_root / "schema_seed.proposed.json", schema_seed)
    write_json(output_root / "config.proposed.json", proposed_config)
    write_json(output_root / "proposal_summary.json", summary)
    write_report(output_root / "schema_proposal_report.md", summary, taxonomy_nodes)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def load_raw_config(path: Path) -> dict[str, Any]:
    config_path = path.expanduser().resolve()
    with config_path.open("rb") as handle:
        if config_path.suffix.lower() == ".json":
            return json.loads(handle.read().decode("utf-8"))
        return toml_compat.load(handle)


def load_variant_reports(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    rows = value.get("variants") if isinstance(value, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"Missing variants in {path}")
    return [row for row in rows if isinstance(row, dict)]


def load_variants(path: Path) -> dict[str, dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Invalid schema variants file: {path}")
    return {str(key): value for key, value in value.items() if isinstance(value, dict)}


def choose_strategy(reports: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {str(row.get("variant_id")): row for row in reports}
    ranked = sorted(reports, key=lambda row: -float(row.get("probe_score") or 0.0))
    best = ranked[0]
    hybrid = by_id.get("hybrid_two_axis", {})
    evidence = by_id.get("evidence_practice", {})
    method = by_id.get("method_ecology", {})
    hybrid_score = float(hybrid.get("probe_score") or 0.0)
    evidence_score = float(evidence.get("probe_score") or 0.0)
    method_score = float(method.get("probe_score") or 0.0)
    if hybrid_score >= evidence_score - 0.03 and evidence_score >= 0.75 and method_score >= 0.6:
        strategy_id = "practice_primary_method_secondary"
        primary = "evidence_practice"
        secondary = ["method_ecology"]
        rationale = "Hybrid and evidence-practice variants are close, so use evidence practice as the stable primary axis and preserve method ecology as a second axis."
    elif evidence_score >= method_score:
        strategy_id = "evidence_practice_only"
        primary = "evidence_practice"
        secondary = []
        rationale = "Evidence-practice variant outperformed method ecology and does not need a second method-family axis."
    else:
        strategy_id = "method_ecology_only"
        primary = "method_ecology"
        secondary = []
        rationale = "Method ecology variant is the strongest non-corpus schema."
    return {
        "strategy_id": strategy_id,
        "best_variant_id": best.get("variant_id"),
        "primary_variant_id": primary,
        "secondary_variant_ids": secondary,
        "rationale": rationale,
    }


def build_taxonomy_nodes(
    variants: dict[str, dict[str, Any]],
    candidates: list[dict[str, Any]],
    *,
    strategy: dict[str, Any],
) -> list[dict[str, Any]]:
    corpus_terms = [row for row in candidates if row.get("variant_id") == "corpus_terms"]
    rows: list[dict[str, Any]] = []
    for variant_id in [strategy["primary_variant_id"], *strategy.get("secondary_variant_ids", [])]:
        for node in (variants.get(variant_id) or {}).get("nodes") or []:
            if not isinstance(node, dict):
                continue
            rows.append(proposal_node(node, variant_id=variant_id, corpus_terms=corpus_terms))
    return rows


def proposal_node(node: dict[str, Any], *, variant_id: str, corpus_terms: list[dict[str, Any]]) -> dict[str, Any]:
    label = str(node.get("canonical_label") or "")
    if variant_id == "method_ecology":
        dimension = "method_family"
        prefix = "method_family"
        definition = METHOD_DEFINITIONS.get(label) or str(node.get("definition") or "")
        schema_role = "secondary_method_family_axis"
    else:
        dimension = "evidence_practice"
        prefix = "evidence_practice"
        definition = PRACTICE_DEFINITIONS.get(label) or str(node.get("definition") or "")
        schema_role = "primary_evidence_practice_axis"
    suffix = str(node.get("node_id") or label).split("__")[-1]
    aliases = dedupe([label, *list(node.get("aliases") or []), *NODE_ALIAS_HINTS.get(label, []), *mapped_corpus_terms(label, corpus_terms)])
    inclusion = inclusion_criteria(label, dimension)
    exclusion = exclusion_criteria(label, dimension)
    boundary = boundary_notes(label, dimension)
    return {
        "node_id": f"{prefix}__{slugify(suffix)}",
        "dimension": dimension,
        "canonical_label": label,
        "definition": definition,
        "inclusion_criteria": inclusion,
        "exclusion_criteria": exclusion,
        "aliases": aliases,
        "negative_examples": negative_examples(label, dimension),
        "schema_role": schema_role,
        "entity_scope": entity_scope(label, dimension),
        "relation_affordances": relation_affordances(label, dimension),
        "boundary_notes": boundary,
        "node_card": {
            "card_type": "taxonomy_node_card",
            "title": label,
            "dimension": dimension,
            "definition": definition,
            "inclusion_criteria": inclusion,
            "exclusion_criteria": exclusion,
            "aliases": aliases,
            "negative_examples": negative_examples(label, dimension),
            "entity_scope": entity_scope(label, dimension),
            "relation_affordances": relation_affordances(label, dimension),
            "boundary_notes": boundary,
            "provenance": {
                "probe_variant": variant_id,
                "source": "schema_probe_proposal",
                "corpus_terms_used_as_aliases": mapped_corpus_terms(label, corpus_terms),
            },
        },
        "probe_source": variant_id,
    }


def inclusion_criteria(label: str, dimension: str) -> list[str]:
    if dimension == "evidence_practice":
        return [
            f"Include papers where {label} is a central evidence-production practice, not merely a background phrase.",
            "Require title or abstract evidence that the practice shapes data, measurement, modeling, evaluation, tooling, access, or governance.",
            "Allow applied papers when the practice is explicit enough to support method-evolution analysis.",
        ]
    return [
        f"Include papers where {label} is the main method family, computational design, or analytic tradition.",
        "Require explicit method-family language, named methods, or clear computational procedure evidence.",
        "Allow historical terminology and aliases when they refer to the same method family.",
    ]


def exclusion_criteria(label: str, dimension: str) -> list[str]:
    return [
        "Exclude generic academic wording, discourse connectives, section labels, and isolated common nouns.",
        "Exclude papers where matching words appear only in references, boilerplate, or broad disciplinary background.",
        "Do not use this node as an entity name; entities must be specific methods, data sources, measures, models, protocols, tools, or governance practices observed in document text.",
    ]


def negative_examples(label: str, dimension: str) -> list[str]:
    examples = ["science", "thus", "to this end", "free", "second", "paper", "study", "method", "model", "analysis"]
    if dimension == "evidence_practice":
        examples.extend(["data", "research", "results"])
    return examples


def entity_scope(label: str, dimension: str) -> list[str]:
    mapping = {
        "Data Source / Evidence Base": ["data_source"],
        "Measurement / Annotation Strategy": ["measurement_strategy"],
        "Modeling / Simulation Strategy": ["modeling_strategy"],
        "Evaluation / Validation Practice": ["evaluation_protocol"],
        "Computational Infrastructure / Tooling": ["infrastructure_tooling"],
        "Access / Ethics / Governance": ["governance_practice"],
        "Digital Trace Data": ["data_source", "method"],
        "Survey / Administrative / Population Data Systems": ["data_source"],
        "Computational Infrastructure / Algorithms": ["infrastructure_tooling", "method"],
        "Reproducibility / Ethics / Governance": ["governance_practice", "evaluation_protocol"],
    }
    return mapping.get(label, ["method"] if dimension == "method_family" else ["method"])


def relation_affordances(label: str, dimension: str) -> list[str]:
    if label in {"Data Source / Evidence Base", "Computational Infrastructure / Tooling", "Computational Infrastructure / Algorithms"}:
        return ["enables", "adapts", "combines"]
    if label in {"Measurement / Annotation Strategy", "Text-as-Data / Computational Text Analysis"}:
        return ["operationalizes", "validates", "improves", "combines"]
    if label in {"Evaluation / Validation Practice", "Reproducibility / Ethics / Governance"}:
        return ["validates", "improves", "replaces"]
    return ["extends", "improves", "adapts", "replaces", "combines"]


def boundary_notes(label: str, dimension: str) -> list[str]:
    notes = [
        "This card defines a taxonomy node, not a graph entity.",
        "Graph entities are extracted separately from document text and must pass entity-quality checks.",
    ]
    if label == "Access / Ethics / Governance":
        notes.append("Keep governance practices separate from generic policy or institutional background unless data access, ethics, or reproducibility directly shapes method use.")
    if label == "Machine Learning / AI Classification":
        notes.append("Artificial intelligence and machine learning are broad aliases; prefer specific extracted entities when available.")
    return notes


def mapped_corpus_terms(label: str, corpus_terms: list[dict[str, Any]]) -> list[str]:
    available = {str(row.get("canonical_label") or "").lower(): str(row.get("canonical_label") or "") for row in corpus_terms}
    mapping = {
        "Text-as-Data / Computational Text Analysis": ["natural language processing", "information retrieval"],
        "Machine Learning / AI Classification": ["artificial intelligence", "machine learning", "data mining"],
        "Online Interaction / Social Media": ["social media", "world wide web", "social network"],
        "Agent-Based Modeling / Social Simulation": ["computational model", "computational sociology"],
        "Computational Infrastructure / Tooling": ["programming language", "world wide web", "information retrieval"],
        "Computational Infrastructure / Algorithms": ["programming language", "world wide web", "information retrieval"],
        "Bibliometrics / Knowledge Mapping": ["information retrieval"],
        "Modeling / Simulation Strategy": ["computational model", "computational sociology"],
        "Data Source / Evidence Base": ["social media", "world wide web", "social network"],
    }
    terms = []
    for key in mapping.get(label, []):
        if key in available:
            terms.append(available[key])
            terms.append(key)
    return terms


def build_schema_seed(taxonomy_nodes: list[dict[str, Any]]) -> dict[str, Any]:
    entity_schema = {}
    pattern_map = entity_patterns(taxonomy_nodes)
    for entity_type in ENTITY_TYPES:
        entity_schema[entity_type] = {
            "entity_type": entity_type,
            "definition": ENTITY_LABELS[entity_type],
            "inclusion_criteria": f"Include quoted mentions of {entity_type.replace('_', ' ')} that are specific enough to support an evolution relation.",
            "exclusion_criteria": "Exclude generic paper structure, purely disciplinary labels, isolated topic names, and unsupported buzzwords.",
            "aliases": [],
            "allowed_dimensions": ["evidence_practice", "method_family"],
            "example_mentions": pattern_map.get(entity_type, [])[:16],
            "negative_examples": ["method", "model", "analysis", "study", "paper", "approach", "data", "result"],
            "quality_rules": ["quote_required", "canonical_name_required", "reject_generic_phrases", "prefer_method_or_practice_specificity"],
        }
    return {
        "entity_schema": entity_schema,
        "relation_schema": RELATION_SCHEMA,
        "evidence_schema": EVIDENCE_SCHEMA,
    }


def entity_patterns(taxonomy_nodes: list[dict[str, Any]]) -> dict[str, list[str]]:
    by_label = {row["canonical_label"]: list(row.get("aliases") or []) for row in taxonomy_nodes}
    return {
        "method": dedupe(
            by_label.get("Text-as-Data / Computational Text Analysis", [])
            + by_label.get("Network Analysis", [])
            + by_label.get("Causal Inference & Experiments", [])
            + by_label.get("Agent-Based Modeling / Social Simulation", [])
            + by_label.get("LLM-Assisted Methods", [])
            + by_label.get("Machine Learning / AI Classification", [])
            + by_label.get("Computational Infrastructure / Algorithms", [])
            + by_label.get("Bibliometrics / Knowledge Mapping", [])
        ),
        "data_source": dedupe(
            by_label.get("Data Source / Evidence Base", [])
            + by_label.get("Online Interaction / Social Media", [])
            + by_label.get("Digital Trace Data", [])
            + by_label.get("Survey / Administrative / Population Data Systems", [])
        ),
        "measurement_strategy": dedupe(by_label.get("Measurement / Annotation Strategy", []) + by_label.get("Text-as-Data / Computational Text Analysis", [])),
        "modeling_strategy": dedupe(by_label.get("Modeling / Simulation Strategy", []) + by_label.get("Agent-Based Modeling / Social Simulation", [])),
        "evaluation_protocol": dedupe(by_label.get("Evaluation / Validation Practice", [])),
        "infrastructure_tooling": dedupe(
            by_label.get("Computational Infrastructure / Tooling", [])
            + by_label.get("Computational Infrastructure / Algorithms", [])
            + by_label.get("Bibliometrics / Knowledge Mapping", [])
        ),
        "governance_practice": dedupe(by_label.get("Access / Ethics / Governance", []) + by_label.get("Reproducibility / Ethics / Governance", [])),
    }


def build_proposed_config(
    raw_config: dict[str, Any],
    *,
    base_config_path: Path,
    base_corpus_path: Path | None,
    taxonomy_path: Path,
    schema_seed_path: Path,
    output_root: Path,
    run_id_suffix: str,
    taxonomy_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    proposed = deepcopy(raw_config)
    project = proposed.setdefault("project", {})
    base_run_id = str(project.get("run_id") or base_config_path.stem)
    project["run_id"] = f"{base_run_id}_{slugify(run_id_suffix)}"

    corpus = proposed.setdefault("corpus", {})
    if base_corpus_path is not None:
        corpus["path"] = str(base_corpus_path)

    taxonomy = proposed.setdefault("taxonomy", {})
    taxonomy["nodes_path"] = taxonomy_path.name
    taxonomy["dimensions"] = {
        "evidence_practice": {
            "display_name": "Evidence Production Practice",
            "definition": "Primary schema axis for how computational social-science evidence is produced, measured, modeled, evaluated, tooled, and governed.",
        },
        "method_family": {
            "display_name": "Method Family",
            "definition": "Secondary schema axis for broad computational method families used in social-science research.",
        },
    }
    taxonomy["expansion_enabled"] = False
    taxonomy["coevolution_enabled"] = False

    schema = proposed.setdefault("schema", {})
    schema["schema_seed_path"] = schema_seed_path.name
    schema["entity_schema_mode"] = "fixed"
    schema["relation_schema_mode"] = "fixed"
    schema["evidence_schema_mode"] = "fixed"
    schema["max_schema_revisions"] = max(5, int(schema.get("max_schema_revisions") or 0))

    graph = proposed.setdefault("graph", {})
    graph["entity_dimensions"] = ["evidence_practice", "method_family"]
    graph["entity_types"] = ENTITY_TYPES
    graph["strong_edge_types"] = ["extends", "improves", "replaces", "adapts", "operationalizes", "enables", "validates", "combines"]
    graph["max_relation_types"] = max(12, int(graph.get("max_relation_types") or 0))
    graph["entity_patterns"] = entity_patterns(taxonomy_nodes)
    graph["entity_aliases"] = entity_aliases(taxonomy_nodes)
    graph["edge_cues"] = {edge_type: spec["cues"] for edge_type, spec in RELATION_SCHEMA.items()}
    graph["method_cue_terms"] = dedupe(
        list(graph.get("method_cue_terms") or [])
        + [
            "annotation",
            "benchmark",
            "classification",
            "coding",
            "data access",
            "evaluation",
            "infrastructure",
            "measurement",
            "modeling",
            "simulation",
            "validation",
        ]
    )

    output = proposed.setdefault("output", {})
    output["root"] = str((output_root / "main_run_output").resolve())
    return proposed


def entity_aliases(taxonomy_nodes: list[dict[str, Any]]) -> dict[str, list[str]]:
    aliases = {}
    for node in taxonomy_nodes:
        values = [item for item in node.get("aliases") or [] if str(item).lower() != str(node.get("canonical_label") or "").lower()]
        if values:
            aliases[str(node["canonical_label"]).lower()] = dedupe(values)
    return aliases


def dedupe(values: list[Any]) -> list[str]:
    seen = set()
    rows = []
    for value in values:
        text = " ".join(str(value or "").split())
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(text)
    return rows


def write_report(path: Path, summary: dict[str, Any], taxonomy_nodes: list[dict[str, Any]]) -> None:
    lines = [
        "# Schema Probe Proposal",
        "",
        f"- Strategy: `{summary['strategy']['strategy_id']}`",
        f"- Rationale: {summary['strategy']['rationale']}",
        f"- Base config: `{summary['base_config']}`",
        f"- Probe root: `{summary['probe_root']}`",
        f"- Proposed config: `{summary['outputs']['config']}`",
        "",
        "## Variant Evidence",
        "",
    ]
    for variant_id, metrics in summary["variant_scores"].items():
        lines.append(
            f"- `{variant_id}`: score {metrics.get('probe_score')}, coverage {metrics.get('coverage')}, "
            f"mean nodes/doc {metrics.get('mean_nodes_per_document')}, overloaded {metrics.get('overloaded_documents')}"
        )
    lines.extend(["", "## Proposed Taxonomy", ""])
    for dimension in sorted({row["dimension"] for row in taxonomy_nodes}):
        lines.extend([f"### {dimension}", ""])
        for node in [row for row in taxonomy_nodes if row["dimension"] == dimension]:
            lines.append(f"- `{node['node_id']}`: {node['canonical_label']}")
        lines.append("")
    lines.extend(
        [
            "## Main-Flow Use",
            "",
            "Validate the proposal before running the full pipeline:",
            "",
            "```bash",
            f"PYTHONPATH=src python -m evotaxa.cli validate-config --config {summary['outputs']['config']}",
            "```",
            "",
            "If validation passes, run it as a candidate main-flow configuration:",
            "",
            "```bash",
            f"PYTHONPATH=src python -m evotaxa.cli run-full --config {summary['outputs']['config']} --print-manifest",
            "```",
            "",
            "This proposal does not overwrite the existing project config or taxonomy.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
