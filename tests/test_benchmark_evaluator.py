"""Unit tests for automated Near-Miss comparative benchmark evaluator."""

import unittest

from geocontract.benchmark.evaluator import (
    evaluate_near_miss_benchmark,
    render_benchmark_markdown,
)


class TestNearMissEvaluator(unittest.TestCase):
    def test_full_160_case_comparative_evaluation(self) -> None:
        res = evaluate_near_miss_benchmark()
        self.assertEqual(res["total_cases"], 160)
        self.assertEqual(res["bare_pass_count"], 0)
        self.assertGreaterEqual(res["geocontract_intercept_rate"], 0.95)
        self.assertGreaterEqual(res["geocontract_verified_repair_rate"], 0.95)

        md = render_benchmark_markdown(res)
        self.assertIn("GeoContract Near-Miss Adversarial Benchmark Results", md)
        self.assertIn("unsolvable_reject_task", md)


if __name__ == "__main__":
    unittest.main()
