# EvoTaxa

EvoTaxa is a config-driven framework for taxonomy-guided evolution modeling.

The first implementation in this repository is `run-lite`: a deterministic Phase 1 + MEG-lite pipeline that normalizes arbitrary domain data, enriches taxonomy nodes, detects simple taxonomy events, extracts method/mechanism entities, builds typed evolution edges, validates evidence quotes, separates trusted/candidate edges, searches local lineage chains, and emits forecast/social-analysis hooks.

`run-full` adds the research-plan modules: initial taxonomy induction when no taxonomy is provided, expansion trigger scoring, expansion candidate generation, optional LLM judging with cache/retry/schema validation, accepted-candidate application into an expanded taxonomy snapshot, quote-grounded edge evidence auditing, taxonomy-graph co-evolution revisions, and forecast-hook scoring.

## Why Config-Driven

EvoTaxa is not tied to ForeSci field names. A scientific paper corpus and a social-science corpus can use different fields as long as the config maps them into the minimal internal contract.

See [docs/input_contract.md](docs/input_contract.md).

## Install

```bash
pip install -e .
```

## Smoke Runs

Scientific research example:

```bash
python -m evotaxa.cli run-lite \
  --config configs/scientific_research.example.toml \
  --print-manifest
```

Social science example:

```bash
python -m evotaxa.cli run-lite \
  --config configs/social_science.example.toml \
  --print-manifest
```

Full pipeline:

```bash
python -m evotaxa.cli run-full \
  --config configs/social_science.example.toml \
  --print-manifest
```

Schema-only commands:

```bash
python -m evotaxa.cli infer-schema \
  --config configs/social_science.example.toml \
  --print-summary

python -m evotaxa.cli adapt-schema \
  --config configs/social_science.example.toml \
  --print-summary
```

Ablation suite:

```bash
python -m evotaxa.cli run-ablation \
  --config configs/social_science.example.toml \
  --variants default no_coevolution no_expansion no_edge_judge no_llm \
  --print-summary
```

Local OpenAI-compatible LLM development:

```toml
[llm]
provider = "openai_compat"
model_name = "your-model-name"
api_key = "token-abc123"
base_url = "http://localhost:8001/v1"
enabled_tasks = ["entity_extraction", "taxonomy_candidate_judge", "edge_evidence_judge"]
```

For committed configs, prefer `api_key_env` instead of a literal token.
Set `enabled_tasks = []` to disable model calls by default, or `enabled_tasks = ["*"]` to allow every LLM-backed task.

For adaptive schema work, also enable `relation_schema_inference` and `entity_evidence_schema_inference`.

## Output Layout

Each run writes:

```text
<output_root>/
  corpus/
    documents.normalized.jsonl
    manifest.json
  taxonomy/
    taxonomy_nodes.enriched.json
    taxonomy_nodes.expanded.json
    taxonomy_events.jsonl
    taxonomy_induction_audit.jsonl
    expansion_trigger_scores.jsonl
    expansion_candidates.jsonl
    expansion_application_report.jsonl
    revision_candidates.jsonl
    revision_application_report.jsonl
    coevolution_iterations.jsonl
    node_quality_scores.jsonl
    taxonomy_judge_report.json
    document_assignments.normalized.jsonl
  schema/
    entity_schema.fixed.json
    entity_schema.inferred.json
    entity_schema.final.json
    entity_schema.revisions.jsonl
    relation_schema.fixed.json
    relation_schema.inferred.json
    relation_schema.final.json
    relation_schema.revisions.jsonl
    evidence_schema.fixed.json
    evidence_schema.inferred.json
    evidence_schema.final.json
    evidence_schema.revisions.jsonl
    schema_reports.jsonl
  graph/
    method_registry.jsonl
    method_aliases.jsonl
    entity_linking_report.jsonl
    entity_quality_report.jsonl
    llm_entity_mentions.jsonl
    paper_method_mentions.jsonl
    method_edges.paper_level.jsonl
    method_edges.trusted.jsonl
    method_edges.candidate.jsonl
    method_edges.unverified.jsonl
    method_edges.aggregated.jsonl
    method_edges.all_aggregated.jsonl
    edge_evidence_audit.jsonl
    method_evidence_records.jsonl
    entity_summary.json
  search/
    evolution_chains.jsonl
    branch_points.jsonl
  hooks/
    forecast_hooks.jsonl
    social_analysis_hooks.jsonl
    hook_score_report.json
  feedback/
    taxonomy_graph_feedback.jsonl
  evaluation/
    quality_report.json
  audit/
    llm_judge_records.jsonl
    llm_cache.jsonl
    unverified_edges.jsonl
    low_confidence_nodes.jsonl
  manifest.json
```

## Config Sections

- `[project]`: domain metadata and run id.
- `[corpus]`: field mappings, accepted roles, cutoff policy, and source type.
- `[taxonomy]`: taxonomy node/assignment paths and field mappings.
- `[taxonomy.dimensions.*]`: domain-specific taxonomy dimensions.
- `[schema]`: fixed, inferred, or adaptive schema modes for entity, relation, and evidence schemas.
- `[graph]`: entity types, strong edge types, cue terms, and extraction limits.
- `[graph.entity_patterns]`: optional seed entities by entity type.
- `[graph.entity_aliases]`: canonical entity names mapped to aliases for entity linking.
- `[graph.entity_denylist]` / `[graph.entity_allowlist]`: manual entity quality overrides.
- `[graph.edge_cues]`: phrase cues for typed evolution edges.
- `[llm]`: optional OpenAI-compatible model configuration for candidate and edge judging.
- `[output]`: output root.

## Adaptive Schema Evolution

EvoTaxa treats schema as a versioned artifact. `[schema]` supports:

- `fixed`: use configured entity/relation/evidence contracts.
- `inferred`: infer a domain schema from corpus samples before extraction.
- `adaptive`: infer or load a schema, then revise it from entity filtering and edge evidence audit signals.

The relation schema is injected into edge construction and LLM edge judging. The entity schema constrains quote-grounded entity extraction. The evidence schema defines which quote-backed slots are audited. Each run writes fixed, inferred, final, and revision artifacts under `schema/`.

## Edge Evidence

Every edge is audited after construction. EvoTaxa checks quotes in `bottleneck`, `mechanism`, and `tradeoff` against the source and target documents, then writes:

- `graph/method_edges.trusted.jsonl`: strong edge types above the trusted confidence threshold with verified quote evidence.
- `graph/method_edges.candidate.jsonl`: plausible but weaker edges, including non-strong edge types and edges below the trusted threshold.
- `graph/method_edges.unverified.jsonl`: edges below the candidate threshold or lacking usable evidence.
- `graph/edge_evidence_audit.jsonl`: field-level quote checks and the reason for each edge status.

Search, hooks, and feedback use trusted edges when available; if a run has no trusted edges, they fall back to candidate edges so small exploratory corpora still produce inspectable outputs.

## Taxonomy-Graph Co-Evolution

In `run-full`, graph feedback can now revise the taxonomy and then rerun the graph layer. Revisions are conservative by default:

- `split_child`: creates a graph-derived child only when the entity type matches the taxonomy dimension and the label is not already present.
- `cross_link`: annotates a node with cross-dimensional linked entities or nodes.
- `state_annotation`: marks nodes as `growing` or `fragmenting` when trusted edges show branching structure.

The loop writes `taxonomy/revision_candidates.jsonl`, `taxonomy/revision_application_report.jsonl`, and `taxonomy/coevolution_iterations.jsonl`.

## Evaluation

Every run writes `evaluation/quality_report.json`, an intrinsic quality report covering taxonomy quality, entity filtering, edge grounding, co-evolution yield, forecast hooks, and LLM reliability. This is not a substitute for a human gold-standard evaluation, but it gives each experiment a consistent health check and ablation target.

`run-ablation` writes `ablation_summary.json`, `ablation_summary.jsonl`, and one run directory per variant. The default variants are `default`, `no_coevolution`, `no_expansion`, `no_edge_judge`, and `no_llm`.

## Current Scope

`run-lite` is intentionally lightweight. `run-full` exposes the complete algorithmic skeleton, but high-quality production results still depend on better LLM prompts, stronger entity linking, larger corpora, and human audit.
