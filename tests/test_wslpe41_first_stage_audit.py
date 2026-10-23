"""Source-only regression for first-stage blocked journal recovery inspection."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from kingdoms import wslpe41_first_stage_audit as audit
from kingdoms import wslpe41_provided_install as install
from kingdoms.wslpe41_install_flow import InstallBlocked


class FirstStageAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vmx = self.root / "fresh.vmx"
        self.vmx.write_text("VMX")
        self.journal = self.root / audit.INSTANCE / "provided-install.json"
        self.journal.parent.mkdir(mode=0o700)
        self.journal.write_text(json.dumps({
            "schema": install.SCHEMA, "instance": audit.INSTANCE,
            "vmx": str(self.vmx), "status": "BLOCKED", "next_stage": 0,
            "configuration_validated": 0, "inflight": {"number": 1, "stage": "apply"},
            "proofs": [],
        }))
        self.journal.chmod(0o600)

    def remote(self, *, service=True, directory=True, executable=True, candidate=False):
        return SimpleNamespace(status_code=0, std_out=(
            "WSLPE41_STAGE1_AUDIT=" + json.dumps({
                "schema": "kingdoms.wslpe41.first-stage-readonly.v1",
                "computer": "WSLPE-WS01",
                "service_exists": service,
                "service_matches_expected": service and executable,
                "scenario_directory_exists": directory,
                "service_executable_exists": executable,
                "candidate_exists": candidate,
            }) + "\r\n").encode())

    def test_valid_blocked_first_stage_inspection_does_not_modify_journal(self):
        saved = self.journal.read_bytes()
        with (patch.object(audit, "STATE_ROOT", self.root),
              patch.object(audit, "existing_management",
                           return_value=(SimpleNamespace(vmx=self.vmx), {}, b"cert", "pass", "learner")),
              patch.object(audit.management, "auth_helper", return_value=object()),
              patch.object(audit.management, "operator_session") as session,
              patch.object(audit.management, "run_powershell", return_value=self.remote())):
            session.return_value.__enter__.return_value = object()
            report = []
            self.assertTrue(audit.inspect(report=report.append))
        self.assertIn("[WINDOWS FIXTURE] PRESENT_NEEDS_VALIDATION", report)
        self.assertIn("[NO CHANGES] Journal and Windows remain unchanged; no automatic replay", report)
        self.assertEqual(saved, self.journal.read_bytes())

    def test_partial_stage_is_not_reported_clean_or_complete(self):
        with (patch.object(audit, "STATE_ROOT", self.root),
              patch.object(audit, "existing_management",
                           return_value=(SimpleNamespace(vmx=self.vmx), {}, b"cert", "pass", "learner")),
              patch.object(audit.management, "auth_helper", return_value=object()),
              patch.object(audit.management, "operator_session") as session,
              patch.object(audit.management, "run_powershell",
                           return_value=self.remote(service=False, directory=True, executable=False))):
            session.return_value.__enter__.return_value = object()
            output = []
            self.assertFalse(audit.inspect(report=output.append))
            self.assertIn("[WINDOWS FIXTURE] PARTIALLY_PRESENT", output)

    def test_nonfirst_stage_and_uncertain_journals_fail_closed(self):
        with patch.object(audit, "STATE_ROOT", self.root):
            for inflight in (None, {"number": 2, "stage": "apply"}, {"number": 1, "stage": "validate"}):
                obj = json.loads(self.journal.read_text())
                obj["inflight"] = inflight
                self.journal.write_text(json.dumps(obj))
                with self.assertRaisesRegex(InstallBlocked, "not an exact first-stage"):
                    audit.inspect()
            self.journal.unlink()
            with self.assertRaisesRegex(InstallBlocked, "unavailable"):
                audit.inspect()


if __name__ == "__main__":
    unittest.main()
