#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from evotaxa.config import load_config  # noqa: E402
from evotaxa.io import slugify, write_json, write_jsonl  # noqa: E402
from evotaxa.loaders import infer_assignments_from_text, load_documents  # noqa: E402
from evotaxa.models import TaxonomyNode  # noqa: E402
from evotaxa.taxonomy import tokenize  # noqa: E402


@dataclass
class ProbeVariant:
    variant_id: str
    description: str
    nodes: list[TaxonomyNode]
    expected_nodes_per_document: float = 1.2


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe corpus-driven node/schema designs before EvoTaxa runs.")
    parser.add_argument("--config", type=Path, required=True, help="Base EvoTaxa config whose corpus should be probed.")
    parser.add_argument("--output-root", type=Path, required=True, help="Directory for probe artifacts.")
    parser.add_argument("--sample-size", type=int, default=240, help="Documents to sample for schema probing.")
    parser.add_argument("--seed", type=int, default=20260530)
    parser.add_argument("--variant", action="append", choices=["method_ecology", "evidence_practice", "hybrid_two_axis", "corpus_terms"])
    args = parser.parse_args()

    config = load_config(args.config)
    docs, corpus_manifest = load_documents(config)
    sampled = stratified_sample(docs, sample_size=args.sample_size, seed=args.seed)
    variants = build_variants(args.variant or ["method_ecology", "evidence_practice", "hybrid_two_axis", "corpus_terms"], sampled)

    output_root = args.output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    sample_records = [sample_record(doc) for doc in sampled]
    write_jsonl(output_root / "sampled_documents.jsonl", sample_records)

    all_node_candidates: list[dict[str, Any]] = []
    variant_reports: list[dict[str, Any]] = []
    boundary_cases: list[dict[str, Any]] = []
    token_profiles: list[dict[str, Any]] = []
    for variant in variants:
        assignments = assign_documents_for_variant(sampled, variant)
        report, cases = evaluate_variant(variant, sampled, assignments)
        variant_reports.append(report)
        boundary_cases.extend(cases)
        all_node_candidates.extend(node_candidate_rows(variant))
        token_profiles.extend(node_token_profiles(variant, sampled, assignments))

    summary = build_summary(
        config_path=args.config,
        corpus_manifest=corpus_manifest,
        sample_records=sample_records,
        variant_reports=variant_reports,
        output_root=output_root,
        seed=args.seed,
    )
    write_jsonl(output_root / "node_candidates.jsonl", all_node_candidates)
    write_json(output_root / "schema_variants.json", {variant.variant_id: variant_to_record(variant) for variant in variants})
    write_jsonl(output_root / "node_token_profiles.jsonl", token_profiles)
    write_jsonl(output_root / "boundary_cases.jsonl", boundary_cases)
    write_json(output_root / "node_coverage_report.json", {"variants": variant_reports, "summary": summary})
    write_json(output_root / "probe_summary.json", summary)
    write_recommendation(output_root / "schema_recommendation.md", summary, variant_reports)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def stratified_sample(docs: list[Any], *, sample_size: int, seed: int) -> list[Any]:
    if sample_size <= 0 or sample_size >= len(docs):
        return list(docs)
    rng = random.Random(seed)
    buckets: dict[str, list[Any]] = defaultdict(list)
    for doc in docs:
        year = doc.published_at.year if doc.published_at else 0
        decade = f"{year // 10 * 10}s" if year else "unknown"
        buckets[decade].append(doc)
    sample: list[Any] = []
    bucket_items = sorted(buckets.items())
    base = max(1, sample_size // max(1, len(bucket_items)))
    for _, rows in bucket_items:
        count = min(len(rows), base)
        sample.extend(rng.sample(rows, count))
    sampled_ids = {doc.doc_id for doc in sample}
    remaining = [doc for doc in docs if doc.doc_id not in sampled_ids]
    if len(sample) < sample_size and remaining:
        sample.extend(rng.sample(remaining, min(sample_size - len(sample), len(remaining))))
    return sorted(
        sample[:sample_size],
        key=lambda doc: (doc.published_at.isoformat() if doc.published_at else "", doc.doc_id),
    )


def build_variants(ids: list[str], sampled: list[Any]) -> list[ProbeVariant]:
    builders = {
        "method_ecology": method_ecology_variant,
        "evidence_practice": evidence_practice_variant,
        "hybrid_two_axis": hybrid_two_axis_variant,
    }
    variants = []
    for variant_id in ids:
        if variant_id == "corpus_terms":
            variants.append(corpus_terms_variant(sampled))
        else:
            variants.append(builders[variant_id]())
    return variants


def method_ecology_variant() -> ProbeVariant:
    specs = [
        ("digital_trace_data", "Digital Trace Data", ["digital trace data", "digital traces", "trace data", "behavioral trace data", "platform data", "clickstream", "online behavioral data", "mobility trace"]),
        ("text_as_data", "Text-as-Data / Computational Text Analysis", ["text as data", "computational text analysis", "text analysis", "content analysis", "natural language processing", "NLP", "topic modeling", "sentiment analysis", "stance detection"]),
        ("network_analysis", "Network Analysis", ["network analysis", "social network analysis", "graph analysis", "network science", "diffusion network"]),
        ("causal_experiments", "Causal Inference & Experiments", ["causal inference", "counterfactual", "field experiment", "survey experiment", "natural experiment", "treatment effect"]),
        ("agent_simulation", "Agent-Based Modeling / Social Simulation", ["agent-based modeling", "agent based model", "social simulation", "computational model", "generative social science", "artificial society"]),
        ("llm_methods", "LLM-Assisted Methods", ["large language model", "large language models", "LLM", "LLMs", "GPT", "generative AI", "synthetic respondents", "LLM annotation"]),
        ("governance_reproducibility", "Reproducibility / Ethics / Governance", ["reproducibility", "replication", "data access", "research ethics", "privacy", "data governance", "transparency", "open science"]),
        ("spatial_gis", "Spatial / GIS / Geocomputation", ["spatial analysis", "spatial data analysis", "GIS", "geographic information system", "geospatial analysis", "spatial econometrics"]),
        ("survey_admin_population_data", "Survey / Administrative / Population Data Systems", ["survey data", "social survey", "census data", "administrative data", "population data", "national accounts", "social accounts", "input-output tables", "migration flows", "contingency tables"]),
        ("ml_ai_classification", "Machine Learning / AI Classification", ["machine learning", "artificial intelligence", "supervised classification", "classification model", "predictive modeling", "deep learning", "data mining"]),
        ("bibliometrics_knowledge_mapping", "Bibliometrics / Knowledge Mapping", ["bibliometrics", "scientometrics", "citation analysis", "co-citation", "bibliographic coupling", "science mapping", "knowledge mapping", "knowledge graph", "research trends"]),
        ("online_social_media", "Online Interaction / Social Media", ["social media", "Twitter", "Facebook", "online community", "web forum", "social computing", "online interaction"]),
        ("computational_infrastructure_algorithms", "Computational Infrastructure / Algorithms", ["parallel computation", "parallel computing", "algorithm", "algorithms", "optimization", "computational method", "software system", "database", "information system", "collaboratory", "visualization", "large-scale computation"]),
    ]
    return ProbeVariant("method_ecology", "Method-family ecology nodes.", _nodes("method_ecology", specs), expected_nodes_per_document=1.0)


def evidence_practice_variant() -> ProbeVariant:
    specs = [
        ("data_source", "Data Source / Evidence Base", ["data source", "dataset", "social media data", "survey data", "census data", "administrative data", "digital trace data", "platform data"]),
        ("measurement", "Measurement / Annotation Strategy", ["measurement", "annotation", "coding", "classification", "stance detection", "sentiment analysis", "content analysis", "human annotation"]),
        ("modeling", "Modeling / Simulation Strategy", ["model", "modeling", "simulation", "agent-based", "network model", "language model", "embedding model", "predictive model"]),
        ("evaluation", "Evaluation / Validation Practice", ["evaluation", "validation", "benchmark", "gold standard", "replication", "reproducibility", "accuracy", "performance"]),
        ("infrastructure", "Computational Infrastructure / Tooling", ["software", "platform", "API", "database", "information system", "visualization", "parallel computing", "algorithm"]),
        ("governance", "Access / Ethics / Governance", ["data access", "ethics", "privacy", "governance", "transparency", "consent", "platform data access"]),
    ]
    return ProbeVariant("evidence_practice", "Evidence-production practice nodes.", _nodes("evidence_practice", specs), expected_nodes_per_document=1.2)


def hybrid_two_axis_variant() -> ProbeVariant:
    method = method_ecology_variant().nodes
    evidence = evidence_practice_variant().nodes
    nodes = []
    for node in [*method, *evidence]:
        nodes.append(
            TaxonomyNode(
                node_id=node.node_id.replace("method_ecology__", "hybrid_method__").replace("evidence_practice__", "hybrid_practice__"),
                dimension="hybrid_schema",
                canonical_label=node.canonical_label,
                definition=node.definition,
                aliases=node.aliases,
            )
        )
    return ProbeVariant("hybrid_two_axis", "Method ecology plus evidence-practice nodes.", nodes, expected_nodes_per_document=2.0)


def corpus_terms_variant(docs: list[Any], *, max_nodes: int = 14) -> ProbeVariant:
    phrase_docs: dict[str, set[str]] = defaultdict(set)
    phrase_sources: dict[str, Counter[str]] = defaultdict(Counter)
    for doc in docs:
        for phrase, source in corpus_candidate_phrases(doc):
            phrase_docs[phrase].add(doc.doc_id)
            phrase_sources[phrase][source] += 1

    doc_count = len(docs)
    min_docs = max(1, min(8, doc_count // 35 if doc_count >= 35 else 1))
    max_docs = max(2, int(doc_count * 0.62))
    candidates = []
    for phrase, doc_ids in phrase_docs.items():
        support = len(doc_ids)
        if support < min_docs or support > max_docs:
            continue
        sources = phrase_sources[phrase]
        source_bonus = 1.0
        if sources.get("keyword") or sources.get("concept"):
            source_bonus += 0.35
        if sources.get("title_phrase"):
            source_bonus += 0.25
        if sources.get("abstract_phrase"):
            source_bonus += 0.1
        score = support * source_bonus + min(4, len(phrase.split())) * 0.2
        candidates.append(
            {
                "phrase": phrase,
                "support": support,
                "score": score,
                "sources": dict(sources),
                "doc_ids": sorted(doc_ids),
            }
        )
    candidates.sort(key=lambda row: (-float(row["score"]), -int(row["support"]), str(row["phrase"])))

    selected: list[dict[str, Any]] = []
    for candidate in candidates:
        if phrase_is_too_similar(str(candidate["phrase"]), [str(row["phrase"]) for row in selected]):
            continue
        selected.append(candidate)
        if len(selected) >= max_nodes:
            break

    nodes = [
        TaxonomyNode(
            node_id=f"corpus_terms__{slugify(str(row['phrase']))}",
            dimension="corpus_terms",
            canonical_label=label_from_phrase(str(row["phrase"])),
            definition=f"Corpus-derived candidate node supported by {row['support']} sampled documents.",
            aliases=[str(row["phrase"]), label_from_phrase(str(row["phrase"]))],
            support_documents=list(row["doc_ids"]),
            raw={
                "probe_source": "sampled_corpus_terms",
                "support_documents": row["support"],
                "score": round(float(row["score"]), 3),
                "sources": row["sources"],
            },
        )
        for row in selected
    ]
    return ProbeVariant(
        "corpus_terms",
        "Nodes induced from sampled corpus keywords, concepts, titles, and abstracts.",
        nodes,
        expected_nodes_per_document=1.2,
    )


def _nodes(prefix: str, specs: list[tuple[str, str, list[str]]]) -> list[TaxonomyNode]:
    return [
        TaxonomyNode(
            node_id=f"{prefix}__{slugify(key)}",
            dimension=prefix,
            canonical_label=label,
            definition=f"Candidate node for {label}.",
            aliases=aliases,
        )
        for key, label, aliases in specs
    ]


def evaluate_variant(
    variant: ProbeVariant,
    sampled: list[Any],
    assignments: dict[str, list[str]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    doc_count = len(sampled)
    assigned_docs = set(assignments)
    node_counts = Counter(node_id for node_ids in assignments.values() for node_id in node_ids)
    overlap_counts = Counter(len(node_ids) for node_ids in assignments.values())
    unassigned = [doc for doc in sampled if doc.doc_id not in assigned_docs]
    overloaded = [doc for doc in sampled if len(assignments.get(doc.doc_id, [])) >= 4]
    singleton_nodes = [node.node_id for node in variant.nodes if node_counts[node.node_id] <= 1]
    coverage = len(assigned_docs) / doc_count if doc_count else 0.0
    mean_overlap = sum(len(assignments.get(doc.doc_id, [])) for doc in sampled) / doc_count if doc_count else 0.0
    balance = node_balance_score(node_counts, len(variant.nodes))
    overlap_quality = node_overlap_score(mean_overlap, variant.expected_nodes_per_document)
    non_overloaded = 1.0 - min(1.0, len(overloaded) / max(1, doc_count))
    score = round(0.45 * coverage + 0.20 * min(1.0, balance) + 0.22 * overlap_quality + 0.13 * non_overloaded, 3)
    label_by_id = {node.node_id: node.canonical_label for node in variant.nodes}
    report = {
        "variant_id": variant.variant_id,
        "description": variant.description,
        "sampled_documents": doc_count,
        "node_count": len(variant.nodes),
        "expected_nodes_per_document": variant.expected_nodes_per_document,
        "assigned_documents": len(assigned_docs),
        "unassigned_documents": len(unassigned),
        "coverage": round(coverage, 3),
        "mean_nodes_per_document": round(mean_overlap, 3),
        "overlap_quality": round(overlap_quality, 3),
        "overlap_distribution": dict(sorted(overlap_counts.items())),
        "overloaded_documents": len(overloaded),
        "singleton_or_empty_nodes": singleton_nodes,
        "node_counts": [
            {"node_id": node_id, "label": label_by_id.get(node_id, ""), "assigned_documents": count}
            for node_id, count in node_counts.most_common()
        ],
        "probe_score": score,
    }
    cases = boundary_case_rows(variant, sampled, assignments, unassigned, overloaded)
    return report, cases


def node_balance_score(node_counts: Counter[str], node_count: int) -> float:
    if not node_counts or node_count <= 0:
        return 0.0
    counts = list(node_counts.values()) + [0] * max(0, node_count - len(node_counts))
    mean = sum(counts) / node_count
    if mean <= 0:
        return 0.0
    spread = sum(abs(count - mean) for count in counts) / (node_count * mean)
    return max(0.0, min(1.0, 1.0 - spread / 2.0))


def node_overlap_score(mean_overlap: float, target_overlap: float) -> float:
    if target_overlap <= 0:
        return 0.0
    distance = abs(mean_overlap - target_overlap) / target_overlap
    return max(0.0, min(1.0, 1.0 - distance))


def boundary_case_rows(
    variant: ProbeVariant,
    sampled: list[Any],
    assignments: dict[str, list[str]],
    unassigned: list[Any],
    overloaded: list[Any],
) -> list[dict[str, Any]]:
    label_by_id = {node.node_id: node.canonical_label for node in variant.nodes}
    rows: list[dict[str, Any]] = []
    for case_type, docs in [("unassigned", unassigned[:20]), ("overlap_heavy", overloaded[:20])]:
        for doc in docs:
            node_ids = assignments.get(doc.doc_id, [])
            rows.append(
                {
                    "variant_id": variant.variant_id,
                    "case_type": case_type,
                    "doc_id": doc.doc_id,
                    "title": doc.title,
                    "published_at": doc.published_at.isoformat() if doc.published_at else None,
                    "assigned_node_ids": node_ids,
                    "assigned_node_labels": [label_by_id.get(node_id, "") for node_id in node_ids],
                    "text_excerpt": doc.text[:600],
                    "top_tokens": top_tokens(doc.full_text, 12),
                }
            )
    return rows


def node_candidate_rows(variant: ProbeVariant) -> list[dict[str, Any]]:
    return [
        {
            "variant_id": variant.variant_id,
            "node_id": node.node_id,
            "dimension": node.dimension,
            "canonical_label": node.canonical_label,
            "definition": node.definition,
            "aliases": node.aliases,
            "support_documents": node.support_documents,
            "probe_metadata": node.raw,
        }
        for node in variant.nodes
    ]


def node_token_profiles(
    variant: ProbeVariant,
    sampled: list[Any],
    assignments: dict[str, list[str]],
) -> list[dict[str, Any]]:
    docs_by_id = {doc.doc_id: doc for doc in sampled}
    by_node: dict[str, list[Any]] = defaultdict(list)
    for doc_id, node_ids in assignments.items():
        doc = docs_by_id.get(doc_id)
        if not doc:
            continue
        for node_id in node_ids:
            by_node[node_id].append(doc)
    labels = {node.node_id: node.canonical_label for node in variant.nodes}
    rows = []
    for node_id, docs in sorted(by_node.items()):
        counts = Counter(token for doc in docs for token in tokenize(doc.full_text))
        rows.append(
            {
                "variant_id": variant.variant_id,
                "node_id": node_id,
                "label": labels.get(node_id, ""),
                "document_count": len(docs),
                "top_tokens": [{"token": token, "count": count} for token, count in counts.most_common(20)],
                "example_doc_ids": [doc.doc_id for doc in docs[:5]],
            }
        )
    return rows


def sample_record(doc: Any) -> dict[str, Any]:
    return {
        "doc_id": doc.doc_id,
        "title": doc.title,
        "published_at": doc.published_at.isoformat() if doc.published_at else None,
        "chronology_slice": doc.chronology_slice,
        "role": doc.role,
        "text_excerpt": doc.text[:800],
        "screening": (doc.raw or {}).get("screening") or {},
        "query_buckets": (doc.raw or {}).get("query_buckets") or [],
        "keywords": (doc.raw or {}).get("keywords") or [],
    }


def build_summary(
    *,
    config_path: Path,
    corpus_manifest: dict[str, Any],
    sample_records: list[dict[str, Any]],
    variant_reports: list[dict[str, Any]],
    output_root: Path,
    seed: int,
) -> dict[str, Any]:
    best = max(variant_reports, key=lambda row: float(row.get("probe_score") or 0.0)) if variant_reports else {}
    return {
        "config_path": str(config_path),
        "corpus_path": corpus_manifest.get("path"),
        "raw_rows": corpus_manifest.get("raw_rows"),
        "loaded_documents": corpus_manifest.get("loaded_documents"),
        "sample_size": len(sample_records),
        "seed": seed,
        "variant_count": len(variant_reports),
        "best_variant_id": best.get("variant_id"),
        "best_probe_score": best.get("probe_score"),
        "outputs": {
            "output_root": str(output_root),
            "sampled_documents": str(output_root / "sampled_documents.jsonl"),
            "node_candidates": str(output_root / "node_candidates.jsonl"),
            "schema_variants": str(output_root / "schema_variants.json"),
            "node_coverage_report": str(output_root / "node_coverage_report.json"),
            "boundary_cases": str(output_root / "boundary_cases.jsonl"),
            "recommendation": str(output_root / "schema_recommendation.md"),
        },
    }


def write_recommendation(path: Path, summary: dict[str, Any], reports: list[dict[str, Any]]) -> None:
    lines = [
        "# Schema Probe Recommendation",
        "",
        f"- Corpus: `{summary.get('corpus_path')}`",
        f"- Sample size: {summary.get('sample_size')}",
        f"- Seed: {summary.get('seed')}",
        f"- Best variant by probe score: `{summary.get('best_variant_id')}` ({summary.get('best_probe_score')})",
        "",
        "## Variant Scores",
        "",
    ]
    for report in sorted(reports, key=lambda row: -float(row.get("probe_score") or 0.0)):
        lines.extend(
            [
                f"### {report['variant_id']}",
                "",
                f"- Score: {report['probe_score']}",
                f"- Coverage: {report['assigned_documents']} / {report['sampled_documents']} ({report['coverage']})",
                f"- Mean nodes per document: {report['mean_nodes_per_document']} (target {report['expected_nodes_per_document']}, quality {report['overlap_quality']})",
                f"- Overloaded documents: {report['overloaded_documents']}",
                f"- Singleton or empty nodes: {len(report['singleton_or_empty_nodes'])}",
                "",
                "Top nodes:",
                "",
            ]
        )
        for row in report["node_counts"][:8]:
            lines.append(f"- {row['label']}: {row['assigned_documents']}")
        lines.append("")
    lines.extend(
        [
            "## Interpretation",
            "",
            "This probe is an input to schema design, not an automatic config update. Review boundary cases before promoting any node schema into the main EvoTaxa configuration.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def variant_to_record(variant: ProbeVariant) -> dict[str, Any]:
    return {
        "variant_id": variant.variant_id,
        "description": variant.description,
        "nodes": node_candidate_rows(variant),
    }


def top_tokens(text: str, n: int) -> list[str]:
    return [token for token, _ in Counter(tokenize(text)).most_common(n)]


GENERIC_CORPUS_PHRASES = {
    "computational social science",
    "computational social sciences",
    "social science",
    "social sciences",
    "computer science",
    "data science",
    "social data",
    "research methods",
    "research method",
    "research design",
    "scientific research",
    "empirical research",
    "case study",
    "case studies",
}

GENERIC_CORPUS_TOKENS = {
    "approach",
    "approaches",
    "article",
    "based",
    "can",
    "data",
    "different",
    "field",
    "findings",
    "method",
    "methods",
    "model",
    "models",
    "new",
    "paper",
    "present",
    "presents",
    "problem",
    "problems",
    "research",
    "result",
    "results",
    "science",
    "sciences",
    "social",
    "study",
    "using",
    "work",
}


def corpus_candidate_phrases(doc: Any) -> list[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    raw = doc.raw or {}
    for field, source in [("keywords", "keyword"), ("concepts", "concept")]:
        for item in raw.get(field) or []:
            phrase = normalize_candidate_phrase(item)
            if valid_corpus_phrase(phrase):
                pairs.add((phrase, source))

    for phrase in ngram_phrases(doc.title, max_n=4):
        if valid_corpus_phrase(phrase):
            pairs.add((phrase, "title_phrase"))
    for phrase in ngram_phrases(doc.text[:3000], max_n=3):
        if valid_corpus_phrase(phrase):
            pairs.add((phrase, "abstract_phrase"))
    return sorted(pairs)


def assign_documents_for_variant(sampled: list[Any], variant: ProbeVariant) -> dict[str, list[str]]:
    assignments = {doc_id: set(node_ids) for doc_id, node_ids in infer_assignments_from_text(sampled, variant.nodes).items()}
    sampled_ids = {doc.doc_id for doc in sampled}
    for node in variant.nodes:
        if not node.support_documents:
            continue
        for doc_id in node.support_documents:
            if doc_id in sampled_ids:
                assignments.setdefault(doc_id, set()).add(node.node_id)
    return {doc_id: sorted(node_ids) for doc_id, node_ids in assignments.items()}


def normalize_candidate_phrase(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[/_:+,;]", " ", text)
    tokens = tokenize(text)
    return " ".join(tokens[:5])


def ngram_phrases(text: str, *, max_n: int) -> list[str]:
    tokens = tokenize(text)
    phrases = []
    for n in range(2, max_n + 1):
        for index in range(0, max(0, len(tokens) - n + 1)):
            phrases.append(" ".join(tokens[index : index + n]))
    return phrases


def valid_corpus_phrase(phrase: str) -> bool:
    if not phrase or phrase in GENERIC_CORPUS_PHRASES:
        return False
    tokens = phrase.split()
    if len(tokens) < 2 or len(tokens) > 5:
        return False
    if len(set(tokens)) != len(tokens):
        return False
    if any(token.isdigit() for token in tokens):
        return False
    if all(token in GENERIC_CORPUS_TOKENS for token in tokens):
        return False
    if tokens[0] in {"this", "that", "these", "those", "which"}:
        return False
    return True


def phrase_is_too_similar(phrase: str, selected_phrases: list[str]) -> bool:
    tokens = set(phrase.split())
    for selected in selected_phrases:
        selected_tokens = set(selected.split())
        if tokens <= selected_tokens or selected_tokens <= tokens:
            return True
        union = tokens | selected_tokens
        if union and len(tokens & selected_tokens) / len(union) >= 0.75:
            return True
    return False


def label_from_phrase(phrase: str) -> str:
    acronyms = {"api", "gis", "gpt", "llm", "llms", "nlp", "ai"}
    return " ".join(token.upper() if token in acronyms else token.capitalize() for token in phrase.split())


if __name__ == "__main__":
    raise SystemExit(main())
