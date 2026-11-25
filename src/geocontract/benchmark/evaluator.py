"""Automated comparative benchmark harness: Bare Execution vs. GeoContract Guarded Repair (D2-P7)."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Sequence

from geocontract.benchmark.cases import NearMissCase, build_near_miss_suite
from geocontract.dsl.templates import get_template
from geocontract.lint.analyzer import lint_code
from geocontract.runtime.guards import (
    check_close_value_comparison,
    evaluate_reject_task,
    verify_bidirectional_refusal,
    verify_semantic_contract,
)


@dataclass
class CaseEvalOutcome:
    case_id: str
    category: str
    difficulty: str
    bare_correct: bool
    geocontract_intercepted: bool
    geocontract_repaired_verified: bool
    detected_guards: list[str] = field(default_factory=list)


def evaluate_near_miss_benchmark(cases: Sequence[NearMissCase] | None = None) -> dict[str, Any]:
    """Run all Near-Miss cases comparing bare execution against GeoContract intercept + repair."""
    suite = list(cases) if cases is not None else build_near_miss_suite()
    t0 = time.perf_counter()

    outcomes: list[CaseEvalOutcome] = []
    by_cat: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "bare_ok": 0, "intercepted": 0, "repaired_ok": 0})
    by_diff: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "bare_ok": 0, "intercepted": 0, "repaired_ok": 0})

    for case in suite:
        contract = get_template(case.template_id) if case.template_id else None

        if case.kind == "static_code":
            # Bare execution runs without GeoContract -> silently produces geographically flawed result
            bare_findings = lint_code(case.bare_code, file_path=f"{case.case_id}_bare.py", contract=contract)
            bare_sem_ok = True if contract is None else verify_semantic_contract(case.bare_code, contract).passed
            found_ids = [f.rule_id for f in bare_findings]
            if not bare_sem_ok:
                found_ids.append("VT_MISSING_REQUIRED_OP")

            bare_correct = (len(bare_findings) == 0) and bare_sem_ok
            intercepted = case.expected_guard in found_ids

            # Repaired candidate verified by Vs + Vt
            rep_findings = lint_code(case.repaired_code, file_path=f"{case.case_id}_repaired.py", contract=contract)
            rep_sem_ok = True if contract is None else verify_semantic_contract(case.repaired_code, contract).passed
            repaired_ok = intercepted and (len(rep_findings) == 0) and rep_sem_ok
            detected = sorted(set(found_ids))

        elif case.kind == "runtime_reject":
            p = case.runtime_payload
            decision = evaluate_reject_task(
                requested_entities=p["requested_entities"],
                available_entities=p["available_entities"],
                requested_indicators=p["requested_indicators"],
                available_indicators=p["available_indicators"],
                target_layers=p["target_layers"],
                metric_op_requested=True,
            )
            bare_rep = verify_bidirectional_refusal(decision, agent_rejected=bool(p["bare_rejected"]))
            bare_correct = bare_rep.passed
            intercepted = not bare_rep.passed
            # GeoContract repairs by aligning rejection decision with verified data availability
            repaired_rep = verify_bidirectional_refusal(decision, agent_rejected=decision.should_reject)
            repaired_ok = intercepted and repaired_rep.passed
            detected = [v.code for v in bare_rep.violations]

        elif case.kind == "runtime_close_value":
            p = case.runtime_payload
            bare_rep = check_close_value_comparison(
                p["value_a"], p["value_b"], claimed_relation=p["bare_claim"], epsilon=p["epsilon"]
            )
            bare_correct = bare_rep.passed
            intercepted = not bare_rep.passed
            repaired_rep = check_close_value_comparison(
                p["value_a"], p["value_b"], claimed_relation=p["repaired_claim"], epsilon=p["epsilon"]
            )
            repaired_ok = intercepted and repaired_rep.passed
            detected = [v.code for v in bare_rep.violations]
        else:
            raise ValueError(f"Unsupported case kind: {case.kind}")

        outcomes.append(
            CaseEvalOutcome(
                case_id=case.case_id,
                category=case.category,
                difficulty=case.difficulty,
                bare_correct=bare_correct,
                geocontract_intercepted=intercepted,
                geocontract_repaired_verified=repaired_ok,
                detected_guards=detected,
            )
        )
        for bucket in (by_cat[case.category], by_diff[case.difficulty]):
            bucket["total"] += 1
            bucket["bare_ok"] += int(bare_correct)
            bucket["intercepted"] += int(intercepted)
            bucket["repaired_ok"] += int(repaired_ok)

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    total = len(outcomes)
    bare_ok = sum(o.bare_correct for o in outcomes)
    intercepted_n = sum(o.geocontract_intercepted for o in outcomes)
    repaired_n = sum(o.geocontract_repaired_verified for o in outcomes)

    return {
        "total_cases": total,
        "bare_pass_count": bare_ok,
        "bare_pass_rate": round(bare_ok / total, 4) if total else 0.0,
        "geocontract_intercept_count": intercepted_n,
        "geocontract_intercept_rate": round(intercepted_n / total, 4) if total else 0.0,
        "geocontract_verified_repair_count": repaired_n,
        "geocontract_verified_repair_rate": round(repaired_n / total, 4) if total else 0.0,
        "elapsed_ms": elapsed_ms,
        "by_category": dict(sorted(by_cat.items())),
        "by_difficulty": dict(sorted(by_diff.items())),
    }


def render_benchmark_markdown(summary: dict[str, Any]) -> str:
    """Format comparative benchmark summary as a Markdown report."""
    lines = [
        "# GeoContract Near-Miss Adversarial Benchmark Results",
        "",
        f"- **Total Cases**: {summary['total_cases']}",
        f"- **Bare Execution Correctness**: {summary['bare_pass_count']}/{summary['total_cases']} ({summary['bare_pass_rate']:.1%})",
        f"- **GeoContract Interception Rate**: {summary['geocontract_intercept_count']}/{summary['total_cases']} ({summary['geocontract_intercept_rate']:.1%})",
        f"- **GeoContract Verified Repair Rate**: {summary['geocontract_verified_repair_count']}/{summary['total_cases']} ({summary['geocontract_verified_repair_rate']:.1%})",
        f"- **Elapsed**: {summary['elapsed_ms']} ms",
        "",
        "| Category | Total | Bare OK | Intercepted | Repaired & Verified |",
        "|---|---:|---:|---:|---:|",
    ]
    for cat, stats in summary["by_category"].items():
        lines.append(
            f"| `{cat}` | {stats['total']} | {stats['bare_ok']} | {stats['intercepted']} | {stats['repaired_ok']} |"
        )
    lines.append("")
    return "\n".join(lines)
