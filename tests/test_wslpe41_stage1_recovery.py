"""No-VM source regression for bounded stage-1 recovery and permanent journal lineage."""
import hashlib
import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from kingdoms import wslpe41_provided_install as provided
from kingdoms import wslpe41_first_stage_audit as audit
from kingdoms.wslpe41_install_flow import FreshGuestIdentity, InstallBlocked


class FirstStageRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / "state"
        self.journal = self.root / provided.INSTANCE / "provided-install.json"
        self.journal.parent.mkdir(mode=0o700, parents=True)
        self.identity = FreshGuestIdentity(
            instance_id=provided.INSTANCE, workspace=str(base),
            vmx=str(base / "fresh.vmx"),
            subnet="172.28.232.0/24", source_commit="a" * 40,
        )
        self.context = SimpleNamespace(
            identity=self.identity, management_address="172.28.233.31",
            expected_address="172.28.232.31",
            private_vars=base / "private-vars.yml",
        )
        self.old = provided._base_state(self.context)
        self.old.update(
            status="BLOCKED", source_commit="b" * 40,
            inflight={"number": 1, "stage": "apply"},
        )
        self.journal.write_text(json.dumps(self.old, sort_keys=True))
        self.journal.chmod(0o600)
        self.raw = self.journal.read_bytes()

    def fake_audit(self, *, report, evidence_out):
        evidence_out.update({
            "service_exists": False,
            "service_matches_expected": False,
            "scenario_directory_exists": False,
            "service_executable_exists": False,
            "candidate_exists": False,
        })
        report("[WINDOWS FIXTURE] ABSENT")
        return False

    def _dependencies(self, inspection=None, returncode=0):
        # Existing guest, operator TLS, private files and source verification
        # are already covered by _preflight's independent tests.
        from contextlib import ExitStack
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(provided, "STATE_ROOT", self.root))
        stack.enter_context(patch.object(provided, "_preflight",
                                         return_value=(self.context, "O" * 30, "L" * 30)))
        stack.enter_context(patch.object(
            provided, "_stages", return_value=(SimpleNamespace(
                number=1, stage="apply", transport="ansible",
                argv=("/tmp/ansible-playbook", "-i", "/tmp/inventory")),)))
        stack.enter_context(patch.object(audit, "inspect", side_effect=inspection or self.fake_audit))
        stack.enter_context(patch("kingdoms.wslpe41_stage_executor._environment",
                                  return_value={"ANSIBLE_NOCOLOR": "1"}))
        stack.enter_context(patch("kingdoms.wslpe41_stage_executor._inventory"))
        runner = stack.enter_context(patch.object(
            provided.subprocess, "run",
            return_value=SimpleNamespace(returncode=returncode, stdout="", stderr="")))
        install = stack.enter_context(patch.object(provided, "_install_steps",
                                                  return_value="PAUSED"))
        return runner, install

    def test_absent_fixture_syntax_check_archives_old_journal_once(self):
        runner, install = self._dependencies()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(provided.recover_clean_blocked_stage1(), "PAUSED")
        prior = self.journal.parent / "provided-install.blocked-stage1.json"
        intent = self.journal.parent / "stage1-recovery-intent.json"
        self.assertEqual(prior.read_bytes(), self.raw)
        self.assertTrue(intent.is_file())
        record = json.loads(self.journal.read_text())
        self.assertEqual(record["status"], "RUNNING")
        self.assertEqual(record["next_stage"], 0)
        self.assertEqual(record["recovery"]["archived_sha256"],
                         hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(record["recovery"]["archived_source_commit"], "b" * 40)
        self.assertEqual(record["source_commit"], "a" * 40)
        self.assertIn("--syntax-check", runner.call_args.args[0])
        install.assert_called_once()
        with self.assertRaisesRegex(InstallBlocked, "already attempted"):
            provided.recover_clean_blocked_stage1()
        self.assertEqual(prior.read_bytes(), self.raw)

    def test_partial_remote_windows_state_refuses_recovery_without_archive(self):
        def partial(*, report, evidence_out):
            self.fake_audit(report=report, evidence_out=evidence_out)
            evidence_out["service_exists"] = True
            return False
        runner, install = self._dependencies(inspection=partial)
        with self.assertRaisesRegex(InstallBlocked, "artifacts are present"):
            provided.recover_clean_blocked_stage1()
        self.assertEqual(self.journal.read_bytes(), self.raw)
        self.assertFalse((self.journal.parent / "stage1-recovery-intent.json").exists())
        runner.assert_not_called()
        install.assert_not_called()

    def test_syntax_failure_preserves_original_journal_no_scenario(self):
        runner, install = self._dependencies(returncode=4)
        with self.assertRaisesRegex(InstallBlocked, "syntax check failed"):
            provided.recover_clean_blocked_stage1()
        self.assertEqual(self.journal.read_bytes(), self.raw)
        self.assertFalse((self.journal.parent / "stage1-recovery-intent.json").exists())
        install.assert_not_called()

    def test_mismatched_journal_refuses_before_remote_or_syntax(self):
        self.old["inflight"] = {"number": 2, "stage": "apply"}
        self.journal.write_text(json.dumps(self.old))
        runner, install = self._dependencies()
        with self.assertRaisesRegex(InstallBlocked, "exact failed stage1"):
            provided.recover_clean_blocked_stage1()
        runner.assert_not_called()
        install.assert_not_called()

    def test_cli_requires_explicit_stage1_recovery_approval(self):
        source = Path(__file__).resolve().parents[1] / "scripts/wslpe41-provided-install.py"
        spec = importlib.util.spec_from_file_location("provided_recovery_cli", source)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with patch.object(mod, "recover_clean_blocked_stage1") as operation:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(mod.main(["--recover-clean-stage1"]), 2)
                self.assertEqual(mod.main(["--recover-clean-stage1",
                                           "--authorize", "START-EXISTING-WSLPE41"]), 2)
            operation.assert_not_called()


if __name__ == "__main__":
    unittest.main()
