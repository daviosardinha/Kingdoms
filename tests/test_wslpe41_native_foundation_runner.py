"""Source-only WSLPE41 native foundation and unified runner tests."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from kingdoms.wslpe41_foundation_executor import MARKERS, run_foundation_stage
from kingdoms.wslpe41_fresh_contract import fresh_scenario_manifest
from kingdoms.wslpe41_install_flow import (
    FreshGuestAttestation, FreshGuestIdentity, InstallBlocked, StageProof, install_41,
)
from kingdoms.wslpe41_native_stage_runner import NativeStageRunner
from kingdoms.wslpe41_runtime_proof import ObservedStageResult
from kingdoms.wslpe41_stage_executor import AnsibleStageContext


class NativeFoundationRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Path(self.tmp.name) / "workspace"
        self.instance = self.workspace / "wslpe41-new-test"
        (self.instance / "ansible").mkdir(parents=True)
        self.ansible = Path(self.tmp.name) / "ansible-playbook"
        self.ansible.write_text("#!/bin/sh\n")
        self.ansible.chmod(0o700)
        self.inventory = self.instance / "ansible/inventory"
        self.inventory.write_text("[wslpe]\nws01\n")
        self.varsfile = self.instance / "ansible/private-vars.yml"
        self.varsfile.write_text("all:\n  vars: {}\n")
        self.varsfile.chmod(0o600)
        self.identity = FreshGuestIdentity(
            instance_id=self.instance.name, workspace=str(self.workspace),
            vmx=str(self.instance / "provider/WSLPE-WS01.vmx"),
            subnet="172.28.232.0/24", source_commit="a" * 40,
        )
        self.context = AnsibleStageContext(
            identity=self.identity, instance_dir=self.instance,
            ansible=self.ansible, inventory=self.inventory,
            private_vars=self.varsfile, expected_address="172.28.232.31",
        )
        self.attestation = FreshGuestAttestation(
            instance_id=self.identity.instance_id, vmx=self.identity.vmx,
            source_commit=self.identity.source_commit,
            created_by_this_install=True, standalone_workgroup=True,
            learner_ready=True, operator_recovery_ready=True,
            management_isolated=True, fresh_tls_identity=True,
        )
        self.jea = next(s for s in fresh_scenario_manifest() if s.number == 30)

    def fake_run(self, stage):
        output = "\n".join(MARKERS[stage]) + "\n"
        return SimpleNamespace(returncode=0, stdout=output, stderr="")

    def test_learner_foundation_reuses_exact_existing_playbook(self):
        with (patch("kingdoms.wslpe41_foundation_executor._guest") as guest,
              patch("kingdoms.wslpe41_foundation_executor._inventory"),
              patch("kingdoms.wslpe41_foundation_executor._environment", return_value={}),
              patch("kingdoms.wslpe41_foundation_executor.subprocess.run",
                    return_value=self.fake_run("learner")) as run):
            proof = run_foundation_stage(self.context, "learner")
        self.assertTrue(proof.passed)
        self.assertFalse(proof.operator_authenticated)
        self.assertEqual(guest.call_count, 2)
        args, kwargs = run.call_args
        self.assertTrue(args[0][-1].endswith("ansible/wslpe-foundation.yml"))
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(args[0][1:7], [
            "-i", str(self.inventory), "-i", str(self.varsfile),
            "--limit", "ws01,localhost",
        ])

    def test_operator_requires_explicit_approval_and_live_console_check(self):
        with self.assertRaisesRegex(InstallBlocked, "explicit handoff"):
            run_foundation_stage(self.context, "operator")
        with (patch("kingdoms.wslpe41_foundation_executor._guest"),
              patch("kingdoms.wslpe41_foundation_executor._inventory"),
              patch("kingdoms.wslpe41_foundation_executor._environment", return_value={}),
              patch("kingdoms.wslpe41_foundation_executor.subprocess.run") as run):
            with self.assertRaisesRegex(InstallBlocked, "console recovery"):
                run_foundation_stage(
                    self.context, "operator", operator_handoff_approved=True,
                    console_recovery_check=lambda identity: False,
                )
            run.assert_not_called()
            run.return_value = self.fake_run("operator")
            proof = run_foundation_stage(
                self.context, "operator", operator_handoff_approved=True,
                console_recovery_check=lambda identity: identity == self.identity,
            )
            self.assertTrue(proof.passed)
            self.assertFalse(proof.operator_authenticated)
            self.assertEqual(run.call_args.args[0][-2:], [
                "-e", '{"wslpe_operator_handoff_approved":true}',
            ])

    def test_no_forged_or_partial_foundation_proof(self):
        for code, output in (
            (0, "WSLPE_WINDOWS_STANDALONE=PASS\n"),
            (1, "\n".join(MARKERS["learner"])),
            (0, "\n".join(MARKERS["learner"]) + "\n" + MARKERS["learner"][0]),
        ):
            with (patch("kingdoms.wslpe41_foundation_executor._guest"),
                  patch("kingdoms.wslpe41_foundation_executor._inventory"),
                  patch("kingdoms.wslpe41_foundation_executor._environment", return_value={}),
                  patch("kingdoms.wslpe41_foundation_executor.subprocess.run",
                        return_value=SimpleNamespace(returncode=code, stdout=output, stderr=""))):
                with self.assertRaisesRegex(InstallBlocked, "Windows proof missing"):
                    run_foundation_stage(self.context, "learner")

    def test_unsafe_private_vars_and_unknown_stage_fail_before_execution(self):
        with self.assertRaisesRegex(InstallBlocked, "Unknown"):
            run_foundation_stage(self.context, "unapproved")
        self.varsfile.chmod(0o644)
        with self.assertRaisesRegex(InstallBlocked, "owner-only"):
            run_foundation_stage(self.context, "learner")

    def test_preflight_accepts_only_independently_attested_matching_guest(self):
        attestor = Mock(return_value=self.attestation)
        runner = NativeStageRunner(self.context, attestor)
        with (patch("kingdoms.wslpe41_native_stage_runner._guest") as guest,
              patch("kingdoms.wslpe41_native_stage_runner._environment", return_value={}),
              patch("kingdoms.wslpe41_native_stage_runner._inventory")):
            self.assertEqual(runner.preflight(self.identity), self.attestation)
            self.assertEqual(guest.call_count, 2)
            attestor.assert_called_once_with(self.identity)
            with self.assertRaisesRegex(InstallBlocked, "different instance"):
                runner.preflight(FreshGuestIdentity(
                    "another-wslpe", self.identity.workspace, self.identity.vmx,
                    self.identity.subnet, self.identity.source_commit,
                ))
        runner.attest_fresh_guest = lambda identity: FreshGuestAttestation(
            **{**self.attestation.__dict__, "fresh_tls_identity": False}
        )
        with (patch("kingdoms.wslpe41_native_stage_runner._guest"),
              patch("kingdoms.wslpe41_native_stage_runner._environment", return_value={}),
              patch("kingdoms.wslpe41_native_stage_runner._inventory")):
            with self.assertRaisesRegex(InstallBlocked, "not proven"):
                runner.preflight(self.identity)

    def test_ordinary_scenario_delegates_to_exact_ansible_executor(self):
        scenario = fresh_scenario_manifest()[0]
        expected = StageProof(scenario.number, "apply", "ansible", "wslpe41.proof", True)
        runner = NativeStageRunner(self.context, lambda identity: self.attestation)
        with patch("kingdoms.wslpe41_native_stage_runner.run_ansible_stage",
                   return_value=expected) as stage:
            self.assertEqual(runner.run_stage(scenario, "apply"), expected)
            stage.assert_called_once_with(self.context, scenario, "apply")

    def test_jea_requires_real_guest_console_and_winrm_recovery_marker(self):
        runner = NativeStageRunner(self.context, lambda identity: self.attestation)
        with self.assertRaisesRegex(InstallBlocked, "guest-console executor"):
            runner.run_stage(self.jea, "activate")
        def observation(*, transport="guest_console", recovered=True):
            stdout = "WSLPE45_JEA_LOCAL_APPLY=PASS\n"
            if recovered:
                stdout += "WSLPE45_JEA_WINRM_LOCAL_RECOVERY=PASS\n"
            return ObservedStageResult(
                instance_id=self.identity.instance_id, vmx=self.identity.vmx,
                transport=transport, returncode=0, stdout=stdout, stderr="",
            )
        with patch("kingdoms.wslpe41_native_stage_runner._guest"):
            runner.activate_jea_console = lambda identity: observation()
            proof = runner.run_stage(self.jea, "activate")
            self.assertTrue(proof.passed)
            self.assertEqual(proof.transport, "guest_console")
            for candidate in (observation(transport="ansible"),
                              observation(recovered=False)):
                runner.activate_jea_console = lambda identity, c=candidate: c
                with self.assertRaisesRegex(InstallBlocked, "console/recovery proof"):
                    runner.run_stage(self.jea, "activate")


    def test_entire_41_scenario_journal_uses_one_native_runner(self):
        """83 stages, one transaction, no separate 20/21 orchestration."""
        calls = []
        def ansible_stage(context, scenario, stage):
            calls.append((scenario.number, stage))
            return StageProof(
                scenario.number, stage, "ansible",
                f"wslpe41.{scenario.number:02d}.{stage}.testproof", True,
            )
        def jea_console(identity):
            calls.append((30, "activate"))
            return ObservedStageResult(
                instance_id=identity.instance_id, vmx=identity.vmx,
                transport="guest_console", returncode=0,
                stdout=("WSLPE45_JEA_LOCAL_APPLY=PASS\\n"
                        "WSLPE45_JEA_WINRM_LOCAL_RECOVERY=PASS\\n"),
                stderr="",
            )
        runner = NativeStageRunner(
            self.context, lambda identity: self.attestation, jea_console,
        )
        with (patch("kingdoms.wslpe41_native_stage_runner._guest"),
              patch("kingdoms.wslpe41_native_stage_runner._environment", return_value={}),
              patch("kingdoms.wslpe41_native_stage_runner._inventory"),
              patch("kingdoms.wslpe41_native_stage_runner.run_ansible_stage",
                    side_effect=ansible_stage)):
            journal = install_41(
                self.identity, runner, Path(self.tmp.name) / "private-state",
            )
        report = json.loads(journal.read_text())
        self.assertEqual(report["configuration_validated"], 41)
        self.assertEqual(report["status"], "CONFIGURATION_VALIDATED")
        self.assertEqual(len(calls), 83)
        self.assertEqual(calls.count((30, "activate")), 1)
        self.assertEqual(len({n for n, _ in calls}), 41)
        self.assertFalse((journal.parent / ".incomplete").exists())
        self.assertEqual(report["learner_exploitation"], "NOT_PROVEN")


if __name__ == "__main__":
    unittest.main()
