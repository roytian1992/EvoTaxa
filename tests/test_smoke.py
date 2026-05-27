from __future__ import annotations

from pathlib import Path

from evotaxa.config import load_config
from evotaxa.graph import extract_entities, merge_llm_entity_mentions
from evotaxa.llm import build_llm_client
from evotaxa.pipeline import run_full, run_lite


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_scientific_config_runs() -> None:
    config = load_config(REPO_ROOT / "configs" / "scientific_research.example.toml")
    manifest = run_lite(config)
    assert manifest["counts"]["documents"] == 3
    assert manifest["counts"]["taxonomy_nodes"] == 3
    assert manifest["counts"]["entities"] >= 2
    assert (Path(manifest["output_root"]) / "hooks" / "forecast_hooks.jsonl").exists()


def test_social_config_runs() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_science.example.toml")
    manifest = run_lite(config)
    assert manifest["counts"]["documents"] == 4
    assert manifest["counts"]["taxonomy_nodes"] == 4
    assert manifest["counts"]["entities"] >= 3
    assert manifest["counts"]["filtered_entities"] >= 1
    assert manifest["counts"]["entity_link_records"] >= manifest["counts"]["entities"]
    assert (Path(manifest["output_root"]) / "hooks" / "social_analysis_hooks.jsonl").exists()


def test_full_pipeline_writes_expansion_and_feedback_artifacts() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_science.example.toml")
    manifest = run_full(config)
    output_root = Path(manifest["output_root"])
    assert manifest["mode"] == "full"
    assert manifest["counts"]["expansion_signals"] >= 1
    assert manifest["counts"]["applied_expansions"] >= 1
    assert (output_root / "taxonomy" / "expansion_trigger_scores.jsonl").exists()
    assert (output_root / "taxonomy" / "taxonomy_nodes.expanded.json").exists()
    assert (output_root / "taxonomy" / "expansion_application_report.jsonl").exists()
    assert (output_root / "graph" / "method_aliases.jsonl").exists()
    assert (output_root / "graph" / "entity_linking_report.jsonl").exists()
    assert (output_root / "graph" / "entity_quality_report.jsonl").exists()
    assert (output_root / "graph" / "llm_entity_mentions.jsonl").exists()
    assert (output_root / "feedback" / "taxonomy_graph_feedback.jsonl").exists()
    assert (output_root / "hooks" / "hook_score_report.json").exists()


def test_local_llm_config_shape_is_supported() -> None:
    config = load_config(REPO_ROOT / "configs" / "local_llm.example.toml")
    assert config.llm.provider == "openai_compat"
    assert config.llm.model == "your-model-name"
    assert config.llm.api_key == "token-abc123"
    assert config.llm.base_url == "http://localhost:8001/v1"
    assert "entity_extraction" in config.llm.enabled_tasks


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
