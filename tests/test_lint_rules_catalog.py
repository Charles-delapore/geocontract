"""Unit tests for geolint rule definitions (G001-G028)."""

import unittest

from geocontract.lint.rules import RULES, list_rules


class TestLintRuleDefinitions(unittest.TestCase):
    def test_at_least_25_rules_defined(self) -> None:
        self.assertGreaterEqual(len(RULES), 25)
        self.assertEqual(len(list_rules()), 28)

    def test_rules_have_unique_slugs_and_valid_severities(self) -> None:
        slugs = [r.slug for r in list_rules()]
        self.assertEqual(len(slugs), len(set(slugs)))
        for r in list_rules():
            self.assertIn(r.severity, ("error", "warning"))
            self.assertTrue(r.suggested_fix)
            self.assertTrue(r.provenance)


if __name__ == "__main__":
    unittest.main()
