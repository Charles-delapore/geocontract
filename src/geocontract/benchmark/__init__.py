"""Adversarial Geographic Near-Miss Benchmark Suite & Evaluation Framework (D2-P7)."""

from geocontract.benchmark.cases import NearMissCase, build_near_miss_suite
from geocontract.benchmark.evaluator import (
    CaseEvalOutcome,
    evaluate_near_miss_benchmark,
    render_benchmark_markdown,
)

__all__ = [
    "CaseEvalOutcome",
    "NearMissCase",
    "build_near_miss_suite",
    "evaluate_near_miss_benchmark",
    "render_benchmark_markdown",
]
