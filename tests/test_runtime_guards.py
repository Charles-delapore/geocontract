"""Unit tests for reject_task guard, close-value epsilon guard, and semantic verifier Vt."""

import unittest

from geocontract.dsl.templates import get_template
from geocontract.runtime.guards import (
    check_close_value_comparison,
    evaluate_reject_task,
    verify_bidirectional_refusal,
    verify_semantic_contract,
)


class TestRuntimeGuards(unittest.TestCase):
    def test_reject_task_unsolvable_and_bidirectional_check(self) -> None:
        # Unsolvable: non-existent municipality + display-only layer
        dec = evaluate_reject_task(
            requested_entities=["Atlantis"],
            available_entities=["Murcia", "Cordoba"],
            target_layers=[{"name": "basemap", "display_only": True, "crs": "EPSG:3857"}],
        )
        self.assertTrue(dec.should_reject)
        self.assertEqual(dec.missing_entities, ["Atlantis"])
        self.assertEqual(dec.display_only_targets, ["basemap"])

        # Answering an unsolvable task fails; rejecting it passes
        self.assertFalse(verify_bidirectional_refusal(dec, agent_rejected=False).passed)
        self.assertTrue(verify_bidirectional_refusal(dec, agent_rejected=True).passed)

        # Solvable task: refusing it fails (Axis Spatial D02/D03)
        dec_ok = evaluate_reject_task(
            requested_entities=["Murcia"],
            available_entities=["Murcia", "Cordoba"],
            requested_indicators=["green_pct"],
            available_indicators=["green_pct"],
            target_layers=[{"name": "green_cover", "display_only": False, "crs": "EPSG:3035"}],
            metric_op_requested=True,
        )
        self.assertFalse(dec_ok.should_reject)
        self.assertFalse(verify_bidirectional_refusal(dec_ok, agent_rejected=True).passed)
        self.assertTrue(verify_bidirectional_refusal(dec_ok, agent_rejected=False).passed)

    def test_close_value_epsilon_guard_murcia_cordoba(self) -> None:
        # GeoNatureAgent C01: 68.5% vs 68.4% (diff 0.1pp <= 0.5pp)
        self.assertFalse(
            check_close_value_comparison(68.5, 68.4, claimed_relation="higher", epsilon=0.5).passed
        )
        self.assertTrue(
            check_close_value_comparison(68.5, 68.4, claimed_relation="effectively_equal", epsilon=0.5).passed
        )
        self.assertTrue(
            check_close_value_comparison(75.0, 68.4, claimed_relation="higher", epsilon=0.5).passed
        )

    def test_semantic_verifier_vt_by_family(self) -> None:
        c_buf = get_template("tpl-buffer-count-points")
        fake_buf = "df = sources.copy()\ndf['target_count'] = 0\ndf.to_csv('out.csv')\n"
        self.assertFalse(verify_semantic_contract(fake_buf, c_buf).passed)

        real_buf = "b = sources.to_crs('EPSG:3857').buffer(500)\nc = gpd.sjoin(b, targets).groupby('source_id').size()\n"
        self.assertTrue(verify_semantic_contract(real_buf, c_buf).passed)

        c_net = get_template("tpl-net-shortest-path-time")
        bad_net = "d = origins.distance(hospitals)\n"
        self.assertFalse(verify_semantic_contract(bad_net, c_net).passed)
        good_net = "u = nearest_nodes(G, x, y)\nd = shortest_path_length(G, u, v, weight='length')\n"
        self.assertTrue(verify_semantic_contract(good_net, c_net).passed)


if __name__ == "__main__":
    unittest.main()
