from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.materialize_screened_corpus import main as materialize_screened_corpus_main
from scripts.audit_edges_role_aware import main as audit_edges_role_aware_main
from scripts.screen_relevance import ScreeningRubric, append_jsonl, load_cached_decisions, load_prompt_template, screening_prompt
from evotaxa.content_cleaning import clean_title_abstract
from evotaxa.llm import _loads_json_object, _schema_valid


def test_clean_title_abstract_removes_openalex_web_chrome() -> None:
    cleaned = clean_title_abstract(
        title="Electronic documents give reproducible research a new meaning",
        abstract=(
            "PreviousNext No Access SEG Technical Program Expanded Abstracts 1992 "
            "Electronic documents give reproducible research a new meaning Authors: A. B. "
            "https://doi.org/10.1190/1.1822162 Sections About PDF/ePub Tools Add to favorites "
            "Download Citations Cited By Packaging research artefacts with RO-Crate"
        ),
    )
    assert "doi.org" not in cleaned.text
    assert "Cited By" not in cleaned.text
    assert cleaned.cleaned_length < cleaned.original_length
    assert cleaned.removed_markers


def test_json_repair_parses_malformed_relevance_screening_output() -> None:
    output, repaired = _loads_json_object(
        "{screening_decision: core, screening_score: .8, screening_reason: 'usable', "
        "method_relevance: .9, social_science_relevance: .7, evolution_signal: .4}"
    )
    assert repaired is True
    assert output["screening_decision"] == "core"
    assert _schema_valid("relevance_screening", output) is True


def test_resume_retries_cached_llm_errors_by_default(tmp_path: Path) -> None:
    path = tmp_path / "screening_decisions.jsonl"
    append_jsonl(path, {"doc_id": "ok", "run_signature": "sig", "screening_decision": "core"})
    append_jsonl(path, {"doc_id": "retry", "run_signature": "sig", "screening_decision": "llm_error"})

    cached = load_cached_decisions(path, run_signature="sig")
    assert set(cached) == {"ok"}

    cached_with_errors = load_cached_decisions(path, run_signature="sig", cache_errors=True)
    assert set(cached_with_errors) == {"ok", "retry"}


def test_relevance_schema_allows_missing_optional_subscores() -> None:
    assert _schema_valid(
        "relevance_screening",
        {
            "screening_decision": "core",
            "screening_score": 0.9,
            "screening_reason": "Explicit computational social-science method evidence.",
        },
    )


def test_relevance_screening_uses_yaml_prompt_template_by_default() -> None:
    template = load_prompt_template(REPO_ROOT / "task_specs" / "prompts" / "screening" / "relevance_screening.yaml")
    prompt = screening_prompt(
        {
            "title": "Network models for social data",
            "abstract": "We introduce network models for social data.",
            "publication_year": 2020,
        },
        ScreeningRubric(
            domain_id="css",
            domain_definition="Computational social science methods.",
            core_criteria=["Explicit computational method evidence."],
            peripheral_criteria=[],
            exclude_criteria=[],
        ),
        template,
    )
    assert "Screen this paper before it enters an EvoTaxa corpus." in prompt
    assert "Network models for social data" in prompt
    assert "Explicit computational method evidence." in prompt


def test_materialize_screened_corpus_maps_peripheral_to_support(tmp_path: Path, monkeypatch) -> None:
    corpus = tmp_path / "corpus.jsonl"
    decisions = tmp_path / "screening_decisions.jsonl"
    output = tmp_path / "corpus.core_support.jsonl"
    summary = tmp_path / "summary.json"

    append_jsonl(
        corpus,
        {
            "doc_id": "core_doc",
            "title": "Network models for social data",
            "abstract": "We introduce a network model for social data.",
            "publication_year": 2020,
            "role": "core",
        },
    )
    append_jsonl(
        corpus,
        {
            "doc_id": "support_doc",
            "title": "Adjacent text analysis study",
            "abstract": "We use text analysis in education research.",
            "publication_year": 2021,
            "role": "core",
        },
    )
    append_jsonl(corpus, {"doc_id": "excluded_doc", "title": "No method", "abstract": "Background.", "publication_year": 2022})
    append_jsonl(decisions, {"doc_id": "core_doc", "screening_decision": "core", "screening_score": 0.9})
    append_jsonl(decisions, {"doc_id": "support_doc", "screening_decision": "peripheral", "screening_score": 0.55})
    append_jsonl(decisions, {"doc_id": "excluded_doc", "screening_decision": "exclude", "screening_score": 0.1})

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "materialize_screened_corpus.py",
            "--input",
            str(corpus),
            "--decisions",
            str(decisions),
            "--output",
            str(output),
            "--summary",
            str(summary),
            "--include-decisions",
            "core,peripheral",
            "--role-map",
            "peripheral=support",
        ],
    )
    assert materialize_screened_corpus_main() == 0

    rows = [__import__("json").loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [row["doc_id"] for row in rows] == ["core_doc", "support_doc"]
    assert [row["role"] for row in rows] == ["core", "support"]
    assert rows[1]["screening"]["screening_decision"] == "peripheral"


def test_role_aware_edge_audit_writes_stratified_sample(tmp_path: Path, monkeypatch) -> None:
    run_root = tmp_path / "run"
    output_root = tmp_path / "audit"
    (run_root / "corpus").mkdir(parents=True)
    (run_root / "graph").mkdir(parents=True)
    (run_root / "taxonomy").mkdir(parents=True)

    append_jsonl(
        run_root / "corpus" / "documents.normalized.jsonl",
        {"doc_id": "D1", "title": "Core method", "text": "Core method uses benchmark data.", "role": "core"},
    )
    append_jsonl(
        run_root / "corpus" / "documents.normalized.jsonl",
        {"doc_id": "D2", "title": "Support method", "text": "Support method adapts benchmark data.", "role": "support"},
    )
    append_jsonl(
        run_root / "graph" / "method_registry.jsonl",
        {
            "entity_id": "method__core_method",
            "canonical_name": "core method",
            "entity_type": "method",
            "support_documents": ["D1"],
            "taxonomy_nodes": ["n1"],
        },
    )
    append_jsonl(
        run_root / "graph" / "method_registry.jsonl",
        {
            "entity_id": "method__support_method",
            "canonical_name": "support method",
            "entity_type": "method",
            "support_documents": ["D2"],
            "taxonomy_nodes": ["n1"],
        },
    )
    edge = {
        "edge_id": "adapts__core__support__d2",
        "source_entity": "method__core_method",
        "target_entity": "method__support_method",
        "edge_type": "adapts",
        "source_document": "D1",
        "target_document": "D2",
        "time_delta_days": 1,
        "taxonomy_nodes": ["n1"],
        "confidence": 0.8,
        "evidence": {"cue": "adapts"},
    }
    append_jsonl(run_root / "graph" / "method_edges.trusted.jsonl", edge)
    append_jsonl(run_root / "graph" / "method_edges.candidate.jsonl", {**edge, "edge_id": "compares__core__support__d2", "edge_type": "compares"})
    append_jsonl(
        run_root / "graph" / "edge_evidence_audit.jsonl",
        {
            "edge_id": "adapts__core__support__d2",
            "verified_quote_count": 1,
            "verified_quote_fields": ["mechanism"],
            "quote_checks": [
                {
                    "field": "mechanism",
                    "quote": "Support method adapts benchmark data.",
                    "verified": True,
                    "matched_document": "D2",
                    "reason": "quote_verified",
                }
            ],
        },
    )
    (run_root / "taxonomy" / "taxonomy_nodes.enriched.json").write_text(
        '[{"node_id": "n1", "canonical_label": "Method Node", "aliases": []}]\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit_edges_role_aware.py",
            "--run-root",
            str(run_root),
            "--output-root",
            str(output_root),
            "--max-samples",
            "4",
        ],
    )
    assert audit_edges_role_aware_main() == 0

    rows = [__import__("json").loads(line) for line in (output_root / "edge_audit_sample.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows
    assert any(row["role_pair"] == "core->support" for row in rows)
    assert (output_root / "edge_audit_sheet.csv").exists()
    assert (output_root / "edge_audit_summary.json").exists()
