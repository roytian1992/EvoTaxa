# Macro Pattern Synthesis

## Scope

The macro pattern synthesis layer is an optional second-level view over existing EvoTaxa outputs. It estimates domain-level evolution patterns from detector-backed evidence; it does not replace the micro layer of quote-grounded entities, relations, state transitions, and trajectories.

The layer should be treated as exploratory until the state and trajectory artifacts are stable on at least one real social-science corpus. Fixture outputs are implementation checks, not research conclusions.

## Output Files

The layer is disabled by default. When `macro_patterns.enabled = true` and `run-full` is used, EvoTaxa writes:

- `macro_patterns/pattern_profiles.jsonl`: one row per reported macro pattern.
- `macro_patterns/pattern_evidence.jsonl`: detector evidence records linked back to micro artifacts.
- `macro_patterns/pattern_timeline.jsonl`: visualization-friendly pattern scores by time slice.
- `macro_patterns/pattern_summary.json`: run-level counts and configuration.

The same paths are exposed through `manifest.json` under `artifact_layout`.

## Pattern Detectors

The first implementation includes detectors for:

- differentiation
- convergence
- hybridization
- recontextualization
- cyclical return
- institutionalization
- substitution
- fragmentation
- stabilization

The detectors use existing EvoTaxa artifacts:

- taxonomy events
- state snapshot and state transitions
- evolution trajectories
- relation edge scores
- schema revisions
- relation rejection records
- temporal node support

Each profile includes visualization-oriented fields: `time_span`, `representative_node_ids`, `representative_nodes`, `representative_trajectories`, `pattern_score`, `evidence_ids`, and `explanation`.

## LLM Boundary

LLM use is optional through `macro_patterns.llm_summary_enabled`. If enabled, the LLM receives already detected pattern profiles and evidence records and can only summarize that evidence. It must not create pattern ids, scores, nodes, trajectories, or evidence ids from scratch.

## Config

```toml
[macro_patterns]
enabled = true
min_pattern_score = 0.2
max_patterns = 20
max_evidence_per_pattern = 8
use_negative_evidence = true
llm_summary_enabled = false
```

If the section is omitted, `enabled` defaults to `false`.

## Ablations

Macro pattern interpretation is covered by ablation variants:

- `no_coevolution`: disables taxonomy-graph coevolution.
- `no_schema_adaptation`: locks entity, relation, and evidence schema modes to fixed.
- `no_negative_evidence`: removes rejected relation records from macro pattern synthesis.

These ablations are intended to show how pattern profiles change when important micro-level signals are removed.
