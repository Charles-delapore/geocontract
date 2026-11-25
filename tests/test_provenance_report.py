"""Unit tests for HTML/Markdown audit report and executable replay script generation."""

import ast
import tempfile
import unittest
from pathlib import Path

from geocontract.provenance.dag import LineageDAG
from geocontract.provenance.report import (
    export_audit_bundle,
    render_html_audit,
    render_markdown_audit,
    render_replay_script,
)


class TestProvenanceReport(unittest.TestCase):
    def test_export_audit_bundle_and_valid_replay_script(self) -> None:
        dag = LineageDAG("audit-demo-01", contract_id="tpl-overlay-flood-ratio")
        dag.register_entity("tracts", label="Tracts", role="input", payload_or_path=b"tracts-data", crs="EPSG:4326", geometry_type="Polygon")
        dag.register_entity("flood_out", label="Flood Exposure", role="output", payload_or_path=b"out-data", crs="EPSG:3857", geometry_type="Polygon")
        dag.record_activity(
            "step1",
            activity_type="RepairRound",
            tool="qgis:reprojectlayer",
            parameters={"target_crs": "EPSG:3857"},
            inputs=["tracts"],
            outputs=["flood_out"],
            violations=[{"code": "G002", "message": "area on EPSG:4326"}],
            status="accepted",
            repair_round=1,
        )

        md = render_markdown_audit(dag)
        self.assertIn("GeoContract Audit Evidence Report", md)
        self.assertIn("G002", md)

        html_out = render_html_audit(dag)
        self.assertIn("<!DOCTYPE html>", html_out)
        self.assertIn("W3C PROV-JSON", html_out)

        script = render_replay_script(dag)
        ast.parse(script)  # Must be syntactically valid Python
        ns: dict = {}
        exec(compile(script, "<replay>", "exec"), ns)
        replayed = ns["replay"]()
        self.assertEqual(len(replayed), 1)
        self.assertEqual(replayed[0]["tool"], "qgis:reprojectlayer")

        with tempfile.TemporaryDirectory() as tmp:
            bundle = export_audit_bundle(dag, Path(tmp))
            for key, path in bundle.items():
                self.assertTrue(path.is_file(), f"Missing exported {key}")


if __name__ == "__main__":
    unittest.main()
