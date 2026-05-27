from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from evotaxa.config import EvoTaxaConfig, load_config
from evotaxa.io import write_json, write_jsonl
from evotaxa.pipeline import run_full, run_lite


DEFAULT_ABLATION_VARIANTS = ["default", "no_coevolution", "no_expansion", "no_edge_judge", "no_llm"]


def run_ablation_suite(
    config_or_path: EvoTaxaConfig | str | Path,
    *,
    output_root: str | Path | None = None,
    variants: list[str] | None = None,
    mode: str = "full",
) -> dict[str, Any]:
    base_config = load_config(config_or_path) if not isinstance(config_or_path, EvoTaxaConfig) else config_or_path
    selected_variants = variants or list(DEFAULT_ABLATION_VARIANTS)
    suite_root = Path(output_root).expanduser().resolve() if output_root else _default_ablation_root(base_config)
    suite_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    manifests: dict[str, dict[str, Any]] = {}
    for variant in selected_variants:
        run_config = _variant_config(base_config, variant, suite_root)
        manifest = run_full(run_config) if mode == "full" else run_lite(run_config)
        manifests[variant] = manifest
        rows.append(_summary_row(variant, manifest))

    summary = {
        "config_path": str(base_config.path),
        "mode": mode,
        "output_root": str(suite_root),
        "variants": rows,
        "best_variant_by_quality": _best_variant(rows, "quality_score"),
        "best_variant_by_trusted_edges": _best_variant(rows, "trusted_edges"),
    }
    write_jsonl(suite_root / "ablation_summary.jsonl", rows)
    write_json(suite_root / "ablation_summary.json", summary)
    write_json(suite_root / "ablation_manifests.json", manifests)
    return summary


def _variant_config(base_config: EvoTaxaConfig, variant: str, suite_root: Path) -> EvoTaxaConfig:
    config = deepcopy(base_config)
    config.project.run_id = f"{base_config.project.run_id}__{variant}"
    config.output.root = suite_root / variant
    if variant == "default":
        return config
    if variant == "no_coevolution":
        config.taxonomy.coevolution_enabled = False
        config.taxonomy.max_coevolution_iterations = 0
        return config
    if variant == "no_expansion":
        config.taxonomy.expansion_enabled = False
        config.taxonomy.coevolution_enabled = False
        config.taxonomy.max_coevolution_iterations = 0
        return config
    if variant == "no_edge_judge":
        config.graph.llm_edge_judge_limit = 0
        config.llm.enabled_tasks = [task for task in config.llm.enabled_tasks if task not in {"edge_evidence_judge", "*"}]
        return config
    if variant == "no_llm":
        config.llm.enabled_tasks = []
        config.llm.provider = "deterministic"
        return config
    raise ValueError(f"Unknown ablation variant: {variant}")


def _summary_row(variant: str, manifest: dict[str, Any]) -> dict[str, Any]:
    counts = manifest.get("counts") or {}
    return {
        "variant": variant,
        "output_root": manifest.get("output_root"),
        "quality_score": counts.get("quality_score", 0.0),
        "taxonomy_nodes": counts.get("taxonomy_nodes", 0),
        "entities": counts.get("entities", 0),
        "trusted_edges": counts.get("trusted_edges", 0),
        "candidate_edges": counts.get("candidate_edges", 0),
        "unverified_edges": counts.get("unverified_edges", 0),
        "forecast_hooks": counts.get("forecast_hooks", 0),
        "applied_expansions": counts.get("applied_expansions", 0),
        "applied_revisions": counts.get("applied_revisions", 0),
        "coevolution_iterations": counts.get("coevolution_iterations", 0),
        "llm_judge_records": counts.get("llm_judge_records", 0),
    }


def _best_variant(rows: list[dict[str, Any]], key: str) -> str:
    if not rows:
        return ""
    return str(max(rows, key=lambda row: float(row.get(key) or 0.0)).get("variant") or "")


def _default_ablation_root(config: EvoTaxaConfig) -> Path:
    base = Path(config.output.root)
    return base.parent / f"{base.name}_ablations"
