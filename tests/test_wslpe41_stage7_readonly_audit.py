"""No-VM read-only stage7 audit: preserve all six validated scenario proofs."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from kingdoms import wslpe41_stage7_readonly_audit as audit
from kingdoms import wslpe41_provided_install as provided
from kingdoms.wslpe41_install_flow import InstallBlocked


class Stage7ReadOnlyAuditTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name) / "state"
        self.path = self.root / audit.INSTANCE / "provided-install.json"
        self.path.parent.mkdir(parents=True, mode=0o700)
        self.root.chmod(0o700)
        self.path.parent.chmod(0o700)
        self.vmx = Path(self.t.name) / "guest.vmx"
        self.vmx.write_text("existing")
        self.record = {
            "schema": provided.SCHEMA, "instance": audit.INSTANCE,
            "vmx": str(self.vmx), "status": "BLOCKED",
            "next_stage": 12, "configuration_validated": 6,
            "inflight": {"number": 7, "stage": "apply"},
            "failure_gate": "Scenario #7 apply: Ansible rc=2; last_task=windows_lpe : Apply AlwaysInstallElevated candidate; stdout_sha256_prefix=123456789abc",
            "proofs": [
                {"number": i // 2 + 1, "stage": "apply" if i % 2 == 0 else "validate",
                 "transport": "ansible", "evidence_id": f"proof-{i}"}
                for i in range(12)
            ],
        }
        self._save()

    def _save(self):
        self.path.write_text(json.dumps(self.record))
        self.path.chmod(0o600)

    def observed(self, *, partial=False):
        body = {
            "schema": "kingdoms.wslpe41.stage7-readonly.v1", "computer": "WSLPE-WS01",
            "learner_exists": True, "learner_enabled": True,
            "profile_registry_exists": False, "profile_directory_exists": False,
            "ntuser_dat_exists": False, "scenario_directory_exists": partial,
            "state_file_exists": partial, "state_snapshot_matches_learner": False,
            "machine_policy_value": 1 if partial else None,
            "learner_hive_loaded": False, "learner_policy_value": None,
        }
        return SimpleNamespace(status_code=0, std_out=(
            "WSLPE41_STAGE7_AUDIT=" + json.dumps(body) + "\r\n").encode())

    def _mocks(self, remote):
        from contextlib import ExitStack
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(audit, "STATE_ROOT", self.root))
        stack.enter_context(patch.object(audit, "existing_management",
                                         return_value=(SimpleNamespace(vmx=self.vmx), {}, b"der", "operator-secret", "learner")))
        stack.enter_context(patch.object(audit.management, "auth_helper", return_value=object()))
        session = stack.enter_context(patch.object(audit.management, "operator_session"))
        session.return_value.__enter__.return_value = object()
        call = stack.enter_context(patch.object(audit.management, "run_powershell", return_value=remote))
        return call

    def test_readonly_absent_state_preserves_full_journal(self):
        previous = self.path.read_bytes()
        execute = self._mocks(self.observed())
        lines = []
        evidence = audit.inspect(report=lines.append)
        self.assertFalse(evidence["scenario_directory_exists"])
        self.assertIn("[PASS] Six validated scenarios; exactly twelve preserved runtime proofs", lines)
        self.assertIn("[STATE] NO_SCENARIO7_POLICY_ARTIFACTS_VISIBLE; profile may still be pre-existing", lines)
        self.assertEqual(previous, self.path.read_bytes())
        script = execute.call_args.args[1]
        self.assertIn("Get-LocalUser", script)
        self.assertIn("Get-ItemProperty", script)
        self.assertNotIn("New-ItemProperty", script)
        self.assertNotIn("reg.exe load", script)
        self.assertNotIn("Start-Process", script)

    def test_partial_state_does_not_authorize_replay(self):
        self._mocks(self.observed(partial=True))
        logs = []
        result = audit.inspect(report=logs.append)
        self.assertEqual(result["machine_policy_value"], 1)
        self.assertIn("[STATE] PARTIAL_OR_PRESENT; no stage replay permitted", logs)
        self.assertEqual(self.record["next_stage"], 12)

    def test_invalid_journal_never_contacts_windows(self):
        for key, value in [
            ("next_stage", 0), ("configuration_validated", 5),
            ("inflight", {"number": 8, "stage": "apply"}),
        ]:
            original = self.record[key]
            self.record[key] = value
            self._save()
            with patch.object(audit, "STATE_ROOT", self.root), patch.object(audit, "existing_management") as caller:
                with self.assertRaisesRegex(InstallBlocked, "exact blocked"):
                    audit.inspect()
                caller.assert_not_called()
            self.record[key] = original
        self._save()

    def test_invalid_runtime_proof_sequence_fails_closed(self):
        self.record["proofs"][5]["number"] = 7
        self._save()
        with patch.object(audit, "STATE_ROOT", self.root):
            with self.assertRaisesRegex(InstallBlocked, "twelve preceding"):
                audit.inspect()


if __name__ == "__main__":
    unittest.main()
