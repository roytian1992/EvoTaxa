# Adaptive Temporal Windows

## Scope

Adaptive temporal windows are a micro-level timing layer. They do not replace document dates, yearly chronology slices, trajectories, or macro pattern timelines.

The goal is to avoid forcing every domain into a global monthly or yearly bucket. Dense topics can produce short evidence windows; sparse topics can produce long windows.

## Time Layers

EvoTaxa now uses three complementary time views:

- `published_at`: document-level date used for temporal ordering, edge `time_delta_days`, edge scoring, and trajectory coherence.
- `chronology_slice`: configured corpus slice used for state summaries and macro timeline aggregation. The OpenAlex computational-social-science corpus currently uses year-level slices.
- adaptive temporal windows: evidence-density windows built per scope after entities, mentions, edges, and trajectories are available.

## Output Files

When `temporal_windows.enabled = true`, `run-full` writes:

- `temporal_windows/micro_windows.jsonl`: one row per adaptive window.
- `temporal_windows/window_assignments.jsonl`: event-to-window assignments.
- `temporal_windows/window_summary.json`: run-level counts and configuration.

The same paths are listed in `manifest.json`.

## Window Scopes

Supported scopes:

- `global`: document evidence across the whole corpus.
- `taxonomy_node`: mention evidence within each taxonomy node.
- `entity_type`: mention evidence within each entity type.
- `relation_type`: edge evidence within each relation type.

Each scope is windowed independently. This is the important part: `LLM annotation` can form short windows in 2023-2026 while a slower-moving method family keeps multi-year windows.

## Closing Rules

A window closes when either:

- the scope accumulates enough documents, mentions, or edges and has lasted at least `min_duration_days`; or
- it reaches `max_duration_days`.

The final partial window is kept so late-stage evidence is still visible.

## Config

```toml
[temporal_windows]
enabled = true
scope_types = ["global", "taxonomy_node", "entity_type", "relation_type"]
min_documents_per_window = 500
min_mentions_per_window = 800
min_edges_per_window = 250
min_duration_days = 30
max_duration_days = 1095
```

Small fixture configs use lower thresholds so smoke tests produce visible windows.

## Interpretation

These windows are evidence windows, not historical periods. They are best used for micro-level change detection, local burstiness, and deciding where to inspect trajectories or relation shifts. Macro narratives should still be read from stable state, trajectory, and macro pattern artifacts after real-corpus validation.
