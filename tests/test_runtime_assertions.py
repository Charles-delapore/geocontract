"""Unit tests for runtime spatial invariant probes (Shapely/NumPy + pure-Python fallback)."""

import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely.geometry import Polygon

from geocontract.dsl.templates import get_template
from geocontract.runtime.assertions import (
    check_area_conservation,
    check_boundary_clip,
    check_geometry_validity,
    check_numeric_invariants,
    check_resampling_drift,
    check_row_conservation,
    verify_output_contract,
)


class TestRuntimeAssertions(unittest.TestCase):
    def test_geometry_validity_shapely_and_pure_python(self) -> None:
        valid_poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
        bowtie = Polygon([(0, 0), (10, 10), (10, 0), (0, 10), (0, 0)])
        gdf = gpd.GeoDataFrame({"id": [1, 2]}, geometry=[valid_poly, bowtie], crs="EPSG:3857")
        rep = check_geometry_validity(gdf)
        self.assertFalse(rep.passed)
        self.assertEqual(rep.metrics["invalid_count"], 1)

        # Pure-Python GeoJSON fallback
        gj_valid = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}
        gj_bowtie = {"type": "Polygon", "coordinates": [[[0, 0], [10, 10], [10, 0], [0, 10], [0, 0]]]}
        rep_py = check_geometry_validity([gj_valid, gj_bowtie], force_pure_python=True)
        self.assertFalse(rep_py.passed)
        self.assertEqual(rep_py.metrics["invalid_count"], 1)

    def test_area_and_row_conservation(self) -> None:
        p1 = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
        p2 = Polygon([(0, 0), (10, 0), (10, 12), (0, 12), (0, 0)])
        self.assertTrue(check_area_conservation([p1], [p1]).passed)
        self.assertFalse(check_area_conservation([p1], [p2], rel_tol=0.05).passed)

        self.assertTrue(check_row_conservation(10, 10, rule="equal_to_source").passed)
        self.assertFalse(check_row_conservation(10, 7, rule="equal_to_source").passed)

    def test_boundary_clip_both_backends(self) -> None:
        bnd = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
        inside = Polygon([(1, 1), (5, 1), (5, 5), (1, 5), (1, 1)])
        outside = Polygon([(8, 8), (12, 8), (12, 12), (8, 12), (8, 8)])
        self.assertTrue(check_boundary_clip([inside], [bnd]).passed)
        self.assertFalse(check_boundary_clip([inside, outside], [bnd]).passed)

        bnd_gj = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}
        out_gj = {"type": "Polygon", "coordinates": [[[8, 8], [12, 8], [12, 12], [8, 12], [8, 8]]]}
        self.assertFalse(check_boundary_clip([out_gj], [bnd_gj], force_pure_python=True).passed)

    def test_resampling_drift_numpy_and_pure_python(self) -> None:
        arr1 = np.array([[10.0, 12.0, -9999.0], [11.0, 13.0, 14.0]])
        arr2_ok = np.array([[10.1, 12.1, -9999.0], [10.9, 13.0, 13.9]])
        arr2_bad = np.array([[10.0, 12.0, -9999.0], [11.0, 13.0, 50.0]])
        self.assertTrue(check_resampling_drift(arr1, arr2_ok, nodata=-9999.0).passed)
        self.assertFalse(check_resampling_drift(arr1, arr2_bad, nodata=-9999.0).passed)
        self.assertTrue(
            check_resampling_drift([[10, 12, -9999], [11, 13]], [[10.1, 11.9, -9999], [11.0, 13.0]], nodata=-9999, force_pure_python=True).passed
        )

    def test_numeric_invariants_and_output_contract(self) -> None:
        rows_bad = [{"id": "1", "travel_min": -3.5, "ratio": 1.2}]
        rep = check_numeric_invariants(rows_bad, nonnegative_cols=["travel_min"], ratio_cols=["ratio"])
        self.assertFalse(rep.passed)
        self.assertEqual(len(rep.violations), 2)

        tpl = get_template("tpl-buffer-count-points")
        tpl.datasets[0].row_count = 2
        with tempfile.TemporaryDirectory() as tmp:
            out_csv = Path(tmp) / "out.csv"
            out_csv.write_text("source_id,target_count\n1,5\n2,0\n", encoding="utf-8")
            self.assertTrue(verify_output_contract(tpl, out_csv).passed)
            out_csv.write_text("source_id,target_count\n1,-1\n1,2\n", encoding="utf-8")
            bad_rep = verify_output_contract(tpl, out_csv)
            self.assertFalse(bad_rep.passed)
            codes = {v.code for v in bad_rep.violations}
            self.assertIn("RT_DUPLICATE_ID", codes)
            self.assertIn("RT_NUMERIC_BOUNDS", codes)


if __name__ == "__main__":
    unittest.main()
