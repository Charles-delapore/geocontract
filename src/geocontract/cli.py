"""Unified CLI for GeoContract (D2-P1 through D2-P7)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from geocontract._version import __version__
from geocontract.benchmark.evaluator import evaluate_near_miss_benchmark, render_benchmark_markdown
from geocontract.catalog.index import get_operator_graph
from geocontract.dsl.compiler import compile_intent_to_contract
from geocontract.dsl.schema import load_contract
from geocontract.dsl.templates import list_templates
from geocontract.lint.eval_corpus import evaluate_geolint_corpus
from geocontract.lint.sarif import main as geolint_main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="geocontract",
        description="GeoContract: Spatial Contracts & Verifiable Geospatial Agent Middleware.",
    )
    parser.add_argument("--version", action="version", version=f"geocontract {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    # compile
    p_comp = sub.add_parser("compile", help="Compile a natural-language spatial query to a GeoContract skeleton.")
    p_comp.add_argument("query", help="Natural-language geospatial query.")
    p_comp.add_argument("--format", choices=("yaml", "json"), default="yaml")
    p_comp.add_argument("--output", default=None)

    # validate
    p_val = sub.add_parser("validate", help="Strictly validate a JSON/YAML GeoContract file.")
    p_val.add_argument("contract_file", help="Path to JSON or YAML contract.")

    # templates
    p_tpl = sub.add_parser("templates", help="List built-in standard spatial contract templates.")
    p_tpl.add_argument("--family", default=None)

    # lint (delegates to geolint)
    p_lint = sub.add_parser("lint", help="Run geolint static AST spatial anti-pattern linter.")
    p_lint.add_argument("paths", nargs="+")
    p_lint.add_argument("--contract", default=None)
    p_lint.add_argument("--format", choices=("text", "json", "sarif"), default="text")
    p_lint.add_argument("--output", default=None)

    # lint-eval
    sub.add_parser("lint-eval", help="Evaluate geolint recall and false-positive rate on the 60-sample corpus.")

    # catalog-search
    p_cat = sub.add_parser("catalog-search", help="Search the local 340-operator spatial knowledge graph.")
    p_cat.add_argument("query", nargs="?", default=None)
    p_cat.add_argument("--provider", default=None)
    p_cat.add_argument("--crs", default=None)
    p_cat.add_argument("--input-geometry", default=None)
    p_cat.add_argument("--limit", type=int, default=10)

    # benchmark
    p_bench = sub.add_parser("benchmark", help="Run the 160-case adversarial Near-Miss comparative benchmark.")
    p_bench.add_argument("--format", choices=("json", "markdown"), default="markdown")
    p_bench.add_argument("--output", default=None)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "compile":
        c = compile_intent_to_contract(args.query)
        rendered = c.to_json() if args.format == "json" else c.to_yaml()
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        else:
            print(rendered)
        return 0

    if args.command == "validate":
        c = load_contract(args.contract_file)
        print(f"VALID: {c.contract_id} (family={c.family}, constraints={len(c.constraints)})")
        return 0

    if args.command == "templates":
        tpls = list_templates(family=args.family)
        for t in tpls:
            print(f"{t.contract_id}\t{t.family}\t{len(t.constraints)} constraints\t{t.query}")
        return 0

    if args.command == "lint":
        l_argv = list(args.paths) + ["--format", args.format]
        if args.contract:
            l_argv += ["--contract", args.contract]
        if args.output:
            l_argv += ["--output", args.output]
        return geolint_main(l_argv)

    if args.command == "lint-eval":
        metrics = evaluate_geolint_corpus()
        summary = {k: v for k, v in metrics.items() if k != "details"}
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    if args.command == "catalog-search":
        kg = get_operator_graph()
        hits = kg.search(
            args.query,
            provider=args.provider,
            crs_constraint=args.crs,
            input_geometry=args.input_geometry,
            limit=args.limit,
        )
        print(json.dumps([h.to_dict() for h in hits], indent=2, ensure_ascii=False))
        return 0

    if args.command == "benchmark":
        res = evaluate_near_miss_benchmark()
        rendered = json.dumps(res, indent=2, ensure_ascii=False) if args.format == "json" else render_benchmark_markdown(res)
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        else:
            print(rendered)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
