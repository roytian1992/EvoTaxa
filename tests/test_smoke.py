from __future__ import annotations

from pathlib import Path

from evotaxa.config import load_config
from evotaxa.pipeline import run_lite


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
    assert manifest["counts"]["documents"] == 3
    assert manifest["counts"]["taxonomy_nodes"] == 4
    assert manifest["counts"]["entities"] >= 3
    assert (Path(manifest["output_root"]) / "hooks" / "social_analysis_hooks.jsonl").exists()

