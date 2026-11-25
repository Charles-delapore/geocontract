"""End-to-end tests for VerifiableMCPProxy covering 12 typical mis-call classes + rollback."""

import unittest

from geocontract.dsl.templates import get_template
from geocontract.mcp.mock_server import MockGeoMCPServer
from geocontract.mcp.protocol import make_tool_call_request
from geocontract.mcp.proxy import VerifiableMCPProxy


class TestMCPProxyBoundedHealing(unittest.TestCase):
    def _proxy(self) -> tuple[MockGeoMCPServer, VerifiableMCPProxy]:
        srv = MockGeoMCPServer()
        return srv, VerifiableMCPProxy(srv, max_rounds=3)

    def test_12_typical_miscalls_intercepted_and_healed_within_3_rounds(self) -> None:
        cases = [
            # 1. Buffer on EPSG:4326 geographic CRS
            ("buffer_geo_crs", make_tool_call_request(1, "vector_buffer", {"input_layer": "schools", "distance": 500}), None, "MCP_BUFFER_GEOGRAPHIC_CRS"),
            # 2. Unclipped buffer under clip_to_boundary contract
            ("unclipped_buffer", make_tool_call_request(2, "vector_buffer", {"input_layer": "tracts", "distance": 200}), get_template("tpl-buffer-clipped-boundary"), "MCP_UNCLIPPED_BUFFER"),
            # 3. raster_reproject missing explicit resampling (ADR-0011) + reflection gate
            ("missing_resampling", make_tool_call_request(3, "raster_reproject", {"input_layer": "dem_4326", "target_crs": "EPSG:32619"}), None, "MCP_MISSING_RESAMPLING"),
            # 4. Continuous raster with nearest resampling
            ("continuous_nearest", make_tool_call_request(4, "raster_reproject", {"input_layer": "dem_4326", "target_crs": "EPSG:32619", "resampling": "nearest"}), None, "MCP_RESAMPLING_MISMATCH"),
            # 5. Categorical raster with bilinear resampling
            ("categorical_bilinear", make_tool_call_request(5, "raster_reproject", {"input_layer": "nlcd_5070", "target_crs": "EPSG:3857", "resampling": "bilinear"}), None, "MCP_RESAMPLING_MISMATCH"),
            # 6. raster_stats without mask_nodata=True
            ("unmasked_nodata", make_tool_call_request(6, "raster_stats", {"input_layer": "dem_4326"}), None, "MCP_UNMASKED_NODATA"),
            # 7. sjoin with misaligned CRS
            ("sjoin_crs_mismatch", make_tool_call_request(7, "qgis_processing_sjoin", {"left_layer": "schools", "right_layer": "tracts", "how": "left", "predicate": "within"}), None, "MCP_SJOIN_CRS_MISMATCH"),
            # 8. sjoin with inverted point-polygon predicate
            ("inverted_predicate", make_tool_call_request(8, "qgis_processing_sjoin", {"left_layer": "schools", "right_layer": "tracts", "how": "left", "predicate": "contains"}), None, "MCP_INVERTED_PREDICATE"),
            # 9. sjoin with how='inner' dropping zero matches
            ("inner_sjoin_zeros", make_tool_call_request(9, "qgis_processing_sjoin", {"left_layer": "tracts", "right_layer": "tracts", "how": "inner", "predicate": "intersects"}), get_template("tpl-sjoin-points-in-polygons"), "MCP_INNER_SJOIN_DROPS_ZEROS"),
            # 10. overlay on invalid geometries
            ("invalid_overlay", make_tool_call_request(10, "qgis_processing_overlay", {"left_layer": "dirty_parcels", "right_layer": "tracts"}), None, "MCP_INVALID_GEOMETRY_OVERLAY"),
            # 11. slope on geographic DEM
            ("slope_geo_dem", make_tool_call_request(11, "qgis_processing_slope", {"input_layer": "dem_4326"}), None, "MCP_SLOPE_GEOGRAPHIC_DEM"),
            # 12. Euclidean shortcut when network_distance_required
            ("network_shortcut", make_tool_call_request(12, "vector_distance", {"left_layer": "schools", "right_layer": "tracts"}), get_template("tpl-net-shortest-path-time"), "MCP_NETWORK_SHORTCUT"),
            # 13. Display-only layer stats -> auto-routed to reject_task
            ("display_only_reject", make_tool_call_request(13, "raster_stats", {"input_layer": "basemap_tiles"}), None, "MCP_DISPLAY_ONLY_REJECT"),
        ]

        for label, req, contract, expected_code in cases:
            with self.subTest(case=label):
                _, proxy = self._proxy()
                res = proxy.execute_with_healing(req, contract=contract)
                self.assertTrue(res.accepted, f"{label} failed to heal: {res.trace}")
                self.assertLessEqual(res.rounds_used, 3)
                self.assertFalse(res.rolled_back)
                all_codes = {d.code for rnd in res.diagnostics_history for d in rnd}
                self.assertIn(expected_code, all_codes, f"{label} missing expected diagnostic {expected_code}")

    def test_stale_revision_healed_and_unrecoverable_call_rolls_back(self) -> None:
        srv, proxy = self._proxy()
        proxy.revision_guard.bump_revision("extra_layer", {"crs": "EPSG:3857"})
        stale_req = make_tool_call_request(20, "vector_buffer", {"input_layer": "tracts", "distance": 100, "revision": 1})
        res = proxy.execute_with_healing(stale_req)
        self.assertTrue(res.accepted)
        self.assertEqual(res.rounds_used, 1)

        # Unrecoverable: arbitrary Python execution + stub repair that refuses to change tool -> rollback after 3 rounds
        bad_req = make_tool_call_request(21, "qgis_exec_python", {"code": "import os"})
        rev_before = proxy.revision_guard.revision
        res_fail = proxy.execute_with_healing(bad_req, repair_fn=lambda r, _d: r, max_rounds=3)
        self.assertFalse(res_fail.accepted)
        self.assertTrue(res_fail.rolled_back)
        self.assertEqual(res_fail.rounds_used, 3)
        self.assertEqual(proxy.revision_guard.revision, rev_before)


if __name__ == "__main__":
    unittest.main()
