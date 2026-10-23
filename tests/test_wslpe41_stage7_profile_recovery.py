"""Source-only safety tests for first bounded scenario7 profile recovery.

No test launches VMware, connects to Windows, creates a profile or runs Ansible.
"""
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from kingdoms import wslpe41_stage7_profile_recovery as recovery
from kingdoms import wslpe41_provided_install as provided
from kingdoms import wslpe41_stage7_readonly_audit as audit
from kingdoms.wslpe41_install_flow import FreshGuestIdentity, InstallBlocked


class Stage7ProfileRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        home = Path(self.temp.name)
        self.state_root = home / "state"
        self.state_dir = self.state_root / audit.INSTANCE
        self.state_dir.mkdir(parents=True, mode=0o700)
        self.state_root.chmod(0o700)
        self.state_dir.chmod(0o700)
        self.journal = self.state_dir / "provided-install.json"
        self.vmx = home / "fresh-wslpe.vmx"
        self.vmx.write_text("VMX")
        self.identity = FreshGuestIdentity(
            instance_id=audit.INSTANCE, workspace=str(home),
            vmx=str(self.vmx), subnet="172.28.232.0/24", source_commit="b" * 40,
        )
        self.context = SimpleNamespace(identity=self.identity)
        self.record = {
            "schema": provided.SCHEMA, "instance": audit.INSTANCE,
            "vmx": str(self.vmx), "source_commit": "a" * 40,
            "jea_nonce": "f" * 32, "status": "BLOCKED",
            "next_stage": 12, "configuration_validated": 6,
            "inflight": {"number": 7, "stage": "apply"},
            "failure_class": "InstallBlocked",
            "failure_gate": "Scenario #7 apply: Ansible rc=2; last_task=windows_lpe : Apply AlwaysInstallElevated candidate; stdout_sha256_prefix=5e9cf174414e",
            "proofs": [
                {"number": i // 2 + 1, "stage": "apply" if i % 2 == 0 else "validate",
                 "transport": "ansible", "evidence_id": "proof-" + str(i)}
                for i in range(12)
            ],
            "course_release": "NOT_AUTHORIZED",
        }
        self.journal.write_text(json.dumps(self.record))
        self.journal.chmod(0o600)
        self.original = self.journal.read_bytes()
        self.evidence = {
            "learner_exists": True, "learner_enabled": True,
            "profile_registry_exists": False, "profile_directory_exists": False,
            "ntuser_dat_exists": False, "scenario_directory_exists": True,
            "state_file_exists": False, "state_snapshot_matches_learner": False,
            "machine_policy_value": None, "learner_hive_loaded": False,
            "learner_policy_value": None,
        }
        self.stages = tuple([
            SimpleNamespace(
                number=i // 2 + 1, stage="apply" if i % 2 == 0 else "validate",
                transport="ansible",
            ) for i in range(82)
        ] + [SimpleNamespace(number=41, stage="validate", transport="ansible")])

    def _mocks(self, evidence=None, profile_failure=None):
        from contextlib import ExitStack
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(provided, "STATE_ROOT", self.state_root))
        stack.enter_context(patch.object(provided, "_preflight",
                                         return_value=(self.context, "operator", "learner")))
        stack.enter_context(patch.object(provided, "_stages", return_value=self.stages))
        stack.enter_context(patch.object(audit, "_journal_state", return_value=self.record))
        observer = stack.enter_context(patch.object(audit, "inspect",
                                                   return_value=evidence or self.evidence))
        creator = stack.enter_context(patch.object(
            recovery, "_create_profile_verified",
            side_effect=profile_failure,
        ))
        installer = stack.enter_context(patch.object(provided, "_install_steps",
                                                   return_value="PAUSED"))
        return observer, creator, installer

    def test_profile_recovery_preserves_first_six_scenarios(self):
        observer, creator, installer = self._mocks()
        self.assertEqual(recovery.recover(), "PAUSED")
        history = self.state_dir / "provided-install.blocked-stage7.json"
        intent = self.state_dir / "stage7-profile-recovery-intent.json"
        self.assertEqual(history.read_bytes(), self.original)
        self.assertTrue(intent.is_file())
        state = json.loads(self.journal.read_text())
        self.assertEqual(state["next_stage"], 12)
        self.assertEqual(state["configuration_validated"], 6)
        self.assertEqual(state["proofs"], self.record["proofs"])
        self.assertEqual(state["jea_nonce"], self.record["jea_nonce"])
        self.assertEqual(state["source_commit"], "b" * 40)
        self.assertEqual(state["stage7_profile_recovery"]["previous_journal_sha256"],
                         hashlib.sha256(self.original).hexdigest())
        observer.assert_called_once()
        creator.assert_called_once()
        installer.assert_called_once()
        self.assertEqual(installer.call_args.args[3][12].number, 7)
        with self.assertRaisesRegex(InstallBlocked, "already attempted"):
            recovery.recover()

    def test_existing_scenario_policy_blocks_before_any_write(self):
        bad = dict(self.evidence)
        bad["machine_policy_value"] = 1
        _, creator, installer = self._mocks(evidence=bad)
        with self.assertRaisesRegex(InstallBlocked, "state changed"):
            recovery.recover()
        self.assertEqual(self.journal.read_bytes(), self.original)
        self.assertFalse((self.state_dir / "stage7-profile-recovery-intent.json").exists())
        creator.assert_not_called()
        installer.assert_not_called()

    def test_native_profile_failure_blocks_and_never_replays_stage7(self):
        _, creator, installer = self._mocks(
            profile_failure=InstallBlocked("Native CreateProfile stage7 preparation failed"))
        with self.assertRaisesRegex(InstallBlocked, "native", flags=0):
            recovery.recover()
        new = json.loads(self.journal.read_text())
        self.assertEqual(new["status"], "BLOCKED")
        self.assertEqual(new["inflight"], {"number": 7, "stage": "profile_prepare"})
        self.assertEqual(new["proofs"], self.record["proofs"])
        self.assertEqual((self.state_dir / "provided-install.blocked-stage7.json").read_bytes(), self.original)
        installer.assert_not_called()

    def test_no_windows_change_when_profile_already_exists(self):
        bad = dict(self.evidence)
        bad["profile_registry_exists"] = True
        _, creator, installer = self._mocks(evidence=bad)
        with self.assertRaisesRegex(InstallBlocked, "state changed"):
            recovery.recover()
        creator.assert_not_called()
        installer.assert_not_called()
        self.assertEqual(self.journal.read_bytes(), self.original)

    def test_source_profile_script_has_no_policy_or_scenario_writes(self):
        script = recovery.CREATE_PROFILE_SCRIPT
        self.assertIn('EntryPoint="CreateProfile"', script)
        self.assertIn("WSLPE41_STAGE7_LEARNER_PROFILE=CREATED_AND_VERIFIED", script)
        self.assertNotIn("New-ItemProperty", script)
        self.assertNotIn("Set-ItemProperty", script)
        self.assertNotIn("reg.exe load", script)
        self.assertNotIn("Start-Process", script)
        self.assertNotIn("targetPassword", script)


if __name__ == "__main__":
    unittest.main()
