# Relevance Screening

## Boundary

Relevance screening is a corpus-preparation step, not part of the EvoTaxa evolution pipeline.

EvoTaxa should start from already relevant papers. Different domains need different relevance rubrics, so the screening tool is intentionally kept outside `run-full`.

## Design

The screening layer is split into three independently managed parts:

- Generic code: `scripts/screen_relevance.py`
- Generic prompt template: `prompts/relevance_screening.md`
- Domain rubric: `configs/relevance_domains/*.toml`
- LLM connection config: `configs/llm/*.toml`

The prompt is domain-neutral. It receives the selected domain rubric and a paper record, then returns `core`, `peripheral`, or `exclude`.

Before prompting the model, the script performs deterministic title/abstract cleaning. It removes common OpenAlex web-page artefacts such as navigation text, DOI/tool menus, citation sections, and repeated title/author headers. The LLM sees the cleaned abstract, and `corpus.screened.jsonl` stores the cleaned `abstract`/`text` plus the original abstract under `raw_abstract`.

`core` means the paper is usable evidence for EvoTaxa in that domain. It is not restricted to pure method-development papers. Applied papers can be `core` when the title or abstract explicitly describes a computational method, data practice, measurement strategy, model, benchmark, evaluation, reproducibility issue, or governance issue strongly enough to support entity extraction and evolution modeling.

`peripheral` means potentially useful but separable evidence. This is the right label for adjacent applied studies, conceptually related AI/social-science papers, or records where computational method/data evidence is present but thin, routine, or domain-specific.

`exclude` means generic or incidental relevance. Generic terms such as method, model, data, text, social, or research are not enough by themselves.

## Outputs

For each run, the script writes:

- `screening_decisions.jsonl`: one screening decision per input row.
- `cleaning_records.jsonl`: one abstract-cleaning audit record per newly screened input row.
- `corpus.screened.jsonl`: filtered corpus containing only requested decisions, usually `core`.
- `screening_summary.json`: counts, paths, and run configuration.

The original corpus is never modified.

## Example

LLM pilot:

```bash
EVOTAXA_LLM_API_KEY=... python scripts/screen_relevance.py \
  --input data/computational_social_science/corpus.jsonl \
  --output-root data/computational_social_science_screening/llm_pilot \
  --rubric configs/relevance_domains/computational_social_science_methods.toml \
  --prompt-template prompts/relevance_screening.md \
  --llm-config configs/llm/qwen_local.toml \
  --limit 100 \
  --include-decisions core
```

After screening, point the EvoTaxa corpus config at the screened corpus:

```toml
[corpus]
path = "../data/computational_social_science_screening/llm_full/corpus.screened.jsonl"
accepted_roles = ["core"]
```

## Resume

The script appends decisions as it runs and reloads `screening_decisions.jsonl` by default. Re-running the same command resumes completed documents by `doc_id`.

Resume is protected by a run signature derived from the prompt template, domain rubric, and LLM connection settings. If any of those change, old decisions in the same output directory are ignored and recomputed.

Rows labeled `llm_error` are retried on resume by default, because they usually indicate a transient model or schema issue rather than a stable relevance decision. Use `--cache-errors` only when you intentionally want to keep prior `llm_error` rows.

Use `--no-resume` to force a fresh run.

## Sharded Full Runs

For large corpora, run independent shards into separate output directories and merge them after all workers complete. This avoids concurrent writes to the same JSONL files while keeping each shard resumable.

The current 16-worker CSS run uses this root:

```text
data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025
```

Monitor it with:

```bash
python scripts/screening_status.py \
  --run-root data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025
```

When every shard reaches its assigned limit, merge with:

```bash
python scripts/merge_screening_shards.py \
  --shards-root data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/shards \
  --output-root data/computational_social_science_screening/llm_full_cleaning_repair_20260530_0025/merged
```

## Current CSS Rubric

The current computational-social-science rubric is:

- `configs/relevance_domains/computational_social_science_methods.toml`

It distinguishes:

- `core`: usable computational-social-science method/data evidence, including applied studies with explicit and transferable computational method signals.
- `peripheral`: adjacent applied or conceptual papers with possible but weaker method signal.
- `exclude`: weak, generic, or incidental relevance.

Screening is LLM-only. The classifier receives only the cleaned paper JSON, generic prompt, and selected domain rubric. LLM output is parsed as JSON, repaired with `json_repair` when needed, schema-checked, and retried according to `max_retries` in the LLM config. If all attempts fail or return an invalid schema, the row is labeled `llm_error` and is not included in the screened corpus unless that label is explicitly requested.
