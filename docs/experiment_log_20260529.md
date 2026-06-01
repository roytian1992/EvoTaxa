# Experiment Log 2026-05-29

## Scope

- Project: EvoTaxa
- Purpose: Add optional macro pattern synthesis over existing state, trajectory, taxonomy, schema, edge, and negative-evidence artifacts.
- Status: Implemented and smoke-tested on fixture corpora.

## Inputs

- Code path: `/vepfs-mlp2/c20250513/241404044/users/roytian/EvoTaxa`
- Configs:
  - `configs/social_science.example.toml`
  - `configs/social_misinformation_governance.adaptive.toml`
- Baseline handoff: `docs/HANDOFF_20260529_evotaxa_next_steps.md`

## Commands

```bash
cd /vepfs-mlp2/c20250513/241404044/users/roytian/EvoTaxa
pytest -q
PYTHONPATH=src python -m evotaxa.cli run-full --config configs/social_science.example.toml --print-manifest
```

## Outputs

- Output directories used by tests:
  - `examples/social_smoke_output`
  - `examples/misinformation_governance_adaptive_output`
  - `examples/social_ablation_smoke_output`
  - `examples/social_no_expansion_smoke_output`
  - `examples/social_macro_ablation_smoke_output`
- New macro artifacts:
  - `macro_patterns/pattern_profiles.jsonl`
  - `macro_patterns/pattern_evidence.jsonl`
  - `macro_patterns/pattern_timeline.jsonl`
  - `macro_patterns/pattern_summary.json`

## Counts And Metrics

- Raw count: fixture-dependent; no real OpenAlex corpus was added in this session.
- Filtered count: not applicable.
- Completed count: 25 tests plus one targeted full pipeline CLI run.
- Evaluated count: 25 tests plus one targeted full pipeline CLI run.
- Key metrics: `pytest -q` reported `25 passed in 2.09s`; targeted social fixture full run reported 7 macro patterns, 53 macro evidence records, and 7 timeline rows.

## Changes

- Files changed:
  - `src/evotaxa/config.py`
  - `src/evotaxa/llm.py`
  - `src/evotaxa/macro_patterns.py`
  - `src/evotaxa/pipeline.py`
  - `src/evotaxa/ablation.py`
  - `tests/test_smoke.py`
  - `configs/social_science.example.toml`
  - `configs/social_misinformation_governance.adaptive.toml`
  - `docs/macro_pattern_synthesis.md`
  - `docs/experiment_log_20260529.md`
- Data/release changes: none.
- Backup status: no external backup or commit was requested.

## Trajectory

### 2026-05-29 20:01 CST - Macro Pattern Synthesis

- Goal: Implement the planned macro pattern layer while keeping it optional and detector-backed.
- Starting point: Handoff stated macro pattern synthesis was planned but should wait for stable real-corpus state and trajectory artifacts before being used as a research conclusion.
- Actions taken: Added `MacroPatternConfig`, deterministic detectors for differentiation, convergence, hybridization, recontextualization, cyclical return, institutionalization, substitution, fragmentation, and stabilization; wired full pipeline outputs; added optional LLM summarization constrained to detector evidence; extended ablation variants and tests.
- Decisions or rationale: The implementation estimates macro differences from existing micro artifacts instead of imposing a single evolution theory. LLM cannot generate profiles from scratch.
- Verified facts: `pytest -q` passed with 25 tests; direct `python -m evotaxa.cli` required `PYTHONPATH=src` because the package was not installed editable in this shell.
- Outputs or changed paths: macro pattern artifacts are written under `macro_patterns/` and listed in `manifest.json`.
- Problems or dead ends: Initial ablation test confused taxonomy coevolution revisions with schema revisions; fixed by adding `schema_revisions` to ablation summary.
- Current state: Fixture-level implementation is stable. Results are not yet a real social-science empirical finding.
- Next steps: Run the OpenAlex computational-social-science corpus, inspect state and trajectory stability, then evaluate whether macro pattern profiles are substantively meaningful.

### 2026-05-29 20:38 CST - OpenAlex CSS Methods Sizing

- Goal: Find a data-rich real scenario and estimate the maximum currently available OpenAlex corpus size.
- Starting point: The selected scenario is `computational_social_science_methods`, using OpenAlex `title_and_abstract.search` from 1990-01-01 to 2026-12-31 with `has_abstract:true` and `is_retracted:false`.
- Actions taken: Added `scripts/download_openalex_corpus.py`, a seed taxonomy at `configs/computational_social_science_methods.taxonomy.json`, and a baseline config at `configs/computational_social_science_methods.openalex.toml`; ran OpenAlex count-only union sizing.
- Decisions or rationale: Count-only sizing downloads only work ids/year/type/query buckets, not full abstracts, so it can estimate scale cheaply before downloading the full text-bearing corpus.
- Verified facts: The 12 query buckets have 41,293 has-abstract hits before deduplication and 25,206 deduplicated OpenAlex works in union.
- Outputs or changed paths:
  - Sizing manifest: `data/openalex/computational_social_science_methods_sizing/openalex_union_manifest.json`
  - Sizing ids: `data/openalex/computational_social_science_methods_sizing/openalex_union_ids.jsonl`
  - Pilot corpus: `data/openalex/computational_social_science_methods/corpus.jsonl`
  - Pilot raw records: `data/openalex/computational_social_science_methods/openalex_raw.jsonl`
- Problems or dead ends: A 1,500-document pilot full run completed but showed entity noise and low trusted-edge rate; it should be treated as a systems smoke run, not as a research result.
- Current state: Maximum immediately usable OpenAlex abstract corpus for the current bucket set is 25,206 deduplicated works. The next step is to download this full union corpus and process it in scalable stages.
- Next steps: Use `--count-only` manifest to drive a full union download, then run staged EvoTaxa passes: metadata/taxonomy assignment first, graph extraction with stricter entity filters second, macro patterns last.

### 2026-05-29 21:20 CST - OpenAlex Full Corpus Download

- Goal: Download the full title+abstract corpus for the current computational-social-science methods query set with resumable paging.
- Starting point: Count-only sizing estimated 25,206 deduplicated OpenAlex works from 41,293 has-abstract query hits.
- Actions taken: Upgraded `scripts/download_openalex_corpus.py` to write each successful API page under `pages/`, maintain `download_state.json`, and finalize by merging pages into normalized `corpus.jsonl` plus `openalex_raw.jsonl`; launched the full download.
- Decisions or rationale: Page-level raw files plus state make the download resumable. Re-running the same command skips completed queries and resumes the current cursor.
- Verified facts: Full download completed with all 12 query buckets marked `complete`; final normalized corpus has 25,063 rows and raw records have 25,063 rows.
- Outputs or changed paths:
  - Corpus: `data/computational_social_science/corpus.jsonl`
  - Raw records: `data/computational_social_science/openalex_raw.jsonl`
  - Manifest: `data/computational_social_science/manifest.json`
  - Resume state: `data/computational_social_science/download_state.json`
  - Page cache: `data/computational_social_science/pages/`
  - Dataset documentation: `docs/computational_social_science_dataset.md`
- Problems or dead ends: A small resume smoke test initially repeated the first page because the cursor variable was not updated after writing state; fixed before full download.
- Current state: Full title+abstract corpus is available locally. The relevance filter removed 268 low-relevance rows and 14 rows were missing title or abstract at normalization time.
- Next steps: Point a full-corpus EvoTaxa config at `data/computational_social_science/corpus.jsonl`, then run staged processing with stricter entity filters and graph caps.

### 2026-05-29 22:13 CST - Qwen Local LLM Debug Run

- Goal: Connect the local OpenAI-compatible Qwen endpoint to EvoTaxa and verify which LLM-assisted algorithm stages are usable for debugging.
- Starting point: Local endpoint at `http://127.0.0.1:8001/v1` advertised model `Qwen3.5-397B-A17B-FP8` through `/v1/models`; the provided API key was used only through `EVOTAXA_LLM_API_KEY` and was not written into config files.
- Actions taken: Added `configs/qwen_local_llm.example.toml`; added optional `LLMConfig.max_tokens` support for future controlled probes but left the Qwen debug config uncapped; improved JSON parse errors with `finish_reason` and content excerpts; added configurable `graph.llm_taxonomy_judge_limit`; changed the Qwen debug config to fixed schema, limited entity/taxonomy/relation calls, and disabled `edge_evidence_judge` for the main smoke run.
- Decisions or rationale: Full adaptive schema inference and edge evidence judging were too slow for this shared endpoint in a broad full-pipeline smoke run. The debug config now exercises entity extraction, taxonomy candidate judging, and relation extraction without imposing an output token cap or letting expensive stages dominate algorithm iteration.
- Verified facts: A direct entity extraction probe returned valid JSON. `validate-config` passed for `configs/qwen_local_llm.example.toml`. Final full fixture run completed at `examples/qwen_local_llm_output` with 4 documents, 11 entities, 10 accepted LLM entity mentions, 4 final relation pairs, 2 accepted LLM relation edges, 48 trusted edges, 235 trajectories, 7 macro patterns, and overall quality score 0.747.
- Outputs or changed paths:
  - Config: `configs/qwen_local_llm.example.toml`
  - Output manifest: `examples/qwen_local_llm_output/manifest.json`
  - LLM audit: `examples/qwen_local_llm_output/audit/llm_judge_records.jsonl`
  - Relation report: `examples/qwen_local_llm_output/graph/relation_extraction_report.jsonl`
- Problems or dead ends: Early full runs appeared to hang while waiting on model responses, likely because the shared service was busy rather than because EvoTaxa needed an output cap. A temporary `max_tokens=256` test truncated relation batch JSON and produced parse failures, so the main Qwen config now avoids `max_tokens`. `edge_evidence_judge` also stalled in an earlier run and remains disabled in the main Qwen debug config pending isolated prompt reduction.
- Current state: Qwen is usable for fixture-scale entity extraction, taxonomy candidate judging, and relation batch extraction. It is not yet configured for full OpenAlex-scale per-document LLM extraction or edge-evidence judging.
- Next steps: For `data/computational_social_science/corpus.jsonl`, run staged non-LLM/rule-heavy passes first, then selectively enable Qwen on sampled documents, candidate relation batches, or high-value audit slices. Keep adaptive schema and edge evidence prompts as separate targeted probes before enabling them in a large run.

### 2026-05-29 22:35 CST - Adaptive Micro Temporal Windows

- Goal: Replace the idea of global monthly micro slices with optional evidence-density windows that can vary by topic, entity type, and relation type.
- Starting point: EvoTaxa already had `published_at` for temporal ordering and `chronology_slice` for state/macro aggregation. The OpenAlex CSS corpus currently uses year-level chronology slices, which is too coarse for local bursts but cleaner for macro summaries.
- Actions taken: Added `TemporalWindowConfig`, `src/evotaxa/temporal_windows.py`, and pipeline outputs under `temporal_windows/`; enabled the layer in social, adaptive, Qwen, and OpenAlex CSS configs with fixture-scale and OpenAlex-scale thresholds; added smoke coverage and documentation in `docs/temporal_windows.md`.
- Decisions or rationale: Windows close when a scope accumulates enough document, mention, or edge evidence, or when `max_duration_days` is reached. Each scope is windowed independently, so dense themes can form short windows while sparse themes keep long windows.
- Verified facts: Targeted tests passed for adaptive temporal window closure and full pipeline artifact writing. `validate-config` passed for `configs/computational_social_science_methods.openalex.toml`.
- Outputs or changed paths:
  - Code: `src/evotaxa/temporal_windows.py`, `src/evotaxa/config.py`, `src/evotaxa/pipeline.py`
  - Configs: `configs/social_science.example.toml`, `configs/social_misinformation_governance.adaptive.toml`, `configs/qwen_local_llm.example.toml`, `configs/computational_social_science_methods.openalex.toml`
  - Docs: `docs/temporal_windows.md`
  - Pipeline artifacts: `temporal_windows/micro_windows.jsonl`, `temporal_windows/window_assignments.jsonl`, `temporal_windows/window_summary.json`
- Problems or dead ends: None in fixture tests. OpenAlex thresholds are initial guesses and should be tuned after the first full-corpus run by inspecting window counts and mean duration.
- Current state: Dynamic micro windows are optional, manifest-visible, and do not replace existing dates, year slices, trajectories, or macro pattern timelines.
- Next steps: Run the OpenAlex CSS config and inspect `temporal_windows/window_summary.json` before interpreting local bursts or macro patterns.

### 2026-05-29 22:48 CST - Relevance Screening Spot Check

- Goal: Check whether the current OpenAlex CSS corpus is mostly truly relevant before deciding whether to add an LLM-based relevance filter.
- Starting point: The corpus already had OpenAlex query filters, local rule-based relevance filtering, title/abstract requirements, deduplication, and `role = core` loader filtering.
- Actions taken: Sampled 12 random records from `data/computational_social_science/corpus.jsonl` with seed `20260529` and manually reviewed title/abstract snippets.
- Decisions or rationale: The sample showed substantial boundary noise, so a second-stage filter is justified before treating the full corpus as core CSS methods evidence.
- Verified facts: The sample split was approximately 3 core, 5 peripheral, and 4 exclude. Examples of noise included HIV policy/access, eHealth scoping review, precision psychiatry, and literary/anthropological text studies.
- Outputs or changed paths: `docs/relevance_screening_audit_20260529.md`
- Problems or dead ends: The existing rule filter catches obvious low-relevance rows but is too permissive for broad query buckets and generic terms like method, data, text, social, and model.
- Current state: The dataset is good for broad discovery but not clean enough for final empirical interpretation without a second-stage screening label.
- Next steps: Add a calibrated screening layer with `core`, `peripheral`, and `exclude` decisions, ideally with LLM assistance plus sampled manual audit.

### 2026-05-29 23:12 CST - Generic Relevance Screening Tool

- Goal: Add LLM-capable relevance screening without making it part of the EvoTaxa main evolution pipeline.
- Starting point: User clarified that screening code should be generic, prompt templates should be separately managed, and different domains should provide different rubrics.
- Actions taken: Added `scripts/screen_relevance.py`, generic prompt `prompts/relevance_screening.md`, domain rubric `configs/relevance_domains/computational_social_science_methods.toml`, and model config `configs/llm/qwen_local.toml`; moved screening docs to `docs/relevance_screening.md`.
- Decisions or rationale: `run-full` remains unchanged. Screening produces a separate `corpus.screened.jsonl`; the main EvoTaxa config should point to that file when the user wants a screened corpus.
- Verified facts: Early rules pilot on 200 rows completed with 12 core, 68 peripheral, and 120 exclude, exposing keyword-noise boundaries. LLM pilot on 3 rows completed with 0 core, 1 peripheral, 2 exclude, 3 model-used records, and 0 errors.
- Outputs or changed paths:
  - Script: `scripts/screen_relevance.py`
  - Generic prompt: `prompts/relevance_screening.md`
  - Domain rubric: `configs/relevance_domains/computational_social_science_methods.toml`
  - LLM config: `configs/llm/qwen_local.toml`
  - Pilot outputs: `data/computational_social_science_screening/rules_pilot_200_v2/`, `data/computational_social_science_screening/llm_pilot_3_v2/`
- Problems or dead ends: The initial combined rubric+LLM config design was too coupled and was replaced. The local Qwen service is shared and can be slow, but decisions are appended incrementally and resumable.
- Current state: Screening is a reusable pre-processing tool with separated code, prompt, domain rubric, and model connection.
- Next steps: Run a larger LLM screening pilot, manually audit a stratified sample of `core`, `peripheral`, and `exclude`, then decide whether to run the full 25k corpus.

### 2026-05-29 23:58 CST - Relevance Core Calibration

- Goal: Recalibrate `core` after inspecting pilot decisions and deciding that core should mean usable EvoTaxa evidence, not only pure method-development papers.
- Starting point: The generic prompt said to use `core` only for strong domain evidence. Early rules-mode pilots were useful for exposing keyword noise but were not acceptable as the formal relevance classifier.
- Actions taken: Relaxed the generic prompt and CSS rubric so applied social-science studies can be core when title/abstract explicitly describe computational method or data practice; removed the rules execution path from `scripts/screen_relevance.py`; made the screener require an LLM config; added schema validation for the `relevance_screening` task in `src/evotaxa/llm.py`; added a run signature so resume only reuses decisions produced by the same prompt, rubric, and LLM settings.
- Decisions or rationale: Formal screening must use LLM decisions rather than rules. Generic terms such as method, model, data, text, social, or research should not create core labels by themselves, and LLM failures should become `llm_error` rather than silently falling back to rule labels.
- Verified facts: `python3 -m py_compile scripts/screen_relevance.py src/evotaxa/llm.py` passed. Missing `--llm-config` now exits with an argparse error. LLM-only smoke at `data/computational_social_science_screening/llm_pilot_1_calibrated_no_rules_offset120/` screened 1 row, used the model, returned 1 core, and had 0 errors; the decision record contains no `rule_*` fields.
- Outputs or changed paths:
  - Script: `scripts/screen_relevance.py`
  - Generic prompt: `prompts/relevance_screening.md`
  - Domain rubric: `configs/relevance_domains/computational_social_science_methods.toml`
  - Docs: `docs/relevance_screening.md`
  - Pilot output: `data/computational_social_science_screening/llm_pilot_1_calibrated_no_rules_offset120/`
- Problems or dead ends: Earlier rules pilots promoted catalog/proceedings or metadata-driven records and are superseded by the LLM-only screening path.
- Current state: `core` is now defined as usable domain evidence for EvoTaxa, including explicit applied method/data papers. LLM screening is the only supported classifier path in `scripts/screen_relevance.py`.
- Next steps: Run a larger LLM pilot with the calibrated prompt/rubric and manually audit a stratified sample before launching full 25k screening.

### 2026-05-30 00:15 CST - Screening Cleaning And Repair

- Goal: Combine relevance screening with abstract cleaning, and make LLM JSON handling robust enough for long resumable runs.
- Starting point: Screening was LLM-only and resumable, but it passed raw OpenAlex abstracts to the prompt. Some abstracts contained web navigation, DOI/tool menus, citation lists, repeated titles, and other page artefacts. LLM JSON parsing used strict `json.loads` only.
- Actions taken: Added `src/evotaxa/content_cleaning.py`; integrated title/abstract cleaning into `scripts/screen_relevance.py`; added `cleaning_records.jsonl`, cleaning summary counts, and `raw_abstract` preservation in screened corpus rows; added `json-repair` as a project dependency; updated `src/evotaxa/llm.py` to attempt `json.loads`, then `json_repair`, then schema validation and retry; increased `configs/llm/qwen_local.toml` `max_retries` to 3.
- Decisions or rationale: Cleaning should happen before relevance judgment because noisy abstracts can change both relevance and score. Repair and retry should live in the shared LLM client so relation/entity/schema tasks also benefit.
- Verified facts: `json-repair` is installed in the conda Python used for EvoTaxa (`0.58.7`). `py_compile` passed for `scripts/screen_relevance.py`, `src/evotaxa/llm.py`, and `src/evotaxa/content_cleaning.py`. Targeted tests passed: `tests/test_relevance_screening.py` and `tests/test_smoke.py::test_qwen_local_llm_config_uses_env_key_without_token_limit`. A real Qwen smoke at `data/computational_social_science_screening/llm_pilot_1_cleaning_offset48/` cleaned `W2020859734` from 9,360 to 169 abstract characters, removed 9,191 characters, and returned `exclude` with 0 errors, 0 repaired outputs, and 0 retries. A missing-key dry run produced `llm_error` and no screened corpus.
- Outputs or changed paths:
  - Code: `src/evotaxa/content_cleaning.py`, `scripts/screen_relevance.py`, `src/evotaxa/llm.py`
  - Dependency: `pyproject.toml`
  - Config: `configs/llm/qwen_local.toml`
  - Tests: `tests/test_relevance_screening.py`
  - Docs: `docs/relevance_screening.md`
- Problems or dead ends: The system `python3` does not have `pip`; the conda Python used for runs already has `json-repair`. The dependency is now declared in `pyproject.toml` for reproducible installs.
- Current state: Screening now cleans input text before prompting and records cleaning/repair metadata. The screened corpus uses cleaned `abstract` and `text`, preserves the original abstract as `raw_abstract`, and includes `content_cleaning` metadata.
- Next steps: Run a small LLM pilot with cleaned abstracts, inspect `cleaning_records.jsonl`, then proceed to a larger screened-corpus pilot.

### 2026-05-30 00:24 CST - Full Screening Launch

- Goal: Launch LLM relevance screening for the full 25,063-row OpenAlex computational-social-science corpus with cleaned abstracts, JSON repair, and resumable shard outputs.
- Starting point: Input corpus was `data/computational_social_science/corpus.jsonl`; rubric was `configs/relevance_domains/computational_social_science_methods.toml`; prompt was `prompts/relevance_screening.md`; LLM config was `configs/llm/qwen_local.toml` against local Qwen service `http://127.0.0.1:8001/v1`.
- Actions taken: Added `scripts/screening_status.py` and `scripts/merge_screening_shards.py`; launched 16 tmux workers named `evotaxa_screen_0` through `evotaxa_screen_15`; each shard writes to `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/shards/shard_XX`.
- Decisions or rationale: Sharding keeps JSONL writes independent while preserving per-shard resume. The resume cache now retries `llm_error` rows by default so transient service failures are not treated as stable relevance labels; `--cache-errors` can keep old failures when intentionally needed.
- Verified facts: All 16 tmux sessions were running after launch. Status at 00:30 CST showed 177 completed decisions: 35 `core`, 47 `peripheral`, 95 `exclude`, 0 `llm_error`, 0 repaired outputs, and 0 retried outputs. `pytest -q tests/test_relevance_screening.py` passed with 3 tests.
- Outputs or changed paths:
  - Run root: `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/`
  - Shards: `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/shards/shard_00` through `shard_15`
  - Logs: `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/logs/shard_*.log`
  - Launch command: `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/launch_16_workers.sh`
  - Docs: `docs/relevance_screening.md`
- Commands:
  - `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/launch_16_workers.sh`

### 2026-05-30 22:24 CST - Strict Evolution Dashboard Edge Scope

- Goal: Fix the visualization so the evolution graph shows only evolution edges, not generic trusted/candidate relations.
- Starting point: The dashboard used `graph/method_edges.trusted.jsonl` directly. Those edges were evidence-stratified relation candidates, not all valid temporal evolution links; in the 200-document pilot they included cross-type and same-time relations.
- Actions taken: Updated `scripts/build_evolution_visualization.py` so embedded dashboard edges are restricted to same entity type with `time_delta_days > 0`; restricted trajectories, pattern links, temporal-window representative edges, yearly edge counts, and node degree to the same strict edge set. Updated `scripts/serve_evolution_dashboard.py` so node detail incident edges come only from the strict dashboard payload.
- Decisions or rationale: `trusted` remains an internal audit tier, but the user-facing evolution view now uses a stricter display contract: source and target must be comparable node types and target evidence must be later than source evidence.
- Verified facts: `python -m py_compile scripts/build_evolution_visualization.py scripts/serve_evolution_dashboard.py` passed. API check at `http://127.0.0.1:8765/api/data` returned 40 strict evolution edges for the 200-document LLM pilot with 0 type/time violations and 45 trajectories with no missing edge references. The 4,126-core deterministic run summary now reports 10 strict evolution edges and 11 strict trajectories.
- Outputs or changed paths:
  - Code: `scripts/build_evolution_visualization.py`, `scripts/serve_evolution_dashboard.py`
  - Pilot static page: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/run_output_no_thinking/visualization/evolution_dashboard.html`
  - 4,126-core static page: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/main_run_output_entity_grounding_v4_one_sided_current/visualization/evolution_dashboard.html`
  - Backend: tmux session `evotaxa_dashboard`, URL `http://127.0.0.1:8765/`
- Problems or dead ends: The stricter display exposes that the current relation extraction produces few defensible evolution edges, especially in the deterministic 4,126-core run. This is a data/algorithm signal, not a visualization bug.
- Current state: The dashboard no longer presents cross-type, same-time, or generic relation candidates as evolution edges.
- Next steps: Strengthen upstream relation extraction for evolution-specific edges, likely with LLM relation extraction/judging that explicitly requires same-type successor semantics and temporal evidence.
  - `/vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python scripts/screening_status.py --run-root data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025`
  - `/vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python scripts/merge_screening_shards.py --shards-root data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/shards --output-root data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/merged`
- Problems or dead ends: The Qwen service is shared, so wall-clock runtime is uncertain. Worker logs may remain empty until a shard completes because stdout/stderr are redirected and summaries are printed at process end.
- Current state: Full screening is running in tmux. Incremental decisions are being appended inside each shard directory.
- Next steps: Periodically run `scripts/screening_status.py`; after all shards reach their assigned limits, merge shards, inspect `screening_summary.json`, and audit stratified samples before making the screened corpus the EvoTaxa input.

### 2026-05-30 01:10 CST - Screening Error Diagnosis

- Goal: Diagnose the `llm_error` rows appearing during the full 16-worker relevance screening run.
- Starting point: Status showed 5 `llm_error` rows under `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/shards/` while the run was still active.
- Actions taken: Located all current `llm_error` decisions with `rg`; inspected their error messages and content excerpts; relaxed the `relevance_screening` schema validation in `src/evotaxa/llm.py` so `screening_decision`, `screening_score`, and `screening_reason` remain hard requirements while `method_relevance`, `social_science_relevance`, and `evolution_signal` are optional and can be filled by the existing normalizer.
- Decisions or rationale: Most schema failures contained a usable main relevance judgment but were rejected because auxiliary sub-scores were missing or malformed. Treating those sub-scores as optional avoids unnecessary `llm_error` rows without allowing label-free or score-free outputs.
- Verified facts: Current observed error classes were 1 timeout after 3 attempts, 1 output that echoed paper metadata instead of a screening object, and 3 outputs with usable main screening decisions but failed strict schema validation. `pytest -q tests/test_relevance_screening.py` passed with 4 tests; `py_compile` passed for `src/evotaxa/llm.py`.
- Outputs or changed paths:
  - Code: `src/evotaxa/llm.py`
  - Tests: `tests/test_relevance_screening.py`
  - Current affected shards: `shard_00`, `shard_01`, `shard_09`, `shard_15`
- Problems or dead ends: The full run was still active, so failed rows in running shard output files were not rewritten immediately. The existing resume behavior skips successful cached rows and retries `llm_error` rows, so these can be repaired by rerunning the affected shards after completion.
- Current state: The schema fix is in place for future retries and new model calls. Existing `llm_error` rows remain in the active shard files until the affected shards are resumed.
- Next steps: After the original workers finish, rerun affected shards with `--resume` to retry only `llm_error` rows, then merge all shards.

### 2026-05-30 11:17 CST - Auto Retry Monitor

- Goal: Automatically repair screening `llm_error` rows and merge shards after the original 16-worker run finishes.
- Starting point: Full screening was near completion under `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/`; 5 `llm_error` rows remained and 5 original worker tmux sessions were still active.
- Actions taken: Added executable script `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/auto_retry_and_merge.sh`; launched tmux session `evotaxa_screen_auto_retry` with `WAIT_SECONDS=30` and `MAX_RETRY_ROUNDS=3`.
- Decisions or rationale: The monitor waits for original `evotaxa_screen_[0-9]+` sessions to exit before launching any retry sessions. It retries only shards whose decision count is below expected limit or whose `screening_decisions.jsonl` still contains `llm_error`; successful cached rows are skipped by `--resume`.
- Verified facts: The monitor started successfully and logged that it was waiting for 5 original workers. Status at launch showed 25,024 completed decisions, 4,115 `core`, 7,246 `peripheral`, 13,658 `exclude`, and 5 `llm_error`.
- Outputs or changed paths:
  - Script: `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/auto_retry_and_merge.sh`
  - Monitor log: `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/logs/auto_retry_and_merge.log`
  - Monitor session: `evotaxa_screen_auto_retry`
- Commands:
  - `tmux new-session -d -s evotaxa_screen_auto_retry "cd /vepfs-mlp2/c20250513/241404044/users/roytian/EvoTaxa && export EVOTAXA_LLM_API_KEY='$EVOTAXA_LLM_API_KEY' && WAIT_SECONDS=30 MAX_RETRY_ROUNDS=3 data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/auto_retry_and_merge.sh > data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/logs/auto_retry_and_merge.log 2>&1"`
- Problems or dead ends: None at launch. Merge will stop with exit code 2 if any shard remains incomplete or has `llm_error` after 3 retry rounds.
- Current state: Auto retry monitor is running in tmux and waiting for original screening workers to finish.
- Next steps: Check `logs/auto_retry_and_merge.log`; after it reports merge complete, inspect `merged/screening_summary.json`.

### 2026-05-30 11:27 CST - Full Screening Completed

- Goal: Verify completion of the 25,063-row LLM relevance screening run after automatic retries and shard merge.
- Starting point: `evotaxa_screen_auto_retry` was waiting for original workers, then retried shards with `llm_error` rows.
- Actions taken: Read `logs/auto_retry_and_merge.log`; inspected `merged/screening_summary.json`; verified merged file line counts and absence of `llm_error`; checked that no `evotaxa_screen*` tmux sessions remained.
- Decisions or rationale: The merged output is the canonical screened corpus for downstream EvoTaxa runs because it includes all 16 shards after retry repair and has zero remaining screening errors.
- Verified facts: Original workers finished at 2026-05-30 11:24 CST. Retry round 1 relaunched `shard_00`, `shard_01`, `shard_09`, and `shard_15`; after retry, all 25,063 input rows had decisions and `llm_error` was 0. Merge completed at 2026-05-30 11:26 CST. `wc -l` showed 25,063 merged decisions, 25,063 cleaning records, and 4,126 screened core rows.
- Outputs or changed paths:
  - Final summary: `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/merged/screening_summary.json`
  - Final decisions: `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/merged/screening_decisions.jsonl`
  - Final screened corpus: `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/merged/corpus.screened.jsonl`
  - Final cleaning records: `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/merged/cleaning_records.jsonl`
- Counts and metrics:
  - Input rows: 25,063
  - `core`: 4,126
  - `peripheral`: 7,264
  - `exclude`: 13,673
  - `llm_error`: 0
  - Model-used records: 25,063
  - Retried outputs: 19
  - Cleaned abstracts: 6,876
  - Removed abstract characters: 43,312,918
- Problems or dead ends: None after retry. JSON repair count stayed 0; the earlier errors were resolved by retry and relaxed relevance-screening subscore validation.
- Current state: Full LLM relevance screening is complete. The final downstream corpus path is `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/merged/corpus.screened.jsonl`.
- Next steps: Audit stratified samples of `core`, `peripheral`, and `exclude`; update the OpenAlex CSS EvoTaxa config to point to the screened corpus when ready; then run the evolution pipeline on the 4,126 core rows.

### 2026-05-30 12:52 CST - Screened Corpus Node Design And Full Run

- Goal: Decide a practical node design for the screened computational-social-science corpus and verify whether the EvoTaxa full algorithm can run on it.
- Starting point: Final screened corpus had 4,126 `core` rows at `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/merged/corpus.screened.jsonl`. The previous OpenAlex config still pointed to the unscreened corpus and the seed taxonomy had 7 method nodes.
- Actions taken: Expanded `configs/computational_social_science_methods.taxonomy.json` to 13 medium-grained method ecology nodes; changed `configs/computational_social_science_methods.openalex.toml` to point at the screened corpus; changed output root to `examples/openalex_css_methods_screened_clean_entities_v1_output`; added phrase-boundary taxonomy assignment in `src/evotaxa/loaders.py`; capped candidate document pairs during generation in `src/evotaxa/graph.py`; filtered academic transition phrases in `src/evotaxa/entity_quality.py`; added targeted tests.
- Decisions or rationale: Nodes should be medium-grained local evolution spaces, not individual algorithms or a single monolithic method bucket. The 13-node design covers text-as-data, networks, causal/experimental designs, agent simulation, LLM-assisted methods, governance/reproducibility, spatial/GIS, survey/admin data, ML/AI classification, bibliometrics, online/social-media methods, digital traces, and computational infrastructure.
- Verified facts: Node assignment coverage rose to 3,311 of 4,126 screened documents (80.2%). Targeted tests passed: 8 tests covering relevance screening, phrase-boundary matching, candidate-pair limits, academic transition phrase filtering, and Qwen config shape. `validate-config` passed for the screened OpenAlex config. Full `run-full` completed successfully.
- Outputs or changed paths:
  - Node design note: `docs/computational_social_science_node_design.md`
  - Config: `configs/computational_social_science_methods.openalex.toml`
  - Taxonomy: `configs/computational_social_science_methods.taxonomy.json`
  - Code: `src/evotaxa/loaders.py`, `src/evotaxa/graph.py`, `src/evotaxa/entity_quality.py`
  - Tests: `tests/test_smoke.py`
  - Run output: `examples/openalex_css_methods_screened_clean_entities_v1_output/`
- Counts and metrics from `examples/openalex_css_methods_screened_clean_entities_v1_output/manifest.json`:
  - Documents: 4,126
  - Taxonomy nodes: 13
  - Entities: 519
  - Mentions: 7,220
  - Paper-level edges: 2,885
  - Trusted edges: 127
  - Candidate edges: 2,758
  - Trajectories: 589
  - Macro patterns: 9
  - Temporal windows: 169
  - Quality score: 0.659
- Problems or dead ends: The first full run attempt stalled because high-frequency entity pairs generated large cartesian document-pair lists before slicing; fixed by applying `max_edge_candidates_per_entity` during pair generation. The first completed run exposed noisy academic transition entities (`in this work`, `for this purpose`, `on the other hand`); fixed by filtering them from the entity layer and rerunning.
- Current state: The algorithm is runnable end-to-end on the screened 4,126-row corpus. The current bottleneck is quality, not execution: trusted-edge rate is low (127 trusted vs. 2,758 candidate), so relation cues and evidence auditing need calibration before interpreting macro patterns as substantive findings.
- Next steps: Audit trusted/candidate edge samples, especially `replaces`, `adapts`, and `improves`; consider small Qwen-assisted relation auditing on high-value edge samples; then decide whether to enable taxonomy expansion or schema adaptation for the next run.

### 2026-05-30 13:25 CST - Corpus-Driven Schema Probing

- Goal: Add a pre-main-flow probing workflow so initial node/schema design can be chosen from sampled corpus evidence instead of only hand-authored assumptions.
- Starting point: The screened CSS corpus and a 13-node method taxonomy were already runnable, but the user questioned whether node meaning and initial schema should be decided by corpus content.
- Actions taken: Added `scripts/probe_schema_design.py`; added corpus-derived `corpus_terms` variant alongside `method_ecology`, `evidence_practice`, and `hybrid_two_axis`; added decade-aware random sampling, boundary-case output, token profiles, node-candidate output, variant scoring, and a human-readable recommendation report; documented the workflow in `docs/schema_probing.md`; added a regression test in `tests/test_smoke.py`.
- Decisions or rationale: Probing remains outside `run-full` and does not automatically rewrite taxonomy configs. The score balances coverage, node-balance, expected document overlap, and overloaded documents; corpus-derived terms are retained as discovery evidence but are penalized when broad metadata concepts over-assign many nodes per document.
- Commands:
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python scripts/probe_schema_design.py --config configs/computational_social_science_methods.openalex.toml --output-root data/schema_probe/css_screened_20260530_v1 --sample-size 240 --seed 20260530`
  - `/vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/pytest -q tests/test_smoke.py::test_schema_probe_script_writes_artifacts tests/test_relevance_screening.py`
- Verified facts: The formal probe loaded 4,126 screened documents, sampled 240 documents from publication years 1990-2026, evaluated 4 variants, and wrote all planned artifacts. Targeted tests passed with 5 tests in 0.23s.
- Outputs or changed paths:
  - Script: `scripts/probe_schema_design.py`
  - Docs: `docs/schema_probing.md`
  - Test: `tests/test_smoke.py`
  - Probe root: `data/schema_probe/css_screened_20260530_v1/`
  - Summary: `data/schema_probe/css_screened_20260530_v1/probe_summary.json`
  - Coverage report: `data/schema_probe/css_screened_20260530_v1/node_coverage_report.json`
  - Recommendation: `data/schema_probe/css_screened_20260530_v1/schema_recommendation.md`
- Counts and metrics from `node_coverage_report.json`:
  - `hybrid_two_axis`: score 0.848, coverage 213/240 (0.887), mean nodes per document 2.188, overlap quality 0.906, overloaded documents 44.
  - `evidence_practice`: score 0.842, coverage 193/240 (0.804), mean nodes per document 1.321, overlap quality 0.899, overloaded documents 9.
  - `method_ecology`: score 0.742, coverage 148/240 (0.617), mean nodes per document 0.867, overlap quality 0.867, overloaded documents 1.
  - `corpus_terms`: score 0.668, coverage 222/240 (0.925), mean nodes per document 2.688, overlap quality 0.0, overloaded documents 68.
- Interpretation: `hybrid_two_axis` and `evidence_practice` are effectively tied. This suggests the next formal node design should treat evidence-production practice as the main stable axis and preserve method-family labels as a second interpretive axis rather than forcing all documents into a single flat method taxonomy. Corpus-derived terms such as Artificial Intelligence, Political Science, Machine Learning, World Wide Web, Social Media, Natural Language Processing, Data Mining, Social Network, Computational Sociology, and Information Retrieval are useful for aliases or missing-node review, but too broad to promote directly as the primary schema.
- Problems or dead ends: An early implementation let query buckets produce candidate nodes and over-rewarded broad OpenAlex concepts. Query buckets were removed from corpus-term induction, support documents from keywords/concepts were made explicit, and the scoring function was adjusted to penalize mismatch with expected node overlap.
- Current state: Schema probing is available as a reusable optional workflow and has produced a first CSS recommendation. It has not yet rewritten `configs/computational_social_science_methods.taxonomy.json`.
- Next steps: Manually review `boundary_cases.jsonl` for `hybrid_two_axis` and `evidence_practice`; decide whether to split the main config into a practice axis plus method-family axis; add aliases for older terminology such as computer simulation, formal model, e-social science infrastructure, optimization, matrix problems, and artificial societies.

### 2026-05-30 13:55 CST - Schema Probing Agent And Main-Flow Proposal

- Goal: Extend schema probing into an agent/workflow that can output schema artifacts suitable for a later EvoTaxa main algorithm run.
- Starting point: The first probe workflow produced coverage reports and recommendations, but it did not generate a ready-to-validate taxonomy, schema seed, or config. The user wanted a probing agent/workflow that can output schemas for downstream main flow.
- Actions taken: Added `scripts/propose_schema_from_probe.py`; expanded the probe `method_ecology` variant to match the 13 method-family candidates used by the current CSS config; reran the probe into `data/schema_probe/css_screened_20260530_v2/`; generated a main-flow proposal under `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/`; updated `docs/schema_probing.md`; added regression coverage for proposal generation in `tests/test_smoke.py`.
- Decisions or rationale: The workflow is now two-stage: `probe_schema_design.py` observes and compares candidate schemas, while `propose_schema_from_probe.py` converts selected probe evidence into main-flow-ready artifacts without overwriting existing configs. The proposal uses JSON config because `load_config` supports JSON directly and relative paths inside the proposal directory are easy to validate.
- Commands:
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python scripts/probe_schema_design.py --config configs/computational_social_science_methods.openalex.toml --output-root data/schema_probe/css_screened_20260530_v2 --sample-size 240 --seed 20260530`
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python scripts/propose_schema_from_probe.py --base-config configs/computational_social_science_methods.openalex.toml --probe-root data/schema_probe/css_screened_20260530_v2 --output-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal --run-id-suffix practice_method_probe_v2`
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python -m evotaxa.cli validate-config --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/config.proposed.json`
  - `/vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/pytest -q tests/test_smoke.py::test_schema_probe_script_writes_artifacts tests/test_smoke.py::test_schema_probe_proposal_writes_mainflow_config tests/test_relevance_screening.py`
- Verified facts: The v2 proposal config validates successfully. Targeted tests passed with 6 tests in 0.81s. The proposal contains 19 taxonomy nodes: 6 evidence-practice nodes plus 13 method-family nodes. It includes 7 entity types, 10 relation types, and 9 evidence slots.
- Outputs or changed paths:
  - Proposal script: `scripts/propose_schema_from_probe.py`
  - Updated probe script: `scripts/probe_schema_design.py`
  - Updated docs: `docs/schema_probing.md`
  - Updated tests: `tests/test_smoke.py`
  - Probe root: `data/schema_probe/css_screened_20260530_v2/`
  - Proposal root: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/`
  - Proposed taxonomy: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/taxonomy.proposed.json`
  - Proposed schema seed: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/schema_seed.proposed.json`
  - Proposed config: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/config.proposed.json`
  - Proposal report: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/schema_proposal_report.md`
- Counts and metrics from v2:
  - `evidence_practice`: score 0.842, coverage 0.804, mean nodes/doc 1.321, overloaded 9.
  - `hybrid_two_axis`: score 0.812, coverage 0.904, mean nodes/doc 2.446, overloaded 53.
  - `method_ecology`: score 0.771, coverage 0.717, mean nodes/doc 1.125, overloaded 6.
  - `corpus_terms`: score 0.668, coverage 0.925, mean nodes/doc 2.688, overloaded 68.
- Interpretation: The agent selected `practice_primary_method_secondary`: evidence-production practice is the primary axis, while method family remains a second axis for locality and interpretation. The proposed relation schema adds CSS-specific relation types `operationalizes`, `enables`, `validates`, and `combines`, and the evidence schema adds slots for methodological problem, data basis, measurement design, validation evidence, infrastructure context, implementation context, governance constraint, mechanism, and tradeoff.
- Problems or dead ends: The first proposal used only the 9-node method probe, while the active CSS config already had 13 method nodes. Fixed by expanding the probe method variant and regenerating the proposal as v2.
- Current state: A main-flow-ready candidate schema/config exists and validates, but it has not yet been promoted into `configs/`.
- Next steps: Run `run-full` with `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/config.proposed.json`, compare manifest and edge quality against `examples/openalex_css_methods_screened_clean_entities_v1_output/`, and then decide whether to promote the proposed taxonomy/schema into canonical config files.

### 2026-05-30 14:15 CST - Proposal Main-Flow Run And Node Card Boundary

- Goal: Verify that the schema-probing proposal can run the full EvoTaxa pipeline, and clarify the difference between taxonomy node cards and graph entities after noisy entity names appeared.
- Starting point: The v2 proposal existed at `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/` and validated successfully, but had not been run. During inspection, strings such as `science`, `thus`, `to this end`, and `free` appeared as graph entities, raising the question of whether nodes were being stored too thinly.
- Actions taken: Ran `run-full` using the v2 proposed config; inspected manifest, quality report, entity quality report, trusted edges, and taxonomy node output; added `node_card` fields to proposal taxonomy nodes; documented node-card vs. graph-entity boundaries in `docs/schema_probing.md`; tightened entity-quality filtering so generic single-token stopwords are hard-filtered; added tests for node cards and generic entity filtering.
- Decisions or rationale: Taxonomy nodes should be card-like schema objects, not just labels. Graph entities are separate text-derived objects. The noisy strings were entity-extraction/quality-filter failures, not taxonomy-node design failures. The fix belongs in entity quality plus clearer node-card metadata.
- Commands:
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python -m evotaxa.cli run-full --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/config.proposed.json --print-manifest`
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python scripts/propose_schema_from_probe.py --base-config configs/computational_social_science_methods.openalex.toml --probe-root data/schema_probe/css_screened_20260530_v2 --output-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal --run-id-suffix practice_method_probe_v2`
  - `/vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/pytest -q tests/test_smoke.py::test_schema_probe_script_writes_artifacts tests/test_smoke.py::test_schema_probe_proposal_writes_mainflow_config tests/test_smoke.py::test_entity_quality_filters_academic_transition_phrases tests/test_relevance_screening.py`
- Verified facts: The final v2 proposal run completed on 4,126 screened documents with 19 taxonomy nodes, 3,820 inferred document assignments, 117 kept entities, 29 filtered entities, 19,197 mentions, 3,625 paper-level edges, 267 trusted edges, 3,358 candidate edges, 238 aggregated edges, 1,032 trajectories, 325 temporal windows, and quality score 0.663. The prior 13-node baseline had 3,311 assignments, 519 entities, 2,885 paper-level edges, 127 trusted edges, 589 trajectories, 169 temporal windows, and quality score 0.659. Targeted tests passed with 7 tests in 0.48s.
- Outputs or changed paths:
  - Updated proposal script: `scripts/propose_schema_from_probe.py`
  - Updated entity filter: `src/evotaxa/entity_quality.py`
  - Updated docs: `docs/schema_probing.md`
  - Updated tests: `tests/test_smoke.py`
  - Final proposal run: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/main_run_output/`
  - Final proposal manifest: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/main_run_output/manifest.json`
  - Final proposal quality report: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/main_run_output/evaluation/quality_report.json`
- Interpretation: The proposal run is runnable and produces more trusted edges than the baseline, but edge evidence remains the bottleneck: trusted-edge rate is 0.076 and edge-evidence score is 0.383. The node-card schema is cleaner and more explicit, but entity extraction still needs stronger boundaries for long title fragments and broad phrases such as `computational social science`.
- Problems or dead ends: Initial proposal run admitted noisy entities like `method__second`, `method__at_the_same_time`, `method__science`, `method__thus`, `method__to_this_end`, and `method__free`. Generic single-token stopwords and academic transition phrases are now hard-filtered; final trusted edges no longer contained those exact noisy entities.
- Current state: The probing-agent workflow now produces card-like taxonomy nodes, a schema seed, a validating config, and a completed candidate full run. It should be treated as a candidate schema, not yet as the promoted canonical config.
- Next steps: Improve graph entity extraction so entity names are specific methods/practices rather than node labels or title fragments; consider LLM-assisted entity extraction/auditing on a small sample; then compare baseline vs. proposal on manually audited trusted/candidate edge samples before promotion.

### 2026-05-30 14:35 CST - Core+Support Stability Run

- Goal: Use the 7,264 `peripheral` screened papers as a support layer without merging them silently into the 4,126-paper `core` evidence layer.
- Starting point: The current candidate schema run used only `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/merged/corpus.screened.jsonl`, which contains 4,126 `core` rows. The full screening decisions also contain 7,264 `peripheral` rows and 13,673 `exclude` rows.
- Actions taken: Added `scripts/materialize_screened_corpus.py` to reconstruct screened corpus views from the original OpenAlex corpus plus completed `screening_decisions.jsonl`; materialized `core+support` corpus with `peripheral` mapped to `role=support`; added a regression test for the materializer; copied the proposal config into `config.core_support.json`; ran `validate-config`; ran full EvoTaxa on the 11,390-row `core+support` view; generated a machine-readable comparison against the core-only proposal run.
- Decisions or rationale: `support` is useful as an adjacent discovery and stability layer, but it should remain role-labeled. It should not be treated as equal-strength `core` evidence when reporting substantive conclusions.
- Commands:
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python scripts/materialize_screened_corpus.py --input data/computational_social_science/corpus.jsonl --decisions data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/merged/screening_decisions.jsonl --output data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/merged/corpus.core_support.jsonl --summary data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/merged/corpus.core_support.summary.json --include-decisions core,peripheral --role-map peripheral=support`
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python -m evotaxa.cli validate-config --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/config.core_support.json`
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python -m evotaxa.cli run-full --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/config.core_support.json --print-manifest`
  - `/vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/pytest -q tests/test_relevance_screening.py`
- Verified facts:
  - Materialized corpus: 11,390 rows, with 4,126 `core` and 7,264 `support`; 13,673 `exclude` rows skipped.
  - Materialized summary: `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/merged/corpus.core_support.summary.json`
  - Core+support run completed in roughly 8.5 minutes with deterministic LLM configuration.
  - Targeted relevance/materializer tests passed: 5 tests in 0.05s.
- Outputs or changed paths:
  - Materializer script: `scripts/materialize_screened_corpus.py`
  - Materialized corpus: `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/merged/corpus.core_support.jsonl`
  - Core+support config: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/config.core_support.json`
  - Core+support output: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/core_support_run_output/`
  - Comparison report: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/core_support_comparison.json`
- Counts and metrics:
  - Core-only proposal run: 4,126 documents, 117 entities, 19,197 mentions, 3,625 paper-level edges, 267 trusted edges, 1,032 trajectories, 325 temporal windows, quality score 0.663.
  - Core+support run: 11,390 documents, 397 entities, 46,640 mentions, 3,855 paper-level edges, 256 trusted edges, 1,126 trajectories, 483 temporal windows, quality score 0.666.
  - Edge evidence: trusted-edge rate changed from 0.074 to 0.066; edge-evidence score changed from 0.382 to 0.378.
  - Entity layer: kept entities changed from 117 to 397; entity-layer score changed from 0.784 to 0.820.
  - Trusted-edge role pairs in the core+support run: 12 `core->core`, 43 `core->support`, 65 `support->core`, and 136 `support->support`.
  - Trusted-edge overlap between core-only and core+support outputs was low: 9 shared edge IDs, 258 core-only-only, and 247 core+support-only.
  - Macro pattern set remained the same 9 detector types. Ranking changed: `substitution` was rank 1 in core-only but rank 7 in core+support; `recontextualization` was rank 2 in core-only and rank 1 in core+support.
- Interpretation: Adding support substantially increases entity coverage and temporal windows, but it does not increase trusted-edge yield and it changes which edge IDs and macro-pattern rankings dominate. This supports a two-layer interpretation policy: core-only remains the primary evidence layer, while core+support is a discovery/stability layer with explicit role provenance.
- Problems or dead ends: None blocking. The low trusted-edge overlap indicates the current deterministic entity/edge extraction is sensitive to corpus composition, so support-inclusive conclusions require role-aware reporting and sampled edge audit before substantive claims.
- Current state: Both core-only and core+support proposal runs are complete and directly comparable. The support layer is available and useful, but not yet suitable for unqualified main conclusions.
- Next steps: Add role provenance to downstream comparison/reporting artifacts, audit sampled trusted edges by role pair, and consider weighting or filtering so support documents can contribute discovery signals without overwhelming core-evidence interpretation.

### 2026-05-30 14:55 CST - Role-Aware Edge Audit Sample

- Goal: Produce a fixed, role-aware edge audit sample from the completed `core+support` run so entity quality, relation type validity, quote support, taxonomy locality, and evidence-layer status can be reviewed before changing the algorithm.
- Starting point: The `core+support` run had 3,855 paper-level edges, 256 trusted edges, and 3,599 candidate edges. The previous comparison showed support-heavy trusted edges and low overlap with the core-only run.
- Actions taken: Added `scripts/audit_edges_role_aware.py`; added a regression test using a minimal synthetic run root; generated a 120-edge stratified audit sample from `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/core_support_run_output/`; wrote JSONL, CSV, summary JSON, and a README for manual or LLM-assisted annotation.
- Decisions or rationale: The audit script is intentionally outside the main pipeline. It reads completed run artifacts and writes a separate audit directory. It does not call LLMs by default, so the same fixed sample can later be manually annotated or passed to Qwen without changing the sample frame.
- Commands:
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python scripts/audit_edges_role_aware.py --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/core_support_run_output --output-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/edge_audit_role_aware_20260530 --seed 20260530 --per-role-pair 8 --per-edge-type 4 --per-status 24 --max-samples 120`
  - `/vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/pytest -q tests/test_relevance_screening.py`
- Verified facts:
  - Input edges: 3,855 total, with 3,599 `candidate` and 256 `trusted`.
  - Input role pairs: 382 `core->core`, 611 `core->support`, 999 `support->core`, and 1,863 `support->support`.
  - Audit sample: 120 edges, with 60 `candidate` and 60 `trusted`.
  - Sample role pairs: 13 `core->core`, 23 `core->support`, 33 `support->core`, and 51 `support->support`.
  - Sample edge types: 18 `adapts`, 39 `background`, 4 `combines`, 3 `compares`, 21 `enables`, 7 `extends`, 3 `improves`, 1 `operationalizes`, 2 `replaces`, 18 `uses_component`, and 4 `validates`.
  - Targeted tests passed: 6 tests in 0.09s.
- Outputs or changed paths:
  - Script: `scripts/audit_edges_role_aware.py`
  - Tests: `tests/test_relevance_screening.py`
  - Audit root: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/edge_audit_role_aware_20260530/`
  - JSONL sample: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/edge_audit_role_aware_20260530/edge_audit_sample.jsonl`
  - CSV audit sheet: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/edge_audit_role_aware_20260530/edge_audit_sheet.csv`
  - Summary: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/edge_audit_role_aware_20260530/edge_audit_summary.json`
  - README: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/edge_audit_role_aware_20260530/edge_audit_readme.md`
- Auto-diagnostic results:
  - Auto recommendations in the 120-edge sample: 107 `entity_repair_needed`, 12 `quote_relation_reinspect`, and 1 `discovery_only`.
  - Auto flags: 114 `quote_does_not_name_both_entities`, 68 `source_entity_generic_or_broad`, 77 `target_entity_generic_or_broad`, 6 `source_entity_title_fragment`, 6 `source_entity_matches_taxonomy_label`, 3 `target_entity_matches_taxonomy_label`, 107 `support_involved`, 51 `support_only_edge`, and 60 `weak_edge_type_for_primary_claim`.
- Interpretation: The audit sample strongly suggests that the immediate bottleneck is entity and evidence grounding, not simply role weighting. Many edges are driven by node-label-like entities, broad schema terms, title fragments, or quotes that verify a string span but do not substantively support the typed relation between both entities.
- Problems or dead ends: The automatic flags are diagnostics, not final validity judgements. Manual or LLM-assisted annotation is still needed for a calibrated accept/reject rate.
- Current state: A fixed role-aware audit sample is ready for manual/Qwen annotation. The next algorithm change should focus on entity repair and stricter quote-to-relation grounding.
- Next steps: Use the fixed audit sample to calibrate entity filters and quote support rules; then rerun core-only and core+support after entity repair and compare trusted-edge yield, role-pair composition, and macro-pattern ranking stability.

## Caveats

- Known failures: none after smoke tests.
- Assumptions: Fixture corpora are only smoke tests.
- Follow-up: Build real OpenAlex corpus and compare macro pattern artifacts across default, no-coevolution, no-schema-adaptation, and no-negative-evidence runs.

### 2026-05-30 16:05 CST - Entity Grounding Repair And Qwen Pilot Launch

- Goal: Repair noisy graph entities and quote grounding after the role-aware audit showed many broad entities, title fragments, and string-matched but relation-unsupported quotes.
- Starting point: The core-only proposal run at `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/main_run_output/` used 4,126 `core` papers and produced 117 entities, 267 trusted edges, 1,032 trajectories, and quality score 0.663, but audit diagnostics indicated entity/evidence grounding problems.
- Actions taken: Added stricter entity-quality filters for schema-bucket labels, academic transition phrases, generic single tokens, and incomplete sentence fragments; changed edge evidence audit to distinguish substring verification from relation-supported quote grounding; added configurable `graph.quote_relation_grounding_mode` with `substring`, `one_sided_cue`, and `two_sided_cue`; added `llm.extra_body` passthrough so Qwen requests can set `chat_template_kwargs.enable_thinking=false`; updated LLM entity extraction prompts to include entity schema definitions, inclusion/exclusion criteria, negative examples, and quality rules; created deterministic comparison runs and a 200-paper LLM pilot workspace.
- Decisions or rationale: The deterministic runs are calibration/ablation, not final evidence. The strict `two_sided_cue` mode is useful for diagnosing weak quote support, but it is too strict for the current deterministic edge builder. Qwen should be used for entity extraction, relation extraction, and evidence judging; no `max_tokens` is set, per the Qwen service guidance.
- Commands:
  - `/vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/pytest -q tests/test_smoke.py::test_entity_quality_filters_academic_transition_phrases tests/test_smoke.py::test_edge_evidence_stratification_requires_grounded_quotes tests/test_smoke.py::test_edge_evidence_quote_must_support_relation_not_only_substring tests/test_smoke.py::test_edge_evidence_trusted_quote_must_ground_both_entities tests/test_smoke.py::test_edge_evidence_one_sided_cue_mode_is_configurable tests/test_smoke.py::test_social_config_runs tests/test_relevance_screening.py`
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python -m evotaxa.cli validate-config --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/config.entity_grounding_v2.json`
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python -m evotaxa.cli validate-config --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/config.entity_grounding_v3.json`
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python -m evotaxa.cli run-full --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/config.entity_grounding_v4_one_sided_current.json --print-manifest`
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python -m evotaxa.cli run-full --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/config.llm_smoke_12.json --print-manifest`
  - `tmux new-session -d -s evotaxa_llm_pilot_200 "/tmp/evotaxa_llm_pilot_200_cmd.sh > data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/logs/run_full_200_no_thinking.log 2>&1"`
- Verified facts:
  - Targeted tests passed after the grounding/config changes: 12 tests in 0.35s, then 10 tests in 0.19s, then 9 tests in 0.06s after adding `llm.extra_body` and cache-key request options.
  - Deterministic v2 (`one_sided_cue`, earlier filters) completed with 79 entities, 26 trusted edges, 60 trajectories, quality score 0.590.
  - Deterministic v3 (`two_sided_cue`, current strict filters) completed with 31 entities, 0 trusted edges, 0 trajectories, quality score 0.468.
  - Deterministic v4 (`one_sided_cue`, current strict filters) completed with 31 entities, 11 trusted edges, 15 trajectories, quality score 0.567.
  - The 12-paper no-thinking Qwen smoke completed with 23 LLM records: 12 `entity_extraction`, 3 `relation_extraction_batch`, and 8 `edge_evidence_judge`; 22 used the model, 1 edge judge timed out and fell back; 0 JSON repairs; 49 accepted LLM entity mentions; 1 accepted LLM relation edge; 0 trusted final edges; quality score 0.488.
  - Qwen requests use `base_url=http://127.0.0.1:8001/v1`, `model=Qwen3.5-397B-A17B-FP8`, `response_format={"type":"json_object"}`, `chat_template_kwargs.enable_thinking=false`, `temperature=0.0`, and no `max_tokens`.
  - 200-paper pilot was launched in tmux session `evotaxa_llm_pilot_200`; after launch it had started writing `llm_pilot_200_no_thinking_cache.jsonl` with at least 2 successful `entity_extraction` records and 0 errors at the last check.
- Outputs or changed paths:
  - Code: `src/evotaxa/entity_quality.py`, `src/evotaxa/edge_evidence.py`, `src/evotaxa/config.py`, `src/evotaxa/llm.py`, `src/evotaxa/pipeline.py`
  - Tests/config: `tests/test_smoke.py`, `configs/qwen_local_llm.example.toml`
  - Deterministic configs: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/config.entity_grounding_v2.json`, `config.entity_grounding_v3.json`, `config.entity_grounding_v4_one_sided_current.json`
  - Deterministic outputs: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/main_run_output_entity_grounding_v2/`, `main_run_output_entity_grounding_v3/`, `main_run_output_entity_grounding_v4_one_sided_current/`
  - LLM pilot root: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/`
  - LLM smoke output: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/smoke_12_no_thinking_output/`
  - LLM pilot config: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/config.llm_pilot_200.json`
  - LLM pilot cache: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/llm_pilot_200_no_thinking_cache.jsonl`
  - LLM pilot log: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/logs/run_full_200_no_thinking.log`
  - Comparison artifact: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/entity_grounding_llm_pilot_comparison_20260530.json`
- Interpretation: Entity filtering removes many schema buckets and sentence fragments, but deterministic relation construction remains too weak to be the final source of trusted evolution claims. The Qwen smoke confirms JSON stability with schema-rich prompts and no thinking, but edge-evidence judging is slow and strict; the 200-paper pilot is needed to see whether LLM entities/relations improve graph quality at a meaningful sample size.
- Problems or dead ends: A first 12-paper Qwen smoke was started without the explicit no-thinking payload and was stopped after caching 8 successful entity records because it was too slow. The completed no-thinking smoke still had one edge-judge timeout fallback. v3 strict two-sided grounding produced no trusted edges and should not be promoted as the default mode.
- Current state: Code supports configurable quote grounding, schema-aware LLM entity prompts, Qwen no-thinking payloads, and request-option-aware LLM cache keys. The 200-paper Qwen pilot is running in tmux and should be monitored before launching any 4,126-paper full LLM run.
- Next steps: Monitor `evotaxa_llm_pilot_200`; when complete, inspect `run_output_no_thinking/manifest.json`, `evaluation/quality_report.json`, `graph/entity_quality_report.jsonl`, `graph/relation_extraction_report.jsonl`, and `graph/edge_evidence_audit.jsonl`; then decide whether to run full 4,126 core with LLM relation extraction/edge judge or first adjust evidence-judge thresholds.

### 2026-05-30 16:08 CST - Entity Grounding Repair And LLM Pilot Launch

- Goal: Repair the entity/evidence grounding bottleneck found in the role-aware edge audit, then verify that Qwen can run the schema-rich entity/relation/evidence workflow with thinking disabled before scaling beyond deterministic baselines.
- Starting point: The role-aware audit sample showed many node-label-like entities, title fragments, generic phrases, and quotes that matched text spans without proving the typed relation. The core-only proposal run had 4,126 documents, 117 kept entities, 267 trusted edges, and quality score 0.663, but trusted edges still contained weak grounding patterns.
- Actions taken: Added conservative entity filters for schema bucket phrases, domain stop phrases, generic single tokens, and incomplete sentence fragments; changed quote auditing to record substring verification separately from relation support; added configurable `graph.quote_relation_grounding_mode` with `substring`, `one_sided_cue`, and `two_sided_cue`; passed entity-schema definitions and boundary rules into LLM entity extraction prompts; added `llm.extra_body` support so OpenAI-compatible/vLLM requests can send `chat_template_kwargs.enable_thinking=false`; added cache keys that include request options; created a 200-document decade-stratified LLM pilot corpus plus a 12-document Qwen smoke.
- Decisions or rationale: Deterministic runs are retained as ablation/calibration artifacts, not final empirical outputs. `two_sided_cue` is useful as a strict diagnostic but too severe for the current deterministic edge builder. The LLM workflow keeps the schema-rich prompt unchanged, does not set `max_tokens`, and explicitly disables Qwen thinking via request body.
- Commands:
  - `/vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/pytest -q tests/test_smoke.py::test_entity_quality_filters_academic_transition_phrases tests/test_smoke.py::test_edge_evidence_stratification_requires_grounded_quotes tests/test_smoke.py::test_edge_evidence_quote_must_support_relation_not_only_substring tests/test_smoke.py::test_edge_evidence_trusted_quote_must_ground_both_entities tests/test_smoke.py::test_edge_evidence_one_sided_cue_mode_is_configurable tests/test_smoke.py::test_social_config_runs tests/test_relevance_screening.py`
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python -m evotaxa.cli validate-config --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/config.entity_grounding_v2.json`
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python -m evotaxa.cli validate-config --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/config.entity_grounding_v3.json`
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python -m evotaxa.cli run-full --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/config.entity_grounding_v4_one_sided_current.json --print-manifest`
  - `EVOTAXA_LLM_API_KEY=$EVOTAXA_LLM_API_KEY PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python -m evotaxa.cli run-full --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/config.llm_smoke_12.json --print-manifest`
  - `tmux new-session -d -s evotaxa_llm_pilot_200 "/tmp/evotaxa_llm_pilot_200_cmd.sh > data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/logs/run_full_200_no_thinking.log 2>&1"`
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python scripts/llm_pilot_status.py --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530`
- Verified facts:
  - Targeted tests after the grounding/config changes passed: 12 tests in 0.35s; later LLM/config status tests passed: 9 tests in 0.06s and 7 tests in 0.23s.
  - v2 deterministic run (`one_sided_cue`, earlier filters) completed with 4,126 documents, 79 entities, 26 trusted edges, 60 trajectories, 70 temporal windows, and quality score 0.590.
  - v3 deterministic run (`two_sided_cue`, strict filters) completed with 4,126 documents, 31 entities, 0 trusted edges, 0 trajectories, 66 temporal windows, and quality score 0.468. This confirms that strict two-sided quote grounding is too restrictive for the current deterministic edge builder.
  - v4 deterministic run (`one_sided_cue`, current strict entity filters) completed with 4,126 documents, 31 entities, 11 trusted edges, 15 trajectories, 58 temporal windows, 16 forecast hooks, and quality score 0.567.
  - Qwen 12-document no-thinking smoke used `chat_template_kwargs.enable_thinking=false`, no `max_tokens`, and completed with 12 documents, 33 entities, 49 accepted LLM entity mentions, 12 LLM relation pairs, 1 accepted LLM relation edge, 8 edge evidence judge attempts, 220 candidate edges, 0 trusted edges, and quality score 0.488.
  - Qwen smoke LLM records: 23 total records, 12 `entity_extraction`, 3 `relation_extraction_batch`, 8 `edge_evidence_judge`; 22 used-model records, 0 JSON repairs, 1 timeout error record, attempts distribution 21 first-attempt and 2 second-attempt records. The run completed despite the timeout fallback.
  - 200-document pilot corpus: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/corpus.core_200.jsonl`, sampled from 4,126 core records with seed 20260530; decade counts were 24 from 1990s, 50 from 2000s, 61 from 2010s, and 65 from 2020s.
  - 200-document pilot status at launch check: tmux session `evotaxa_llm_pilot_200` was running, cache existed at `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/llm_pilot_200_no_thinking_cache.jsonl`, and had 4 successful `entity_extraction` records, 0 errors, 0 JSON repairs.
- Outputs or changed paths:
  - Code: `src/evotaxa/entity_quality.py`, `src/evotaxa/edge_evidence.py`, `src/evotaxa/config.py`, `src/evotaxa/llm.py`, `src/evotaxa/pipeline.py`
  - Tests: `tests/test_smoke.py`
  - Qwen example config: `configs/qwen_local_llm.example.toml`
  - Deterministic configs: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/config.entity_grounding_v2.json`, `config.entity_grounding_v3.json`, `config.entity_grounding_v4_one_sided_current.json`
  - Deterministic outputs: `main_run_output_entity_grounding_v2/`, `main_run_output_entity_grounding_v3/`, `main_run_output_entity_grounding_v4_one_sided_current/`
  - LLM pilot root: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/`
  - LLM smoke config/output/cache: `config.llm_smoke_12.json`, `smoke_12_no_thinking_output/`, `llm_smoke_12_no_thinking_cache.jsonl`
  - LLM pilot config/cache/log/output target: `config.llm_pilot_200.json`, `llm_pilot_200_no_thinking_cache.jsonl`, `logs/run_full_200_no_thinking.log`, `run_output_no_thinking/`
  - Comparison artifact: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/entity_grounding_llm_pilot_comparison_20260530.json`
  - Status helper: `scripts/llm_pilot_status.py`
- Interpretation: Entity filters substantially reduce deterministic graph noise, but relation evidence becomes sparse. The Qwen smoke shows schema-rich LLM entity extraction is stable and much cleaner than the deterministic entity layer, while relation/evidence judging remains conservative and expensive. The next useful evidence is the 200-document pilot result, not another deterministic full run.
- Problems or dead ends: The first Qwen smoke was started before explicitly passing `enable_thinking=false` and was stopped after 8 cached records; the no-thinking smoke used a separate cache. Edge evidence judge is slow and produced one timeout fallback in the completed 12-document smoke. The smoke ended with 0 trusted edges because quote-to-relation grounding remains strict; this is a calibration finding, not a final failure.
- Current state: The 200-document Qwen pilot is running in tmux session `evotaxa_llm_pilot_200` with thinking disabled, no token cap, and a dedicated cache. Deterministic v2/v3/v4 comparison and Qwen smoke results are recorded in the comparison JSON.
- Next steps: Monitor `scripts/llm_pilot_status.py`; when the 200-document pilot finishes, inspect entity quality, accepted/rejected LLM relations, edge evidence reasons, and whether LLM-rewritten evidence creates trusted edges. If relation/evidence remains too sparse, calibrate relation prompts or trusted-edge criteria before any 4,126-document LLM run.

#### Follow-up at 2026-05-30 16:09 CST

- Adjustment: Increased Qwen pilot `llm.timeout_seconds` from 120 to 300 in `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/config.llm_pilot_200.json` and `config.llm_smoke_12.json`.
- Rationale: The completed 12-document smoke showed schema-rich prompts were valid but slow; one edge evidence judge produced a timeout fallback under the 120-second limit. The user confirmed that slower no-thinking generation is acceptable and requested not to compress prompts or set `max_tokens`.
- Action: Restarted tmux session `evotaxa_llm_pilot_200`; preserved the pre-restart log by moving it under `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/logs/` with a `pre_timeout300` timestamped name.
- Verified state after restart: `scripts/llm_pilot_status.py` reported 6 cached `entity_extraction` records, 0 errors, 0 JSON repairs, and tmux session `evotaxa_llm_pilot_200` running. Existing successful cache rows are reused.

#### Follow-up at 2026-05-30 16:?? CST - Completed Entity Extraction Quality Snapshot

- Scope: Audited the completed portion of the running 200-document Qwen pilot cache at `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/llm_pilot_200_no_thinking_cache.jsonl` while the tmux run was still active.
- Verified facts: At audit time the cache contained 73 `entity_extraction` records for 67 unique documents. The first 6 documents appeared twice because the cache-key logic was changed to include request options and the pilot was restarted; the deduplicated audit keeps the latest record per document.
- Deduplicated entity quality: 67 unique documents, 272 extracted entities, 0 documents with zero entities, mean 4.06 entities/document, valid entity types only, confidence mean 0.901, and 268/272 quotes validated by EvoTaxa quote verification (0.985).
- Entity type mix: 128 `modeling_strategy`, 83 `method`, 21 `infrastructure_tooling`, 17 `evaluation_protocol`, 16 `data_source`, and 7 `measurement_strategy`.
- Current downstream filter interaction: Applying the current heuristic entity-quality scorer to LLM entities would put 153 entities at score >= 0.6, 51 in 0.42-0.6, and 68 below the 0.42 threshold. Many low scores are valid but long or generic-token-containing method names, suggesting the heuristic filter is too harsh for quote-grounded LLM entities.
- Quality caveats: Some extracted names remain broad or action-like, including `simulation`, `empirical performance`, `arbitrary reordering of an entire vote`, and `relating the k-robustness to the 1-robustness`. A few quote checks failed exact EvoTaxa validation, mostly because of partial quotes or punctuation/context differences.
- Output: Wrote audit summary to `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/completed_entity_extraction_quality_audit_deduped.json`.
- Interpretation: Qwen entity extraction is much cleaner and more grounded than deterministic entity extraction, but downstream quality filtering should distinguish LLM quote-grounded entities from heuristic candidate strings before full interpretation.

#### Follow-up at 2026-05-30 18:36 CST - LLM Pilot Parallelization And Completion

- Scope: Fixed the 200-document Qwen pilot after discovering it had been launched as a single sequential `run-full` process despite the intended 16-worker execution.
- Problem: The tmux run `evotaxa_llm_pilot_200` was initially executing with `NLWP=1` and only reached 137 unique documents after more than two hours. This was operator error in the launch/code path, not a Qwen service failure.
- Actions taken: Stopped the single-threaded run without deleting cache; added `llm.max_workers`; made the OpenAI-compatible LLM cache thread-safe; parallelized full-run LLM entity extraction, relation extraction batches, and edge evidence judging with deterministic output ordering; set `max_workers=16` in `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/config.llm_pilot_200.json` and `configs/qwen_local_llm.example.toml`; relaunched the same pilot in tmux with the existing cache.
- Verification: `py_compile` passed for `src/evotaxa/config.py`, `src/evotaxa/llm.py`, and `src/evotaxa/pipeline.py`. Targeted pytest command passed 3 selected tests in 0.21s: `test_qwen_local_llm_config_uses_env_key_without_token_limit`, `test_entity_extraction_prompt_uses_entity_schema_boundaries`, and `test_empty_enabled_tasks_does_not_call_llm`. After relaunch, the Python process reported `NLWP=17`, confirming 16 worker threads plus the main thread.
- Completed run: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/run_output_no_thinking/manifest.json` was generated at `2026-05-30T10:32:33.587380+00:00`.
- LLM cache status: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/llm_pilot_200_no_thinking_cache.jsonl` contains 266 records: 206 `entity_extraction` records, 20 `relation_extraction_batch` records, and 40 `edge_evidence_judge` records. All records had empty error strings, first-attempt success, 0 JSON repairs, and used the model. The 206 entity records include 6 duplicate historical records from the earlier cache-key restart; manifest counts are based on the 200-document run.
- Manifest counts: 200 documents, 19 taxonomy nodes, 494 final entities, 906 raw entities, 412 filtered entities, 843 LLM entity mentions, 80 LLM relation pairs, 0 LLM relation edges, 80 relation rejections, 1,636 paper-level edges, 168 trusted edges, 1,468 candidate edges, 752 trajectories, 192 temporal windows, 7 macro patterns, 260 LLM judge records, and quality score 0.625.
- Quality summary: `evaluation/quality_report.json` reports overall quality 0.625 with dimension scores: taxonomy 0.888, entity layer 0.586, edge evidence 0.346, coevolution 0.258, forecast hooks 0.672, and LLM reliability 1.000. LLM reliability details: 260 records, 260 model-used records, schema-valid rate 1.0, error count 0, cache-hit rate 0.527.
- Interpretation: Parallel execution solved the throughput problem. The LLM entity layer scaled cleanly and the full pilot produced many downstream trajectories, but schema-guided LLM relation extraction rejected all 80 tested pairs, so relation prompt/pair construction still needs calibration before using LLM relations as the main edge source. Trusted edges in this pilot come from the existing graph/evidence pipeline after LLM entity integration and edge judging, not from accepted LLM relation edges.
- Current state: No `evotaxa_llm_pilot_200` tmux session or `run-full` process remains active. The completed output is under `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/run_output_no_thinking/`.
- Next steps: Audit `graph/relation_rejections.jsonl`, `graph/edge_evidence_audit.jsonl`, `graph/entity_quality_report.jsonl`, and representative `graph/method_registry.jsonl` cards before any 4,126-document LLM run. In particular, inspect why relation extraction returns 0 accepted edges and whether pair construction is giving Qwen comparable/evolution-relevant pairs.

#### Follow-up at 2026-05-30 19:56 CST - Prompt Template Unification

- Scope: Unified EvoTaxa LLM prompts under a YAML prompt-spec directory, following the `task_specs/prompts(_en)` pattern used by `/vepfs-mlp2/c20250513/241404044/users/roytian/NarrativeKnowledgeWeaver/archive/NarrativeKnowledgeWeaver_langgraph`.
- Actions taken: Added `src/evotaxa/prompts.py` with a lightweight YAML prompt loader and declared-variable renderer; added prompt templates under `task_specs/prompts/llm/` for entity extraction, relation extraction, relation batch extraction, edge evidence judging, taxonomy candidate judging, schema inference, schema revision judging, macro pattern summary, and the JSON-only system prompt; added `task_specs/prompts/screening/relevance_screening.yaml`; changed `src/evotaxa/llm.py` to render prompts from YAML instead of hardcoding task strings; changed `scripts/screen_relevance.py` to default to the YAML relevance prompt while preserving legacy Markdown template compatibility; added `llm.prompt_dir` and `llm.system_prompt_id` config fields; added `PyYAML>=6.0.1` dependency.
- Decisions or rationale: The renderer replaces only declared `{variable}` names and leaves undeclared braces untouched, so JSON examples inside templates are safe. The OpenAI-compatible cache key now includes the rendered system prompt, so changing the YAML system instruction creates a distinct cache entry. Existing task prompt text was preserved as closely as possible to avoid invalidating behavior beyond the intended prompt-management refactor.
- Verification:
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python -m py_compile src/evotaxa/prompts.py src/evotaxa/config.py src/evotaxa/llm.py scripts/screen_relevance.py`
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python -m pytest tests/test_smoke.py tests/test_relevance_screening.py` passed 44 tests in 3.59s.
  - `PYTHONPATH=src /vepfs-mlp2/c20250513/241404044/users/roytian/anaconda3/bin/python -m evotaxa.cli validate-config --config configs/qwen_local_llm.example.toml` passed and resolved normalized paths.
- Outputs or changed paths: `src/evotaxa/prompts.py`, `src/evotaxa/llm.py`, `src/evotaxa/config.py`, `scripts/screen_relevance.py`, `configs/qwen_local_llm.example.toml`, `pyproject.toml`, `tests/test_smoke.py`, `tests/test_relevance_screening.py`, and new YAML prompt files under `task_specs/prompts/`.
- Current state: Prompt text is now centrally managed and editable without modifying `llm.py`. Relevance screening uses the same prompt infrastructure by default, while older Markdown templates remain loadable for backward compatibility.
- Next steps: Relation prompt quality still needs calibration because the completed 200-document pilot rejected all 80 LLM relation pairs. With templates externalized, the next iteration should modify only `task_specs/prompts/llm/relation_extraction_batch.yaml` and potentially relation pair-construction logic, then rerun a small cached pilot.

#### Follow-up at 2026-05-30 20:37 CST - Qwen3 Relation Candidate Calibration

- Scope: Investigated why the completed 200-document Qwen pilot produced 80 schema-guided LLM relation pairs but 0 accepted LLM relation edges.
- Starting point: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/run_output_no_thinking/graph/relation_extraction_report.jsonl` showed the first rejected pairs connected `evaluation_protocol__empirical_performance` to methods such as `method__genetic_algorithm` and `modeling_strategy__multi_agent_simulation` across unrelated papers. Rejection reasons were dominated by `weak_co_mention`, which was appropriate behavior by Qwen.
- Actions taken: Changed relation pair construction to use entity mentions, target-document source evidence, relation cue proximity, same-document evidence, plausible entity-type pairs, chronology, directional cues, and per-pair taxonomy-node merging before LLM calls; added `graph.llm_relation_candidate_min_score`; recorded `candidate_score` and `candidate_evidence` in relation reports; tightened relation extraction prompts to say candidate metadata is retrieval evidence only and to require `{description, quote}` evidence objects; made LLM string evidence backward-compatible by preserving strings as quotes; expanded quote-grounding cue terms for `adapts`, `improves`, and `validates`; added `scripts/probe_relation_candidates.py`.
- Qwen config: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/qwen235_relation_probe_20260530/config.qwen235_relation_probe.json` uses `model_name=Qwen3-235B-FP8`, `base_url=http://127.0.0.1:8001/v1`, `api_key_env=EVOTAXA_LLM_API_KEY`, `enabled_tasks=["relation_extraction_batch"]`, `chat_template_kwargs.enable_thinking=false`, `temperature=0`, and no `max_tokens`.
- Commands:
  - `curl -s http://127.0.0.1:8001/v1/models -H 'Authorization: Bearer <EVOTAXA_LLM_API_KEY>'`
  - `EVOTAXA_LLM_API_KEY=$EVOTAXA_LLM_API_KEY PYTHONPATH=src python scripts/probe_relation_candidates.py --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/qwen235_relation_probe_20260530/config.qwen235_relation_probe.json --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/run_output_no_thinking --output-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/qwen235_relation_probe_20260530/probe_output_candidates_only --limit 24 --batch-size 4`
  - `EVOTAXA_LLM_API_KEY=$EVOTAXA_LLM_API_KEY PYTHONPATH=src python scripts/probe_relation_candidates.py --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/qwen235_relation_probe_20260530/config.qwen235_relation_probe.json --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/run_output_no_thinking --output-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/qwen235_relation_probe_20260530/probe_output_llm_24_prompt_v2 --limit 24 --batch-size 4 --run-llm`
  - `PYTHONPATH=src python -m pytest tests/test_smoke.py tests/test_relevance_screening.py -q`
- Verified facts: Qwen3 service at port 8001 exposed only `Qwen3-235B-FP8`; a JSON smoke request succeeded with `enable_thinking=false`. Candidate-only probe generated 24 candidates, all same-document, both-entity-mentioned, and relation-cue-near-entity, with no repeated taxonomy-node duplicates. Qwen3 prompt-v2 probe ran 6 relation-extraction batches, all first-attempt success, no errors, no JSON repairs, and accepted 9 of 24 candidates.
- Accepted relation sample: `probe_output_llm_24_prompt_v2/llm_relation_report.jsonl` contains accepted `uses_component`, `adapts`, `extends`, `improves`, and `validates` edges. After quote-grounding cue updates, 6 accepted strong edges audit as trusted on their quote evidence, 2 accepted non-strong `uses_component` edges remain candidates by design, and 1 `extends` edge remains candidate because the quote does not sufficiently ground the relation.
- Outputs: Probe artifacts are under `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/qwen235_relation_probe_20260530/`, including `probe_output_candidates_only/summary.json`, `probe_output_llm_24_prompt_v2/summary.json`, `candidate_pairs.jsonl`, `llm_relation_report.jsonl`, `llm_relation_edges.jsonl`, and `llm_relation_records.jsonl`.
- Interpretation: The 0/80 LLM relation result was primarily a candidate-generation problem, not a Qwen capability problem. With evidence-constrained candidates and the Qwen3-235B-FP8 model, relation extraction produces plausible accepted edges and quote objects. The remaining risk is entity direction/schema ambiguity in a few cases, so the next full run should still be staged before scaling to all 4,126 core papers.
- Current state: Code/tests are updated and `PYTHONPATH=src python -m pytest tests/test_smoke.py tests/test_relevance_screening.py -q` passed 46 tests in 3.79s.
- Next steps: Run a 200-document end-to-end Qwen3-235B-FP8 pilot with the new relation candidate logic and relation prompt, then compare accepted LLM edges, trusted edges, trajectories, and edge evidence audit against the previous `run_output_no_thinking` pilot before launching a 4,126-document LLM run.

#### Follow-up at 2026-05-30 21:17 CST - Evolution Dashboard Visualization

- Goal: Create a reusable visualization for demonstrating EvoTaxa evolution artifacts from a completed run.
- Actions taken: Added `scripts/build_evolution_visualization.py`, which reads an EvoTaxa `run-root` and generates a self-contained static HTML dashboard plus a small summary JSON. The dashboard includes run metrics, yearly document/entity/edge/window signals, an interactive entity-edge evolution graph, macro-pattern selection/highlighting, trajectory list, temporal-window list, and click-through evidence cards for entities, edges, trajectories, patterns, and windows.
- Commands:
  - `python -m py_compile scripts/build_evolution_visualization.py`
  - `python scripts/build_evolution_visualization.py --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/main_run_output_entity_grounding_v4_one_sided_current`
  - `python scripts/build_evolution_visualization.py --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/run_output_no_thinking`
  - Node syntax parse of the generated dashboard script succeeded for the 4,126-core page.
- Outputs:
  - Full core dashboard: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/main_run_output_entity_grounding_v4_one_sided_current/visualization/evolution_dashboard.html`
  - Full core summary: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/main_run_output_entity_grounding_v4_one_sided_current/visualization/evolution_dashboard.summary.json`
  - 200-document LLM pilot dashboard: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/run_output_no_thinking/visualization/evolution_dashboard.html`
  - 200-document LLM pilot summary: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/run_output_no_thinking/visualization/evolution_dashboard.summary.json`
- Verified facts:
  - Full core page embeds 4,126 documents, 31 entity cards, 11 trusted edges, 15 trajectories, 7 macro patterns, 58 temporal windows, and quality score 0.567. Date span is 1990-07-01 to 2026-07-25.
  - 200-document LLM pilot page embeds 200 documents, 240 displayed entity cards from 494 total, 168 trusted edges, 240 displayed trajectories from 752 total, 7 macro patterns, 192 temporal windows, and quality score 0.625. Date span is 1990-07-01 to 2026-05-27.
  - The current environment does not have Playwright installed, so browser screenshot QA was not run. Static HTML structure checks and Node script parse checks passed.
- Interpretation: The 4,126-core dashboard is the better high-level coverage view, but its graph layer is sparse because the strict deterministic run currently has only 11 trusted edges. The 200-document LLM pilot dashboard is better for live demonstration of dense micro trajectories and macro-pattern highlighting.
- Current state: The visualization generator is reusable for future EvoTaxa outputs and does not require a dev server; the generated HTML can be opened directly.

#### Follow-up at 2026-05-30 21:39 CST - Backend Dashboard And Node Cards

- Goal: Add a lightweight backend so the evolution dashboard can expose every node card, not only the nodes visible in the SVG graph.
- Actions taken: Added `scripts/serve_evolution_dashboard.py`; changed `scripts/build_evolution_visualization.py` so the same frontend can run either as a self-contained static HTML page or as a backend-loaded page. Added a first-class node-card browser with search, type filtering, pagination, and click-through detail cards.
- Backend APIs:
  - `/` or `/dashboard`: dashboard frontend.
  - `/api/data`: visualization payload for the active run.
  - `/api/runs`: active run summary.
  - `/api/entities?q=&type=&limit=&offset=`: paginated node cards.
  - `/api/entities/{entity_id}`: full node detail, including raw node record, support documents, incident trusted edges, and related trajectories.
- Launch command:
  - `tmux new-session -d -s evotaxa_dashboard "cd /vepfs-mlp2/c20250513/241404044/users/roytian/EvoTaxa && python scripts/serve_evolution_dashboard.py --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/run_output_no_thinking --port 8765 > data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/run_output_no_thinking/visualization/logs/dashboard_server.log 2>&1"`
- Current service:
  - URL: `http://127.0.0.1:8765/`
  - tmux session: `evotaxa_dashboard`
  - Log: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/run_output_no_thinking/visualization/logs/dashboard_server.log`
  - Active run: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/run_output_no_thinking`
- Verified facts: `py_compile` passed for both visualization scripts. The served page returned 50,253 bytes and its script parsed under Node. `/api/entities?limit=5` returned 494 total nodes and 5 rows. `/api/entities/method__collective_fermi_estimation` returned 2 support documents, 31 incident edges, 432 related trajectories, and the raw node record keys `aliases`, `canonical_name`, `entity_id`, `entity_type`, `first_seen_date`, `support_documents`, and `taxonomy_nodes`.
- Note: A temporary API verification failure during development was caused by a shell pipeline/heredoc mistake that made Python read empty stdin after `curl`; the backend endpoint itself returned HTTP 200 and valid JSON.

#### Follow-up at 2026-05-30 21:51 CST - Time-Sliced Evolution View

- Problem: The initial all-node/all-edge SVG was a hairball and not a reliable presentation surface. It exposed too many edges and labels at once, making the visual read as noise rather than evolution.
- Decision: Treat the graph as a time-windowed navigation view, not as the full audit surface. Full node and evidence inspection remains in the backend node-card browser and detail API.
- Actions taken: Reworked the main graph so the Y axis is time from top to bottom and the X axis is entity type lanes. The default view shows the densest one-year window instead of the entire corpus. Added controls for previous/next time window and zoom in/out across 3-month, 1-year, 5-year, and global granularities.
- Current behavior:
  - Default: the oldest one-year window, with older evidence at the top and newer evidence lower in the chart.
  - `Zoom in`: moves to 3-month windows around the current center.
  - `Zoom out`: moves to 5-year and then global context.
  - A time slider is the primary navigation control for moving the active time window.
  - Mouse wheel over the graph moves the active window; Ctrl/Command + wheel changes granularity.
  - Selecting a macro pattern, node, edge, or trajectory keeps the selected context but restricts the visual to the active time slice when appropriate.
- Node-card readability: Replaced internal edge ids in the `关联边` and trajectory evidence sections with human-readable edge cards showing relation type, source node name, target node name, year, confidence, and a compact evidence quote.
- Verification: `py_compile` passed for `scripts/build_evolution_visualization.py` and `scripts/serve_evolution_dashboard.py`. The regenerated static pages succeeded for both the 200-document LLM pilot and 4,126-core run. The backend was restarted in tmux session `evotaxa_dashboard`; the served page includes the slider/wheel time controls and parsed successfully under Node. `/api/runs` still reports the active 200-document pilot with 494 entities and 168 trusted edges. `/api/entities/method__collective_fermi_estimation` returns 31 incident edges, and the top returned edge has relation type `improves` with a readable quote excerpt.

#### Follow-up at 2026-05-30 22:04 CST - Edge Presence And Type Selection

- Problem: The dashboard could show a time slice with no trusted edges while still looking like an evolution view. It also laid all entity types side by side, which made the chart too wide and weakly informative.
- Actions taken: Changed the default time window to the earliest window with trusted-edge evidence rather than the earliest node/document timestamp. Added an entity-type selection bar above the graph (`全部类型`, `method`, `modeling_strategy`, etc.). Selecting an entity type filters edges to those touching that type and jumps to the earliest trusted-edge window for that selected type.
- Empty-state behavior: If the active time slice has no trusted edges under the current type/filter selection, the graph now displays an explicit message: `当前时间片没有 trusted edge；这不是演化证据窗口。拖动时间滑杆或切换类型。`
- Verification: `py_compile` passed, both static dashboards regenerated, backend restarted, served page parsed under Node, and `/api/runs` still reports the active 200-document pilot with 168 trusted edges.

#### Follow-up at 2026-05-30 23:02 CST - Explicit Successor Edges For Dashboard

- Problem: `method_edges.trusted.jsonl` was an internal evidence-quality layer, not a clean user-facing evolution layer. It included same-document and cross-type relations, so the dashboard could show edges that were not true old-to-new successor links.
- Decision: Evolution visualization should show only explicit successor/predecessor edges. Old nodes do not automatically point to new nodes; if a target is genuinely new or no predecessor is supported, it remains an unlinked/birth node in this layer.
- Actions taken: Added `task_specs/prompts/llm/successor_edge_batch.yaml`, `extract_successor_edges_for_pairs` in `src/evotaxa/llm.py`, and `scripts/extract_successor_edges.py`. The successor prompt now rejects co-topic pairs, broad/generic predecessors, direction reversals, synonym or label variants, component-only use, and new concepts without predecessor evidence. Candidate filtering also excludes poor display-level entity names such as action/title-like phrases before successor judging.
- Dashboard changes: `scripts/build_evolution_visualization.py` and `scripts/serve_evolution_dashboard.py` now prefer `graph/successor_edges.accepted.jsonl` when present, including if it is empty. The dashboard summary exposes `edge_source`, `successor_edges`, `strict_evolution_edges`, `entities_with_accepted_predecessor`, `entities_as_accepted_predecessor`, `entities_without_accepted_predecessor`, and `predecessor_policy`. Header and empty-state text explicitly state that unlinked nodes are not forced into evolution edges.
- Commands:
  - `EVOTAXA_LLM_API_KEY=$EVOTAXA_LLM_API_KEY PYTHONPATH=src python scripts/extract_successor_edges.py --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/qwen235_relation_probe_20260530/config.qwen235_relation_probe.json --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/run_output_no_thinking --output-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/successor_edge_probe_20260530/llm_24_v4_display_filter --candidate-limit 120 --llm-limit 24 --batch-size 4 --run-llm`
  - `cp data/schema_probe/css_screened_20260530_v2/mainflow_proposal/successor_edge_probe_20260530/llm_24_v4_display_filter/successor_edges.accepted.jsonl data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/run_output_no_thinking/graph/successor_edges.accepted.jsonl`
  - `cp data/schema_probe/css_screened_20260530_v2/mainflow_proposal/successor_edge_probe_20260530/llm_24_v4_display_filter/summary.json data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/run_output_no_thinking/graph/successor_edges.extraction_summary.json`
  - `python scripts/build_evolution_visualization.py --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/llm_pilot_200_20260530/run_output_no_thinking --max-nodes 1200 --max-edges 1200 --max-trajectories 800 --max-windows 400`
- Verified facts: On the 200-document pilot, the successor probe judged 24 LLM candidates from 120 generated candidates, produced 6 LLM records with no errors, and accepted 4 successor edges. Rejection reasons were `component_only` 4, `synonym_or_label_variant` 2, `co_topic_only` 7, `direction_reversed` 2, and `generic_predecessor` 5. The accepted edges are `computational modeling -> computational organizational theory`, `simulation experiments -> replicable simulation experiments`, `word embeddings -> evolutionary clustering`, and `computational modeling -> agent simulation`.
- Current dashboard state: `http://127.0.0.1:8765/` is served from tmux session `evotaxa_dashboard`. `/api/data` reports `edge_source=graph/successor_edges.accepted.jsonl`, 200 documents, 494 node cards, 4 successor edges, 4 one-edge trajectories, 4 nodes with accepted predecessor, and 490 nodes without accepted predecessor in this pilot display.
- Interpretation: The sparse dashboard is expected because this is still a 200-document pilot and only 24 successor candidates have been LLM-judged. The 490 unlinked nodes should be read as “no accepted predecessor in the current pilot extraction,” not as proof that every node is a genuinely new concept.
- Next steps: Scale successor extraction to the 4,126 core-paper run after staging candidate limits and worker/concurrency settings. Keep the successor layer independent from the broader relation graph so presentation edges remain strictly evolutionary.

#### Follow-up at 2026-05-30 23:34 CST - Full 4,126 Successor Extraction With 24 Workers

- Goal: Run explicit successor/predecessor extraction on the 4,126 core-paper artifacts using 24 concurrent LLM workers.
- Code changes: `scripts/extract_successor_edges.py` now supports `--workers` and `--resume`. It writes `successor_llm_records.jsonl`, `successor_decisions.jsonl`, `successor_edges.accepted.jsonl`, and `summary.json` incrementally after each completed batch, so a run can be monitored or resumed without losing completed decisions.
- Config: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/successor_edge_full_4126_20260530/config.qwen235_successor_full_4126.json` uses `Qwen3-235B-FP8`, `http://127.0.0.1:8001/v1`, `enable_thinking=false`, no `max_tokens`, and a separate successor cache at `successor_edge_full_4126_20260530/qwen235_successor_full_4126_cache.jsonl`.
- Primary 4,126 run checked: `main_run_output_entity_grounding_v4_one_sided_current` has 4,126 documents but only 31 registry entities, 18 usable successor entities, and 42 successor candidates. Command output root: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/successor_edge_full_4126_20260530/current_v4_successor_24w`.
- Secondary 4,126 run checked: `main_run_output` has 4,126 documents, 117 registry entities, 85 usable successor entities, and 295 successor candidates. Command output root: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/successor_edge_full_4126_20260530/main_run_output_successor_24w`.
- Commands:
  - `EVOTAXA_LLM_API_KEY=$EVOTAXA_LLM_API_KEY PYTHONPATH=src python scripts/extract_successor_edges.py --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/successor_edge_full_4126_20260530/config.qwen235_successor_full_4126.json --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/main_run_output --output-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/successor_edge_full_4126_20260530/main_run_output_successor_24w --candidate-limit 0 --llm-limit 295 --batch-size 4 --workers 24 --run-llm --resume`
  - `EVOTAXA_LLM_API_KEY=$EVOTAXA_LLM_API_KEY PYTHONPATH=src python scripts/extract_successor_edges.py --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/successor_edge_full_4126_20260530/config.qwen235_successor_full_4126.json --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/main_run_output_entity_grounding_v4_one_sided_current --output-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/successor_edge_full_4126_20260530/current_v4_successor_24w --candidate-limit 0 --llm-limit 42 --batch-size 4 --workers 24 --run-llm --resume`
- Verified facts:
  - `main_run_output_successor_24w`: 295/295 candidates judged, 74 LLM records, `llm_errors={"": 74}`, 1 accepted edge, rejections dominated by `co_topic_only` 152 and `generic_predecessor` 74.
  - `current_v4_successor_24w`: 42/42 candidates judged, 11 LLM records, `llm_errors={"": 11}`, 2 accepted edges, rejections dominated by `co_topic_only` 16 and `generic_predecessor` 15.
  - No tmux successor sessions remained after completion.
- Quality interpretation: The accepted edges are not strong presentation edges because their predecessors are broad labels such as `social science research` and `big data`. They should not be installed into the dashboard as final evolution edges without additional node-layer cleanup or a narrower predecessor policy.
- Decision: Do not copy these full-run accepted edges into `graph/successor_edges.accepted.jsonl` yet. The run completed successfully, but the useful result is diagnostic: current 4,126 artifacts do not contain a sufficiently rich, stable node layer for successor visualization.
- Next steps: Run or repair the full 4,126 node/card extraction layer with Qwen, aiming for pilot-like node density and cleaner node names, then rerun successor extraction. Successor extraction is now fast and resumable; the blocking issue is upstream node quality and coverage.

#### Follow-up at 2026-05-31 00:01 CST - Full 4,126 LLM Node/Card Run Started

- Goal: Build a full 4,126-paper LLM entity/node-card layer before rerunning successor extraction.
- Cleanup: Removed old generated run directories under `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/`, including `core_support_run_output`, `main_run_output`, `main_run_output_entity_grounding_v2`, `main_run_output_entity_grounding_v3`, old relation probe outputs, old successor pilot probe outputs, and 12-document smoke outputs. Kept the 200-document dashboard pilot, the current sparse v4 run as a failure baseline, full successor diagnostics, configs, taxonomy/schema proposal, and source corpora.
- Config: Created `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/config.full_llm_nodes_4126.json`. It points to `data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/merged/corpus.screened.jsonl` with 4,126 core rows, uses `Qwen3-235B-FP8` at `http://127.0.0.1:8001/v1`, `enable_thinking=false`, no `max_tokens`, `enabled_tasks=["entity_extraction"]`, `max_workers=24`, `llm_entity_extraction_limit=5`, and disables LLM relation extraction, edge judging, macro patterns, and temporal windows for this first node-card production pass.
- Launch command:
  - `tmux new-session -d -s evotaxa_full_llm_nodes "cd /vepfs-mlp2/c20250513/241404044/users/roytian/EvoTaxa && EVOTAXA_LLM_API_KEY=$EVOTAXA_LLM_API_KEY PYTHONPATH=src python -m evotaxa.cli run-full --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/config.full_llm_nodes_4126.json --print-manifest > data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/logs/run.log 2>&1"`
- Current state at 2026-05-31 00:00 CST: tmux session `evotaxa_full_llm_nodes` is running. Cache file `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/full_llm_nodes_4126_cache.jsonl` had 168 records after about 4.5 minutes. The full output root will be `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output`.
- Monitoring commands:
  - `tmux list-sessions | rg evotaxa_full_llm_nodes`
  - `wc -l data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/full_llm_nodes_4126_cache.jsonl`
  - `tail -n 40 data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/logs/run.log`
- Next steps: When the run writes `manifest.json`, inspect entity counts, node quality, and sample node cards. If node density is acceptable, rebuild the dashboard from this run and rerun `scripts/extract_successor_edges.py` against it with 24 workers.

#### Follow-up at 2026-05-31 10:54 CST - Full 4,126 Node Run, Successor Edges, And Dashboard

- Goal: Replace the 200-document pilot visualization with a 4,126-core-paper node/card layer plus explicit old-to-new successor edges only.
- Full node/card run result: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/manifest.json` reports 4,126 documents, 8,122 kept registry entities, 14,120 raw entities, 5,998 filtered entities, 29,590 entity link records, 18,732 LLM entity mentions, 13,666 paper-level mentions, 37 old trusted heuristic edges, 60 old heuristic trajectories, quality score 0.594, and 4,126 LLM judge records with schema-valid rate 1.0.
- Successor candidate preparation: `scripts/extract_successor_edges.py` was tightened to prefilter older sources, skip label variants, skip broad predecessor labels, lower substring-only score inflation, support `--workers`, `--resume`, `--retry-failed-decisions`, `--max-sources-per-target`, and `--per-target-candidates`, and write JSONL outputs incrementally.
- Candidate-only diagnostic: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/successor_candidates_cleaned_v2/summary.json` reports 7,165 usable successor entities and 38,398 retained candidates after considering 729,172 source-target pairs. Important filter counts: 159,186 skipped as generic predecessor source, 85,770 below candidate-score threshold, 246 same-core labels, and 97 additional label/context variants. Candidate score mean was 0.440.
- LLM successor run: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/successor_llm_2000_cleaned_v2_24w/summary.json` reports 2,000 top candidates judged using Qwen3-235B-FP8, 24 workers for the main run, batch size 4, `enable_thinking=false`, no `max_tokens`, and incremental resume outputs. It produced 501 LLM records including one retry attempt for a 4-pair schema-validation failure; 342 raw accepted edges and 1,658 raw rejections. Rejections were dominated by `co_topic_only` 828, `generic_predecessor` 305, `component_only` 180, `direction_reversed` 125, `not_method_successor` 100, and `synonym_or_label_variant` 85. Four candidates remained `model_not_run` after repeated malformed-but-rejecting model output and are treated as rejected for display.
- Strict display filter: Added `scripts/filter_successor_edges.py` to keep raw LLM decisions auditable while installing only high-precision display edges. It enforces confidence >= 0.84, time delta >= 180 days, same-type successor semantics, label-quality guards, no same-document edge, no broad/general label target, no misbucketed embedding/model data-source edge, and explicit lineage evidence. Output: `.../successor_llm_2000_cleaned_v2_24w/strict_final/successor_edges.strict_accepted.jsonl`.
- Installed strict edges: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/graph/successor_edges.accepted.jsonl` now contains 136 strict successor edges. `graph/successor_edges.strict_summary.json` reports 342 raw accepted, 136 strict accepted, 206 raw accepted rejected by the strict display filter, 108 predecessor source entities, 123 successor target entities, and relation counts: extends 64, improves 25, specializes 26, generalizes 11, adapts 6, replaces 4.
- Dashboard rebuild: `scripts/build_evolution_visualization.py` was rerun against the full run. `visualization/evolution_dashboard.summary.json` reports 4,126 documents, 8,122 entities, 136 successor edges, 136 strict evolution edges, 123 nodes with accepted predecessor, 108 nodes as accepted predecessor, 7,999 nodes without accepted predecessor, 1,600 embedded entities, and 136 embedded trajectories. The date span shown by normalized full-run documents is 1990-07-01 to 2026-07-25.
- Dashboard backend: `scripts/serve_evolution_dashboard.py` now serves the full run at `http://127.0.0.1:8765/` from tmux session `evotaxa_dashboard`. `/api/runs` confirms run root `.../full_llm_nodes_4126_20260530/run_output`; `/api/entities?limit=3` returns 8,122 total node cards; `/api/entities/method__word_embedding` returns support documents, representative mentions, incident strict edges, trajectories, and the raw entity record.
- Dashboard code changes: Node detail cards now include representative LLM/rule mentions, support document snippets, taxonomy labels, strict incoming/outgoing evolution edges, trajectories, and raw node records. The visual graph uses vertical time flow with older items above newer items, starts at the earliest available edge/node window, supports the slider and wheel-based time navigation, and shows only `graph/successor_edges.accepted.jsonl` when present.
- Commands:
  - `EVOTAXA_LLM_API_KEY=$EVOTAXA_LLM_API_KEY PYTHONPATH=src python scripts/extract_successor_edges.py --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/successor_edge_full_4126_20260530/config.qwen235_successor_full_4126.json --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output --output-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/successor_llm_2000_cleaned_v2_24w --candidate-limit 2000 --llm-limit 2000 --batch-size 4 --workers 24 --max-sources-per-target 120 --per-target-candidates 6 --run-llm --resume`
  - `EVOTAXA_LLM_API_KEY=$EVOTAXA_LLM_API_KEY PYTHONPATH=src python scripts/extract_successor_edges.py --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/successor_edge_full_4126_20260530/config.qwen235_successor_full_4126.json --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output --output-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/successor_llm_2000_cleaned_v2_24w --candidate-limit 2000 --llm-limit 2000 --batch-size 4 --workers 4 --max-sources-per-target 120 --per-target-candidates 6 --run-llm --resume --retry-failed-decisions`
  - `PYTHONPATH=scripts:src python scripts/filter_successor_edges.py --input-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/successor_llm_2000_cleaned_v2_24w --output-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/successor_llm_2000_cleaned_v2_24w/strict_final --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output --min-confidence 0.84 --min-time-delta-days 180 --install`
  - `python scripts/build_evolution_visualization.py --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output --max-nodes 1600 --max-edges 1200 --max-trajectories 1000 --max-windows 400 --support-doc-limit 12`
  - `tmux new-session -d -s evotaxa_dashboard "cd /vepfs-mlp2/c20250513/241404044/users/roytian/EvoTaxa && source ../anaconda3/bin/activate && python scripts/serve_evolution_dashboard.py --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output --port 8765 --max-nodes 1600 --max-edges 1200 --max-trajectories 1000 --max-windows 400 > data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/visualization/logs/dashboard_server.log 2>&1"`
- Caveats: This is a top-2,000-candidate successor pass, not an exhaustive 38,398-candidate successor extraction. Strict display edges are intentionally high precision and sparse. Some remaining accepted edges are still candidates for human review because the upstream node layer can contain broad names or imperfect entity-type assignment. Macro-pattern synthesis remains disabled. Temporal windows are not generated in this run, so the dashboard's time slicing is visualization-only over node/edge dates.
- Next steps: Inspect the 136 strict edges in the dashboard, decide whether the default strict filter is too conservative, then expand LLM judging to top 5,000 or 10,000 candidates if more edge density is needed. Separately improve node-card persistence so registry records carry richer card fields directly rather than reconstructing card details from mentions and documents at serve time.

#### Follow-up at 2026-05-31 12:58 CST - Materialized Cards And Successor Trajectories

- Goal: Reduce the gap between the intended EvoTaxa artifact contract and the current dashboard-only reconstruction by making node cards and successor-edge trajectories first-class run artifacts.
- Starting point: The 4,126-paper full LLM node run had 8,122 registry entities and 136 strict successor edges, but complete node cards were reconstructed by `scripts/serve_evolution_dashboard.py` at request time. The run also still contained legacy `trajectory/evolution_trajectories.jsonl` with 60 heuristic trusted-edge trajectories, while the dashboard generated successor trajectories transiently.
- Actions taken: Added `scripts/materialize_evolution_artifacts.py`; it reads normalized documents, taxonomy, entity schema, method registry, mentions, and `graph/successor_edges.accepted.jsonl`, then writes materialized node cards and strict-successor trajectories. Updated `scripts/build_evolution_visualization.py` and `scripts/serve_evolution_dashboard.py` so the dashboard and APIs prefer `graph/entity_cards.jsonl` and `trajectory/successor_trajectories.jsonl` when present. Added a focused regression test to ensure parallel successor edges between the same two entities are not collapsed by entity-path deduplication.
- Outputs:
  - Node cards: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/graph/entity_cards.jsonl`
  - Card summary: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/graph/entity_cards.summary.json`
  - Successor trajectories: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/trajectory/successor_trajectories.jsonl`
  - Successor trajectory eval: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/trajectory/successor_trajectory_eval.jsonl`
  - Updated dashboard summary: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/visualization/evolution_dashboard.summary.json`
- Verified facts:
  - `scripts/materialize_evolution_artifacts.py` produced 8,122 entity cards, 136 strict successor edges, and 146 successor trajectories.
  - `trajectory/successor_trajectory_eval.jsonl` reports 136 strict successor edges covered by at least one successor trajectory, mean successor trajectory score 0.868, mean path length 1.074, and max path length 2.
  - The run manifest now includes `counts.entity_cards = 8122`, `counts.successor_trajectories = 146`, and artifact layout entries for `entity_cards`, `successor_trajectories`, and `successor_trajectory_eval`.
  - Rebuilt dashboard summary reports `entity_cards = 8122`, `successor_edges = 136`, `trajectories = 146`, `successor_trajectories = 146`, and `embedded_trajectories = 146`.
  - API check at `http://127.0.0.1:8765/api/entities/method__word_embedding` returned `materialized_card != null`, 15 support documents, 15 mentions, 5 incident strict edges, and successor trajectories with `trajectory_source = graph/successor_edges.accepted.jsonl`.
  - `python -m py_compile scripts/materialize_evolution_artifacts.py scripts/build_evolution_visualization.py scripts/serve_evolution_dashboard.py tests/test_smoke.py` passed.
  - `PYTHONPATH=src pytest -q tests/test_smoke.py::test_successor_trajectory_materialization_preserves_parallel_edges` passed.
- Commands:
  - `python scripts/materialize_evolution_artifacts.py --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output --support-doc-limit 24 --mention-limit 24 --edge-limit 24`
  - `python scripts/build_evolution_visualization.py --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output --max-nodes 1600 --max-edges 1200 --max-trajectories 1000 --max-windows 400 --support-doc-limit 12`
  - `tmux new-session -d -s evotaxa_dashboard "cd /vepfs-mlp2/c20250513/241404044/users/roytian/EvoTaxa && source ../anaconda3/bin/activate && python scripts/serve_evolution_dashboard.py --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output --port 8765 --max-nodes 1600 --max-edges 1200 --max-trajectories 1000 --max-windows 400 > data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/visualization/logs/dashboard_server.log 2>&1"`
- Current state: The dashboard is again served from tmux session `evotaxa_dashboard` at `http://127.0.0.1:8765/`. Node cards and successor trajectories are now inspectable JSONL artifacts instead of dashboard-only derived objects.
- Caveats: The legacy `trajectory/evolution_trajectories.jsonl` remains in the run as a historical pipeline artifact and still reflects old trusted-edge semantics. Use `trajectory/successor_trajectories.jsonl` for current evolution display and audit. Temporal windows are still disabled for this run, and successor extraction still covers only the top 2,000 candidate pairs.
- Next steps: Expand successor LLM judging to top 5,000 or 10,000 candidates after auditing the current 136 strict edges; then rerun `materialize_evolution_artifacts.py` and rebuild the dashboard. Separately, wire successor trajectories into the main pipeline or make this materialization step a standard post-run command.

#### Follow-up at 2026-05-31 13:27 CST - Domain-Grounded Node Cards And Type Diagnostics

- Goal: Address the problem that some nodes and trajectories were too generic for computational social science, for example showing generic ML lineages such as `artificial neural network -> convolutional neural network -> graph convolutional network` instead of domain-grounded social-science method evolution.
- Actions taken:
  - Tightened `task_specs/prompts/llm/entity_extraction.yaml` so future entity extraction must return `contextual_name`, `domain_context`, and `method_role`, and must not return bare general-purpose AI/ML algorithm names unless they are used as social-science method/data/measurement/tool/evaluation objects in the document.
  - Updated `src/evotaxa/graph.py` so LLM entity mention audit records can preserve `contextual_name`, `domain_context`, and `method_role`.
  - Updated `src/evotaxa/llm.py` schema validation to accept and validate those optional contextual fields.
  - Extended `scripts/materialize_evolution_artifacts.py` to infer contextual display fields for the existing 4,126-paper run from quotes, support documents, and taxonomy labels. It now writes `display_name`, `contextual_name`, `domain_context`, `method_role`, `context_terms`, `generic_technology_name`, and `domain_grounding_score` into each node card.
  - Added `schema/entity_type_diagnostics.json` with entity-type counts, successor-edge counts, generic-technology rates, domain-grounding scores, and suggested merged schema groups.
  - Updated `scripts/build_evolution_visualization.py` and `scripts/serve_evolution_dashboard.py` so dashboard node cards and trajectory labels prefer contextual display names while preserving canonical labels for audit.
  - Tightened `scripts/filter_successor_edges.py` so generic ML architecture lineages are rejected from the display successor layer unless there is clear corpus-internal lineage evidence; this removed the ANN/CNN/GCN-style trajectory from the dashboard.
- Verified facts:
  - Strict successor display edges decreased from 127 to 126 after the additional generic-architecture filter. `generic_ml_architecture_not_css_evolution` now accounts for 10 strict rejections.
  - Materialized artifacts now report 8,122 entity cards, 126 strict successor edges, and 132 successor trajectories.
  - `schema/entity_type_diagnostics.json` reports the current entity-type distribution: `method` 3,165 (38.97%), `measurement_strategy` 1,505 (18.53%), `data_source` 1,007 (12.40%), `modeling_strategy` 946 (11.65%), `infrastructure_tooling` 710 (8.74%), `evaluation_protocol` 581 (7.15%), and `governance_practice` 208 (2.56%).
  - Type diagnostic suggests merged display/schema groups: `analytic_method = method + modeling_strategy + measurement_strategy`, `evidence_and_infrastructure = data_source + infrastructure_tooling`, and `validation_and_governance = evaluation_protocol + governance_practice`. The strongest merge pressure is `governance_practice`, with low share and only one strict successor edge.
  - API check at `http://127.0.0.1:8765/api/entities/method__word_embedding` now returns `name = word embedding for social media text`, `canonical = word embedding`, `domain_context = social media text`, `method_role = measurement_or_annotation`, and `generic = true`.
  - API check at `http://127.0.0.1:8765/api/data` now shows contextual trajectory labels, for example `word embedding for social media text -> bidirectional encoder representations from transformers for social media text`, while preserving canonical labels separately.
  - Tests passed: `PYTHONPATH=src pytest -q tests/test_smoke.py::test_successor_display_filter_rejects_generic_ml_architecture_lineage tests/test_smoke.py::test_successor_trajectory_materialization_preserves_parallel_edges`.
- Outputs:
  - Contextual node cards: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/graph/entity_cards.jsonl`
  - Type diagnostics: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/schema/entity_type_diagnostics.json`
  - Updated strict edges: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/graph/successor_edges.accepted.jsonl`
  - Updated trajectories: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/trajectory/successor_trajectories.jsonl`
  - Updated dashboard: `http://127.0.0.1:8765/`
- Current state: Node cards now carry both canonical terms and domain-grounded display context. The dashboard still supports canonical audit, but the visible labels are less likely to read as generic AI/ML taxonomy.
- Caveats: Existing contextual fields are inferred post hoc from quotes/titles/taxonomy labels because the 4,126-paper entity extraction cache was created before the prompt required contextual fields. A future full node extraction run should let the LLM populate those fields directly. Entity type merging is diagnostic only; the run still uses the seven original entity types.
- Next steps: Convert `entity_type_diagnostics.json` into an adaptive schema revision step: merge sparse or weakly separated types for display and candidate generation, while preserving fine-grained original types as audit metadata. Then rerun successor candidate generation using contextual display labels and merged type groups.

#### Follow-up at 2026-05-31 14:11 CST - Adaptive Schema Groups For Candidate Generation And Display

- Goal: Make entity types evolvable/mergeable instead of forcing sparse extracted types such as `governance_practice` to remain independent evolution lanes.
- Decision: Do not rerun relevance screening or the full 4,126-document entity extraction. Preserve the original `entity_type` as audit metadata, but add `schema_group` as the default axis for successor candidate generation, strict edge interpretation, node browsing, and dashboard lanes.
- Schema groups:
  - `analytic_method = method + modeling_strategy + measurement_strategy`
  - `evidence_and_infrastructure = data_source + infrastructure_tooling`
  - `validation_and_governance = evaluation_protocol + governance_practice`
- Code changes:
  - Added `scripts/schema_groups.py` as the shared schema-group mapping.
  - Updated `scripts/extract_successor_edges.py` with `--candidate-scope {schema_group,entity_type}`; default is now `schema_group`. Candidate and edge records now keep `source_entity_type`, `target_entity_type`, `source_schema_group`, `target_schema_group`, and `candidate_scope_value`.
  - Updated `task_specs/prompts/llm/successor_edge_batch.yaml` so the LLM prompt explains same-schema-group successor judging and cross-original-type audit context.
  - Updated `scripts/filter_successor_edges.py`, `scripts/materialize_evolution_artifacts.py`, `scripts/build_evolution_visualization.py`, and `scripts/serve_evolution_dashboard.py` so display and filtering use schema groups while preserving original entity types in node/edge details.
  - Added stricter label filtering for plural/singular label variants and broad ML predecessors such as `supervised machine learning` or `semi supervised machine learning algorithm`.
- Candidate diagnostic:
  - Output root: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/successor_candidates_schema_group_v2`
  - Command: `PYTHONPATH=scripts:src python scripts/extract_successor_edges.py --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/successor_edge_full_4126_20260530/config.qwen235_successor_full_4126.json --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output --output-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/successor_candidates_schema_group_v2 --candidate-limit 0 --llm-limit 0 --candidate-scope schema_group --batch-size 4 --workers 1 --max-sources-per-target 120 --per-target-candidates 6`
  - `summary.json` reports 39,182 retained candidates from 7,165 usable successor entities, using three schema groups. Counts: `analytic_method` 27,748, `evidence_and_infrastructure` 7,465, and `validation_and_governance` 3,969.
  - Cross-original-type candidates: 19,981 of 39,182. Largest cross-type directions: `method -> measurement_strategy` 3,879, `measurement_strategy -> method` 3,816, `modeling_strategy -> method` 3,029, `method -> modeling_strategy` 2,527, `infrastructure_tooling -> data_source` 1,707, and `data_source -> infrastructure_tooling` 1,370.
  - Important filter counts: 777,789 source-target pairs considered, 189,699 skipped as generic predecessor source, 68,474 below candidate score, 395 same-core label, 146 duplicate label, and 128 other label/context variants.
- Materialized outputs:
  - `graph/entity_cards.jsonl` now includes `schema_group`, `schema_group_label`, `schema_group_definition`, and `schema_group_members` in each card.
  - `schema/entity_schema_groups.json` records the three group definitions.
  - `schema/entity_type_diagnostics.json` now includes `schema_group_distribution`: `analytic_method` 5,616 cards / 108 strict successor edges, `evidence_and_infrastructure` 1,717 cards / 8 edges, and `validation_and_governance` 789 cards / 10 edges.
- Dashboard state:
  - Static dashboard rebuilt at `visualization/evolution_dashboard.html`.
  - Backend restarted in tmux session `evotaxa_dashboard` at `http://127.0.0.1:8765/`.
  - `/api/data` now reports `entity_types = [analytic_method, evidence_and_infrastructure, validation_and_governance]` and also exposes `raw_entity_type_labels` for audit.
  - `/api/entities/method__word_embedding` returns `type = analytic_method`, `entity_type = method`, and keeps the domain-grounded display name `word embedding for social media text`.
- Verification:
  - `python -m py_compile scripts/schema_groups.py scripts/extract_successor_edges.py scripts/filter_successor_edges.py scripts/materialize_evolution_artifacts.py scripts/build_evolution_visualization.py scripts/serve_evolution_dashboard.py tests/test_smoke.py` passed.
  - `PYTHONPATH=src pytest -q tests/test_smoke.py::test_schema_group_candidate_generation_allows_adjacent_type_evolution tests/test_smoke.py::test_successor_edge_accepts_same_schema_group_across_original_types tests/test_smoke.py::test_successor_display_filter_rejects_generic_ml_architecture_lineage tests/test_smoke.py::test_successor_trajectory_materialization_preserves_parallel_edges` passed.
- Current state: Schema grouping is now implemented for artifacts, candidate generation, strict-edge handling, API responses, and dashboard lanes. The current installed strict edge set still comes from the earlier top-2,000 LLM decisions; the new schema-group candidate pool has not yet been LLM-judged.
- Next steps: Run successor LLM judging against `successor_candidates_schema_group_v2`, ideally first with top 2,000 or 5,000 candidates to compare accepted edge quality and cross-type successor utility before committing to a full 39,182-candidate pass.

#### Follow-up at 2026-05-31 15:13 CST - Full Schema-Group Successor Rerun Started

- Goal: Replace the old top-2,000 successor assets with a full rerun using the new schema-group candidate space, so the dashboard no longer reflects the old same-entity-type evolution edge set.
- Scope: This reruns successor candidate generation and LLM successor judging over all schema-group candidates. It does not rerun relevance screening or the 4,126-document entity extraction because the stale layer is the successor/trajectory/dashboard asset layer.
- Output root: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/successor_schema_group_full_24w_20260531`
- Main run:
  - tmux session: `evotaxa_successor_schema_group_full`
  - command: `EVOTAXA_LLM_API_KEY=$EVOTAXA_LLM_API_KEY PYTHONPATH=scripts:src python scripts/extract_successor_edges.py --config data/schema_probe/css_screened_20260530_v2/mainflow_proposal/successor_edge_full_4126_20260530/config.qwen235_successor_full_4126.json --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output --output-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/successor_schema_group_full_24w_20260531 --candidate-limit 0 --llm-limit 39182 --candidate-scope schema_group --batch-size 4 --workers 24 --max-sources-per-target 120 --per-target-candidates 6 --run-llm --resume`
  - log: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/logs/successor_schema_group_full_24w_20260531.log`
- Automatic watcher:
  - script: `scripts/run_schema_group_successor_full_pipeline.sh`
  - tmux session: `evotaxa_successor_schema_group_watcher`
  - behavior: watches for all 39,182 decisions; if the main run stops early, resumes it with `--retry-failed-decisions`; after completion runs strict filtering, installs new strict edges into `run_output/graph/successor_edges.accepted.jsonl`, materializes cards/trajectories, rebuilds the dashboard, and restarts `evotaxa_dashboard`.
  - log: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/logs/successor_schema_group_full_pipeline_20260531.log`
- Verified early status:
  - The run started with 39,182 candidates, 9,796 batches, batch size 4, and 24 workers.
  - At 2026-05-31 15:18 CST, watcher saw 1,316/39,182 decisions.
  - At 2026-05-31 15:20 CST, `summary.json` showed 337 LLM records, about 1,348 completed decisions, 350 raw accepted edges, and no LLM errors.
  - Early raw accepted edges include cross-original-type successor candidates; these remain raw until the strict display filter runs after full completion.
- Current state: The full rerun is active and incremental. The visible dashboard at `http://127.0.0.1:8765/` will still show the old installed strict asset set until the watcher completes the postprocessing pipeline.

#### Follow-up at 2026-06-01 12:20 CST - Windowed Evolution Browser Dashboard

- Goal: Replace the unreadable global network-style dashboard with a browser for auditable evolution: time window first, strict successor edges only, node/edge cards as the explanatory surface.
- Starting point: The full schema-group successor rerun had completed and installed 832 strict successor edges from 39,182 LLM-judged candidates. The dashboard still embedded 1,600 nodes, 832 edges, and 995 trajectories in a global graph-like view, making the old-to-new chains hard to interpret.
- Code changes:
  - Updated `scripts/build_evolution_visualization.py`.
  - The main view is now titled `演化浏览器`.
  - Default graph selection now starts from the schema group with the most strict successor edges instead of `all`, currently `analytic_method`.
  - The SVG layout no longer uses schema-type lanes. It groups the current time-window subgraph into connected evolution chains, labels lanes as `链 1`, `链 2`, etc., and keeps the vertical axis as time with older items above newer items.
  - The time-window logic includes strict edges whose target appears in the current window and edges whose source appears in the current window with a future successor, so both predecessor and successor context can be inspected.
  - Added an in-page `当前窗口演化边` card grid below the SVG. These cards show source -> target, relation type, confidence, year, and evidence quote, and are clickable into the full edge evidence card.
  - Renamed node-detail sections from generic `关联边/关联轨迹` to `演化边/演化轨迹` to avoid implying co-occurrence or trusted-edge display.
- Outputs:
  - Rebuilt static dashboard: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/visualization/evolution_dashboard.html`
  - Dashboard summary: `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/visualization/evolution_dashboard.summary.json`
  - Running server: tmux session `evotaxa_dashboard`, URL `http://127.0.0.1:8765/`
- Verified facts:
  - `python -m py_compile scripts/build_evolution_visualization.py scripts/serve_evolution_dashboard.py` passed.
  - `build_payload(...)` reports 832 strict evolution edges, 1,600 embedded entities, 832 embedded edges, and 995 trajectories.
  - `node` syntax check over the embedded dashboard script passed.
  - HTTP check at `http://127.0.0.1:8765/` returned the new strings `演化浏览器` and `当前窗口演化边`.
  - `/api/runs` reports the installed run root and 832 strict evolution edges.
  - Default frontend-equivalent window check resolves to `analytic_method`, `1996-01` to `1996-12`, with 2 visible strict evolution edges, so the default view is not empty.
- Caveats:
  - No local Playwright, Puppeteer, jsdom, or Chromium runtime was available, so this pass used HTML/API/JS-syntax validation rather than screenshot-based visual QA.
  - The browser is now much closer to the intended artifact semantics, but the underlying 832 strict edges still include some debatable LLM-accepted lineages that should be audited through the new edge cards.
- Next steps: Visually inspect the running dashboard, then tune the default time granularity and chain/card density based on real usage. If edge quality issues remain visible, address them in `filter_successor_edges.py` or the successor prompt rather than hiding them in the visualization.

#### Follow-up at 2026-06-01 13:10 CST - Monthly Minimum Browser Granularity

- Goal: Make the evolution browser zoom in to monthly windows instead of stopping at three-month windows.
- Change: Updated `scripts/build_evolution_visualization.py` so `TIME_GRANULARITIES` starts with `{ label: "1个月", months: 1 }`; the default view remains the one-year window.
- Outputs: Rebuilt `run_output/visualization/evolution_dashboard.html` and restarted tmux session `evotaxa_dashboard` at `http://127.0.0.1:8765/`.
- Verification: `python -m py_compile scripts/build_evolution_visualization.py scripts/serve_evolution_dashboard.py` passed; embedded dashboard JS syntax check passed; HTTP check on `/` shows `1个月` and no `3个月`; `/api/runs` still reports 832 strict evolution edges, 832 embedded edges, and 995 embedded trajectories.

#### Follow-up at 2026-06-01 13:23 CST - Wheel Interaction Fix

- Goal: Stop the evolution browser from intercepting normal page scrolling when the mouse is over the SVG.
- Change: Updated `scripts/build_evolution_visualization.py` so ordinary wheel events are not prevented. `Ctrl/⌘ + wheel` still zooms the time granularity, and `Shift + wheel` shifts the time window.
- Outputs: Rebuilt `run_output/visualization/evolution_dashboard.html` and restarted tmux session `evotaxa_dashboard` at `http://127.0.0.1:8765/`.
- Verification: `python -m py_compile scripts/build_evolution_visualization.py scripts/serve_evolution_dashboard.py` passed; embedded JS syntax check passed; HTTP check confirms `event.shiftKey` is present, `event.ctrlKey || event.metaKey` is present, and the old unconditional `preventDefault()` wheel handler is absent; `/api/runs` still reports 832 strict evolution edges, 832 embedded edges, and 995 embedded trajectories.

#### Follow-up at 2026-06-01 13:34 CST - Button-Only Time Window Navigation

- Goal: Replace low-value `Shift + wheel` and time-slider window navigation with explicit vertical-axis buttons.
- Change: Updated `scripts/build_evolution_visualization.py` so the evolution browser header now uses `↑ 更早` and `↓ 更新` buttons around the current window label. Removed the time slider and removed all graph-level wheel event bindings. Zoom granularity remains controlled by `Zoom in` and `Zoom out` buttons.
- Outputs: Rebuilt `run_output/visualization/evolution_dashboard.html` and restarted tmux session `evotaxa_dashboard` at `http://127.0.0.1:8765/`.
- Verification: `python -m py_compile scripts/build_evolution_visualization.py scripts/serve_evolution_dashboard.py` passed; embedded JS syntax check passed; HTTP check confirms `timeEarlierButton`/`timeLaterButton` and `↑ 更早`/`↓ 更新` are present, while `timeSlider`, `time-slider`, `shiftKey`, and `addEventListener("wheel"` are absent; `/api/runs` still reports 832 strict evolution edges, 832 embedded edges, and 995 embedded trajectories.

#### Follow-up at 2026-06-01 14:37 CST - Side Arrow Navigation And Sliding Window Step

- Goal: Move time-window navigation into the graph itself and make window movement visually continuous instead of jumping one full year at a time.
- Change: Updated `scripts/build_evolution_visualization.py` so the time-window buttons are now two compact side arrows overlaid on the right side of the SVG: upper arrow for an earlier window, lower arrow for a newer window. Removed the header text buttons. Added `timeWindowStepMonths()`: 1-month and 1-year views move by 1 month per click; 5-year views move by 3 months per click; longer/global views do not use window stepping.
- Outputs: Rebuilt `run_output/visualization/evolution_dashboard.html` and restarted tmux session `evotaxa_dashboard` at `http://127.0.0.1:8765/`.
- Verification: `python -m py_compile scripts/build_evolution_visualization.py scripts/serve_evolution_dashboard.py` passed; embedded JS syntax check passed; HTTP check confirms `graph-nav-earlier`, `graph-nav-later`, `timeWindowStepMonths`, and the step-size label are present, while header `↑ 更早`/`↓ 更新`, `timeSlider`, `time-slider`, and wheel bindings are absent; `/api/runs` still reports 832 strict evolution edges, 832 embedded edges, and 995 embedded trajectories.

#### Follow-up at 2026-06-01 14:50 CST - Readable Surface Names And Full Edge Quotes

- Goal: Avoid misleading apparent truncation in edge cards and improve node display names when the normalized canonical form drops readable punctuation or abbreviations.
- Change:
  - Updated `scripts/materialize_evolution_artifacts.py` so node cards keep `canonical_name` for audit but derive `display_name` from a readable representative mention surface form when it matches the canonical tokens. This preserves forms such as `Competence-Agency (CA)` instead of displaying only `competence agency ca`. Lightly repairs unmatched closing parentheses in mention names.
  - Updated `scripts/build_evolution_visualization.py` so edge-card evidence quotes are no longer truncated by `compact(quote, 220)`. They wrap in the card via CSS instead.
- Outputs: Re-materialized `graph/entity_cards.jsonl`, `trajectory/successor_trajectories.jsonl`, and related summaries; rebuilt `visualization/evolution_dashboard.html`; restarted tmux session `evotaxa_dashboard` at `http://127.0.0.1:8765/`.
- Verification:
  - `python -m py_compile scripts/materialize_evolution_artifacts.py scripts/build_evolution_visualization.py scripts/serve_evolution_dashboard.py` passed.
  - Function check maps canonical `competence agency ca` plus mention `Competence-Agency (CA` to display `Competence-Agency (CA)`.
  - Rebuilt card `measurement_strategy__competence_agency_ca` now has `display_name = Competence-Agency (CA)`, `canonical_name = competence agency ca`, and `contextual_name = Competence-Agency (CA) in social media text`.
  - Successor trajectory labels now include `Competence-Agency (CA)`.
  - Embedded dashboard JS syntax check passed and no longer contains `compact(quote, 220)`.
  - `/api/entities/measurement_strategy__competence_agency_ca` returns `entity.name = Competence-Agency (CA)`.
  - `/api/runs` still reports 832 strict evolution edges, 832 embedded edges, and 995 embedded trajectories.

#### Follow-up at 2026-06-01 15:55 CST - Successor Artifact Macro Pattern Trial

- Goal: Run the optional macro-pattern synthesis layer on the currently installed strict successor artifacts, without introducing LLM-generated macro narratives.
- Starting point: `run_output` contained 4,126 core documents, 8,122 entity cards, 832 strict successor edges, and 995 successor trajectories. `macro_patterns/pattern_summary.json` had previously been disabled or absent from the current dashboard payload.
- Code changes:
  - Added `scripts/synthesize_successor_macro_patterns.py`.
  - The script reads `graph/entity_cards.jsonl`, `graph/successor_edges.accepted.jsonl`, `trajectory/successor_trajectories.jsonl`, and `corpus/documents.normalized.jsonl`.
  - It emits detector-backed `pattern_profiles.jsonl`, `pattern_evidence.jsonl`, `pattern_timeline.jsonl`, and `pattern_summary.json` under `run_output/macro_patterns/`.
  - The current detector set covers differentiation, convergence, hybridization, recontextualization, cyclical return, institutionalization, substitution, fragmentation, and stabilization.
  - Pattern evidence is computed from edge relation types, cross-type successor evidence, cross-context successor evidence, long temporal gaps, incoming/outgoing successor branching, and successor trajectory shapes. No LLM is used to invent macro patterns.
  - Follow-up fix in the same session: branch/convergence/trajectory features now resolve dates through document metadata, and profile records explicitly preserve representative successor trajectories when available.
- Commands:
  - `python -m py_compile scripts/synthesize_successor_macro_patterns.py scripts/build_evolution_visualization.py scripts/serve_evolution_dashboard.py`
  - `PYTHONPATH=scripts:src python scripts/synthesize_successor_macro_patterns.py --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output --min-pattern-score 0.2 --max-patterns 20 --max-evidence-per-pattern 12`
  - `PYTHONPATH=scripts:src python scripts/build_evolution_visualization.py --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output --max-nodes 1600 --max-edges 1200 --max-trajectories 1000 --max-windows 400 --support-doc-limit 12`
  - Restarted tmux dashboard session `evotaxa_dashboard` at `http://127.0.0.1:8765/`.
- Outputs:
  - `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/macro_patterns/pattern_profiles.jsonl`
  - `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/macro_patterns/pattern_evidence.jsonl`
  - `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/macro_patterns/pattern_timeline.jsonl`
  - `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/macro_patterns/pattern_summary.json`
  - Rebuilt `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/visualization/evolution_dashboard.html`
- Verified facts:
  - `pattern_summary.json` reports `enabled = true`, `reported_pattern_count = 9`, `evidence_record_count = 1457`, `timeline_rows = 391`, `successor_edges = 832`, `successor_trajectories = 995`, and `entity_cards = 8122`.
  - Manifest counts now include `macro_patterns = 9`, `macro_pattern_evidence = 1457`, and `macro_pattern_timeline_rows = 391`.
  - Dashboard summary now reports `macro_patterns = 9`, `embedded_patterns = 9`, `strict_evolution_edges = 832`, and `embedded_trajectories = 995`.
  - `/api/data` returned 9 patterns, 832 embedded edges, and 995 embedded trajectories. Pattern link checks showed successor-edge links for all 9 patterns and representative trajectory links for substitution, recontextualization, hybridization, and stabilization.
  - Top profile scores in this detector trial: substitution 1.000, institutionalization 0.878, recontextualization 0.836, hybridization 0.816, differentiation 0.782, convergence 0.714, cyclical_return 0.697, stabilization 0.648, fragmentation 0.518.
- Interpretation:
  - This proves the current strict successor artifacts are sufficient to produce a first optional macro layer with inspectable evidence records and a dashboard-visible pattern list.
  - The layer is not yet a final theory of social-science method evolution. Hybridization and recontextualization are intentionally broad in this first pass because they use cross original entity type and cross context as detector signals; these should be tuned after visual audit.
  - Some patterns are edge/branch-local rather than trajectory-local. Differentiation, convergence, fragmentation, cyclical return, and institutionalization may have few or no representative long trajectories even though they have many strict successor edge or branch signals.
- Next steps: Audit the dashboard pattern cards against their linked edges. If broad modes dominate too much, tune detector weights and thresholds before adding any LLM summarization layer.

#### Follow-up at 2026-06-01 16:15 CST - Rich Macro Pattern Insight Fields

- Goal: Make macro-pattern cards useful for interpretation rather than only showing generic definitions, scores, and representative node IDs.
- Code changes:
  - Updated `scripts/synthesize_successor_macro_patterns.py` with richer pattern definitions and structured insight fields.
  - Added profile fields: `insight`, `analytic_note`, `interpretation_caveat`, `dominant_signals`, `dominant_artifacts`, `dominant_relations`, `dominant_type_transitions`, `dominant_schema_groups`, `temporal_hotspots`, and `representative_evidence`.
  - `representative_evidence` records now preserve the local path, relation, type transition, context shift, quote, edge IDs, trajectory IDs, score, and time slice where available.
  - Updated `scripts/build_evolution_visualization.py` to expose these fields in `/api/data` and render them in the macro-pattern evidence card under `语料洞察`, `检测器读法`, `解释边界`, `主导信号`, `关系构成`, `类型迁移`, `时间热点`, `代表证据`, and `关联演化边`.
- Commands:
  - `python -m py_compile scripts/synthesize_successor_macro_patterns.py scripts/build_evolution_visualization.py scripts/serve_evolution_dashboard.py`
  - `PYTHONPATH=scripts:src python scripts/synthesize_successor_macro_patterns.py --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output --min-pattern-score 0.2 --max-patterns 20 --max-evidence-per-pattern 12`
  - `PYTHONPATH=scripts:src python scripts/build_evolution_visualization.py --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output --max-nodes 1600 --max-edges 1200 --max-trajectories 1000 --max-windows 400 --support-doc-limit 12`
  - Restarted tmux dashboard session `evotaxa_dashboard` at `http://127.0.0.1:8765/`.
- Verified facts:
  - Macro summary remains stable: 9 profiles, 1,457 evidence records, 391 timeline rows, 832 strict successor edges, 995 successor trajectories, and 8,122 entity cards.
  - `/api/data` returns the new rich fields for all 9 patterns.
  - Spot checks: `substitution`, `institutionalization`, and `recontextualization` all include non-empty `insight`, `dominant_signals`, `dominant_relations`, and 8 representative evidence records.
  - HTML contains the new macro-detail sections: `语料洞察`, `检测器读法`, `解释边界`, `主导信号`, `类型迁移`, and `代表证据`.
  - Dashboard summary still reports 9 embedded macro patterns, 832 strict evolution edges, and 995 embedded trajectories.
- Current interpretation state:
  - Macro cards are now useful as detector-backed analytic summaries, but they remain summaries of the current strict successor artifacts rather than an independent theory layer.
  - Broad modes such as hybridization and recontextualization still need visual audit through their linked representative evidence before being used as claims.

#### Follow-up at 2026-06-01 16:35 CST - README And Repository Sync

- Goal: Update top-level documentation and synchronize the current EvoTaxa implementation to git after the CSS workflow, successor-edge dashboard, and macro-pattern trial work.
- README changes:
  - Added the staged large-corpus social-science workflow: OpenAlex download, LLM relevance screening and cleaning, schema probing, main run, successor extraction, strict-edge installation, materialization, macro synthesis, dashboard build, and local dashboard serve.
  - Added output-layout entries for entity cards, strict successor edges, successor trajectories, macro patterns, temporal windows, and visualization artifacts.
  - Added explanations for strict successor edges, node cards, dashboard semantics, and optional macro-pattern synthesis.
  - Replaced literal local API token examples with `api_key_env = "EVOTAXA_LLM_API_KEY"` or shell environment placeholders.
- Safety checks before commit:
  - `python -m py_compile scripts/*.py src/evotaxa/*.py` passed.
  - `PYTHONPATH=src pytest -q` passed with 50 tests.
  - `git diff --cached --check` passed.
  - `data/` remains ignored and was not staged.
  - Literal local API keys were removed from tracked/staged files; local LLM commands now use the `EVOTAXA_LLM_API_KEY` placeholder.

#### Follow-up at 2026-06-01 16:49 CST - Evolution Insight Report Generator

- Goal: Add a reproducible Markdown report that turns macro-pattern profiles and micro successor evidence into an inspectable, presentation-ready evolution insight document.
- Starting point: Current CSS run output already contained 4,126 screened core documents, 8,122 entity cards, 832 strict successor edges, 995 successor trajectories, 9 macro pattern profiles, and 391 macro timeline rows.
- Code changes:
  - Added `scripts/build_evolution_insight_report.py`.
  - The script reads `manifest.json`, `corpus/documents.normalized.jsonl`, `graph/entity_cards.jsonl`, `graph/successor_edges.accepted.jsonl`, `trajectory/successor_trajectories.jsonl`, `macro_patterns/pattern_profiles.jsonl`, and `macro_patterns/pattern_timeline.jsonl`.
  - It writes `reports/evolution_insight_report.md` and `reports/evolution_insight_report.summary.json`, and updates manifest layout/counts unless `--no-manifest-update` is set.
  - Report sections include run boundary notes, main findings, per-pattern macro profiles, representative micro evidence with quotes, relation/type/year distributions, local branching and convergence tables, long-gap/replacement/cross-type edge examples, successor trajectories, and macro-micro synthesis.
  - Updated README with the report-generation command, output layout, and report semantics.
  - Added a smoke test fixture that links one macro substitution profile to a strict successor edge and trajectory.
- Command:
  ```bash
  PYTHONPATH=scripts:src python scripts/build_evolution_insight_report.py \
    --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output \
    --max-patterns 9 \
    --max-evidence-per-pattern 5 \
    --max-micro-examples 8
  ```
- Outputs:
  - `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/reports/evolution_insight_report.md`
  - `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/reports/evolution_insight_report.summary.json`
- Verified facts:
  - Summary JSON reports 4,126 documents, 8,122 entity cards, 832 strict successor edges, 995 successor trajectories, 9 macro patterns, and 391 timeline rows.
  - Top reported patterns are substitution, institutionalization, recontextualization, hybridization, differentiation, convergence, cyclical return, stabilization, and fragmentation.
  - Top relation types are extends 355, specializes 141, adapts 117, improves 96, generalizes 95, and replaces 28.
  - Top type transitions are method -> method 210, measurement_strategy -> method 87, modeling_strategy -> modeling_strategy 86, modeling_strategy -> method 85, method -> modeling_strategy 79, and measurement_strategy -> measurement_strategy 77.
  - The generator is deterministic and does not call an LLM; quoted evidence is excerpted from already accepted successor edges.
- Current state:
  - The report is suitable as the first static narrative artifact for the current CSS run.
  - It is still bounded by the strict successor artifacts; missing or weak successor edges will appear as missing narrative coverage rather than being filled by the report generator.

#### Follow-up at 2026-06-01 21:49 CST - Agentic Narrative Insight Report

- Goal: Replace the table-like deterministic report as the presentation artifact with an LLM-agent-written research memo, while preserving a deterministic evidence appendix for audit.
- Starting point: The previous `evolution_insight_report.md` correctly summarized 4,126 documents, 8,122 entity cards, 832 strict successor edges, 995 successor trajectories, 9 macro patterns, and 391 timeline rows, but read too much like a dashboard export.
- Code changes:
  - Added `scripts/write_agentic_evolution_report.py`.
  - Added report prompts under `task_specs/prompts/reports/` for a five-step writing agent: `scout`, `outline`, `draft`, `critic`, and `revise`.
  - The agent first builds `reports/evolution_insight_report.evidence_pack.json` from macro profiles, accepted successor edges, trajectories, cards, and document metadata.
  - It also builds `reports/evolution_insight_report.reader_evidence_pack.json`, which maps raw machine IDs to reader-facing evidence labels such as E1, P2.1, and T1 before prompts are sent to the model.
  - It then writes `reports/evolution_insight_report.agent.md`, `reports/evolution_insight_report.agent.summary.json`, and `reports/evolution_insight_report.agent_trace.json`.
  - `scripts/build_evolution_insight_report.py` now avoids importing the full `evotaxa` package so the deterministic evidence appendix can run in a minimal Python environment without `PyYAML`.
  - `.gitignore` now excludes local `config.yaml` files; the generated local config uses `api_key_env` and does not store literal API keys in tracked files.
  - README now distinguishes the deterministic evidence appendix from the agentic narrative report and documents the local `config.yaml` shape.
- Commands:
  ```bash
  python3 scripts/write_agentic_evolution_report.py \
    --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output \
    --dry-run \
    --max-patterns 9 \
    --max-evidence-per-pattern 8 \
    --max-micro-examples 10

  EVOTAXA_LLM_API_KEY=... python3 scripts/write_agentic_evolution_report.py \
    --run-root data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output \
    --config config.yaml \
    --max-patterns 9 \
    --max-evidence-per-pattern 8 \
    --max-micro-examples 10
  ```
- Outputs:
  - `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/reports/evolution_insight_report.agent.md`
  - `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/reports/evolution_insight_report.agent.summary.json`
  - `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/reports/evolution_insight_report.evidence_pack.json`
  - `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/reports/evolution_insight_report.reader_evidence_pack.json`
  - `data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output/reports/evolution_insight_report.agent_trace.json`
- Verified facts:
  - The final run used `Qwen3-235B-FP8` at `http://127.0.0.1:8001/v1` with `enable_thinking=false` through `chat_template_kwargs`.
  - Agent trace completed all five steps: scout, outline, draft, critic, and revise.
  - Final report length after reader-evidence rewrite is 5,859 characters / 105 lines.
  - The final report has no emoji-like decoration, no raw successor edge IDs, no pattern IDs, no trajectory IDs, and no double-underscore machine strings in the prose.
  - The report is now organized around interpretable claims: LLM substitution discourse, evaluation-protocol institutionalization, cross-context adaptation, method/modeling hybridization, limits of paradigm-shift claims, and next audit actions.
- Environment caveat:
  - The active system Python lacks `pytest`, `PyYAML`, `json_repair`, and `pip`; script-level `py_compile`, dry-run generation, and live Qwen report generation were verified in this minimal environment.
- Current state:
  - The report is much closer to a research memo than a numeric summary.
  - It remains bounded by the current successor artifacts and should be treated as an evidence-grounded narrative draft, not a final social-science conclusion.
