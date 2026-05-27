from __future__ import annotations

import argparse
import json
from pathlib import Path

from evotaxa.config import load_config
from evotaxa.pipeline import run_full, run_lite


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evotaxa", description="Config-driven taxonomy-guided evolution modeling.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate-config", help="Load and validate a TOML/JSON config.")
    validate_parser.add_argument("--config", required=True, type=Path)

    run_parser = subparsers.add_parser("run-lite", help="Run deterministic taxonomy + MEG-lite pipeline.")
    run_parser.add_argument("--config", required=True, type=Path)
    run_parser.add_argument("--print-manifest", action="store_true")

    full_parser = subparsers.add_parser("run-full", help="Run taxonomy induction, expansion, graph feedback, and scoring pipeline.")
    full_parser.add_argument("--config", required=True, type=Path)
    full_parser.add_argument("--print-manifest", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "validate-config":
        config = load_config(args.config)
        print(
            json.dumps(
                {
                    "config_path": str(config.path),
                    "project": config.project.__dict__,
                    "corpus_path": str(config.corpus.path) if config.corpus.path else None,
                    "taxonomy_nodes_path": str(config.taxonomy.nodes_path) if config.taxonomy.nodes_path else None,
                    "output_root": str(config.output.root),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "run-lite":
        manifest = run_lite(args.config)
        if args.print_manifest:
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
        else:
            print(f"Wrote EvoTaxa artifacts to {manifest['output_root']}")
        return 0

    if args.command == "run-full":
        manifest = run_full(args.config)
        if args.print_manifest:
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
        else:
            print(f"Wrote EvoTaxa full artifacts to {manifest['output_root']}")
        return 0

    raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
