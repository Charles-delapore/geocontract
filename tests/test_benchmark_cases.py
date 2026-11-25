"""Unit tests verifying the 160-case Near-Miss benchmark suite structure."""

import unittest

from geocontract.benchmark.cases import build_near_miss_suite


class TestNearMissSuite(unittest.TestCase):
    def test_suite_has_at_least_150_unique_cases(self) -> None:
        suite = build_near_miss_suite()
        self.assertGreaterEqual(len(suite), 150)
        self.assertEqual(len(suite), 160)
        ids = [c.case_id for c in suite]
        self.assertEqual(len(ids), len(set(ids)))

    def test_covers_all_16_categories(self) -> None:
        suite = build_near_miss_suite()
        cats = {c.category for c in suite}
        self.assertEqual(len(cats), 16)
        for required in (
            "degree_meter_buffer",
            "crs_mismatch_sjoin",
            "unclipped_boundary_buffer",
            "euclidean_network_shortcut",
            "unsolvable_reject_task",
            "close_value_directional_fabrication",
        ):
            self.assertIn(required, cats)


if __name__ == "__main__":
    unittest.main()
