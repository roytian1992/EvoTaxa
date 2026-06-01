# Computational Social Science Node Design

## Purpose

For the OpenAlex computational-social-science corpus, taxonomy nodes should define medium-grained method ecologies rather than individual algorithms or broad theories.

In EvoTaxa, a node is not just a label. It is the local evolution space used for document assignment, entity co-location, edge construction, temporal windows, state summaries, and macro-pattern evidence. If nodes are too broad, unrelated methods create noisy edges. If nodes are too narrow, trajectories fragment before there is enough evidence.

## Current Recommendation

Use one taxonomy dimension, `methods`, with 13 medium-grained nodes:

- Digital Trace Data
- Text-as-Data / Computational Text Analysis
- Network Analysis
- Causal Inference & Experiments
- Agent-Based Modeling / Social Simulation
- LLM-Assisted Social Science Methods
- Reproducibility / Ethics / Data Governance
- Spatial / GIS / Geocomputation
- Survey / Administrative / Population Data Systems
- Machine Learning / AI Classification
- Bibliometrics / Knowledge Mapping
- Online Interaction / Social Media Methods
- Computational Infrastructure / Algorithms

This design keeps nodes interpretable while covering most screened core records. It intentionally allows overlap: for example, a paper can be both `Text-as-Data` and `Online Interaction`, or both `LLM-Assisted Methods` and `Machine Learning / AI Classification`.

## Evidence

Using `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/merged/corpus.screened.jsonl`:

- Loaded documents: 4,126
- Node count: 13
- Documents assigned to at least one node: 3,311
- Unassigned documents: 815
- Coverage: 80.2%

The largest nodes are:

- Online Interaction / Social Media Methods: 1,021 assigned documents
- Machine Learning / AI Classification: 1,006
- Text-as-Data / Computational Text Analysis: 881
- Computational Infrastructure / Algorithms: 763
- LLM-Assisted Social Science Methods: 578
- Reproducibility / Ethics / Data Governance: 520

Low-support nodes, especially `Spatial / GIS / Geocomputation` and `Bibliometrics / Knowledge Mapping`, should be reviewed after more corpus expansion or after checking whether their aliases are too strict.

## Implementation Notes

- The OpenAlex CSS config now points to the screened core corpus.
- The output root for the current runnable baseline is `examples/openalex_css_methods_screened_clean_entities_v1_output`.
- Taxonomy assignment now uses phrase-boundary matching rather than raw substring matching, preventing short aliases such as `GPT` from matching inside unrelated words.
- Entity quality filtering now removes academic transition phrases such as `in this work`, `in recent years`, `for this purpose`, and `on the other hand`.
- Candidate document pairs are capped during generation, not after full cartesian expansion, so high-frequency entities no longer stall full runs.

## Baseline Run

The current full run completed on the screened corpus with:

- Documents: 4,126
- Taxonomy nodes: 13
- Entities: 519
- Mentions: 7,220
- Paper-level edges: 2,885
- Trusted edges: 127
- Candidate edges: 2,758
- Trajectories: 589
- Macro pattern profiles: 9
- Temporal windows: 169
- Overall quality score: 0.659

The pipeline is therefore runnable, but the low trusted-edge rate indicates that relation semantics and evidence auditing are the next quality bottleneck.

## Next Steps

1. Audit a stratified sample of trusted and candidate edges.
2. Tighten relation cues, especially `replaces`, `adapts`, and `improves`.
3. Consider enabling a small Qwen-assisted relation audit on high-value edge samples rather than all pairs.
4. Decide whether unassigned documents should remain outside local node evolution spaces or receive a catch-all/induced node in a later run.
