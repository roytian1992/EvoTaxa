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
- entity types,
- entity seed patterns,
- edge cue phrases,
- output location.

This is what makes the same code usable for scientific research and social science.

## LLM Configuration

EvoTaxa can run without an LLM. In that mode it uses deterministic fallback logic and still writes all artifacts.

For development with a local OpenAI-compatible server:

```toml
[llm]
provider = "openai_compat"
model_name = "GLM-4.6-FP8"
api_key = "token-abc123"
base_url = "http://localhost:8001/v1"
enabled_tasks = ["taxonomy_candidate_judge", "edge_evidence_judge"]
```

For shared configs, use:

```toml
[llm]
provider = "openai_compat"
model_name = "GLM-4.6-FP8"
api_key_env = "EVOTAXA_LLM_API_KEY"
base_url = "http://localhost:8001/v1"
enabled_tasks = []
```

`enabled_tasks = []` means the config is LLM-ready but will not call the model by default.
Use `enabled_tasks = ["*"]` only when every LLM-backed task may call the configured server.
