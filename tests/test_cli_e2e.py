"""End-to-end CLI tests for geocontract and geolint."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from geocontract.cli import main as cli_main


class TestUnifiedCLI(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_main(argv)
        return rc, buf.getvalue()

    def test_compile_validate_templates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_yaml = Path(tmp) / "contract.yaml"
            rc, _ = self._run(["compile", "Count stops within 500m of schools clipped to county", "--output", str(out_yaml)])
            self.assertEqual(rc, 0)
            self.assertTrue(out_yaml.is_file())

            rc2, out2 = self._run(["validate", str(out_yaml)])
            self.assertEqual(rc2, 0)
            self.assertIn("VALID:", out2)

        rc3, out3 = self._run(["templates"])
        self.assertEqual(rc3, 0)
        self.assertEqual(len([l for l in out3.splitlines() if l.strip()]), 36)

    def test_catalog_search_lint_eval_and_benchmark(self) -> None:
        rc, out = self._run(["catalog-search", "gdalwarp", "--limit", "3"])
        self.assertEqual(rc, 0)
        hits = json.loads(out)
        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0]["name"], "gdalwarp")

        rc2, out2 = self._run(["lint-eval"])
        self.assertEqual(rc2, 0)
        m = json.loads(out2)
        self.assertGreaterEqual(m["recall"], 0.90)
        self.assertLess(m["false_positive_rate"], 0.05)

        rc3, out3 = self._run(["benchmark", "--format", "json"])
        self.assertEqual(rc3, 0)
        b = json.loads(out3)
        self.assertEqual(b["total_cases"], 160)
        self.assertEqual(b["geocontract_verified_repair_count"], 160)


if __name__ == "__main__":
    unittest.main()
