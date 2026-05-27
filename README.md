# EvoTaxa

EvoTaxa is a config-driven framework for taxonomy-guided evolution modeling.

The first implementation in this repository is `run-lite`: a deterministic Phase 1 + MEG-lite pipeline that normalizes arbitrary domain data, enriches taxonomy nodes, detects simple taxonomy events, extracts method/mechanism entities, builds typed evolution edges, validates evidence quotes, searches local lineage chains, and emits forecast/social-analysis hooks.

`run-full` adds the research-plan modules: initial taxonomy induction when no taxonomy is provided, expansion trigger scoring, expansion candidate generation, optional LLM judging with cache/retry/schema validation, accepted-candidate application into an expanded taxonomy snapshot, taxonomy-graph feedback, and forecast-hook scoring.

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
    node_quality_scores.jsonl
    taxonomy_judge_report.json
    document_assignments.normalized.jsonl
  graph/
    method_registry.jsonl
    method_aliases.jsonl
    entity_linking_report.jsonl
    entity_quality_report.jsonl
    llm_entity_mentions.jsonl
    paper_method_mentions.jsonl
    method_edges.paper_level.jsonl
    method_edges.aggregated.jsonl
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
- `[graph]`: entity types, strong edge types, cue terms, and extraction limits.
- `[graph.entity_patterns]`: optional seed entities by entity type.
- `[graph.entity_aliases]`: canonical entity names mapped to aliases for entity linking.
- `[graph.entity_denylist]` / `[graph.entity_allowlist]`: manual entity quality overrides.
- `[graph.edge_cues]`: phrase cues for typed evolution edges.
- `[llm]`: optional OpenAI-compatible model configuration for candidate and edge judging.
- `[output]`: output root.

## Current Scope

`run-lite` is intentionally lightweight. `run-full` exposes the complete algorithmic skeleton, but high-quality production results still depend on better LLM prompts, stronger entity linking, larger corpora, and human audit.
