"""Unit tests for MCP JSON-RPC protocol, RevisionGuard, and ReflectionGate."""

import unittest

from geocontract.mcp.protocol import (
    JsonRpcRequest,
    make_protocol_error,
    make_tool_call_request,
    make_tool_result,
)
from geocontract.mcp.revision_guard import ReflectionGate, RevisionGuard


class TestMcpProtocolAndGuards(unittest.TestCase):
    def test_jsonrpc_roundtrip_and_error_semantics(self) -> None:
        req = make_tool_call_request(7, "raster_reproject", {"target_crs": "EPSG:3857", "resampling": "bilinear"})
        parsed = JsonRpcRequest.from_dict(req.to_dict())
        self.assertEqual(parsed.method, "tools/call")
        self.assertEqual(parsed.params["name"], "raster_reproject")

        tool_err = make_tool_result(7, {"error": "CRS mismatch"}, is_error=True)
        self.assertTrue(tool_err.is_tool_error)
        self.assertFalse(tool_err.is_protocol_error)

        proto_err = make_protocol_error(7, -32602, "Invalid params")
        self.assertTrue(proto_err.is_protocol_error)

    def test_revision_guard_stale_write_and_rollback(self) -> None:
        guard = RevisionGuard({"schools": {"crs": "EPSG:4326", "geometry_type": "Point"}})
        cp = guard.create_checkpoint("before-write")
        self.assertEqual(guard.revision, 1)

        guard.bump_revision("schools_proj", {"crs": "EPSG:3857", "geometry_type": "Point"})
        self.assertEqual(guard.revision, 2)

        ok, msg = guard.check_revision(1)
        self.assertFalse(ok)
        self.assertIn("Stale revision", msg)

        guard.rollback(cp.checkpoint_id)
        self.assertEqual(guard.revision, 1)
        self.assertNotIn("schools_proj", guard.layers)

    def test_no_progress_loop_detection(self) -> None:
        guard = RevisionGuard()
        for _ in range(2):
            ok, _ = guard.check_no_progress_loop("vector_buffer", {"distance": 500})
            self.assertTrue(ok)
        ok, msg = guard.check_no_progress_loop("vector_buffer", {"distance": 500})
        self.assertFalse(ok)
        self.assertIn("No-progress loop", msg)

    def test_reflection_gate_sha256_cache(self) -> None:
        gate = ReflectionGate()
        ok, prompts = gate.check_call("raster_reproject", {"target_crs": "EPSG:3857", "resampling": "bilinear"})
        self.assertFalse(ok)
        self.assertEqual(prompts, ["justify_crs_selection", "justify_resampling_method"])

        r1 = gate.store_justification(
            domain="crs_datum",
            intent="Metric slope calculation",
            alternatives=["EPSG:32619", "EPSG:3857"],
            choice="EPSG:3857",
            tradeoffs="Web Mercator conformal; acceptable for local demo",
        )
        self.assertEqual(len(r1.digest), 64)
        gate.store_justification(
            domain="resampling",
            intent="Continuous elevation",
            alternatives=["bilinear", "cubic"],
            choice="bilinear",
            tradeoffs="Smooth interpolation without overshoot",
        )
        ok2, prompts2 = gate.check_call("raster_reproject", {"target_crs": "EPSG:3857", "resampling": "bilinear"})
        self.assertTrue(ok2)
        self.assertEqual(prompts2, [])


if __name__ == "__main__":
    unittest.main()
