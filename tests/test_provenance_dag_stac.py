"""Unit tests for W3C PROV-JSON lineage DAG and STAC Processing v1.2.0 export."""

import tempfile
import unittest
from pathlib import Path

from geocontract.provenance.dag import LineageDAG, compute_sha256
from geocontract.provenance.stac import STAC_PROCESSING_EXT_URL, export_stac_item


class TestProvenanceDAGAndSTAC(unittest.TestCase):
    def test_prov_json_and_sha256_fingerprinting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "schools.geojson"
            inp.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
            dag = LineageDAG("run-001", contract_id="tpl-buffer-count-points")
            e_in = dag.register_entity(
                "schools",
                label="Boston Schools",
                role="input",
                payload_or_path=inp,
                crs="EPSG:4326",
                geometry_type="Point",
            )
            self.assertEqual(len(e_in.sha256), 64)
            self.assertEqual(e_in.sha256, compute_sha256(inp))

            dag.register_entity(
                "schools_buf",
                label="Projected 500m Buffers",
                role="output",
                payload_or_path=b"mock-output-bytes",
                crs="EPSG:26986",
                geometry_type="Polygon",
            )
            dag.record_activity(
                "repair_r1",
                activity_type="RepairRound",
                tool="vector_reproject+vector_buffer",
                parameters={"target_crs": "EPSG:26986", "distance": 500},
                inputs=["schools"],
                outputs=["schools_buf"],
                violations=[{"code": "MCP_BUFFER_GEOGRAPHIC_CRS", "message": "EPSG:4326 buffer"}],
                status="accepted",
                repair_round=1,
            )

            prov = dag.to_prov_json()
            self.assertIn("entity", prov)
            self.assertIn("activity", prov)
            self.assertIn("agent", prov)
            self.assertIn("wasDerivedFrom", prov)
            self.assertEqual(prov["wasDerivedFrom"]["_:d1"]["prov:type"], "prov:Revision")

            stac = export_stac_item(dag)
            self.assertIn(STAC_PROCESSING_EXT_URL, stac["stac_extensions"])
            self.assertEqual(stac["properties"]["processing:level"], "L2")
            self.assertIn("vector_reproject+vector_buffer", stac["properties"]["processing:software"])
            self.assertEqual(stac["links"][0]["rel"], "derived_from")
            self.assertEqual(len(stac["process"][0]["tasks"]), 1)


if __name__ == "__main__":
    unittest.main()
