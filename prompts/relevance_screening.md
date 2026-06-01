Screen this paper before it enters an EvoTaxa corpus.

The screening code is domain-neutral. Use the domain rubric below as the only authority for relevance.

Domain id:
{{domain_id}}

Domain definition:
{{domain_definition}}

Core criteria:
{{core_criteria_json}}

Peripheral criteria:
{{peripheral_criteria_json}}

Exclude criteria:
{{exclude_criteria_json}}

Paper JSON:
{{paper_json}}

Return only a valid JSON object with:

- `screening_decision`: one of `core`, `peripheral`, or `exclude`
- `screening_score`: 0 to 1
- `screening_reason`: concise reason grounded in title/abstract/concepts/keywords
- `method_relevance`: 0 to 1
- `social_science_relevance`: 0 to 1
- `evolution_signal`: 0 to 1

Use `core` when the paper is usable evidence for the domain defined above. It may be a method paper, a data/measurement paper, an evaluation or benchmark paper, a governance/reproducibility paper, or an applied social-science study whose title/abstract explicitly describes computational method or data practice. It does not need to be a pure method-development paper.

Use `peripheral` when the paper is adjacent or applied and may contain useful signals, but the computational-social-science method/data evidence is secondary, thin, or domain-specific enough that it should be separable from core evidence.

Use `exclude` when relevance is weak, generic, or incidental. Generic mentions of method, model, data, text, social, or research are not enough by themselves.
