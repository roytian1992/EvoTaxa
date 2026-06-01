from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from evotaxa.ablation import run_ablation_suite
from evotaxa.cli import main
from evotaxa.config import load_config
from evotaxa.edge_scoring import edge_score_components, score_edges
from evotaxa.edge_evidence import audit_edge_evidence, stratify_edges_by_evidence
from evotaxa.graph import _candidate_document_pairs, build_relation_extraction_pairs, edge_from_relation_extraction, extract_entities, merge_llm_entity_mentions
from evotaxa.loaders import infer_assignments_from_text
from evotaxa.llm import build_llm_client, extract_document_entities, extract_relation_for_pair, extract_relations_for_pairs, judge_edge_evidence, judge_schema_revision
from evotaxa.llm import summarize_macro_pattern
from evotaxa.prompts import render_prompt
from evotaxa.macro_patterns import synthesize_macro_patterns
from evotaxa.models import Document, EntityMention, EvolutionEdge, EvolutionEntity, TaxonomyNode
from evotaxa.pipeline import run_full, run_lite
from evotaxa.schema import adapt_schema_after_graph, resolve_initial_schema
from evotaxa.state import build_evolution_state_snapshot, build_state_transition_report
from evotaxa.temporal_windows import build_temporal_windows
from evotaxa.trajectory import infer_evolution_trajectories
from evotaxa.entity_quality import score_entity_quality


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from extract_successor_edges import build_successor_candidates  # noqa: E402
from materialize_evolution_artifacts import build_successor_trajectories, is_successor_edge  # noqa: E402
from filter_successor_edges import strict_rejection_reason  # noqa: E402


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
    assert (output_root / "graph" / "relation_rejections.jsonl").exists()
    assert (output_root / "graph" / "edge_scores.jsonl").exists()
    assert (output_root / "trajectory" / "evolution_trajectories.jsonl").exists()
    assert (output_root / "trajectory" / "trajectory_eval.jsonl").exists()
    assert (output_root / "state" / "evolution_state.json").exists()
    assert (output_root / "state" / "state_transitions.jsonl").exists()
    assert (output_root / "macro_patterns" / "pattern_profiles.jsonl").exists()
    assert (output_root / "macro_patterns" / "pattern_evidence.jsonl").exists()
    assert (output_root / "macro_patterns" / "pattern_timeline.jsonl").exists()
    assert (output_root / "macro_patterns" / "pattern_summary.json").exists()
    assert (output_root / "temporal_windows" / "micro_windows.jsonl").exists()
    assert (output_root / "temporal_windows" / "window_assignments.jsonl").exists()
    assert (output_root / "temporal_windows" / "window_summary.json").exists()
    assert (output_root / "graph" / "method_edges.trusted.jsonl").exists()
    assert (output_root / "graph" / "method_edges.candidate.jsonl").exists()
    assert (output_root / "graph" / "method_edges.unverified.jsonl").exists()
    assert (output_root / "graph" / "edge_evidence_audit.jsonl").exists()
    assert (output_root / "feedback" / "taxonomy_graph_feedback.jsonl").exists()
    assert (output_root / "evaluation" / "quality_report.json").exists()
    assert (output_root / "reports" / "case_study_report.md").exists()
    assert (output_root / "hooks" / "hook_score_report.json").exists()
    assert manifest["counts"]["edge_scores"] >= manifest["counts"]["paper_level_edges"]
    assert manifest["counts"]["trajectories"] >= 1
    assert manifest["counts"]["state_transitions"] >= 1
    assert manifest["counts"]["macro_patterns"] >= 1
    assert manifest["counts"]["macro_pattern_evidence"] >= manifest["counts"]["macro_patterns"]
    assert manifest["counts"]["temporal_windows"] >= 1
    assert manifest["counts"]["temporal_window_assignments"] >= manifest["counts"]["temporal_windows"]
    assert manifest["artifact_layout"]["case_study_report"] == "reports/case_study_report.md"
    assert manifest["artifact_layout"]["trajectories"] == "trajectory/evolution_trajectories.jsonl"
    assert manifest["artifact_layout"]["macro_pattern_profiles"] == "macro_patterns/pattern_profiles.jsonl"
    assert manifest["artifact_layout"]["temporal_windows"] == "temporal_windows/micro_windows.jsonl"


def test_local_llm_config_shape_is_supported() -> None:
    config = load_config(REPO_ROOT / "configs" / "local_llm.example.toml")
    assert config.llm.provider == "openai_compat"
    assert config.llm.model == "your-model-name"
    assert config.llm.api_key == ""
    assert config.llm.api_key_env == "EVOTAXA_LLM_API_KEY"
    assert config.llm.base_url == "http://localhost:8001/v1"
    assert config.graph.llm_relation_batch_size == 4
    assert "entity_extraction" in config.llm.enabled_tasks
    assert "relation_extraction_batch" in config.llm.enabled_tasks
    assert "schema_revision_judge" in config.llm.enabled_tasks


def test_qwen_local_llm_config_uses_env_key_without_token_limit() -> None:
    config = load_config(REPO_ROOT / "configs" / "qwen_local_llm.example.toml")
    assert config.llm.provider == "openai_compat"
    assert config.llm.model == "Qwen3.5-397B-A17B-FP8"
    assert config.llm.api_key == ""
    assert config.llm.api_key_env == "EVOTAXA_LLM_API_KEY"
    assert config.llm.prompt_dir == REPO_ROOT / "task_specs" / "prompts"
    assert config.llm.system_prompt_id == "llm/system_json"
    assert config.llm.max_tokens == 0
    assert config.llm.max_workers == 16
    assert config.llm.extra_body.get("chat_template_kwargs", {}).get("enable_thinking") is False
    assert config.llm.timeout_seconds == 60
    assert config.schema.relation_schema_mode == "fixed"
    assert config.graph.llm_taxonomy_judge_limit == 4
    assert config.graph.llm_relation_extraction_limit == 4
    assert config.graph.llm_edge_judge_limit == 0
    assert config.temporal_windows.enabled is True
    assert config.temporal_windows.min_documents_per_window == 2


def test_yaml_prompt_loader_preserves_json_braces_and_renders_declared_vars() -> None:
    prompt = render_prompt(
        "llm/relation_extraction_batch",
        {
            "relation_schema": {"extends": {"definition": "Adds to prior work."}},
            "evidence_schema": {"mechanism": {"required": True}},
            "pairs": [{"pair_index": 0, "source_text": "A", "target_text": "B"}],
        },
    )
    assert "Return JSON:" in prompt
    assert '{"relations":' in prompt
    assert "Adds to prior work." in prompt


def test_schema_modes_are_configurable() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_science.example.toml")
    assert config.schema.entity_schema_mode == "fixed"
    assert config.schema.relation_schema_mode == "fixed"
    assert config.schema.evidence_schema_mode == "fixed"


def test_adaptive_temporal_windows_close_on_evidence_density() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_science.example.toml")
    config.temporal_windows.min_documents_per_window = 2
    config.temporal_windows.min_mentions_per_window = 2
    config.temporal_windows.min_edges_per_window = 1
    config.temporal_windows.min_duration_days = 1
    docs = [
        Document(doc_id="D1", title="One", text="platform labeling", published_at=date(2023, 1, 1), chronology_slice="2023"),
        Document(doc_id="D2", title="Two", text="content labeling", published_at=date(2023, 2, 1), chronology_slice="2023"),
        Document(doc_id="D3", title="Three", text="inoculation", published_at=date(2024, 1, 1), chronology_slice="2024"),
    ]
    entities, mentions = extract_entities(docs, {"D1": ["n1"], "D2": ["n1"], "D3": ["n1"]}, config.graph)
    windows = build_temporal_windows(
        docs=docs,
        nodes=[],
        entities=entities,
        mentions=mentions,
        edges=[],
        trajectory_rows=[],
        config=config.temporal_windows,
    )
    assert windows["summary"]["enabled"] is True
    assert windows["summary"]["window_count"] >= 2
    assert any(row["scope_type"] == "global" and row["document_count"] == 2 for row in windows["windows"])


def test_successor_trajectory_materialization_preserves_parallel_edges() -> None:
    entities = {
        "method__older": {"canonical_name": "older", "entity_type": "method"},
        "method__newer": {"canonical_name": "newer", "entity_type": "method"},
    }
    edges = [
        {
            "edge_id": "extends__method_older__method_newer__w1",
            "source_entity": "method__older",
            "target_entity": "method__newer",
            "edge_type": "extends",
            "confidence": 0.91,
            "time_delta_days": 365,
            "taxonomy_nodes": ["n1"],
            "substring_verified": True,
        },
        {
            "edge_id": "improves__method_older__method_newer__w2",
            "source_entity": "method__older",
            "target_entity": "method__newer",
            "edge_type": "improves",
            "confidence": 0.89,
            "time_delta_days": 730,
            "taxonomy_nodes": ["n1"],
            "substring_verified": True,
        },
    ]
    trajectories = build_successor_trajectories(edges, entities)
    covered_edges = {edge_id for row in trajectories for edge_id in row["edge_path"]}
    assert covered_edges == {edge["edge_id"] for edge in edges}
    assert len([row for row in trajectories if row["path_length"] == 1]) == 2


def test_schema_group_candidate_generation_allows_adjacent_type_evolution() -> None:
    docs = {
        "D1": {
            "doc_id": "D1",
            "title": "Older coding strategy",
            "text": "The study introduced manual stance coding for political text.",
            "date": date(2010, 1, 1),
        },
        "D2": {
            "doc_id": "D2",
            "title": "Newer modeling method",
            "text": "We build on stance coding and extend it with supervised stance classification for political text.",
            "date": date(2014, 1, 1),
        },
    }
    entities = [
        {
            "entity_id": "measurement_strategy__stance_coding",
            "canonical_name": "stance coding",
            "entity_type": "measurement_strategy",
            "schema_group": "analytic_method",
            "first_seen_date": date(2010, 1, 1),
            "first_seen": "2010-01-01",
            "support_documents": ["D1"],
            "taxonomy_nodes": ["political_text"],
            "aliases": [],
        },
        {
            "entity_id": "method__supervised_stance_classification",
            "canonical_name": "supervised stance classification",
            "entity_type": "method",
            "schema_group": "analytic_method",
            "first_seen_date": date(2014, 1, 1),
            "first_seen": "2014-01-01",
            "support_documents": ["D2"],
            "taxonomy_nodes": ["political_text"],
            "aliases": [],
        },
    ]
    candidates, _counts = build_successor_candidates(
        entities=entities,
        docs=docs,
        mentions={},
        max_source_age_years=18,
        min_candidate_score=0.1,
        max_sources_per_target=10,
        per_target_candidates=4,
        limit=0,
        skip_label_variants=True,
        candidate_scope="schema_group",
    )
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["schema_group"] == "analytic_method"
    assert candidate["source_entity_type"] == "measurement_strategy"
    assert candidate["target_entity_type"] == "method"


def test_successor_edge_accepts_same_schema_group_across_original_types() -> None:
    entities = {
        "measurement_strategy__stance_coding": {"canonical_name": "stance coding", "entity_type": "measurement_strategy"},
        "method__supervised_stance_classification": {"canonical_name": "supervised stance classification", "entity_type": "method"},
    }
    edge = {
        "edge_id": "extends__measurement_strategy_stance_coding__method_supervised_stance_classification__d2",
        "source_entity": "measurement_strategy__stance_coding",
        "target_entity": "method__supervised_stance_classification",
        "edge_type": "extends",
        "schema_group": "analytic_method",
        "source_schema_group": "analytic_method",
        "target_schema_group": "analytic_method",
        "source_entity_type": "measurement_strategy",
        "target_entity_type": "method",
        "time_delta_days": 1460,
    }
    assert is_successor_edge(edge, entities)


def test_successor_display_filter_rejects_generic_ml_architecture_lineage() -> None:
    row = {
        "accepted": True,
        "edge_type": "specializes",
        "entity_type": "modeling_strategy",
        "confidence": 0.9,
        "time_delta_days": 1416,
        "source_document": "W1",
        "target_document": "W2",
        "source_name": "artificial neural network",
        "target_name": "convolutional neural network",
        "candidate_reasons": ["shared_taxonomy", "name_token_overlap", "target_text_has_evolution_cue"],
        "source_quote": "incorporating artificial neural networks",
        "target_quote": "We build classifiers such as Convolutional Neural Network (CNN) to automatically detect different types of sexism.",
        "rationale": "While the target paper does not explicitly cite the source, the methodological progression from general ANNs to CNNs is well-established in machine learning literature.",
        "evidence": {
            "mechanism": {
                "description": "CNNs are a specialized form of artificial neural networks.",
                "quote": "We build classifiers such as Convolutional Neural Network (CNN)",
            }
        },
    }
    reason = strict_rejection_reason(
        row,
        relation_types={"adapts", "extends", "generalizes", "improves", "replaces", "specializes"},
        min_confidence=0.84,
        min_time_delta_days=180,
    )
    assert reason == "generic_ml_architecture_not_css_evolution"


def test_adaptive_social_case_study_config_runs() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_misinformation_governance.adaptive.toml")
    assert config.schema.entity_schema_mode == "adaptive"
    assert config.schema.relation_schema_mode == "adaptive"
    assert config.schema.evidence_schema_mode == "adaptive"
    manifest = run_full(config)
    output_root = Path(manifest["output_root"])
    assert manifest["mode"] == "full"
    assert manifest["counts"]["documents"] == 4
    assert manifest["counts"]["relation_rejections"] >= 1
    assert (output_root / "schema" / "schema_revision_candidates.jsonl").exists()
    assert (output_root / "graph" / "relation_rejections.jsonl").exists()
    assert (output_root / "graph" / "edge_scores.jsonl").exists()
    assert (output_root / "reports" / "case_study_report.md").exists()


def test_taxonomy_assignment_uses_phrase_boundaries() -> None:
    docs = [
        Document(
            doc_id="D1",
            title="Language models",
            text="This paper studies large language models for annotation.",
            published_at=date(2024, 1, 1),
            chronology_slice="2024",
        ),
        Document(
            doc_id="D2",
            title="Unrelated",
            text="The word flagpole should not match a short alias inside another word.",
            published_at=date(2024, 1, 2),
            chronology_slice="2024",
        ),
    ]
    nodes = [
        TaxonomyNode(
            node_id="methods__llm",
            dimension="methods",
            canonical_label="Large Language Models",
            aliases=["GPT"],
        )
    ]
    assignments = infer_assignments_from_text(docs, nodes)
    assert assignments == {"D1": ["methods__llm"]}


def test_candidate_document_pairs_applies_limit_before_cartesian_expansion() -> None:
    docs = {
        f"D{i}": Document(
            doc_id=f"D{i}",
            title=f"Doc {i}",
            text="method evidence",
            published_at=date(2020, 1, i),
            chronology_slice="2020",
        )
        for i in range(1, 8)
    }
    source = EvolutionEntity(
        entity_id="method__source",
        canonical_name="Source",
        aliases=[],
        first_seen_date="2020-01-01",
        support_documents=list(docs),
        taxonomy_nodes=["n1"],
        entity_type="method",
    )
    target = EvolutionEntity(
        entity_id="method__target",
        canonical_name="Target",
        aliases=[],
        first_seen_date="2020-01-01",
        support_documents=list(docs),
        taxonomy_nodes=["n1"],
        entity_type="method",
    )

    pairs = _candidate_document_pairs(source, target, docs, limit=3)

    assert len(pairs) == 3
    assert all(left.published_at <= right.published_at for left, right in pairs)


def test_relation_extraction_pairs_prioritize_quote_grounded_candidates() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_science.example.toml")
    config.graph.llm_relation_extraction_limit = 2
    config.graph.max_pair_groups_per_node = 8
    config.graph.llm_relation_candidate_min_score = 0.45
    docs = [
        Document(
            doc_id="D1",
            title="Platform labeling",
            text="Platform labeling is an intervention for misinformation.",
            published_at=date(2023, 1, 1),
            chronology_slice="2023",
        ),
        Document(
            doc_id="D2",
            title="Inoculation improves labeling",
            text="The inoculation intervention builds on platform labeling and improves resilience to misleading claims.",
            published_at=date(2024, 1, 1),
            chronology_slice="2024",
        ),
        Document(
            doc_id="D3",
            title="Unrelated benchmark",
            text="Empirical performance is reported for a separate matrix algorithm.",
            published_at=date(2024, 2, 1),
            chronology_slice="2024",
        ),
    ]
    assignments = {
        "D1": ["interventions__labeling"],
        "D2": ["interventions__labeling"],
        "D3": ["interventions__labeling"],
    }
    entities = [
        EvolutionEntity(
            entity_id="intervention__platform_labeling",
            canonical_name="platform labeling",
            aliases=[],
            first_seen_date="2023-01-01",
            support_documents=["D1", "D2"],
            taxonomy_nodes=["interventions__labeling"],
            entity_type="intervention",
        ),
        EvolutionEntity(
            entity_id="intervention__inoculation_intervention",
            canonical_name="inoculation intervention",
            aliases=[],
            first_seen_date="2024-01-01",
            support_documents=["D2"],
            taxonomy_nodes=["interventions__labeling"],
            entity_type="intervention",
        ),
        EvolutionEntity(
            entity_id="measurement_strategy__empirical_performance",
            canonical_name="empirical performance",
            aliases=[],
            first_seen_date="2024-02-01",
            support_documents=["D3"],
            taxonomy_nodes=["interventions__labeling"],
            entity_type="measurement_strategy",
        ),
    ]
    mentions = [
        EntityMention("D1", "intervention__platform_labeling", "platform labeling", assignments["D1"], "Platform labeling is an intervention for misinformation."),
        EntityMention("D2", "intervention__platform_labeling", "platform labeling", assignments["D2"], "The inoculation intervention builds on platform labeling and improves resilience to misleading claims."),
        EntityMention("D2", "intervention__inoculation_intervention", "inoculation intervention", assignments["D2"], "The inoculation intervention builds on platform labeling and improves resilience to misleading claims."),
        EntityMention("D3", "measurement_strategy__empirical_performance", "empirical performance", assignments["D3"], "Empirical performance is reported for a separate matrix algorithm."),
    ]

    pairs = build_relation_extraction_pairs(docs, entities, mentions, config.graph, limit=2)

    assert pairs
    assert pairs[0]["target_document"] == "D2"
    assert pairs[0]["source_entity"]["entity_id"] == "intervention__platform_labeling"
    assert pairs[0]["target_entity"]["entity_id"] == "intervention__inoculation_intervention"
    assert pairs[0]["candidate_score"] >= 0.45
    assert "builds on platform labeling" in pairs[0]["candidate_evidence"]["relation_quote"]


def test_entity_quality_filters_academic_transition_phrases() -> None:
    entity = EvolutionEntity(
        entity_id="method__in_this_work",
        canonical_name="in this work",
        aliases=[],
        first_seen_date="2020-01-01",
        support_documents=["D1", "D2", "D3"],
        taxonomy_nodes=["n1"],
        entity_type="method",
    )
    score, reasons = score_entity_quality(
        entity,
        mention_count=3,
        allowlist=set(),
        denylist=set(),
        generic_phrases=set(),
    )
    assert score == 0.0
    assert reasons == ["domain_stop_phrase"]

    schema_bucket = EvolutionEntity(
        entity_id="method__computational_social_science",
        canonical_name="computational social science",
        aliases=[],
        first_seen_date="2020-01-01",
        support_documents=["D1", "D2", "D3"],
        taxonomy_nodes=["n1"],
        entity_type="method",
    )
    score, reasons = score_entity_quality(
        schema_bucket,
        mention_count=3,
        allowlist=set(),
        denylist=set(),
        generic_phrases=set(),
    )
    assert score == 0.0
    assert reasons == ["schema_bucket_phrase"]

    fragment = EvolutionEntity(
        entity_id="method__early_academic_capital_as_the",
        canonical_name="early academic capital as the",
        aliases=[],
        first_seen_date="2020-01-01",
        support_documents=["D1"],
        taxonomy_nodes=["n1"],
        entity_type="method",
    )
    score, reasons = score_entity_quality(
        fragment,
        mention_count=1,
        allowlist=set(),
        denylist=set(),
        generic_phrases=set(),
    )
    assert score < 0.42
    assert "incomplete_phrase" in reasons

    sentence_fragment = EvolutionEntity(
        entity_id="method__our_analysis_focuses_on_gradual",
        canonical_name="our analysis focuses on gradual",
        aliases=[],
        first_seen_date="2020-01-01",
        support_documents=["D1", "D2"],
        taxonomy_nodes=["n1"],
        entity_type="method",
    )
    score, reasons = score_entity_quality(
        sentence_fragment,
        mention_count=2,
        allowlist=set(),
        denylist=set(),
        generic_phrases=set(),
    )
    assert score < 0.42
    assert "incomplete_phrase" in reasons

    single = EvolutionEntity(
        entity_id="method__science",
        canonical_name="science",
        aliases=[],
        first_seen_date="2020-01-01",
        support_documents=["D1", "D2", "D3"],
        taxonomy_nodes=["n1"],
        entity_type="method",
    )
    score, reasons = score_entity_quality(
        single,
        mention_count=3,
        allowlist=set(),
        denylist=set(),
        generic_phrases=set(),
    )
    assert score == 0.0
    assert reasons == ["generic_single_token"]

    transition = EvolutionEntity(
        entity_id="method__at_the_same_time",
        canonical_name="at the same time",
        aliases=[],
        first_seen_date="2020-01-01",
        support_documents=["D1", "D2", "D3"],
        taxonomy_nodes=["n1"],
        entity_type="method",
    )
    score, reasons = score_entity_quality(
        transition,
        mention_count=3,
        allowlist=set(),
        denylist=set(),
        generic_phrases=set(),
    )
    assert score == 0.0
    assert reasons == ["domain_stop_phrase"]

    generic = EvolutionEntity(
        entity_id="method__second",
        canonical_name="second",
        aliases=[],
        first_seen_date="2020-01-01",
        support_documents=["D1", "D2", "D3"],
        taxonomy_nodes=["n1"],
        entity_type="method",
    )
    score, reasons = score_entity_quality(
        generic,
        mention_count=3,
        allowlist=set(),
        denylist=set(),
        generic_phrases=set(),
    )
    assert score == 0.0
    assert reasons == ["domain_stop_phrase"]


def test_schema_cli_commands_write_artifacts() -> None:
    config_path = REPO_ROOT / "configs" / "social_science.example.toml"
    assert main(["infer-schema", "--config", str(config_path), "--print-summary"]) == 0
    assert main(["adapt-schema", "--config", str(config_path), "--print-summary"]) == 0
    output_root = REPO_ROOT / "examples" / "social_smoke_output"
    assert (output_root / "schema" / "relation_schema.final.json").exists()
    assert (output_root / "schema" / "schema_revision_candidates.jsonl").exists()
    assert (output_root / "schema" / "relation_schema.revisions.jsonl").exists()


def test_schema_probe_script_writes_artifacts(tmp_path: Path) -> None:
    output_root = tmp_path / "schema_probe"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "probe_schema_design.py"),
            "--config",
            str(REPO_ROOT / "configs" / "social_science.example.toml"),
            "--output-root",
            str(output_root),
            "--sample-size",
            "3",
            "--seed",
            "7",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads((output_root / "probe_summary.json").read_text(encoding="utf-8"))
    assert summary["sample_size"] == 3
    assert summary["best_variant_id"] in {"method_ecology", "evidence_practice", "hybrid_two_axis", "corpus_terms"}
    assert (output_root / "sampled_documents.jsonl").exists()
    assert (output_root / "node_candidates.jsonl").exists()
    assert (output_root / "node_coverage_report.json").exists()
    assert (output_root / "boundary_cases.jsonl").exists()
    assert (output_root / "schema_recommendation.md").exists()


def test_schema_probe_proposal_writes_mainflow_config(tmp_path: Path) -> None:
    probe_root = tmp_path / "schema_probe"
    proposal_root = tmp_path / "schema_proposal"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    probe = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "probe_schema_design.py"),
            "--config",
            str(REPO_ROOT / "configs" / "social_science.example.toml"),
            "--output-root",
            str(probe_root),
            "--sample-size",
            "4",
            "--seed",
            "13",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr
    proposal = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "propose_schema_from_probe.py"),
            "--base-config",
            str(REPO_ROOT / "configs" / "social_science.example.toml"),
            "--probe-root",
            str(probe_root),
            "--output-root",
            str(proposal_root),
            "--run-id-suffix",
            "test_probe",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proposal.returncode == 0, proposal.stderr
    proposed_config = load_config(proposal_root / "config.proposed.json")
    assert proposed_config.taxonomy.nodes_path == proposal_root / "taxonomy.proposed.json"
    assert proposed_config.schema.schema_seed_path == proposal_root / "schema_seed.proposed.json"
    assert "operationalizes" in proposed_config.graph.strong_edge_types
    assert proposed_config.graph.entity_dimensions
    taxonomy = json.loads((proposal_root / "taxonomy.proposed.json").read_text(encoding="utf-8"))
    assert taxonomy[0]["node_card"]["card_type"] == "taxonomy_node_card"
    assert "This card defines a taxonomy node, not a graph entity." in taxonomy[0]["node_card"]["boundary_notes"]
    seed = json.loads((proposal_root / "schema_seed.proposed.json").read_text(encoding="utf-8"))
    assert "operationalizes" in seed["relation_schema"]
    assert "measurement_design" in seed["evidence_schema"]
    assert (proposal_root / "schema_proposal_report.md").exists()


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


def test_batched_relation_extraction_task_shape_is_supported() -> None:
    config = load_config(REPO_ROOT / "configs" / "scientific_research.example.toml")
    client = build_llm_client(config.llm)
    pairs = [
        {
            "source_entity": {"entity_id": "method__react", "canonical_name": "ReAct"},
            "target_entity": {"entity_id": "method__toolformer", "canonical_name": "Toolformer"},
            "source_document": "P1",
            "target_document": "P2",
            "taxonomy_nodes": ["methodologies__agents"],
            "time_delta_days": 30,
        },
        {
            "source_entity": {"entity_id": "method__cot", "canonical_name": "Chain-of-Thought"},
            "target_entity": {"entity_id": "method__self_consistency", "canonical_name": "Self-Consistency"},
            "source_document": "P1",
            "target_document": "P3",
            "taxonomy_nodes": ["methodologies__reasoning"],
            "time_delta_days": 60,
        },
    ]
    record = extract_relations_for_pairs(
        client,
        pairs=pairs,
        document_texts={
            "P1": "ReAct introduced tool-use reasoning. Chain-of-Thought improves reasoning traces.",
            "P2": "Toolformer adapts tool-use reasoning to API calls.",
            "P3": "Self-Consistency aggregates multiple reasoning traces.",
        },
        relation_schema={"adapts": {"definition": "Transfer to a new context.", "evidence_slots": ["mechanism"]}},
        evidence_schema={"mechanism": {"definition": "Mechanism.", "required": True}},
    )
    assert len(record.output["relations"]) == 2
    assert record.output["relations"][0]["pair_index"] == 0
    assert record.output["relations"][0]["accept"] is False
    assert record.output["relations"][1]["pair_index"] == 1
    assert record.output["relations"][1]["rejection_reason"] == "model_not_run"


def test_relation_extraction_string_evidence_is_preserved_as_quote() -> None:
    edge = edge_from_relation_extraction(
        {
            "source_entity": {"entity_id": "method__a"},
            "target_entity": {"entity_id": "method__b"},
            "source_document": "D1",
            "target_document": "D1",
            "time_delta_days": 0,
            "taxonomy_nodes": ["n1"],
        },
        {
            "accept": True,
            "edge_type": "uses_component",
            "confidence": 0.8,
            "evidence": {"mechanism": "B uses A as a component."},
        },
        relation_schema={"uses_component": {"evidence_slots": ["mechanism"]}},
        evidence_schema={"mechanism": {"required": True}},
    )

    assert edge is not None
    assert edge.evidence["mechanism"]["quote"] == "B uses A as a component."


def test_empty_enabled_tasks_does_not_call_llm() -> None:
    config = load_config(REPO_ROOT / "configs" / "scientific_research.example.toml")
    client = build_llm_client(config.llm)
    record = client.complete_json(task="edge_evidence_judge", prompt="{}", fallback={"ok": True})
    assert record.used_model is False
    assert record.error == "No LLM tasks enabled."
    assert record.cache_key


def test_entity_extraction_prompt_uses_entity_schema_boundaries() -> None:
    config = load_config(REPO_ROOT / "configs" / "scientific_research.example.toml")
    client = build_llm_client(config.llm)
    record = extract_document_entities(
        client,
        doc_id="P1",
        title="Toolformer",
        text="Toolformer adapts tool-use reasoning to API calls.",
        entity_types=["method"],
        max_entities=3,
        entity_schema={
            "method": {
                "entity_type": "method",
                "definition": "Named computational method.",
                "exclusion_criteria": "Reject generic nouns and incomplete sentence fragments.",
                "negative_examples": ["method", "analysis", "study"],
            }
        },
    )
    assert record.used_model is False
    assert "Allowed entity schema" in record.prompt
    assert "Reject generic nouns" in record.prompt
    assert "Named computational method" in record.prompt


def test_macro_pattern_summary_task_shape_is_supported() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_science.example.toml")
    client = build_llm_client(config.llm)
    profile = {
        "pattern_id": "recontextualization",
        "pattern_score": 0.5,
        "evidence_ids": ["macro_evidence__edge__edge1"],
        "explanation": "Recontextualization is estimated from detector-backed signals.",
    }
    record = summarize_macro_pattern(
        client,
        pattern_profile=profile,
        evidence_records=[
            {
                "evidence_id": "macro_evidence__edge__edge1",
                "pattern_ids": ["recontextualization"],
                "source_evidence_ids": ["edge1"],
            }
        ],
    )
    assert record.output["summary"] == profile["explanation"]
    assert record.used_model is False


def test_schema_revision_judge_rejection_blocks_promotion() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_misinformation_governance.adaptive.toml")
    client = build_llm_client(config.llm)
    docs = [Document(doc_id="D1", title="Audit", text="Algorithmic audit evidence is repeatedly missing.")]
    bundle = resolve_initial_schema(config, docs, [], client)
    audit_rows = [
        {
            "edge_type": "extends",
            "status": "candidate",
            "quote_checks": [
                {"field": "mechanism", "ok": False, "reason": "missing_quote"},
                {"field": "mechanism", "ok": False, "reason": "missing_quote"},
            ],
        }
    ]
    candidate_id = "evidence_review__mechanism"
    adapted, revisions = adapt_schema_after_graph(
        bundle,
        edge_evidence_audit=audit_rows,
        entity_quality_report=[],
        config=config,
        judgements={
            candidate_id: {
                "decision": "reject",
                "confidence": 0.91,
                "rationale": "Keep current evidence slot stable for this run.",
                "risk": "low",
            }
        },
    )
    assert any(row.get("candidate_id") == candidate_id and row.get("judge_decision") == "reject" for row in adapted.revision_candidates)
    assert any(row.get("candidate_id") == candidate_id and row.get("status") == "rejected" for row in revisions)
    assert not adapted.evidence_schema["mechanism"].get("needs_review")


def test_relation_rejections_feed_schema_negative_priors() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_misinformation_governance.adaptive.toml")
    client = build_llm_client(config.llm)
    docs = [Document(doc_id="D1", title="Audit", text="Platform labeling and survey experiments are compared without mechanism evidence.")]
    bundle = resolve_initial_schema(config, docs, [], client)
    adapted, revisions = adapt_schema_after_graph(
        bundle,
        edge_evidence_audit=[],
        entity_quality_report=[],
        relation_rejections=[
            {"edge_type": "background", "source_entity": "intervention__platform_labeling", "target_entity": "measurement_strategy__survey_experiment", "rejection_reason": "weak_co_mention"},
            {"edge_type": "background", "source_entity": "intervention__platform_labeling", "target_entity": "actor__communities", "rejection_reason": "weak_co_mention"},
        ],
        config=config,
    )
    assert any(row.get("revision_type") == "update_negative_prior" for row in adapted.revision_candidates)
    assert any(row.get("revision_type") == "update_negative_prior" and row.get("status") == "applied" for row in revisions)
    assert adapted.relation_schema["background"]["negative_priors"]["weak_co_mention"] == 2


def test_schema_revision_judge_task_shape_is_supported() -> None:
    config = load_config(REPO_ROOT / "configs" / "scientific_research.example.toml")
    client = build_llm_client(config.llm)
    record = judge_schema_revision(
        client,
        candidate={"candidate_id": "rel__mediates", "schema_family": "relation_schema", "revision_type": "add_relation_type", "confidence": 0.7},
        current_schema={"relation_schema": {"extends": {"definition": "Adds to prior work."}}},
    )
    assert record.output["decision"] == "promote"
    assert "rationale" in record.output


def test_edge_scoring_penalizes_temporal_violations() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_science.example.toml")
    edge = EvolutionEdge(
        edge_id="edge_temporal",
        source_entity="intervention__new",
        target_entity="intervention__old",
        edge_type="extends",
        source_document="D2",
        target_document="D1",
        time_delta_days=-10,
        taxonomy_nodes=["interventions"],
        confidence=0.8,
        evidence={"mechanism": {"description": "Mechanism", "quote": "New intervention extends old intervention."}},
        substring_verified=True,
    )
    scores = edge_score_components(
        edge,
        relation_schema={
            "extends": {
                "definition": "Adds capability to a prior intervention.",
                "evidence_slots": ["mechanism"],
            }
        },
        evidence_schema={"mechanism": {"required": True}},
        config=config.graph,
    )
    assert scores["temporal_order"] == 0.0
    assert scores["quote_grounding"] == 1.0
    assert scores["schema_fit"] >= 0.9
    assert scores["edge_score"] < 0.8
    rows = score_edges(
        [edge],
        relation_schema={
            "extends": {
                "definition": "Adds capability to a prior intervention.",
                "evidence_slots": ["mechanism"],
            }
        },
        evidence_schema={"mechanism": {"required": True}},
        config=config.graph,
    )
    assert rows[0]["previous_confidence"] == 0.8
    assert edge.confidence == scores["edge_score"]


def test_trajectory_inference_filters_temporal_violations() -> None:
    good = EvolutionEdge(
        edge_id="good",
        source_entity="a",
        target_entity="b",
        edge_type="extends",
        source_document="D1",
        target_document="D2",
        time_delta_days=20,
        taxonomy_nodes=["n1"],
        confidence=0.82,
        evidence={"edge_score": {"schema_fit": 1.0}},
        substring_verified=True,
    )
    bad = EvolutionEdge(
        edge_id="bad",
        source_entity="b",
        target_entity="c",
        edge_type="extends",
        source_document="D2",
        target_document="D1",
        time_delta_days=-20,
        taxonomy_nodes=["n1"],
        confidence=0.9,
        evidence={"edge_score": {"schema_fit": 1.0}},
        substring_verified=True,
    )
    chains, rows, evaluation = infer_evolution_trajectories([good, bad], strong_edge_types=["extends"])
    assert len(chains) == 1
    assert rows[0]["edge_path"] == ["good"]
    assert any(row["metric"] == "temporal_coherence" for row in evaluation)


def test_evolution_state_snapshot_and_transitions_are_built() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_science.example.toml")
    client = build_llm_client(config.llm)
    doc = Document(doc_id="D1", title="Platform labeling", text="Platform labeling extends warning labels.")
    bundle = resolve_initial_schema(config, [doc], [], client)
    edge = EvolutionEdge(
        edge_id="edge_state",
        source_entity="intervention__warning_labels",
        target_entity="intervention__platform_labeling",
        edge_type="extends",
        source_document="D1",
        target_document="D1",
        time_delta_days=0,
        taxonomy_nodes=["interventions__labeling"],
        confidence=0.7,
        evidence={},
        substring_verified=True,
    )
    node = type("Node", (), {"node_id": "interventions__labeling", "dimension": "interventions", "canonical_label": "Labeling", "support_documents": ["D1"]})()
    state = build_evolution_state_snapshot(
        docs=[doc],
        nodes=[node],
        entities=[],
        edges=[edge],
        taxonomy_events=[{"event_id": "birth__labeling", "event_type": "birth", "target_node_ids": ["interventions__labeling"], "confidence": 0.7}],
        schema_bundle=bundle,
    )
    transitions = build_state_transition_report(
        taxonomy_events=[{"event_id": "birth__labeling", "event_type": "birth", "target_node_ids": ["interventions__labeling"], "confidence": 0.7}],
        schema_revisions=[],
        edge_score_rows=[{"edge_id": "edge_state", "edge_score": 0.5, "temporal_order": 0.8, "source_entity": "a", "target_entity": "b"}],
        relation_rejections=[{"rejection_reason": "weak_co_mention"}],
    )
    assert state["taxonomy"]["node_states"][0]["state"] == "emerging"
    assert any(row["transition_family"] == "negative_relation" for row in transitions)


def test_macro_pattern_detectors_bind_micro_evidence() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_science.example.toml")
    doc = Document(doc_id="D1", title="Platform labeling", text="Platform labeling adapts warning labels to platform governance.")
    node = type(
        "Node",
        (),
        {
            "node_id": "interventions__labeling",
            "dimension": "interventions",
            "canonical_label": "Platform Labeling",
            "support_documents": ["D1"],
        },
    )()
    edge = EvolutionEdge(
        edge_id="edge_adapts",
        source_entity="intervention__warning_labels",
        target_entity="intervention__platform_labeling",
        edge_type="adapts",
        source_document="D1",
        target_document="D1",
        time_delta_days=0,
        taxonomy_nodes=["interventions__labeling"],
        confidence=0.8,
        evidence={"mechanism": {"quote": "adapts warning labels to platform governance"}},
        substring_verified=True,
    )
    patterns = synthesize_macro_patterns(
        docs=[doc],
        nodes=[node],
        taxonomy_events=[
            {
                "event_id": "birth__labeling",
                "event_type": "birth",
                "target_node_ids": ["interventions__labeling"],
                "support_documents": ["D1"],
                "confidence": 0.8,
            }
        ],
        state_snapshot={
            "taxonomy": {
                "node_states": [
                    {
                        "node_id": "interventions__labeling",
                        "state": "stable",
                    }
                ]
            }
        },
        state_transitions=[
            {
                "transition_id": "negative_relation__weak_co_mention",
                "transition_family": "negative_relation",
                "support": 2,
            }
        ],
        trajectory_rows=[
            {
                "trajectory_id": "trajectory__000001",
                "edge_path": ["edge_adapts"],
                "entity_path": ["intervention__warning_labels", "intervention__platform_labeling"],
                "taxonomy_nodes": ["interventions__labeling"],
                "trajectory_score": 0.78,
                "temporal_coherence": 1.0,
                "schema_coherence": 1.0,
                "branching_factor": 1,
            }
        ],
        edges=[edge],
        edge_score_rows=[{"edge_id": "edge_adapts", "edge_score": 0.78}],
        schema_revisions=[
            {
                "candidate_id": "schema__new_context",
                "revision_type": "add_evidence_slot",
                "status": "applied",
                "confidence": 0.7,
            }
        ],
        relation_rejections=[{"rejection_reason": "weak_co_mention"}],
        config=config.macro_patterns,
    )
    profile_by_id = {row["pattern_id"]: row for row in patterns["profiles"]}
    assert "recontextualization" in profile_by_id
    assert "differentiation" in profile_by_id
    assert any("edge_adapts" in row["source_evidence_ids"] for row in patterns["evidence_records"])
    assert profile_by_id["recontextualization"]["representative_trajectories"] == ["trajectory__000001"]
    assert patterns["timeline"]


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


def test_macro_ablation_variants_are_reported() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_misinformation_governance.adaptive.toml")
    output_root = REPO_ROOT / "examples" / "social_macro_ablation_smoke_output"
    summary = run_ablation_suite(config, output_root=output_root, variants=["default", "no_schema_adaptation", "no_negative_evidence"])
    rows = {row["variant"]: row for row in summary["variants"]}
    assert set(rows) == {"default", "no_schema_adaptation", "no_negative_evidence"}
    assert rows["default"]["macro_patterns"] >= 1
    assert rows["no_negative_evidence"]["macro_pattern_evidence"] <= rows["default"]["macro_pattern_evidence"]
    assert rows["no_schema_adaptation"]["schema_revisions"] == 0


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


def test_edge_evidence_quote_must_support_relation_not_only_substring() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_science.example.toml")
    doc = Document(
        doc_id="D1",
        title="Platform labeling",
        text="Platform labeling is widely discussed in civic misinformation governance.",
    )
    edge = EvolutionEdge(
        edge_id="edge_weak_quote",
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
                "description": "Weak mention only.",
                "quote": "Platform labeling is widely discussed in civic misinformation governance.",
            },
        },
        substring_verified=False,
    )

    audit = audit_edge_evidence(edge, {"D1": doc}, config.graph)
    assert audit["status"] == "candidate"
    assert audit["reason"] == "strong_edge_needs_relation_grounding"
    assert audit["verified_quote_count"] == 0
    mechanism_check = next(row for row in audit["quote_checks"] if row["field"] == "mechanism")
    assert mechanism_check["reason"] == "quote_found_but_relation_not_supported"


def test_edge_evidence_trusted_quote_must_ground_both_entities() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_science.example.toml")
    config.graph.quote_relation_grounding_mode = "two_sided_cue"
    doc = Document(
        doc_id="D1",
        title="Big data method",
        text="This method applies to any multi-thematic research area within big data.",
    )
    edge = EvolutionEdge(
        edge_id="edge_one_sided_quote",
        source_entity="method__latent_dirichlet_allocation",
        target_entity="method__big_data",
        edge_type="adapts",
        source_document="D1",
        target_document="D1",
        time_delta_days=0,
        taxonomy_nodes=["methods"],
        confidence=0.9,
        evidence={
            "mechanism": {
                "description": "One-sided mention only.",
                "quote": "This method applies to any multi-thematic research area within big data.",
            },
        },
        substring_verified=False,
    )

    audit = audit_edge_evidence(edge, {"D1": doc}, config.graph)
    assert audit["status"] == "candidate"
    mechanism_check = next(row for row in audit["quote_checks"] if row["field"] == "mechanism")
    assert mechanism_check["entity_token_hits"] == ["target"]
    assert mechanism_check["relation_cue_hit"] is True
    assert mechanism_check["reason"] == "quote_found_but_relation_not_supported"


def test_edge_evidence_one_sided_cue_mode_is_configurable() -> None:
    config = load_config(REPO_ROOT / "configs" / "social_science.example.toml")
    assert config.graph.quote_relation_grounding_mode == "one_sided_cue"
    doc = Document(
        doc_id="D1",
        title="Big data method",
        text="This method applies to any multi-thematic research area within big data.",
    )
    edge = EvolutionEdge(
        edge_id="edge_one_sided_quote",
        source_entity="method__latent_dirichlet_allocation",
        target_entity="method__big_data",
        edge_type="adapts",
        source_document="D1",
        target_document="D1",
        time_delta_days=0,
        taxonomy_nodes=["methods"],
        confidence=0.9,
        evidence={
            "mechanism": {
                "description": "One-sided mention with relation cue.",
                "quote": "This method applies to any multi-thematic research area within big data.",
            },
        },
        substring_verified=False,
    )

    audit = audit_edge_evidence(edge, {"D1": doc}, config.graph)
    assert audit["status"] == "trusted"
    mechanism_check = next(row for row in audit["quote_checks"] if row["field"] == "mechanism")
    assert mechanism_check["entity_token_hits"] == ["target"]
    assert mechanism_check["relation_cue_hit"] is True
    assert mechanism_check["reason"] == "quote_verified_relation_supported"
