# EvoTaxa Input Contract

EvoTaxa is intentionally config-driven. The core pipeline does not require ForeSci field names.

The pipeline normalizes each domain dataset into three internal objects:

- `Document`: one paper, report, interview, news item, policy text, or social-science study.
- `TaxonomyNode`: one concept node in a configured taxonomy dimension.
- `Assignment`: a mapping from document ids to taxonomy node ids.

## Corpus

Corpus input may be JSONL or a JSON list. Configure field names under `[corpus]`.

Required after mapping:

```json
{
  "doc_id": "stable id",
  "title": "short title",
  "text": "abstract, full text, summary, or concatenated evidence text"
}
```

Recommended:

```json
{
  "published_at": "YYYY-MM-DD",
  "chronology_slice": "2025-Q1",
  "role": "core",
  "source_type": "paper|policy|interview|news|report|social_document"
}
```

The actual input fields can be different. For example, social-science data can use `study_id`,
`publication_date`, `summary`, and `inclusion_decision`; the config maps these into the internal contract.

## Taxonomy Nodes

Taxonomy input may be:

- a JSON list of flat nodes,
- JSONL flat nodes,
- a nested JSON tree with `children`,
- a dimension-keyed nested object.

Required after mapping:

```json
{
  "node_id": "stable taxonomy id",
  "canonical_label": "node label",
  "dimension": "mechanisms"
}
```

Recommended:

```json
{
  "parent_id": "parent node id",
  "definition": "what this node means",
  "aliases": ["alternative names"],
  "created_time_slice": "2025-Q1"
}
```

## Assignments

Assignments are optional. If absent, EvoTaxa falls back to simple text matching over node labels and aliases.
For serious runs, provide explicit assignments.

Supported assignment formats include:

```json
{"doc_id": "D1", "taxonomy_nodes": ["mechanisms__inoculation", "interventions__labeling"]}
```

or a dimension map:

```json
{
  "doc_id": "D1",
  "dimension_assignments": {
    "mechanisms": ["mechanisms__inoculation"],
    "interventions": [{"node_id": "interventions__labeling"}]
  }
}
```

## Domain Configuration

The config controls:

- field mappings,
- cutoff policy,
- accepted roles,
- taxonomy dimensions,
- taxonomy co-evolution revision limits,
- entity types,
- entity seed patterns,
- entity alias maps,
- edge cue phrases,
- edge evidence thresholds,
- output location.

This is what makes the same code usable for scientific research and social science.

## Entity Aliases

Use `[graph.entity_aliases]` to keep evolution graph entities from fragmenting across spelling variants, abbreviations, or local terminology.

```toml
[graph.entity_aliases]
"platform labeling" = ["content labeling", "labeling intervention", "platform labels"]
"algorithmic audit" = ["algorithm audit", "algorithmic auditing"]
```

EvoTaxa writes both `graph/method_aliases.jsonl` and `graph/entity_linking_report.jsonl` so merges are auditable.

## Entity Quality

Entity quality filtering runs after alias canonicalization and before edge construction. Low-quality entities are written to `graph/entity_quality_report.jsonl` and do not enter graph edge construction.

Useful config keys:

```toml
[graph]
min_entity_quality = 0.42
entity_allowlist = ["ReAct", "platform labeling"]
entity_denylist = ["this paper", "it addresses the problem of"]
generic_entity_phrases = ["this", "that", "paper", "study", "problem", "challenge"]
```

## LLM Configuration

EvoTaxa can run without an LLM. In that mode it uses deterministic fallback logic and still writes all artifacts.

For development with a local OpenAI-compatible server:

```toml
[llm]
provider = "openai_compat"
model_name = "your-model-name"
api_key_env = "EVOTAXA_LLM_API_KEY"
base_url = "http://localhost:8001/v1"
enabled_tasks = ["entity_extraction", "taxonomy_candidate_judge", "edge_evidence_judge"]
```

For shared configs, use:

```toml
[llm]
provider = "openai_compat"
model_name = "your-model-name"
api_key_env = "EVOTAXA_LLM_API_KEY"
base_url = "http://localhost:8001/v1"
enabled_tasks = []
```

`enabled_tasks = []` means the config is LLM-ready but will not call the model by default.
Use `enabled_tasks = ["*"]` only when every LLM-backed task may call the configured server.

`run-full` writes `audit/llm_cache.jsonl` by default. Repeated prompts reuse this cache, which makes local LLM experiments reproducible and cheaper to resume. LLM outputs are schema-checked before they can modify entity mentions, edge evidence, or taxonomy expansion candidates.

## Edge Evidence Contract

Each edge may carry `bottleneck`, `mechanism`, and `tradeoff` objects under `evidence`. Each object should include:

```json
{
  "description": "short analytical description",
  "quote": "exact quote copied from the source or target document"
}
```

EvoTaxa verifies every quote against the source and target document text. The edge status is controlled by:

```toml
[graph]
llm_edge_judge_limit = 100
trusted_edge_confidence_threshold = 0.65
candidate_edge_confidence_threshold = 0.35
require_verified_evidence_for_trusted = true
```

`graph/method_edges.paper_level.jsonl` keeps all edges. `graph/method_edges.trusted.jsonl`, `graph/method_edges.candidate.jsonl`, and `graph/method_edges.unverified.jsonl` provide the auditable split. `graph/edge_evidence_audit.jsonl` records quote-level verification results and status reasons.

## Taxonomy-Graph Co-Evolution

`run-full` can use trusted graph feedback to revise the taxonomy, then rerun entity extraction, edge construction, evidence audit, hooks, and feedback on the revised taxonomy.

Useful config keys:

```toml
[taxonomy]
coevolution_enabled = true
max_coevolution_iterations = 1
max_revision_candidates = 30
max_applied_revisions = 10
revision_acceptance_threshold = 0.58
```

Revision candidates can be:

- `split_child`: create a graph-derived child when the candidate label is clean, non-duplicate, and compatible with the taxonomy dimension.
- `cross_link`: annotate an existing node with cross-dimensional linked entities or related taxonomy nodes.
- `state_annotation`: mark an existing node as `growing` or `fragmenting`.

The loop writes `taxonomy/revision_candidates.jsonl`, `taxonomy/revision_application_report.jsonl`, and `taxonomy/coevolution_iterations.jsonl`. Applied revisions are also embedded in `taxonomy/taxonomy_nodes.expanded.json` under each node's `raw.graph_revisions`.

## Evaluation Output

Each run writes `evaluation/quality_report.json`. The report aggregates intrinsic checks that do not require a gold label file:

- taxonomy metric means from `node_quality_scores.jsonl`,
- entity kept/filter rates from `entity_quality_report.jsonl`,
- edge trust and quote coverage from `edge_evidence_audit.jsonl`,
- expansion and co-evolution revision yield,
- forecast hook score summaries,
- LLM schema/error/cache reliability.

These metrics are intended as experiment hygiene and ablation targets. A publication-grade evaluation should still add human labels for taxonomy node validity, entity mention accuracy, relation precision, and quote grounding.

## Ablation Output

Use `run-ablation` to run multiple configured variants from the same base config:

```bash
python -m evotaxa.cli run-ablation \
  --config configs/social_science.example.toml \
  --variants default no_coevolution no_expansion no_edge_judge no_llm \
  --print-summary
```

The suite writes:

- `ablation_summary.json`,
- `ablation_summary.jsonl`,
- `ablation_manifests.json`,
- one full EvoTaxa output directory per variant.

Built-in variants are `default`, `no_coevolution`, `no_expansion`, `no_edge_judge`, and `no_llm`.
