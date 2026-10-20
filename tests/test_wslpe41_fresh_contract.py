"""Behavioral source tests for the future independent 41-scenario installer."""
import unittest
from unittest import mock

from kingdoms import wslpe41_fresh_contract as fresh


class FreshScopeTests(unittest.TestCase):
    def test_exact_41_in_source_order_with_four_explicit_exclusions(self):
        rows = fresh.fresh_scenario_manifest()
        self.assertEqual(len(rows), 41)
        self.assertEqual(tuple(r.number for r in rows), fresh.EXPECTED_NUMBERS)
        self.assertEqual(len({r.identifier for r in rows}), 41)
        self.assertFalse(set(fresh.EXCLUDED).intersection(r.number for r in rows))
        self.assertEqual([r.number for r in rows[:20]], list(range(1, 21)))

    def test_source_is_real_not_an_old_master_journal(self):
        rows = fresh.fresh_scenario_manifest()
        self.assertTrue(all((fresh.ROOT / r.playbook).is_file() for r in rows))
        self.assertEqual({r.playbook for r in rows[:20]}, {"ansible/wslpe-lpe-test.yml"})
        self.assertNotIn("resume", "\n".join(r.playbook for r in rows))
        self.assertNotIn("journal", "\n".join(r.playbook for r in rows))

    def test_jea_must_be_separate_out_of_band_activation(self):
        rows = fresh.fresh_scenario_manifest()
        jea = next(r for r in rows if r.number == 30)
        self.assertEqual(jea.identifier, "jea_role_capability_misconfig")
        self.assertEqual(jea.execution_channel, "out_of_band_jea_activation")
        self.assertEqual(jea.playbook, "ansible/wslpe45/jea_local_stage.yml")
        self.assertEqual(
            [r.number for r in rows if r.execution_channel != "standalone_ansible"],
            [30],
        )

    def test_tampered_excluded_identity_fails_closed(self):
        from kingdoms.wslpe_batch_catalog import catalog
        rows = catalog()
        tampered = [dict(r) for r in rows]
        tampered[24]["id"] = "changed_scenario"
        with mock.patch.object(fresh, "catalog", return_value=tampered):
            with self.assertRaisesRegex(fresh.FreshInstallContractError, "exclusions"):
                fresh.fresh_scenario_manifest()

    def test_missing_candidate_source_fails_closed(self):
        rows = fresh.fresh_scenario_manifest()
        target = next(r for r in rows if r.number == 29)
        source = fresh.ROOT / target.playbook
        # Patch Path.is_file for this exact path without changing the checkout.
        with mock.patch.object(fresh.Path, "is_file", autospec=True,
                               side_effect=lambda p: False if p == source else True):
            with self.assertRaisesRegex(fresh.FreshInstallContractError, "Missing"):
                fresh.fresh_scenario_manifest()


if __name__ == "__main__":
    unittest.main()
