"""Unit tests for the 36 standard GeoContract templates across 9 families."""

import unittest

from geocontract.dsl.schema import VALID_FAMILIES, validate_contract_dict
from geocontract.dsl.templates import get_template, list_templates, template_counts_by_family


class TestContractTemplates(unittest.TestCase):
    def test_template_count_and_family_coverage(self) -> None:
        all_tpls = list_templates()
        self.assertGreaterEqual(len(all_tpls), 30)
        self.assertEqual(len(all_tpls), 36)

        counts = template_counts_by_family()
        for fam in VALID_FAMILIES:
            self.assertEqual(counts[fam], 4, f"Expected 4 templates in {fam}")

    def test_every_template_passes_strict_validation(self) -> None:
        for tpl in list_templates():
            self.assertEqual(validate_contract_dict(tpl.to_dict()), [])

    def test_required_guards_present_in_library(self) -> None:
        all_constraints = {c.name for t in list_templates() for c in t.constraints}
        for required in (
            "crs_projected_required",
            "clip_to_boundary",
            "network_distance_required",
            "reject_task",
            "one_output_row_per_source",
            "conservation_of_area",
            "conservation_of_rows",
            "nodata_mask_required",
            "operation_order_enforced",
        ):
            self.assertIn(required, all_constraints)

    def test_get_template_returns_isolated_copy(self) -> None:
        t1 = get_template("tpl-buffer-count-points")
        t1.query = "mutated"
        t2 = get_template("tpl-buffer-count-points")
        self.assertNotEqual(t2.query, "mutated")


if __name__ == "__main__":
    unittest.main()
