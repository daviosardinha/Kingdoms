"""No VMware access: verify real-stage evidence acceptance and rejection semantics."""
from pathlib import Path
import unittest

from kingdoms.wslpe41_fresh_contract import fresh_scenario_manifest
from kingdoms.wslpe41_install_flow import verify_stage
from kingdoms.wslpe41_stage_commands import build_stage_invocation
from kingdoms.wslpe41_runtime_proof import (
    ObservedStageResult, RuntimeProofBlocked, verify_observed_stage,
)


INSTANCE = "wslpe41-fresh-0001"
VMX = "/operator/kingdoms/workspace/wslpe41-fresh-0001/provider/WSLPE-WS01.vmx"
ANSIBLE = Path("/opt/kingdoms-venv/bin/ansible-playbook")
INVENTORY = Path("/operator/kingdoms/workspace/wslpe41-fresh-0001/ansible/inventory")
VARS = Path("/operator/kingdoms/workspace/wslpe41-fresh-0001/ansible/private.yml")


class RuntimeProofTests(unittest.TestCase):
    def stage(self, number, stage):
        scenario = next(s for s in fresh_scenario_manifest() if s.number == number)
        invocation = build_stage_invocation(
            scenario, stage, ansible=ANSIBLE, inventory=INVENTORY,
            varsfile=VARS, expected_address="172.28.232.31", instance_id=INSTANCE)
        return scenario, invocation

    def observation(self, invocation, **overrides):
        data = dict(
            instance_id=INSTANCE, vmx=VMX, transport=invocation.transport,
            returncode=0, stdout=f"guest:\n{invocation.evidence_marker}\n",
            stderr="",
        )
        data.update(overrides)
        return ObservedStageResult(**data)

    def verify(self, invocation, observation):
        return verify_observed_stage(
            invocation, observation, expected_instance_id=INSTANCE,
            expected_vmx=VMX,
        )

    def test_first_20_apply_and_validate_have_windows_backed_proof(self):
        for stage in ("apply", "validate"):
            scenario, invocation = self.stage(1, stage)
            proof = self.verify(invocation, self.observation(invocation))
            verify_stage(scenario, stage, proof)
            self.assertEqual(proof.transport, "ansible")
            self.assertTrue(proof.evidence_id.startswith("wslpe41.01."))

    def test_additional_scenario_uses_exact_existing_marker(self):
        scenario, invocation = self.stage(27, "validate")
        proof = self.verify(invocation, self.observation(invocation))
        verify_stage(scenario, "validate", proof)

    def test_jea_activation_needs_guest_console_and_local_winrm_recovery(self):
        scenario, invocation = self.stage(30, "activate")
        with self.assertRaisesRegex(RuntimeProofBlocked, "recovery"):
            self.verify(invocation, self.observation(invocation))
        result = self.observation(
            invocation,
            stdout=f"{invocation.evidence_marker}\nWSLPE45_JEA_WINRM_LOCAL_RECOVERY=PASS\n",
        )
        proof = self.verify(invocation, result)
        verify_stage(scenario, "activate", proof)

    def test_jea_staging_and_fresh_learner_status_are_separate(self):
        for stage in ("stage", "validate"):
            scenario, invocation = self.stage(30, stage)
            proof = self.verify(invocation, self.observation(invocation))
            verify_stage(scenario, stage, proof)
            self.assertEqual(proof.transport, "ansible")

    def test_rejects_wrong_instance_or_vmx(self):
        _, invocation = self.stage(2, "apply")
        for changes in (
            {"instance_id": "old-master-guest"},
            {"vmx": "/old-master/provider/WSLPE-WS01.vmx"},
        ):
            with self.assertRaisesRegex(RuntimeProofBlocked, "not bound"):
                self.verify(invocation, self.observation(invocation, **changes))

    def test_rejects_remote_jea_activation(self):
        _, invocation = self.stage(30, "activate")
        with self.assertRaisesRegex(RuntimeProofBlocked, "transport"):
            self.verify(invocation, self.observation(
                invocation, transport="ansible",
                stdout=f"{invocation.evidence_marker}\nWSLPE45_JEA_WINRM_LOCAL_RECOVERY=PASS",
            ))

    def test_rejects_failed_ambiguous_or_fake_stage_output(self):
        _, invocation = self.stage(1, "apply")
        for changes in (
            {"returncode": 2},
            {"stdout": ""},
            {"stdout": "WSLPE41_STAGE=wrong:apply:PASS"},
            {"stdout": f"{invocation.evidence_marker}\n{invocation.evidence_marker}"},
        ):
            with self.assertRaises(RuntimeProofBlocked):
                self.verify(invocation, self.observation(invocation, **changes))

    def test_no_raw_output_in_persisted_proof(self):
        _, invocation = self.stage(1, "apply")
        observation = self.observation(
            invocation, stdout=f"{invocation.evidence_marker}\nSECRET_FROM_LOG=redacted",
        )
        proof = self.verify(invocation, observation)
        self.assertNotIn("SECRET", repr(proof))
        self.assertNotIn("redacted", repr(proof))


if __name__ == "__main__":
    unittest.main()
