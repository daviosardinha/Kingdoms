"""One-install WSLPE41 real-source command mapping, with no guest execution."""
import json
from pathlib import Path
import unittest

from kingdoms.wslpe41_fresh_contract import fresh_scenario_manifest
from kingdoms.wslpe41_stage_commands import (
    StagePlanBlocked, build_stage_invocation, one_install_invocations,
)


ANSIBLE = Path("/opt/kingdoms-venv/bin/ansible-playbook")
INVENTORY = Path("/tmp/new-instance/ansible/inventory")
VARS = Path("/tmp/new-instance/ansible/private-vars.yml")
IP = "172.28.232.31"


class StageCommandTests(unittest.TestCase):
    def make(self, scenario, stage):
        return build_stage_invocation(
            scenario, stage, ansible=ANSIBLE, inventory=INVENTORY,
            varsfile=VARS, expected_address=IP,
        )

    def test_one_41_scenario_order_not_20_plus_21_runs(self):
        steps = one_install_invocations(
            ansible=ANSIBLE, inventory=INVENTORY,
            varsfile=VARS, expected_address=IP,
        )
        self.assertEqual(len(steps), 83)
        manifest = fresh_scenario_manifest()
        self.assertEqual([r.number for r in steps if r.stage in ("apply", "activate")],
                         [r.number for r in manifest])
        self.assertEqual(len({r.number for r in steps}), 41)
        self.assertFalse({25, 36, 38, 40}.intersection(r.number for r in steps))
        self.assertEqual(sum(r.transport == "guest_console" for r in steps), 1)

    def test_existing_20_map_to_one_named_technique_per_stage(self):
        first = fresh_scenario_manifest()[0]
        invocation = self.make(first, "apply")
        self.assertEqual(invocation.transport, "ansible")
        self.assertEqual(invocation.evidence_kind, "scenario_specific_windows_role_validation_required")
        self.assertIsNone(invocation.evidence_marker)
        self.assertEqual(invocation.argv[0], str(ANSIBLE))
        self.assertEqual(invocation.argv[1:7],
                         ("-i", str(INVENTORY), "-i", str(VARS), "--limit", "ws01,localhost"))
        self.assertTrue(invocation.argv[-3].endswith("ansible/wslpe-lpe-test.yml"))
        self.assertEqual(json.loads(invocation.argv[-1]),
                         {"wslpe_action": "apply", "wslpe_techniques": [first.identifier]})
        validation = self.make(first, "validate")
        self.assertEqual(json.loads(validation.argv[-1])["wslpe_action"], "validate")

    def test_standalone_additions_use_real_index_and_fresh_shared_library(self):
        scenario = next(r for r in fresh_scenario_manifest() if r.number == 27)
        for stage in ("apply", "validate"):
            invocation = self.make(scenario, stage)
            extra = json.loads(invocation.argv[-1])
            self.assertEqual(extra["wslpe_expected_address"], IP)
            self.assertEqual(extra["wslpe_45_technique"], scenario.identifier)
            self.assertEqual(extra["wslpe_45_action"], stage)
            self.assertTrue(extra["wslpe_deploy21"])
            self.assertFalse(extra["wslpe_pilot_preserve_shared"])
            self.assertEqual(invocation.transport, "ansible")
            self.assertEqual(invocation.evidence_marker,
                f"WSLPE21_STAGE={scenario.identifier}:{'apply' if stage == 'apply' else 'vulnerable'}:PASS")

    def test_jea_is_staged_then_local_console_then_fresh_learner_validation(self):
        scenario = next(r for r in fresh_scenario_manifest() if r.number == 30)
        staged = self.make(scenario, "stage")
        activation = self.make(scenario, "activate")
        validated = self.make(scenario, "validate")
        self.assertEqual(json.loads(staged.argv[-1])["wslpe_jea_stage_approved"], True)
        self.assertTrue(staged.argv[-3].endswith("jea_local_stage.yml"))
        self.assertEqual(activation.transport, "guest_console")
        self.assertEqual(activation.argv, ())
        self.assertEqual(activation.evidence_marker, "WSLPE45_JEA_LOCAL_APPLY=PASS")
        self.assertEqual(activation.evidence_kind, "independent_console_and_winrm_recovery")
        self.assertTrue(validated.argv[-3].endswith("deploy21-jea-status.yml"))
        self.assertEqual(validated.evidence_marker, "WSLPE21_JEA_ACTIVE=PASS")

    def test_rejects_domain_guest_address(self):
        scenario = fresh_scenario_manifest()[0]
        with self.assertRaisesRegex(StagePlanBlocked, "Forbidden"):
            build_stage_invocation(scenario, "apply", ansible=ANSIBLE,
                                   inventory=INVENTORY, varsfile=VARS,
                                   expected_address="10.4.10.31")

    def test_rejects_invalid_or_symlinked_runtime_paths(self):
        scenario = fresh_scenario_manifest()[0]
        with self.assertRaisesRegex(StagePlanBlocked, "absolute"):
            build_stage_invocation(scenario, "apply", ansible=Path("ansible-playbook"),
                                   inventory=INVENTORY, varsfile=VARS,
                                   expected_address=IP)

    def test_rejects_unexpected_stages(self):
        scenario = next(r for r in fresh_scenario_manifest() if r.number == 30)
        with self.assertRaisesRegex(StagePlanBlocked, "Unexpected stage"):
            self.make(scenario, "apply")
        first = fresh_scenario_manifest()[0]
        with self.assertRaisesRegex(StagePlanBlocked, "Unexpected stage"):
            self.make(first, "activate")


if __name__ == "__main__":
    unittest.main()
