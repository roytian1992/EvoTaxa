# Computational Social Science Data Source Assessment

This note evaluates practical data sources for running EvoTaxa on **Computational Social Science Methods**. The goal is not to model recurring public-opinion cycles, but to capture method evolution: concepts split, measurement tools become finer, mechanisms diversify, and new methodological families emerge.

## Recommendation

Use **OpenAlex as the primary corpus source** and **ACL Anthology as a supplemental source** for text-as-data and NLP-heavy method branches.

```text
Primary source: OpenAlex
Supplemental source: ACL Anthology
Domain: Computational Social Science Methods
Date range: 1990-2026
Initial corpus size: 3,000-8,000 papers
Text fields: title + abstract
Core EvoTaxa task: taxonomy induction + schema-adaptive evolution graph + trajectory modeling
```

OpenAlex is the best first choice because it provides publication dates, abstracts, topics/concepts, references, and stable API pagination without requiring an API key.

## Practical Availability Summary

| Source | Download works? | Key required? | Text availability | Date range tested | Suitability |
|---|---:|---:|---|---|---|
| OpenAlex | Yes | No | title, abstract, topics, concepts, references | 1990-2026 | Best primary source |
| ACL Anthology | Yes | No | BibTeX metadata, abstracts file | static files updated 2026-05-26 | Good supplement |
| Semantic Scholar | Unstable in this environment | Usually no for basic use, but rate limited | title, abstract, references if accessible | not reliably tested due to 429 | Not first source |
| arXiv API | Unstable in this environment | No | title, abstract | not reliably tested due to 429/timeout | Not first source |
| Crossref | Yes | No | title/metadata, abstracts usually missing | 1990-2026 search works | Metadata fallback only |

## OpenAlex

### Status

OpenAlex API access was tested successfully. It supports cursor pagination and can return the fields EvoTaxa needs.

Useful fields tested:

```text
id
doi
title
publication_year
publication_date
abstract_inverted_index
topics
concepts
referenced_works
cited_by_count
```

`abstract_inverted_index` can be reconstructed into a normal abstract. A sample 2025 paper for the query `computational social science` returned title, date, topics, concepts, 136 references, and a reconstructable abstract.

### Recommended Query Mode

Use this stricter filter:

```text
title_and_abstract.search:<query>
```

Do **not** rely on broad `search:<query>` counts for corpus design. Broad `search` is much larger because it searches more metadata fields and can inflate the corpus with weak matches.

### Tested OpenAlex Date Ranges

The following counts used `title_and_abstract.search`.

| Query | First nonzero year | Latest tested year | Total count, 1990-2026 |
|---|---:|---:|---:|
| `computational social science` | 1990 | 2026 | 13,917 |
| `text as data social science` | 1990 | 2026 | 14,224 |
| `digital trace data social science` | 1999 | 2026 | 785 |
| `LLM social science annotation` | 2023 | 2026 | 126 |

Additional probe counts:

| Query | Coverage observed |
|---|---|
| `network analysis computational social science` | 1990-2026; 2025 had 284 hits |
| `agent-based modeling computational social science` | 1995-2026; 2025 had 108 hits |

### Interpretation

This date structure is useful for EvoTaxa:

```text
1990s-2000s: network analysis, simulation, early computational social science
2010s: social media data, digital trace data, text-as-data, platform measurement
2020s: reproducibility, data access, computational ethics, LLM-assisted annotation
2023-2026: LLM annotation, synthetic respondents, LLM-assisted social science
```

### Suggested OpenAlex Fields

For an EvoTaxa dataset, export records with:

```text
doc_id = OpenAlex id
doi = DOI
title = title
abstract = reconstructed abstract_inverted_index
publication_year = publication_year
publication_date = publication_date
topics = topics
concepts = concepts
referenced_works = referenced_works
cited_by_count = cited_by_count
source_type = research_paper
seed_query = query bucket used to retrieve the work
```

### Minimal API Pattern

```text
https://api.openalex.org/works?
  filter=title_and_abstract.search:computational social science,
         from_publication_date:1990-01-01,
         to_publication_date:2026-12-31
  &select=id,doi,title,publication_year,publication_date,
          abstract_inverted_index,topics,concepts,
          referenced_works,cited_by_count
  &per-page=200
  &cursor=*
```

Use a real contact email in `mailto` when running a larger download.

## ACL Anthology

### Status

ACL Anthology static metadata files were reachable.

Tested URLs:

```text
https://aclanthology.org/anthology+abstracts.bib.gz
status 200
size about 37.7 MB
last modified 2026-05-26

https://aclanthology.org/anthology.bib.gz
status 200
size about 11.6 MB
last modified 2026-05-26
```

### Use Case

Use ACL Anthology as a supplement for method branches where computational social science overlaps with NLP:

```text
text-as-data
computational text analysis
social media NLP
stance detection
frame detection
ideology detection
LLM annotation
synthetic text annotation
```

ACL should not be the primary CSS corpus because it over-represents NLP venues and under-represents sociology, political science, communication, economics, and broader social science methods.

## Semantic Scholar

### Status

The Semantic Scholar Graph API is theoretically useful because it can return title, abstract, venue, year, references, citations, and paper IDs. In this environment, unauthenticated test requests returned HTTP 429 rate-limit errors.

### Recommendation

Do not use Semantic Scholar as the first data source. Revisit it later if:

```text
1. an API key is available,
2. we need citation graph enrichment,
3. OpenAlex is missing abstracts or references for important papers.
```

## arXiv

### Status

arXiv API tests returned 429 errors and timeouts in this environment. Also, computational social science papers are not uniformly deposited in arXiv.

### Recommendation

Do not use arXiv as the primary corpus. It can be used later for a narrow supplement around:

```text
cs.SI
physics.soc-ph
LLM social science
agent-based social simulation
```

## Crossref

### Status

Crossref API search worked, but results were broad and abstracts were generally missing. It is useful for DOI metadata but weak for EvoTaxa's quote-grounded evidence needs.

### Recommendation

Use Crossref only as a metadata fallback:

```text
DOI normalization
publication date repair
venue/publisher metadata repair
```

Do not use it as the main text corpus.

## Recommended Query Buckets

Use query buckets rather than a single broad query. Store the bucket label in each document record so EvoTaxa can use it as a weak seed taxonomy signal.

### Core CSS Methods

```text
computational social science
computational social science methods
social science computational methods
```

### Text-as-Data

```text
text as data social science
computational text analysis social science
automated content analysis social science
text mining social science
supervised text classification social science
embedding measurement social science
```

### Digital Trace Data

```text
digital trace data social science
social media data social science methods
platform data social science
web browsing data social science
mobile phone data social science
```

### Network Analysis

```text
network analysis computational social science
social network analysis computational social science
online social networks social science methods
diffusion networks social science
```

### Causal Inference And Experiments

```text
causal inference social science digital trace
causal inference social media data
online field experiments social media
natural experiments digital trace data
difference in differences social media data
```

### Agent-Based Modeling And Simulation

```text
agent-based modeling computational social science
social simulation computational social science
agent based social simulation
computational modeling social behavior
```

### LLM-Assisted Social Science

```text
large language models social science annotation
LLM social science research methods
LLM annotation social science
synthetic respondents large language models
large language models survey research
AI agents social science simulation
```

### Reproducibility, Ethics, And Data Governance

```text
computational social science reproducibility
data access computational social science
ethics computational social science
privacy digital trace data social science
platform data access social science
```

## Suggested Initial Taxonomy

Use this as a seed taxonomy, then let EvoTaxa induce and refine subnodes.

```text
Digital Trace Data
Text-as-Data / Computational Text Analysis
Network Analysis
Causal Inference & Experiments
Agent-Based Modeling / Social Simulation
LLM-Assisted Social Science Methods
Reproducibility / Ethics / Data Governance
```

Expected subnode evolution:

```text
Text-as-Data
  -> dictionary methods
  -> topic modeling
  -> supervised text classification
  -> embedding-based measurement
  -> frame / stance / ideology detection
  -> LLM annotation

Digital Trace Data
  -> social media traces
  -> mobility traces
  -> web browsing traces
  -> platform interaction logs
  -> administrative digital records

Causal Inference
  -> natural experiments
  -> difference-in-differences
  -> instrumental variables
  -> matching
  -> online field experiments
  -> causal inference with observational traces

LLM-Assisted Methods
  -> LLM annotation
  -> synthetic respondents
  -> LLM-assisted survey design
  -> agent-based social simulation with LLM agents
```

## EvoTaxa Field Mapping

An OpenAlex-derived record should map into EvoTaxa like this:

```text
doc_id: OpenAlex work id
title: title
text: reconstructed abstract
date: publication_date or publication_year
chronology_slice: publication_year or custom period bucket
source_type: research_paper
role: core
raw.seed_query: query bucket
raw.doi: doi
raw.topics: topics
raw.concepts: concepts
raw.referenced_works: referenced_works
raw.cited_by_count: cited_by_count
```

Suggested time slices:

```text
1990-2008: early computational social science, network analysis, simulation
2009-2014: social media and digital trace data rise
2015-2019: text-as-data, embeddings, platform measurement, causal designs
2020-2022: reproducibility, data access, computational ethics
2023-2026: LLM annotation, synthetic respondents, LLM-assisted social science
```

## First Experiment Design

Start with OpenAlex only.

```text
Corpus: 3,000-8,000 OpenAlex works
Years: 1990-2026
Query mode: title_and_abstract.search
Text: title + abstract
Taxonomy seed: query bucket + OpenAlex topics/concepts
Run mode: run-full
Schema mode: adaptive
```

Evaluation questions:

```text
1. Does EvoTaxa recover the transition from network/simulation methods to digital trace and social media methods?
2. Does it identify text-as-data as a branch that later splits into supervised classification, embeddings, frame/stance detection, and LLM annotation?
3. Does the state model show LLM-assisted methods emerging only after 2023?
4. Do negative relation pairs prevent broad co-mentions from becoming false evolution edges?
5. Are inferred trajectories interpretable enough for a social science methods case study?
```

## Bottom Line

OpenAlex is usable now and should be the backbone of the CSS methods experiment. ACL Anthology is useful as a supplement for NLP-heavy branches. Semantic Scholar and arXiv are not stable enough here for first-pass data collection, and Crossref lacks enough abstract text for quote-grounded evolution modeling.
