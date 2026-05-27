from __future__ import annotations

import argparse
import json
from pathlib import Path

from evotaxa.ablation import DEFAULT_ABLATION_VARIANTS, run_ablation_suite
from evotaxa.config import load_config
from evotaxa.edge_evidence import stratify_edges_by_evidence
from evotaxa.graph import build_edges, extract_entities
from evotaxa.io import iter_jsonl, write_json, write_jsonl
from evotaxa.loaders import attach_node_support, infer_assignments_from_text, load_assignments, load_documents, load_taxonomy_nodes
from evotaxa.llm import build_llm_client
from evotaxa.pipeline import run_full, run_lite
from evotaxa.schema import adapt_schema_after_graph, resolve_initial_schema


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

    ablation_parser = subparsers.add_parser("run-ablation", help="Run configured ablation variants and summarize results.")
    ablation_parser.add_argument("--config", required=True, type=Path)
    ablation_parser.add_argument("--output-root", type=Path)
    ablation_parser.add_argument("--mode", choices=["full", "lite"], default="full")
    ablation_parser.add_argument("--variants", nargs="*", default=list(DEFAULT_ABLATION_VARIANTS))
    ablation_parser.add_argument("--print-summary", action="store_true")

    infer_schema_parser = subparsers.add_parser("infer-schema", help="Resolve fixed/inferred schemas and write schema artifacts.")
    infer_schema_parser.add_argument("--config", required=True, type=Path)
    infer_schema_parser.add_argument("--print-summary", action="store_true")

    adapt_schema_parser = subparsers.add_parser("adapt-schema", help="Adapt schema from an existing run's graph audit artifacts.")
    adapt_schema_parser.add_argument("--config", required=True, type=Path)
    adapt_schema_parser.add_argument("--run-root", type=Path)
    adapt_schema_parser.add_argument("--print-summary", action="store_true")

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

    if args.command == "run-ablation":
        summary = run_ablation_suite(
            args.config,
            output_root=args.output_root,
            variants=args.variants,
            mode=args.mode,
        )
        if args.print_summary:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(f"Wrote EvoTaxa ablation artifacts to {summary['output_root']}")
        return 0

    if args.command == "infer-schema":
        summary = _infer_schema_command(args.config)
        if args.print_summary:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(f"Wrote EvoTaxa schema artifacts to {summary['schema_root']}")
        return 0

    if args.command == "adapt-schema":
        summary = _adapt_schema_command(args.config, args.run_root)
        if args.print_summary:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(f"Wrote EvoTaxa adaptive schema artifacts to {summary['schema_root']}")
        return 0

    raise ValueError(f"Unknown command: {args.command}")


def _infer_schema_command(config_path: Path) -> dict[str, object]:
    config = load_config(config_path)
    docs, _ = load_documents(config)
    current_nodes, _ = load_taxonomy_nodes(config)
    assignments, _ = load_assignments(config)
    if not assignments:
        assignments = infer_assignments_from_text(docs, current_nodes)
    nodes = attach_node_support(docs, current_nodes, assignments)
    client = build_llm_client(config.llm)
    bundle = resolve_initial_schema(config, docs, nodes, client)
    schema_root = Path(config.output.root) / "schema"
    write_json(schema_root / "entity_schema.fixed.json", bundle.fixed_entity_schema)
    write_json(schema_root / "entity_schema.inferred.json", bundle.inferred_entity_schema)
    write_json(schema_root / "entity_schema.final.json", bundle.entity_schema)
    write_json(schema_root / "relation_schema.fixed.json", bundle.fixed_relation_schema)
    write_json(schema_root / "relation_schema.inferred.json", bundle.inferred_relation_schema)
    write_json(schema_root / "relation_schema.final.json", bundle.relation_schema)
    write_json(schema_root / "evidence_schema.fixed.json", bundle.fixed_evidence_schema)
    write_json(schema_root / "evidence_schema.inferred.json", bundle.inferred_evidence_schema)
    write_json(schema_root / "evidence_schema.final.json", bundle.evidence_schema)
    write_jsonl(schema_root / "schema_reports.jsonl", bundle.reports)
    write_jsonl(schema_root / "llm_schema_records.jsonl", (record.to_record() for record in bundle.llm_records))
    return {
        "schema_root": str(schema_root),
        "entity_schema_types": len(bundle.entity_schema),
        "relation_schema_types": len(bundle.relation_schema),
        "evidence_schema_slots": len(bundle.evidence_schema),
        "llm_schema_records": len(bundle.llm_records),
    }


def _adapt_schema_command(config_path: Path, run_root: Path | None) -> dict[str, object]:
    config = load_config(config_path)
    root = Path(run_root or config.output.root)
    docs, _ = load_documents(config)
    current_nodes, _ = load_taxonomy_nodes(config)
    assignments, _ = load_assignments(config)
    if not assignments:
        assignments = infer_assignments_from_text(docs, current_nodes)
    nodes = attach_node_support(docs, current_nodes, assignments)
    client = build_llm_client(config.llm)
    bundle = resolve_initial_schema(config, docs, nodes, client)
    edge_audit_path = root / "graph" / "edge_evidence_audit.jsonl"
    entity_report_path = root / "graph" / "entity_quality_report.jsonl"
    if edge_audit_path.exists():
        edge_audit = list(iter_jsonl(edge_audit_path))
    else:
        entities, mentions = extract_entities(docs, assignments, config.graph)
        edges = build_edges(docs, entities, mentions, config.graph, bundle.relation_schema, bundle.evidence_schema)
        _, _, _, edge_audit = stratify_edges_by_evidence(edges, docs, config.graph)
    entity_report = list(iter_jsonl(entity_report_path)) if entity_report_path.exists() else []
    adapted, revisions = adapt_schema_after_graph(
        bundle,
        edge_evidence_audit=edge_audit,
        entity_quality_report=entity_report,
        config=config,
    )
    schema_root = root / "schema"
    write_json(schema_root / "entity_schema.final.json", adapted.entity_schema)
    write_json(schema_root / "relation_schema.final.json", adapted.relation_schema)
    write_json(schema_root / "evidence_schema.final.json", adapted.evidence_schema)
    write_jsonl(schema_root / "schema_reports.jsonl", adapted.reports)
    write_jsonl(schema_root / "relation_schema.revisions.jsonl", [row for row in revisions if row.get("schema_family") == "relation_schema"])
    write_jsonl(schema_root / "entity_schema.revisions.jsonl", [row for row in revisions if row.get("schema_family") == "entity_schema"])
    write_jsonl(schema_root / "evidence_schema.revisions.jsonl", [row for row in revisions if row.get("schema_family") == "evidence_schema"])
    return {
        "schema_root": str(schema_root),
        "schema_revisions": len(revisions),
        "entity_schema_types": len(adapted.entity_schema),
        "relation_schema_types": len(adapted.relation_schema),
        "evidence_schema_slots": len(adapted.evidence_schema),
    }


if __name__ == "__main__":
    raise SystemExit(main())
