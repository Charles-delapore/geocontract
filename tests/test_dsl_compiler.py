"""Unit tests for the NL intent -> GeoContract skeleton compiler."""

import unittest

from geocontract.dsl.compiler import compile_intent_to_contract
from geocontract.dsl.schema import validate_contract_dict


class TestIntentCompiler(unittest.TestCase):
    def test_compile_buffer_clipped_query(self) -> None:
        c = compile_intent_to_contract(
            "Count bus stops within 500m buffer of schools clipped to county boundary in EPSG:26986"
        )
        self.assertEqual(c.family, "buffer_counting")
        self.assertTrue(c.has_constraint("crs_projected_required"))
        self.assertTrue(c.has_constraint("clip_to_boundary"))
        self.assertEqual(c.output.expected_crs, "EPSG:26986")
        self.assertEqual(c.metadata["extracted_distance_meters"], 500.0)
        self.assertEqual(validate_contract_dict(c.to_dict()), [])

    def test_compile_network_accessibility_chinese(self) -> None:
        c = compile_intent_to_contract("计算每个社区到最近医院的15分钟路网通行时间并保留零匹配")
        self.assertEqual(c.family, "network_accessibility")
        self.assertTrue(c.has_constraint("network_distance_required"))
        self.assertTrue(c.has_constraint("travel_time_unit_minutes"))
        self.assertTrue(c.has_constraint("one_output_row_per_source"))
        self.assertEqual(c.metadata["extracted_time_minutes"], 15.0)

    def test_compile_raster_slope_order(self) -> None:
        c = compile_intent_to_contract("Resample DEM to 10m and compute slope")
        self.assertEqual(c.family, "raster_sampling")
        self.assertTrue(c.has_constraint("operation_order_enforced"))
        self.assertTrue(c.has_constraint("crs_projected_required"))

    def test_compile_compare_and_reject(self) -> None:
        c = compile_intent_to_contract(
            "Compare zonal mean NDVI between Murcia and non-existent town; reject if missing."
        )
        self.assertTrue(c.has_constraint("close_value_epsilon_guard"))
        self.assertTrue(c.has_constraint("reject_task"))

    def test_empty_query_raises(self) -> None:
        with self.assertRaises(ValueError):
            compile_intent_to_contract("   ")


if __name__ == "__main__":
    unittest.main()
