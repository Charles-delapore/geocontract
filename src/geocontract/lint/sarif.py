"""SARIF 2.1.0 formatter and CLI entrypoint for ``geolint`` (D2-P2)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from geocontract._version import __version__
from geocontract.dsl.schema import GeoContract, load_contract
from geocontract.lint.analyzer import lint_file
from geocontract.lint.rules import RULES, LintFinding

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"


def findings_to_sarif(findings: Sequence[LintFinding]) -> dict[str, Any]:
    """Convert geolint findings into a valid SARIF 2.1.0 log object."""
    used_rules = sorted({f.rule_id for f in findings})
    rules_payload = []
    for rid in used_rules:
        r = RULES[rid]
        rules_payload.append(
            {
                "id": r.rule_id,
                "name": r.slug,
                "shortDescription": {"text": r.title},
                "fullDescription": {"text": r.description},
                "help": {"text": r.suggested_fix},
                "defaultConfiguration": {
                    "level": "error" if r.severity == "error" else "warning"
                },
                "properties": {"category": r.category, "provenance": r.provenance},
            }
        )

    results_payload = []
    for f in findings:
        results_payload.append(
            {
                "ruleId": f.rule_id,
                "level": "error" if f.severity == "error" else "warning",
                "message": {"text": f"{f.message} Fix: {f.suggested_fix}"},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": f.file_path},
                            "region": {
                                "startLine": max(1, f.line),
                                "startColumn": max(1, f.col + 1),
                            },
                        }
                    }
                ],
            }
        )

    return {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "geolint",
                        "version": __version__,
                        "informationUri": "https://github.com/Charles-delapore/geocontract",
                        "rules": rules_payload,
                    }
                },
                "results": results_payload,
            }
        ],
    }


def format_findings_text(findings: Sequence[LintFinding]) -> str:
    if not findings:
        return "geolint: 0 issues found."
    lines = []
    for f in findings:
        lines.append(
            f"{f.file_path}:{f.line}:{f.col + 1}: {f.severity.upper()} [{f.rule_id}/{f.slug}] {f.message}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="geolint",
        description="Static AST spatial anti-pattern linter (GeoContract D2-P2).",
    )
    parser.add_argument("paths", nargs="+", help="Python files or directories to lint.")
    parser.add_argument(
        "--contract",
        default=None,
        help="Optional GeoContract JSON/YAML file for contract-aware checks.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json", "sarif"),
        default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write formatted report to file instead of stdout.",
    )
    args = parser.parse_args(argv)

    contract: GeoContract | None = load_contract(args.contract) if args.contract else None
    py_files: list[Path] = []
    for raw_p in args.paths:
        p = Path(raw_p)
        if p.is_dir():
            py_files.extend(sorted(p.rglob("*.py")))
        elif p.is_file():
            py_files.append(p)
        else:
            print(f"geolint: path not found: {raw_p}", file=sys.stderr)
            return 2

    all_findings: list[LintFinding] = []
    for fpath in py_files:
        all_findings.extend(lint_file(fpath, contract=contract))

    if args.format == "sarif":
        rendered = json.dumps(findings_to_sarif(all_findings), ensure_ascii=False, indent=2)
    elif args.format == "json":
        rendered = json.dumps([f.to_dict() for f in all_findings], ensure_ascii=False, indent=2)
    else:
        rendered = format_findings_text(all_findings)

    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)

    return 1 if any(f.severity == "error" for f in all_findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
