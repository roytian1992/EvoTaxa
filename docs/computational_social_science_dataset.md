# Computational Social Science Dataset

## Scope

This document records the current OpenAlex corpus used for EvoTaxa computational-social-science experiments and how to reproduce or extend it later.

The dataset is a title+abstract corpus. Abstracts are reconstructed from OpenAlex `abstract_inverted_index`.

## Current Snapshot

- Dataset path: `data/computational_social_science`
- Normalized corpus: `data/computational_social_science/corpus.jsonl`
- Raw OpenAlex records: `data/computational_social_science/openalex_raw.jsonl`
- Download manifest: `data/computational_social_science/manifest.json`
- Resume state: `data/computational_social_science/download_state.json`
- Page cache: `data/computational_social_science/pages/`
- Size on disk: about `1.3G`
- Normalized rows: `25,063`
- Raw rows: `25,063`
- Date coverage in corpus: `1990-01-01` to `2026-07-25`
- Year coverage: every year from `1990` through `2026`

## Source And Filters

Source:

- OpenAlex Works API
- Endpoint: `https://api.openalex.org/works`
- Query mode: `title_and_abstract.search`

OpenAlex filters:

- `from_publication_date:1990-01-01`
- `to_publication_date:2026-12-31`
- `has_abstract:true`
- `is_retracted:false`

Local normalization filters:

- Drop rows missing title or reconstructed abstract.
- Drop rows failing the local relevance filter.
- Deduplicate by OpenAlex work id.

Skipped during normalization:

- `low_relevance`: `268`
- `missing_title_or_abstract`: `14`

## Query Buckets

```text
computational social science
computational social science methods
social science computational methods
text as data social science
computational text analysis social science
digital trace data social science
network analysis computational social science
agent-based modeling computational social science
LLM social science annotation
synthetic respondents large language models
computational social science reproducibility
platform data access social science
```

OpenAlex has-abstract counts at download time:

| Query | Count |
|---|---:|
| computational social science | 11,756 |
| computational social science methods | 4,708 |
| social science computational methods | 4,708 |
| text as data social science | 11,849 |
| computational text analysis social science | 1,094 |
| digital trace data social science | 736 |
| network analysis computational social science | 1,751 |
| agent-based modeling computational social science | 839 |
| LLM social science annotation | 126 |
| synthetic respondents large language models | 63 |
| computational social science reproducibility | 616 |
| platform data access social science | 3,047 |

The raw bucket-hit sum was `41,293`; after local filtering and deduplication the corpus has `25,063` records.

## Year Counts

```text
1990 24
1991 22
1992 31
1993 28
1994 36
1995 36
1996 44
1997 51
1998 70
1999 76
2000 87
2001 90
2002 108
2003 128
2004 183
2005 203
2006 234
2007 262
2008 318
2009 375
2010 446
2011 571
2012 575
2013 662
2014 713
2015 919
2016 956
2017 1012
2018 1157
2019 1257
2020 1603
2021 1781
2022 1618
2023 2066
2024 2068
2025 2952
2026 2301
```

## Reproduction Command

Run from the repository root:

```bash
python scripts/download_openalex_corpus.py \
  --output-root data/computational_social_science \
  --per-page 200 \
  --max-results-per-query 0 \
  --max-total 0 \
  --sleep-seconds 0.1 \
  --timeout-seconds 30 \
  --max-retries 3
```

The downloader is resumable. Each successful API page is written under `pages/`, and `download_state.json` records query status and cursor position. If the process is interrupted, rerun the same command.

## Future Incremental Update

For a future refresh, such as two months later:

1. Keep the existing `manifest.json` and `download_state.json` as the baseline record.
2. Run a new download into a timestamped staging directory, for example:

```bash
python scripts/download_openalex_corpus.py \
  --output-root data/computational_social_science_refresh_YYYYMMDD \
  --from-date 2026-07-26 \
  --to-date YYYY-MM-DD \
  --per-page 200 \
  --max-results-per-query 0 \
  --max-total 0 \
  --sleep-seconds 0.1 \
  --timeout-seconds 30 \
  --max-retries 3
```

3. Compare new records against `data/computational_social_science/corpus.jsonl` by `openalex_id` or `doc_id`.
4. Append only new works, then regenerate `manifest.json`.
5. Record the refresh in `docs/experiment_log_YYYYMMDD.md` or append a new trajectory entry to the current experiment log.

Do not overwrite the canonical dataset until the refresh manifest and row counts have been checked.

## Caveats

- This is an abstract-only corpus, not a full-text corpus.
- Query buckets are intentionally broad enough to support method-evolution analysis, so some off-topic records may remain.
- `2026` is partial because the current download was made on 2026-05-29 and OpenAlex returned records dated through 2026-07-25.
- Data files under `data/` are local experiment artifacts and are not intended to be committed to git.
