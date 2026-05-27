from __future__ import annotations

from pathlib import Path

from evotaxa.ablation import run_ablation_suite
from evotaxa.cli import main
from evotaxa.config import load_config
from evotaxa.edge_evidence import audit_edge_evidence, stratify_edges_by_evidence
from evotaxa.graph import extract_entities, merge_llm_entity_mentions
from evotaxa.llm import build_llm_client, extract_relation_for_pair, judge_edge_evidence
from evotaxa.models import Document, EvolutionEdge
from evotaxa.pipeline import run_full, run_lite


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_scientific_config_runs() -> None:
    config = load_config(REPO_ROOT / "configs" / "scientific_research.example.toml")
    manifest = run_lite(config)
    output_root = Path(manifest["output_root"])
    assert manifest["counts"]["documents"] == 3
    assert manifest["counts"]["taxonomy_nodes"] == 3
    assert manifest["counts"]["entities"] >= 2
    assert manifest["counts"]["relation_schema_types"] >= 7
    assert (output_root / "hooks" / "forecast_hooks.jsonl").exists()
    assert (output_root / "schema" / "relation_schema.final.json").exists()
    assert (output_root / "schema" / "entity_schema.final.json").exists()
    assert (output_root / "schema" / "evidence_schema.final.json").exists()


def test_social_config_runs() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_science.example.toml")
    manifest = run_lite(config)
    output_root = Path(manifest["output_root"])
    assert manifest["counts"]["documents"] == 4
    assert manifest["counts"]["taxonomy_nodes"] == 4
    assert manifest["counts"]["entities"] >= 3
    assert manifest["counts"]["evidence_schema_slots"] >= 3
    assert manifest["counts"]["filtered_entities"] >= 1
    assert manifest["counts"]["entity_link_records"] >= manifest["counts"]["entities"]
    assert manifest["counts"]["trusted_edges"] >= 1
    assert manifest["counts"]["downstream_edges"] == manifest["counts"]["trusted_edges"]
    assert (output_root / "hooks" / "social_analysis_hooks.jsonl").exists()
    assert (output_root / "schema" / "schema_reports.jsonl").exists()


def test_full_pipeline_writes_expansion_and_feedback_artifacts() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_science.example.toml")
    manifest = run_full(config)
    output_root = Path(manifest["output_root"])
    assert manifest["mode"] == "full"
    assert manifest["counts"]["expansion_signals"] >= 1
    assert manifest["counts"]["applied_expansions"] >= 1
    assert manifest["counts"]["coevolution_iterations"] >= 1
    assert manifest["counts"]["revision_candidates"] >= 1
    assert manifest["counts"]["applied_revisions"] >= 1
    assert manifest["counts"]["quality_score"] > 0
    assert (output_root / "taxonomy" / "expansion_trigger_scores.jsonl").exists()
    assert (output_root / "taxonomy" / "taxonomy_nodes.expanded.json").exists()
    assert (output_root / "taxonomy" / "expansion_application_report.jsonl").exists()
    assert (output_root / "taxonomy" / "revision_candidates.jsonl").exists()
    assert (output_root / "taxonomy" / "revision_application_report.jsonl").exists()
    assert (output_root / "taxonomy" / "coevolution_iterations.jsonl").exists()
    assert (output_root / "schema" / "relation_schema.fixed.json").exists()
    assert (output_root / "schema" / "relation_schema.inferred.json").exists()
    assert (output_root / "schema" / "schema_revision_candidates.jsonl").exists()
    assert (output_root / "schema" / "relation_schema.revisions.jsonl").exists()
    assert (output_root / "schema" / "entity_schema.fixed.json").exists()
    assert (output_root / "schema" / "entity_schema.inferred.json").exists()
    assert (output_root / "schema" / "entity_schema.revisions.jsonl").exists()
    assert (output_root / "schema" / "evidence_schema.fixed.json").exists()
    assert (output_root / "schema" / "evidence_schema.inferred.json").exists()
    assert (output_root / "schema" / "evidence_schema.revisions.jsonl").exists()
    assert (output_root / "graph" / "method_aliases.jsonl").exists()
    assert (output_root / "graph" / "entity_linking_report.jsonl").exists()
    assert (output_root / "graph" / "entity_quality_report.jsonl").exists()
    assert (output_root / "graph" / "llm_entity_mentions.jsonl").exists()
    assert (output_root / "graph" / "relation_extraction_report.jsonl").exists()
    assert (output_root / "graph" / "method_edges.trusted.jsonl").exists()
    assert (output_root / "graph" / "method_edges.candidate.jsonl").exists()
    assert (output_root / "graph" / "method_edges.unverified.jsonl").exists()
    assert (output_root / "graph" / "edge_evidence_audit.jsonl").exists()
    assert (output_root / "feedback" / "taxonomy_graph_feedback.jsonl").exists()
    assert (output_root / "evaluation" / "quality_report.json").exists()
    assert (output_root / "hooks" / "hook_score_report.json").exists()


def test_local_llm_config_shape_is_supported() -> None:
    config = load_config(REPO_ROOT / "configs" / "local_llm.example.toml")
    assert config.llm.provider == "openai_compat"
    assert config.llm.model == "your-model-name"
    assert config.llm.api_key == "token-abc123"
    assert config.llm.base_url == "http://localhost:8001/v1"
    assert "entity_extraction" in config.llm.enabled_tasks
    assert "relation_extraction" in config.llm.enabled_tasks


def test_schema_modes_are_configurable() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_science.example.toml")
    assert config.schema.entity_schema_mode == "fixed"
    assert config.schema.relation_schema_mode == "fixed"
    assert config.schema.evidence_schema_mode == "fixed"


def test_schema_cli_commands_write_artifacts() -> None:
    config_path = REPO_ROOT / "configs" / "social_science.example.toml"
    assert main(["infer-schema", "--config", str(config_path), "--print-summary"]) == 0
    assert main(["adapt-schema", "--config", str(config_path), "--print-summary"]) == 0
    output_root = REPO_ROOT / "examples" / "social_smoke_output"
    assert (output_root / "schema" / "relation_schema.final.json").exists()
    assert (output_root / "schema" / "schema_revision_candidates.jsonl").exists()
    assert (output_root / "schema" / "relation_schema.revisions.jsonl").exists()


def test_dynamic_edge_judge_uses_schema_slots() -> None:
    config = load_config(REPO_ROOT / "configs" / "scientific_research.example.toml")
    client = build_llm_client(config.llm)
    edge = {
        "edge_type": "adapts",
        "confidence": 0.7,
        "evidence": {
            "schema_slots": ["mechanism", "implementation_context"],
            "mechanism": {"description": "Mechanism", "quote": "Toolformer adapts tool-use agents to API calls."},
            "implementation_context": {"description": "Context", "quote": "API calls"},
        },
    }
    record = judge_edge_evidence(
        client,
        edge=edge,
        source_text="Toolformer adapts tool-use agents to API calls.",
        target_text="Toolformer adapts tool-use agents to API calls.",
        relation_schema={"adapts": {"evidence_slots": ["mechanism", "implementation_context"]}},
        evidence_schema={"implementation_context": {"definition": "Implementation setting.", "required": True}},
    )
    assert set(record.output["evidence"]) == {"mechanism", "implementation_context"}
    assert record.output["implementation_context"]["quote"] == "API calls"


def test_relation_extraction_task_shape_is_supported() -> None:
    config = load_config(REPO_ROOT / "configs" / "scientific_research.example.toml")
    client = build_llm_client(config.llm)
    pair = {
        "source_entity": {"entity_id": "method__react", "canonical_name": "ReAct"},
        "target_entity": {"entity_id": "method__toolformer", "canonical_name": "Toolformer"},
        "source_document": "P1",
        "target_document": "P2",
        "taxonomy_nodes": ["methodologies__agents"],
        "time_delta_days": 30,
    }
    record = extract_relation_for_pair(
        client,
        pair=pair,
        source_text="ReAct introduced tool-use reasoning.",
        target_text="Toolformer adapts tool-use reasoning to API calls.",
        relation_schema={"adapts": {"definition": "Transfer to a new context.", "evidence_slots": ["mechanism"]}},
        evidence_schema={"mechanism": {"definition": "Mechanism.", "required": True}},
    )
    assert record.output["accept"] is False
    assert record.output["edge_type"] == "background"
    assert "negative_rationale" in record.output


def test_empty_enabled_tasks_does_not_call_llm() -> None:
    config = load_config(REPO_ROOT / "configs" / "scientific_research.example.toml")
    client = build_llm_client(config.llm)
    record = client.complete_json(task="edge_evidence_judge", prompt="{}", fallback={"ok": True})
    assert record.used_model is False
    assert record.error == "No LLM tasks enabled."
    assert record.cache_key


def test_full_pipeline_can_induce_taxonomy_without_node_file() -> None:
    config = load_config(REPO_ROOT / "configs" / "induction_only.example.toml")
    manifest = run_full(config)
    assert manifest["counts"]["taxonomy_nodes"] >= 2
    assert manifest["inputs"]["taxonomy"]["induced_from_corpus"] is True
    assert (Path(manifest["output_root"]) / "taxonomy" / "taxonomy_induction_audit.jsonl").exists()


def test_ablation_runner_writes_summary() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_science.example.toml")
    output_root = REPO_ROOT / "examples" / "social_ablation_smoke_output"
    summary = run_ablation_suite(config, output_root=output_root, variants=["default", "no_coevolution"])
    assert summary["best_variant_by_quality"]
    assert len(summary["variants"]) == 2
    assert (output_root / "ablation_summary.json").exists()
    assert (output_root / "ablation_summary.jsonl").exists()
    assert (output_root / "default" / "manifest.json").exists()
    assert (output_root / "no_coevolution" / "manifest.json").exists()


def test_no_expansion_ablation_disables_expansion() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_science.example.toml")
    output_root = REPO_ROOT / "examples" / "social_no_expansion_smoke_output"
    summary = run_ablation_suite(config, output_root=output_root, variants=["no_expansion"])
    row = summary["variants"][0]
    assert row["applied_expansions"] == 0
    assert row["applied_revisions"] == 0


def test_quote_grounded_llm_entity_mentions_are_merged() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_science.example.toml")
    docs = [
        type(
            "Doc",
            (),
            {
                "doc_id": "D1",
                "title": "Platform labeling",
                "text": "Platform labeling is an intervention for misinformation.",
                "full_text": "Platform labeling\nPlatform labeling is an intervention for misinformation.",
                "published_at": None,
            },
        )()
    ]
    assignments = {"D1": ["interventions__labeling"]}
    entities, mentions = extract_entities(docs, assignments, config.graph)
    record = type(
        "Record",
        (),
        {
            "prompt": "Document id: D1\n",
            "output": {
                "entities": [
                    {
                        "name": "platform labeling",
                        "entity_type": "intervention",
                        "quote": "Platform labeling is an intervention for misinformation.",
                        "confidence": 0.9,
                    }
                ]
            },
        },
    )()
    merged_entities, merged_mentions, report = merge_llm_entity_mentions(docs, assignments, entities, mentions, [record], config.graph)
    assert any(row["status"] == "accepted" for row in report)
    assert any(entity.canonical_name == "platform labeling" for entity in merged_entities)
    assert any(mention.evidence == "Platform labeling is an intervention for misinformation." for mention in merged_mentions)


def test_edge_evidence_stratification_requires_grounded_quotes() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_science.example.toml")
    doc = Document(
        doc_id="D1",
        title="Platform labeling",
        text="Platform labeling extends warning labels by adding civic context.",
    )
    edge = EvolutionEdge(
        edge_id="edge1",
        source_entity="intervention__warning_labels",
        target_entity="intervention__platform_labeling",
        edge_type="extends",
        source_document="D1",
        target_document="D1",
        time_delta_days=0,
        taxonomy_nodes=["interventions"],
        confidence=0.8,
        evidence={
            "mechanism": {
                "description": "Adds civic context.",
                "quote": "Platform labeling extends warning labels by adding civic context.",
            },
            "bottleneck": {"description": "", "quote": ""},
            "tradeoff": {"description": "", "quote": ""},
        },
        substring_verified=False,
    )
    audit = audit_edge_evidence(edge, {"D1": doc}, config.graph)
    assert audit["status"] == "trusted"
    assert audit["verified_quote_fields"] == ["mechanism"]

    trusted, candidates, unverified, rows = stratify_edges_by_evidence([edge], [doc], config.graph)
    assert [item.edge_id for item in trusted] == ["edge1"]
    assert candidates == []
    assert unverified == []
    assert rows[0]["quote_checks"][0]["reason"] == "missing_quote"
    assert trusted[0].substring_verified is True
    assert trusted[0].evidence["evidence_audit"]["status"] == "trusted"
