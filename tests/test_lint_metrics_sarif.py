"""Tests for geolint SARIF 2.1.0 output, CLI execution, and Recall >= 90% / FPR < 5%."""

import json
import tempfile
import unittest
from pathlib import Path

from geocontract.lint.analyzer import lint_code
from geocontract.lint.eval_corpus import evaluate_geolint_corpus
from geocontract.lint.sarif import findings_to_sarif, main as geolint_main


class TestGeoLintSarifAndMetrics(unittest.TestCase):
    def test_recall_and_fpr_meet_thresholds(self) -> None:
        metrics = evaluate_geolint_corpus()
        self.assertGreaterEqual(metrics["recall"], 0.90, f"Recall too low: {metrics}")
        self.assertLess(metrics["false_positive_rate"], 0.05, f"FPR too high: {metrics}")

    def test_sarif_2_1_0_structure(self) -> None:
        findings = lint_code('import geopandas as gpd\ng = gpd.read_file("a.geojson")\nb = g.geometry.buffer(500)\n', file_path="demo.py")
        sarif = findings_to_sarif(findings)
        self.assertEqual(sarif["version"], "2.1.0")
        self.assertEqual(len(sarif["runs"]), 1)
        run = sarif["runs"][0]
        self.assertEqual(run["tool"]["driver"]["name"], "geolint")
        self.assertGreaterEqual(len(run["results"]), 1)
        self.assertEqual(run["results"][0]["ruleId"], "G001")

    def test_cli_sarif_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            py_path = Path(tmp) / "bad_geo.py"
            out_sarif = Path(tmp) / "report.sarif.json"
            py_path.write_text('import geopandas as gpd\ng = gpd.read_file("a.geojson")\nb = g.geometry.buffer(100)\n', encoding="utf-8")
            rc = geolint_main([str(py_path), "--format", "sarif", "--output", str(out_sarif)])
            self.assertEqual(rc, 1)
            parsed = json.loads(out_sarif.read_text(encoding="utf-8"))
            self.assertEqual(parsed["version"], "2.1.0")
            self.assertEqual(parsed["runs"][0]["results"][0]["ruleId"], "G001")


if __name__ == "__main__":
    unittest.main()
