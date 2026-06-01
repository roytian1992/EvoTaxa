# Corpus-Driven Schema Probing

## Purpose

Schema probing is a pre-main-flow workflow for deciding what EvoTaxa nodes should mean for a new corpus. It samples documents from an already selected corpus, evaluates candidate node schemas, and writes boundary cases for human review before any schema is promoted into the main EvoTaxa config.

This keeps node design corpus-driven. A corpus may mainly show method-family differentiation, evidence-practice shifts, data-source changes, cyclical returns, or recontextualization. The probing layer estimates which representation fits the observed texts instead of assuming one evolution theory upfront.

## Current Command

For the screened OpenAlex computational-social-science corpus:

```bash
cd /vepfs-mlp2/c20250513/241404044/users/roytian/EvoTaxa
PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python scripts/probe_schema_design.py \
  --config configs/computational_social_science_methods.openalex.toml \
  --output-root data/schema_probe/css_screened_20260530_v1 \
  --sample-size 240 \
  --seed 20260530
```

The script samples across publication decades where possible, then fills the remaining quota from the full corpus using the same random seed.

To turn probe artifacts into a candidate main-flow EvoTaxa configuration:

```bash
PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python scripts/propose_schema_from_probe.py \
  --base-config configs/computational_social_science_methods.openalex.toml \
  --probe-root data/schema_probe/css_screened_20260530_v2 \
  --output-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal \
  --run-id-suffix practice_method_probe_v2
```

Then validate the proposed config:

```bash
PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python -m evotaxa.cli validate-config \
  --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/config.proposed.json
```

## Candidate Variants

- `method_ecology`: nodes represent broad computational social-science method families, such as text-as-data, network analysis, causal inference, simulation, LLM-assisted methods, governance, spatial analysis, machine learning, and online/social-media methods.
- `evidence_practice`: nodes represent evidence-production practices, such as data source, measurement, modeling, evaluation, infrastructure, and governance.
- `hybrid_two_axis`: combines method-family and evidence-practice nodes, allowing a document to sit in both a method ecology and a research-practice layer.
- `corpus_terms`: induces candidate nodes from the sampled corpus itself, using title/abstract phrases plus OpenAlex keywords and concepts. This variant is mainly for discovering missing aliases or missing nodes; broad metadata concepts can over-cover the corpus and should not be promoted without boundary review.

These are starting probes, not final ontology claims. More variants can be added when a domain has a stronger candidate theory.

## Outputs

Each probe run writes:

- `sampled_documents.jsonl`: sampled paper IDs, title snippets, date, role, screening metadata, and query buckets.
- `node_candidates.jsonl`: candidate node IDs, labels, dimensions, aliases, and definitions.
- `schema_variants.json`: full variant definitions.
- `node_coverage_report.json`: coverage, overlap, overloaded documents, singleton or empty nodes, node counts, and probe score.
- `node_token_profiles.jsonl`: high-frequency tokens in documents assigned to each candidate node.
- `boundary_cases.jsonl`: unassigned or heavily overlapping documents that should be manually reviewed.
- `probe_summary.json`: compact manifest for the run.
- `schema_recommendation.md`: human-readable ranking and interpretation notes.

The proposal stage writes richer main-flow artifacts:

- `taxonomy.proposed.json`: proposed taxonomy nodes as node cards. Each node includes title, dimension, definition, aliases, inclusion criteria, exclusion criteria, negative examples, entity scope, relation affordances, boundary notes, and probe provenance.
- `schema_seed.proposed.json`: entity, relation, and evidence schema seed that can be read by `schema.schema_seed_path`.
- `config.proposed.json`: complete candidate EvoTaxa config pointing at the proposed taxonomy and schema seed.
- `schema_proposal_report.md`: human-readable explanation of the proposed schema and validation/run commands.

## Node Cards Vs Entities

Taxonomy nodes are card-like schema objects. They define a local evolution space and include boundaries, evidence expectations, aliases, negative examples, and downstream entity scope. A node should not be treated as just a title.

Graph entities are different objects. They are extracted from document text after taxonomy assignment and become possible endpoints for relation edges. Bad strings such as `science`, `thus`, `to this end`, or `free` are entity-extraction noise, not valid taxonomy nodes. The entity-quality layer should filter them before edge construction; the proposal node cards now explicitly state that node cards are not graph entities.

The proposal step writes:

- `taxonomy.proposed.json`: standard EvoTaxa taxonomy nodes for the next main-flow candidate run.
- `schema_seed.proposed.json`: entity, relation, and evidence schemas consumable through `schema.schema_seed_path`.
- `config.proposed.json`: a complete JSON EvoTaxa config that points at the proposed taxonomy and schema seed.
- `proposal_summary.json`: compact machine-readable proposal manifest.
- `schema_proposal_report.md`: human-readable rationale and commands for validation and candidate `run-full`.

## Interpretation Rules

Probe score is only a triage signal. A high score means a candidate schema covers the sample without excessive empty nodes or document overload. It does not prove that the schema is conceptually correct.

Before updating `configs/computational_social_science_methods.taxonomy.json`, review:

- Whether high-count nodes are meaningful rather than generic.
- Whether empty or singleton nodes should be removed, merged, or kept as rare but important categories.
- Whether boundary cases reveal missing nodes.
- Whether overloaded documents need a two-axis schema instead of a flat taxonomy.
- Whether corpus-derived terms are true analytical nodes, aliases, metadata artifacts, or domain labels that are too broad for evolution modeling.
- Whether the chosen node meaning matches the downstream evolution question.

## CSS Probe Result

The current screened CSS probe was run at `data/schema_probe/css_screened_20260530_v2/` with 240 sampled documents from the 4,126-row screened corpus. This v2 run uses the 13-node method-family candidate set plus the evidence-practice and corpus-term variants.

The best single variant was `evidence_practice` with score 0.842, coverage 193/240, and mean 1.321 nodes per document. `hybrid_two_axis` had higher coverage at 217/240 but more overloaded documents and mean 2.446 nodes per document, so it scored 0.812. `method_ecology` improved to score 0.771 after the method-family candidate set was expanded to 13 nodes.

The proposal agent therefore selected `practice_primary_method_secondary`: evidence-production practice is the primary axis, and method-family labels are retained as a second axis for interpretation and trajectory locality. The proposed main-flow artifacts are under `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/`.

The `corpus_terms` variant had high raw coverage, 222/240, but over-assigned documents with mean 2.688 nodes per document. Its strongest terms, including Artificial Intelligence, Political Science, Machine Learning, World Wide Web, Social Media, Natural Language Processing, Data Mining, Social Network, Computational Sociology, and Information Retrieval, should be reviewed as alias or missing-node evidence rather than promoted directly.

## Main-Flow Boundary

This workflow is optional and external to `run-full`. It reads the same corpus config but only writes probe artifacts under `data/schema_probe/`. The main EvoTaxa run still starts from a concrete corpus and taxonomy config.
