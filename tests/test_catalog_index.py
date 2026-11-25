"""Unit tests for D2-P5 Spatial Operator Knowledge Graph and millisecond index."""

import time
import unittest

from geocontract.catalog.index import OperatorKnowledgeGraph, get_operator_graph


class TestOperatorKnowledgeGraph(unittest.TestCase):
    def test_catalog_size_and_providers(self) -> None:
        kg = get_operator_graph()
        self.assertGreaterEqual(len(kg), 250)
        self.assertEqual(len(kg), 340)
        counts = kg.summary_counts()
        self.assertEqual(counts["grass"], 272)
        self.assertEqual(counts["gdal"], 42)
        self.assertGreaterEqual(counts["qgis"], 10)

    def test_search_by_name_geometry_crs_and_contract(self) -> None:
        kg = OperatorKnowledgeGraph()
        op = kg.get("gdalwarp")
        self.assertIsNotNone(op)
        assert op is not None
        self.assertEqual(op.crs_constraint, "crs_transforming")

        proj_ops = kg.search(crs_constraint="projected_required", input_geometry="raster", limit=15)
        self.assertGreater(len(proj_ops), 0)
        for item in proj_ops:
            self.assertEqual(item.crs_constraint, "projected_required")
            self.assertIn("raster", item.input_geometry.lower())

        remed = kg.find_remediation_operators("crs_projected_required", geometry_hint="raster")
        remed_ids = {r.id for r in remed}
        self.assertTrue(any("warp" in rid or "reproject" in rid or "proj" in rid for rid in remed_ids))

    def test_millisecond_query_latency(self) -> None:
        kg = get_operator_graph()
        t0 = time.perf_counter()
        for _ in range(100):
            kg.search("buffer slope overlay", crs_constraint="projected_required", limit=10)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        avg_ms = elapsed_ms / 100.0
        self.assertLess(avg_ms, 5.0, f"Average query latency too slow: {avg_ms:.3f} ms")


if __name__ == "__main__":
    unittest.main()
