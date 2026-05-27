# EvoTaxa: Cutoff-Aware Taxonomy-Guided Evolution Modeling

## 1. Core Idea

EvoTaxa is a unified framework for modeling how research fields, mechanisms, methods, policies, and social issues evolve over time.

The central claim is:

> Temporal taxonomy explains where a field is structurally splitting. Evolution graphs explain why those splits happen, through bottlenecks, mechanisms, adaptations, replacements, and trade-offs.

EvoTaxa combines three existing lines of work:

- TaxoAdapt: multidimensional taxonomy construction with width/depth expansion.
- ResearchForesight/ForeSci: cutoff-aware corpus construction, time-sliced snapshots, benchmark/release discipline, and foresight evaluation.
- Methodological Evolution Graphs: method entities, typed causal edges, evidence-grounded bottleneck-mechanism-tradeoff records, and lineage search.

The resulting framework is not just a taxonomy builder and not just a method graph. It is a cutoff-aware system for discovering, explaining, and auditing temporal evolution.

## 2. Motivation

Current research-infrastructure tools usually organize papers as documents, citation networks, keywords, or static topic clusters. These representations are useful for search, but weak for explaining field evolution.

They usually fail to answer questions like:

- Which subareas are newly emerging versus merely renamed?
- When does a broad topic split into multiple mechanism-level directions?
- Which recurring bottleneck caused a method family, evaluation protocol, or policy tool to evolve?
- Which new direction is a real successor mechanism rather than a popularity spike?
- Which evidence supports an evolution edge, and can that evidence be audited in the original source?

EvoTaxa addresses these questions by combining:

1. A temporal taxonomy that captures structure and granularity.
2. A local evolution graph that captures method/mechanism transitions inside taxonomy regions.
3. Evidence records that make every important transition traceable.

## 3. High-Level Pipeline

```text
Raw corpus
  -> domain harvest and metadata enrichment
  -> relevance screening and core/support labeling
  -> cutoff-aware frozen corpus
  -> enriched temporal taxonomy induction
  -> taxonomy evolution event detection
  -> taxonomy-conditioned evolution graph construction
  -> lineage, branch, and bottleneck search
  -> forecast hooks / analysis hooks / benchmark tasks
```

The key design principle is:

```text
Taxonomy controls where to look.
Evolution graph explains why the structure changes.
```

## 4. Layer 1: Cutoff-Aware Corpus Construction

This layer follows the current ResearchForesight pipeline.

### Inputs

- Raw paper metadata.
- Full text when available.
- Publication metadata such as venue, citation count, publication date, and arXiv id.
- Domain configuration and seed queries.

### Processing

1. Merge and deduplicate raw papers.
2. Compute heuristic domain profiles.
3. Run LLM relevance screening.
4. Label papers as `core`, `support`, `audit_only`, or `exclude`.
5. Freeze a cutoff-aware corpus using only accepted roles.
6. Assign each paper to a chronology slice.

### Outputs

```text
papers_merged.jsonl
publication_enriched.jsonl
paper_screening.jsonl
benchmark_core_labels.jsonl
taxonomy_corpus.core_support.jsonl
taxonomy_corpus.core_support.manifest.json
```

The cutoff boundary is mandatory. No post-cutoff paper may enter taxonomy induction, evolution-edge extraction, retrieval, or answer generation.

## 5. Layer 2: Enriched Temporal Taxonomy

The current taxonomy system already supports multidimensional, time-sliced growth. EvoTaxa upgrades it from a label tree into a richer temporal structure graph.

### Dimensions

For AI research, the default dimensions remain:

- `tasks`
- `methodologies`
- `datasets`
- `evaluation_methods`
- `real_world_domains`

For social science, the dimensions can become:

- `social_issues`
- `actors`
- `mechanisms`
- `interventions`
- `measurement_strategies`
- `contexts`
- `outcomes`
- `public_frames`

### Node Schema

Each taxonomy node should carry more than a label and description:

```json
{
  "node_id": "",
  "dimension": "",
  "canonical_label": "",
  "aliases": [],
  "definition": "",
  "inclusion_criteria": "",
  "exclusion_criteria": "",
  "distinctive_phrases": [],
  "sibling_negative_phrases": [],
  "example_sentences": [],
  "created_time_slice": "",
  "node_status": "birth|emerging|growing|mature|fragmenting|declining",
  "support_papers": [],
  "representative_papers": [],
  "counterexample_papers": [],
  "assignment_uncertainty": 0.0,
  "semantic_coherence": 0.0,
  "temporal_novelty": 0.0,
  "linked_method_entities": [],
  "dominant_bottlenecks": [],
  "dominant_mechanisms": []
}
```

### Node Enrichment

Borrowing from TaxoAdapt, every node should be enriched with:

- Distinctive key phrases.
- Example sentences likely to appear in papers about the node.
- Sibling-negative phrases that help separate nearby nodes.
- Inclusion and exclusion criteria.

This enrichment improves:

- Paper classification.
- Node boundary clarity.
- Retrieval.
- Human audit.
- Downstream method/entity extraction.

### Taxonomy Evolution Events

EvoTaxa should record explicit taxonomy-level events:

- `birth`: a new node appears.
- `split`: one node divides into multiple finer directions.
- `merge`: two nodes become semantically or empirically coupled.
- `rename`: terminology changes while concept continuity remains.
- `decline`: support or growth weakens.
- `fragmentation`: a previously coherent node develops multiple incompatible mechanisms.
- `cross_link`: two nodes become structurally connected across dimensions.

These events should be written as first-class artifacts, not inferred only from final snapshots.

```json
{
  "event_id": "",
  "event_type": "split",
  "time_slice": "",
  "source_node_ids": [],
  "target_node_ids": [],
  "support_papers": [],
  "reason": "",
  "confidence": 0.0
}
```

## 6. Layer 3: Better Expansion Triggers

The current system expands based mainly on density and unlabeled mass. EvoTaxa should use a richer trigger model.

### Trigger Signals

```text
expansion_score =
  paper_density
+ unassigned_mass
+ semantic_heterogeneity
+ assignment_uncertainty
+ temporal_burst
+ method_entity_burst
+ bottleneck_concentration
+ evaluation_shift_signal
```

### Trigger Interpretation

- High unlabeled mass: width expansion.
- Dense leaf with multiple semantic clusters: depth expansion.
- Sibling overlap: merge or alias candidate.
- Sudden new terms: birth candidate.
- Same concept under new terminology: rename candidate.
- Repeated bottleneck in a mature node: hand off to evolution graph.
- New evaluation protocol linked to a method cluster: cross-dimension link.

This prevents taxonomy growth from being driven only by paper counts.

## 7. Layer 4: Taxonomy-Conditioned Evolution Graph

This is the main upgrade inspired by methodological evolution graphs.

Instead of constructing a single global graph over the entire literature, EvoTaxa constructs local evolution graphs inside taxonomy regions.

### Why Local Graphs

Global method graph construction is expensive and noisy. Taxonomy-conditioned graph construction is more practical because taxonomy nodes:

- Limit candidate papers.
- Provide semantic context.
- Reduce pair explosion.
- Improve edge typing precision.
- Make local lineage search more meaningful.

### Graph Nodes

For AI research:

```json
{
  "method_id": "",
  "canonical_name": "",
  "aliases": [],
  "first_seen_date": "",
  "support_papers": [],
  "taxonomy_nodes": [],
  "entity_type": "architecture|training_recipe|agent_loop|retrieval_strategy|evaluation_protocol|dataset_construction|analysis_method"
}
```

For social science:

```json
{
  "mechanism_id": "",
  "canonical_name": "",
  "aliases": [],
  "first_seen_date": "",
  "support_documents": [],
  "taxonomy_nodes": [],
  "entity_type": "intervention|policy_instrument|explanatory_mechanism|measurement_strategy|institutional_response|public_frame"
}
```

### Edge Types

The core relation vocabulary is:

- `extends`: adds a capability or component.
- `improves`: optimizes an existing mechanism along a dimension.
- `replaces`: substitutes a load-bearing mechanism.
- `adapts`: ports a method/mechanism to a new task, modality, group, or context.
- `uses_component`: reuses a method/mechanism as a component.
- `compares`: cites or evaluates against another method/mechanism.
- `background`: contextual mention without methodological relation.

The strong-causal subset is:

```text
extends, improves, replaces, adapts
```

These edges drive lineage search.

### Evidence Records

Every non-background edge should carry an evidence record:

```json
{
  "edge_id": "",
  "source_entity": "",
  "target_entity": "",
  "edge_type": "improves",
  "source_paper": "",
  "target_paper": "",
  "time_delta": "",
  "bottleneck": {
    "description": "",
    "quote": "",
    "dimension": ""
  },
  "mechanism": {
    "description": "",
    "quote": ""
  },
  "tradeoff": {
    "description": "",
    "quote": ""
  },
  "confidence": 0.0,
  "substring_verified": true
}
```

The substring verification rule is important:

> If the quoted bottleneck, mechanism, or trade-off cannot be found in the source text, the edge cannot enter the trusted graph.

Unverified edges may remain in a candidate file, but they should not be used as gold evidence or high-confidence forecast hooks.

## 8. Layer 5: Taxonomy-Graph Feedback Loop

Taxonomy and evolution graph should not be independent modules.

### Taxonomy to Graph

Taxonomy provides:

- Local paper pools.
- Node paths and semantic boundaries.
- Dimension context.
- Candidate pair constraints.
- Cross-node neighborhoods.

### Graph to Taxonomy

Evolution graph provides:

- Evidence for node split.
- Evidence for node merge.
- Method/mechanism lineage inside a node.
- Bottleneck concentration signals.
- Cross-dimension dependencies.
- Node status updates.

Examples:

- If one taxonomy node contains multiple disconnected strong-causal lineages, it may need a split.
- If two sibling nodes share many method entities and edges, they may need a merge or cross-link.
- If a mature node repeatedly cites the same bottleneck but new mechanisms appear, the node may be `fragmenting`.
- If a new method entity appears across multiple slices and starts receiving adaptation edges, it may justify a new branch.

## 9. Layer 6: Lineage and Branch Search

EvoTaxa should support lineage reconstruction over the strong-causal graph.

### Minimal Version

Start with:

- confidence-weighted DFS
- temporal beam search
- branch-point extraction

### Full Version

Add self-guided temporal tree search.

Candidate prior:

```text
edge_prior =
  edge_confidence
* temporal_coherence
* taxonomy_locality
* evidence_strength
```

Chain score:

```text
chain_score =
  normalized_length
+ mean_edge_confidence
+ search_visit_score
+ bottleneck_resolution_score
+ taxonomy_trajectory_score
```

The search should return:

- ancestor chains
- successor chains
- branch points
- unresolved bottleneck paths
- replacement paths
- cross-domain adaptation paths

## 10. Forecast and Analysis Hooks

The main downstream artifact is `forecast_hooks.jsonl`.

```json
{
  "hook_id": "",
  "hook_type": "unresolved_bottleneck|successor_mechanism|replacement_path|evaluation_shift|cross_domain_adaptation|fragmenting_node",
  "taxonomy_node": "",
  "evolution_chain": [],
  "root_bottleneck": "",
  "candidate_successor": "",
  "support_edges": [],
  "support_papers": [],
  "risk_or_tradeoff": "",
  "cutoff_valid": true,
  "confidence": 0.0
}
```

These hooks can be used for:

- benchmark task construction
- research planning
- idea evaluation
- social-science mechanism analysis
- policy/intervention evolution analysis

## 11. Output Artifacts

The recommended artifact layout is:

```text
data/evotaxa/<run_id>/
  corpus/
    taxonomy_corpus.core_support.jsonl
    manifest.json
  taxonomy/
    taxonomy_nodes.enriched.json
    taxonomy_snapshot.enriched.json
    taxonomy_events.jsonl
    paper_assignments.enriched.jsonl
    node_quality_scores.jsonl
  graph/
    method_registry.jsonl
    method_aliases.jsonl
    paper_method_mentions.jsonl
    method_edges.paper_level.jsonl
    method_edges.aggregated.jsonl
    method_evidence_records.jsonl
  search/
    evolution_chains.jsonl
    branch_points.jsonl
  hooks/
    forecast_hooks.jsonl
    social_analysis_hooks.jsonl
  audit/
    unverified_edges.jsonl
    low_confidence_nodes.jsonl
    taxonomy_judge_report.json
```

## 12. Taxonomy Quality Evaluation

Borrow the TaxoAdapt judge ideas and make them production artifacts.

### Metrics

- Dimension alignment: whether a node belongs to the claimed dimension.
- Parent-child granularity: whether child nodes are genuinely more specific than parents.
- Sibling coherence: whether siblings are comparable in specificity.
- Node uniqueness: whether two nodes duplicate each other.
- Paper relevance: whether assigned papers truly belong to the node.
- Coverage: whether children cover enough of the parent paper mass.
- Temporal stability: whether a node remains coherent across slices.
- Boundary clarity: whether inclusion/exclusion criteria separate adjacent nodes.

### Output

```json
{
  "node_id": "",
  "dimension_alignment": 0.0,
  "granularity": 0.0,
  "sibling_coherence": 0.0,
  "uniqueness": 0.0,
  "paper_relevance": 0.0,
  "coverage": 0.0,
  "temporal_stability": 0.0,
  "boundary_clarity": 0.0,
  "judge_notes": ""
}
```

Nodes with poor quality scores should not seed high-confidence graph extraction or benchmark tasks without manual audit.

## 13. How EvoTaxa Improves ForeSci

### Direction Forecasting

Old form:

> Which taxonomy direction will gain momentum?

New form:

> Which mechanism-level successor path is most likely to emerge from a cutoff-visible bottleneck and lineage?

### Bottleneck-Opportunity Discovery

Old form:

> Identify one bottleneck and one opportunity.

New form:

> Identify the bottleneck-to-mechanism transition supported by typed causal edges and evidence quotes.

### Strategic Research Planning

Old form:

> Rank candidate directions.

New form:

> Rank candidates using lineage centrality, bottleneck openness, evidence strength, branch maturity, and trade-off risk.

### Venue Positioning

Old form:

> Choose venue fit and evidence upgrades.

New form:

> Use taxonomy and evolution graph to decide whether the contribution is a method innovation, evaluation innovation, adaptation, component reuse, or application contribution.

## 14. Social Science Extension

EvoTaxa can be transferred to social science by changing the entity vocabulary.

### Taxonomy Dimensions

- `social_issues`
- `actors`
- `mechanisms`
- `interventions`
- `measurement_strategies`
- `contexts`
- `outcomes`
- `public_frames`

### Evolution Graph Entities

- Policy instruments.
- Intervention designs.
- Explanatory mechanisms.
- Measurement strategies.
- Institutional responses.
- Public frames.
- Behavioral mechanisms.

### Edge Interpretation

- `extends`: adds a new component to an existing policy or mechanism.
- `improves`: improves an intervention along cost, adoption, targeting, or outcome dimensions.
- `replaces`: substitutes one mechanism or policy instrument for another.
- `adapts`: ports an intervention to a new population, region, or institution.
- `uses_component`: borrows a submechanism.
- `compares`: empirically compares interventions.
- `background`: contextual mention.

### Example Analyses

- How misinformation research shifted from content moderation to platform governance and inoculation interventions.
- How polarization research moved from survey-based attitude measurement to social-network and platform-mediated mechanisms.
- How AI governance evolved from model-risk framing to institutional accountability, auditing, and regulatory design.
- How education inequality interventions moved from resource access to learning analytics, tutoring, and family/community mechanisms.

## 15. Implementation Roadmap

### Phase 1: Taxonomy Upgrade

Goal: improve taxonomy quality before adding a graph layer.

Tasks:

- Add node enrichment.
- Add inclusion/exclusion criteria.
- Add node-level quality judge.
- Add explicit taxonomy event artifacts.
- Add low-confidence and overlap reports.

Deliverables:

```text
taxonomy_nodes.enriched.json
taxonomy_events.jsonl
node_quality_scores.jsonl
taxonomy_judge_report.json
```

### Phase 2: MEG-Lite

Goal: build a local method evolution graph for one domain.

Recommended pilot domain:

```text
llm_agent
```

Scope:

- Only `methodologies` and `evaluation_methods`.
- Only cutoff-visible papers.
- Use title, abstract, and available full text.
- Start with node-local candidate pairs before global citation resolution.

Deliverables:

```text
method_registry.jsonl
paper_method_mentions.jsonl
method_edges.paper_level.jsonl
method_evidence_records.jsonl
```

### Phase 3: Evolution Hooks

Goal: convert graph structure into forecast/task candidates.

Tasks:

- Extract branch points.
- Extract unresolved bottlenecks.
- Extract successor mechanisms.
- Extract replacement/adaptation paths.
- Build `forecast_hooks.jsonl`.

Deliverables:

```text
evolution_chains.jsonl
branch_points.jsonl
forecast_hooks.jsonl
```

### Phase 4: Search Upgrade

Goal: replace simple lineage search with self-guided temporal search.

Tasks:

- Implement temporal coherence scoring.
- Add graph-aware priors.
- Add branch re-search with masked visited edges.
- Compare with beam search and greedy DFS.

Deliverables:

```text
lineage_search_results.jsonl
lineage_search_eval.json
```

### Phase 5: ForeSci Integration

Goal: improve benchmark construction.

Tasks:

- Generate task candidates from `forecast_hooks.jsonl`.
- Compare old task candidates and EvoTaxa candidates.
- Evaluate expert preference, traceability, and hidden-target alignment.

Deliverables:

```text
evotaxa_task_candidates/
evotaxa_vs_old_task_quality_report.md
```

### Phase 6: Social Science Pilot

Goal: prove cross-domain analysis value.

Candidate domains:

- AI governance.
- Misinformation.
- Political polarization.
- Education inequality.
- Platform labor.

Deliverables:

```text
social_taxonomy_nodes.enriched.json
social_mechanism_edges.jsonl
social_analysis_hooks.jsonl
case_study_report.md
```

## 16. Engineering Plan

Recommended new modules:

```text
src/evotaxa/
  taxonomy_enrichment.py
  taxonomy_judge.py
  taxonomy_events.py
  graph_entities.py
  graph_edges.py
  evidence_validation.py
  lineage_search.py
  hook_generation.py
```

Recommended scripts:

```text
scripts/evotaxa/enrich_taxonomy_nodes.py
scripts/evotaxa/judge_taxonomy_quality.py
scripts/evotaxa/build_taxonomy_events.py
scripts/evotaxa/extract_method_entities.py
scripts/evotaxa/build_method_edges.py
scripts/evotaxa/validate_evidence_records.py
scripts/evotaxa/search_evolution_chains.py
scripts/evotaxa/build_forecast_hooks.py
```

## 17. Evaluation Plan

### Taxonomy Evaluation

Compare:

- Current ResearchForesight taxonomy.
- ResearchForesight + node enrichment.
- ResearchForesight + node enrichment + taxonomy judge pruning.

Metrics:

- Alignment.
- Granularity.
- Sibling coherence.
- Uniqueness.
- Paper relevance.
- Coverage.
- Human audit pass rate.

### Graph Evaluation

Compare:

- Cue-based method evolution assets.
- Taxonomy-conditioned MEG-lite.
- MEG-lite with evidence verification.
- MEG-lite plus temporal lineage search.

Metrics:

- Edge type accuracy.
- Evidence verification rate.
- Bottleneck quote validity.
- Human-rated lineage coherence.
- Forecast hook usefulness.

### Downstream Evaluation

Compare:

- Existing ForeSci task candidates.
- EvoTaxa-generated task candidates.

Metrics:

- Expert preference.
- Traceability.
- Hidden future-target alignment.
- Reduction in evidence-decision drift.
- Improved bottleneck/opportunity specificity.

## 18. Paper Positioning

Possible title:

> EvoTaxa: Cutoff-Aware Taxonomy-Guided Evolution Modeling for Scientific and Social Foresight

Main positioning:

> TaxoAdapt adapts taxonomies to evolving corpora. Methodological evolution graphs expose typed method lineages. EvoTaxa unifies these ideas under temporal cutoff constraints: taxonomy snapshots localize the evolving structure, and evidence-grounded evolution graphs explain the mechanism-level transitions inside that structure.

Core contributions:

1. A cutoff-aware enriched temporal taxonomy framework.
2. A taxonomy-conditioned evolution graph construction method.
3. Evidence-grounded bottleneck-mechanism-tradeoff records for evolution edges.
4. A taxonomy-graph feedback loop for split, merge, birth, rename, and fragmentation events.
5. Downstream use in foresight task construction and social science mechanism/intervention analysis.

## 19. Immediate Next Steps

Recommended first implementation target:

```text
Domain: llm_agent
Cutoff: existing ResearchForesight cutoff
Dimensions: methodologies, evaluation_methods
Goal: build MEG-lite and forecast_hooks.jsonl
```

Minimal deliverable:

1. Enrich existing taxonomy nodes.
2. Judge node quality.
3. Extract method entities from node-local papers.
4. Build typed candidate edges for high-confidence pairs.
5. Verify bottleneck/mechanism/tradeoff quotes.
6. Produce 20-50 forecast hooks.
7. Manually audit whether hooks are better than current cue-based method evolution assets.

This is the shortest path to showing that EvoTaxa is a real algorithmic upgrade rather than a rebranding.
