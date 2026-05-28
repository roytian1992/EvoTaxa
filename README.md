# EvoTaxa

EvoTaxa is a config-driven framework for taxonomy-guided, schema-adaptive, evidence-grounded evolution modeling.

The core idea is to model a domain as an evolving state, not just as a flat set of topics or co-mentioned entities. EvoTaxa jointly maintains:

- a taxonomy that defines domain regions and their boundaries,
- a schema that defines valid entity, relation, and evidence contracts,
- an evolution graph whose edges are quote-grounded and schema-constrained,
- a state model that records how taxonomy, schema, and relations change,
- a trajectory model that reconstructs plausible evolution paths.

`run-lite` is a deterministic version of this pipeline. It normalizes arbitrary domain data, enriches taxonomy nodes, extracts entities, builds typed evolution edges, audits quote evidence, separates trusted/candidate/unverified edges, infers local trajectories, and emits forecast or social-analysis hooks.

`run-full` adds the research modules: taxonomy induction when no taxonomy is provided, taxonomy expansion, optional LLM judging with cache/retry/schema validation, batched schema-guided relation extraction, adaptive schema revision, negative-evidence feedback, taxonomy-graph co-evolution, explicit state-transition artifacts, trajectory scoring, and run-level quality reporting.

## Algorithm Flow

EvoTaxa runs as a closed-loop evolution modeling algorithm:

```text
corpus
  -> normalized documents and cutoff-aware slices
  -> taxonomy induction / enrichment / expansion
  -> entity extraction, linking, and quality filtering
  -> entity / relation / evidence schema resolution
  -> schema-guided relation extraction
  -> quote-grounded evidence audit
  -> edge scoring and trusted/candidate/unverified stratification
  -> taxonomy-graph co-evolution
  -> adaptive schema revision with negative evidence
  -> evolution state snapshot and state transitions
  -> trajectory inference and trajectory evaluation
  -> hooks, reports, ablations, and quality diagnostics
```

The important feedback loops are:

- **Taxonomy to graph**: taxonomy nodes constrain local entity pools, candidate relation pairs, and trajectory context.
- **Graph to taxonomy**: trusted edges and branch patterns trigger node split, cross-link, and state-annotation revisions.
- **Schema to graph**: entity, relation, and evidence schemas constrain extraction and judging.
- **Graph to schema**: failed quotes, weak edges, filtered entities, and rejected relation pairs become schema revision candidates.
- **Negative evidence to schema**: rejected relation pairs are persisted as negative priors and counterexamples, so weak co-mentions do not silently become evolution edges.
- **Edges to trajectories**: trusted edges are composed into evolution trajectories using temporal coherence, quote grounding, schema fit, and taxonomy locality.

This makes EvoTaxa suitable for AI research evolution modeling and for social-science domains such as policy, governance, misinformation, polarization, education, or platform labor.

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
[graph]
llm_relation_batch_size = 4

[llm]
provider = "openai_compat"
model_name = "your-model-name"
api_key = "token-abc123"
base_url = "http://localhost:8001/v1"
enabled_tasks = [
  "entity_extraction",
  "taxonomy_candidate_judge",
  "relation_extraction_batch",
  "edge_evidence_judge",
  "schema_revision_judge",
  "relation_schema_inference",
  "entity_evidence_schema_inference",
]
```

For committed configs, prefer `api_key_env` instead of a literal token.
Set `enabled_tasks = []` to disable model calls by default, or `enabled_tasks = ["*"]` to allow every LLM-backed task.

For adaptive schema work, also enable `relation_schema_inference`, `entity_evidence_schema_inference`, and `schema_revision_judge`.

Adaptive social-science case study:

```bash
python -m evotaxa.cli run-full \
  --config configs/social_misinformation_governance.adaptive.toml \
  --print-manifest
```

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
    schema_revision_candidates.jsonl
    schema_reports.jsonl
  graph/
    method_registry.jsonl
    method_aliases.jsonl
    entity_linking_report.jsonl
    entity_quality_report.jsonl
    llm_entity_mentions.jsonl
    paper_method_mentions.jsonl
    relation_extraction_report.jsonl
    relation_rejections.jsonl
    method_edges.paper_level.jsonl
    method_edges.trusted.jsonl
    method_edges.candidate.jsonl
    method_edges.unverified.jsonl
    edge_scores.jsonl
    method_edges.aggregated.jsonl
    method_edges.all_aggregated.jsonl
    edge_evidence_audit.jsonl
    method_evidence_records.jsonl
    entity_summary.json
  search/
    evolution_chains.jsonl
    branch_points.jsonl
  trajectory/
    evolution_trajectories.jsonl
    trajectory_eval.jsonl
  state/
    evolution_state.json
    state_transitions.jsonl
  hooks/
    forecast_hooks.jsonl
    social_analysis_hooks.jsonl
    hook_score_report.json
  feedback/
    taxonomy_graph_feedback.jsonl
  evaluation/
    quality_report.json
  reports/
    case_study_report.md
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
- `[graph]`: entity types, strong edge types, cue terms, extraction limits, and relation batch size.
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
- `adaptive`: infer or load a schema, propose revision candidates from entity filtering and edge evidence audit signals, then promote bounded revisions.

The relation schema is injected into edge construction and LLM edge judging. The entity schema constrains quote-grounded entity extraction. The evidence schema defines which quote-backed slots are audited. Each run writes fixed, inferred, final, candidate, and promoted revision artifacts under `schema/`.

In `run-full`, enabling `relation_extraction_batch` lets the model create schema-guided relation edges from candidate entity pairs before the evidence judge audits them. Cue-based edges remain as a deterministic fallback and prior. Rejected relation pairs are also written as negative evidence so the run can explain what the model refused to connect.

When schema modes are `adaptive`, EvoTaxa can evolve the relation schema, entity schema, and evidence schema. A model-backed `schema_revision_judge` can decide whether each proposed schema revision should be promoted, rejected, or held for human review.

Rejected relation pairs also feed back into adaptive relation schemas as negative priors and counterexamples. This prevents weak co-mentions from being treated as future evolution edges and makes schema drift inspectable.

## Edge Evidence

Every edge is audited after construction. EvoTaxa checks quotes in `bottleneck`, `mechanism`, and `tradeoff` against the source and target documents, then writes:

- `graph/method_edges.trusted.jsonl`: strong edge types above the trusted confidence threshold with verified quote evidence.
- `graph/method_edges.candidate.jsonl`: plausible but weaker edges, including non-strong edge types and edges below the trusted threshold.
- `graph/method_edges.unverified.jsonl`: edges below the candidate threshold or lacking usable evidence.
- `graph/edge_evidence_audit.jsonl`: field-level quote checks and the reason for each edge status.
- `graph/edge_scores.jsonl`: relation confidence, quote grounding, temporal order, taxonomy locality, schema fit, evidence-slot completeness, and final edge score.
- `graph/relation_rejections.jsonl`: relation candidates rejected because they were weak co-mentions, comparison-only links, temporal violations, schema mismatches, or unsupported by quotes.

## Evolution State And Trajectory

EvoTaxa writes an explicit state layer:

- `state/evolution_state.json`: the current domain state, including document slices, taxonomy node states, entity mix, relation mix, and active schema.
- `state/state_transitions.jsonl`: taxonomy transitions, schema transitions, relation-quality transitions, and negative-relation transitions.

It also writes a trajectory layer:

- `trajectory/evolution_trajectories.jsonl`: inferred evolution trajectories scored by edge confidence, temporal coherence, quote grounding, schema coherence, and taxonomy locality.
- `trajectory/trajectory_eval.jsonl`: intrinsic trajectory health metrics.

The legacy `search/evolution_chains.jsonl` path is retained for compatibility, but the algorithmic layer is trajectory inference rather than search.

Hooks and feedback use trusted edges when available; if a run has no trusted edges, they fall back to candidate edges so small exploratory corpora still produce inspectable outputs.

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
