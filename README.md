# EvoTaxa

EvoTaxa is a config-driven framework for taxonomy-guided evolution modeling.

The first implementation in this repository is `run-lite`: a deterministic Phase 1 + MEG-lite pipeline that normalizes arbitrary domain data, enriches taxonomy nodes, detects simple taxonomy events, extracts method/mechanism entities, builds typed evolution edges, validates evidence quotes, searches local lineage chains, and emits forecast/social-analysis hooks.

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

## Output Layout

Each run writes:

```text
<output_root>/
  corpus/
    documents.normalized.jsonl
    manifest.json
  taxonomy/
    taxonomy_nodes.enriched.json
    taxonomy_events.jsonl
    node_quality_scores.jsonl
    taxonomy_judge_report.json
    document_assignments.normalized.jsonl
  graph/
    method_registry.jsonl
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
  audit/
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
- `[graph.edge_cues]`: phrase cues for typed evolution edges.
- `[output]`: output root.

## Current Scope

`run-lite` is intentionally lightweight. It gives us a stable artifact contract and a working local graph pipeline before adding LLM-based node enrichment, LLM pairwise edge judging, and stronger temporal search.
