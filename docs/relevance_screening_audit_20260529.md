# Relevance Screening Audit 2026-05-29

## Scope

This is a small manual audit of the current OpenAlex computational-social-science corpus after query filtering and the local rule-based relevance filter.

Input corpus:

- `data/computational_social_science/corpus.jsonl`
- Rows: `25,063`
- Existing local filter skipped `268` low-relevance rows and `14` rows missing title or abstract.

## Sample

Command sampled 12 random rows with seed `20260529`.

## Manual Judgement

| # | Year | Title short | Judgement | Note |
|---:|---:|---|---|---|
| 1 | 2015 | Targeting 90-90-90 | exclude | HIV policy/access article; not CSS methods. |
| 2 | 2014 | Quantitative Methods and Socio-Economic Applications in GIS | core | Quantitative/computational methods for social-science applications. |
| 3 | 2023 | eHealth tools for early childhood centers | exclude | Health intervention/scoping-review protocol; method terms are generic. |
| 4 | 2025 | Amazigh language and Digital Humanities | peripheral | Computational humanities / low-resource language; not clearly CSS methods. |
| 5 | 2022 | Precision Psychiatry | peripheral | Computational/ML medicine; adjacent but not CSS methods. |
| 6 | 2016 | Wawacan Siti Permana | exclude | Literary/anthropological text study; not computational methods. |
| 7 | 2025 | Quantum-walk method for influential node identification | core | Network-analysis method with social-network applications. |
| 8 | 2025 | Literary studies and the Network Turn | peripheral | Network analysis in humanities; adjacent, not central CSS. |
| 9 | 2026 | Simulating Lay Health-Seeking Behavior with LLM Personas | core | LLM/synthetic respondent methodology for behavior simulation. |
| 10 | 2015 | Evolutionary Immersion, Digital Arts, Science and Technology | peripheral | Computational/digital arts theory; weak fit for CSS methods. |
| 11 | 2023 | Public access and use of health research | exclude | Health-information scoping review; not method evolution. |
| 12 | 2026 | Teleological Empathy | peripheral | AI/social-science conceptual article; possible adjacent signal. |

Approximate sample split:

- Core: `3/12`
- Peripheral: `5/12`
- Exclude: `4/12`

## Interpretation

The current corpus is broad and useful for discovery, but it is not clean enough to treat all records as core computational-social-science methods evidence.

The main source of noise is not missing abstracts or retractions. It is semantic drift from broad query terms such as `text as data social science`, `platform data access social science`, and generic hits on `method`, `data`, `text`, `social`, or `model`.

## Recommendation

Add a second-stage relevance screening layer before serious full-corpus interpretation.

Suggested labels:

- `core`: explicitly about computational social science methods, data practices, measurement, modeling, annotation, simulation, network/text methods, or method governance.
- `peripheral`: adjacent applied, domain, digital humanities, health, psychiatry, education, or conceptual AI/social-science work that may contain useful method signals but should be separable.
- `exclude`: not meaningfully about CSS methods or their evolution.

LLM screening is likely useful, but should be used as a calibrated audit/filter with sampled human review, not as an unchecked replacement for the current rule filter.
