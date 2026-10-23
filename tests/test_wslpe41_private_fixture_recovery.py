"""No-VM CI for second, fixture-guard-specific stage1 recovery lineage."""
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from kingdoms import wslpe41_provided_install as provided
from kingdoms import wslpe41_fixture_guard_probe as probe
from kingdoms import wslpe41_first_stage_audit as audit
from kingdoms.wslpe41_install_flow import FreshGuestIdentity, InstallBlocked


class PrivateFixtureRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base / "state"
        self.instance_dir = self.root / provided.INSTANCE
        self.instance_dir.mkdir(parents=True, mode=0o700)
        self.root.chmod(0o700)
        self.instance_dir.chmod(0o700)
        self.identity = FreshGuestIdentity(
            instance_id=provided.INSTANCE, workspace=str(base),
            vmx=str(base / "fresh.vmx"),
            subnet="172.28.232.0/24", source_commit="c" * 40,
        )
        self.context = SimpleNamespace(
            identity=self.identity, expected_address="172.28.232.31",
            management_address="172.28.233.31",
            private_vars=base / "private-vars.yml",
        )
        first = provided._base_state(self.context)
        first.update(status="BLOCKED", source_commit="a" * 40,
                     inflight={"number": 1, "stage": "apply"})
        self.original = self.instance_dir / "provided-install.blocked-stage1.json"
        self._write(self.original, first)
        prior = {
            "kind": "one-time-empty-stage1",
            "archived_sha256": hashlib.sha256(self.original.read_bytes()).hexdigest(),
            "archived_source_commit": "a" * 40,
            "new_source_commit": "b" * 40,
            "windows_absence_rechecked": True,
            "ansible_syntax_check": "PASS",
        }
        self._write(self.instance_dir / "stage1-recovery-intent.json", prior)
        failed = provided._base_state(self.context)
        failed.update(status="BLOCKED", source_commit="b" * 40,
                      inflight={"number": 1, "stage": "apply"},
                      failure_class="InstallBlocked",
                      failure_gate="Scenario #1 apply: Ansible rc=2; last_task=Refuse source-visible fixture credentials in any non-status action; stdout_sha256_prefix=112233445566",
                      recovery=prior)
        self.journal = self.instance_dir / "provided-install.json"
        self._write(self.journal, failed)
        self.raw = self.journal.read_bytes()
        self.first_raw = self.original.read_bytes()

    def _write(self, path, value):
        path.write_text(json.dumps(value, sort_keys=True))
        path.chmod(0o600)

    def _audit(self, *, report, evidence_out):
        evidence_out.update({
            "service_exists": False,
            "service_matches_expected": False,
            "scenario_directory_exists": False,
            "service_executable_exists": False,
            "candidate_exists": False,
        })
        return False

    def setup_mocks(self, *, audit_result=None, guard_ok=True, syntax_rc=0):
        from contextlib import ExitStack
        stack=ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(provided, "STATE_ROOT", self.root))
        stack.enter_context(patch.object(provided, "_preflight",
                                         return_value=(self.context, "operator", "learner")))
        stack.enter_context(patch.object(provided, "_stages", return_value=(
            SimpleNamespace(number=1, stage="apply", transport="ansible", argv=(
                "/tmp/ansible-playbook", "-i", "/tmp/inventory", "--limit",
                "ws01,localhost", "/tmp/playbook.yml",
                "-e", "@" + str(self.context.private_vars), "-e", "{}")),
        )))
        stack.enter_context(patch.object(audit, "inspect",
                                         side_effect=audit_result or self._audit))
        guard = stack.enter_context(patch.object(probe, "prove",
                                                 return_value=guard_ok))
        stack.enter_context(patch("kingdoms.wslpe41_stage_executor._environment",
                                  return_value={}))
        stack.enter_context(patch("kingdoms.wslpe41_stage_executor._inventory"))
        run = stack.enter_context(patch.object(provided.subprocess, "run",
                                               return_value=SimpleNamespace(
                                                   returncode=syntax_rc, stdout="", stderr="")))
        installer = stack.enter_context(patch.object(provided, "_install_steps",
                                                     return_value="PAUSED"))
        return guard, run, installer

    def test_second_recovery_preserves_two_archives_and_permanent_intent(self):
        guard, run, installer = self.setup_mocks()
        self.assertEqual(provided.recover_private_fixture_guard_stage1(), "PAUSED")
        second = self.instance_dir / "provided-install.blocked-fixture-stage1.json"
        intent = self.instance_dir / "private-fixture-recovery-intent.json"
        self.assertEqual(second.read_bytes(), self.raw)
        self.assertEqual(self.original.read_bytes(), self.first_raw)
        self.assertTrue(intent.is_file())
        record = json.loads(self.journal.read_text())
        self.assertEqual(record["next_stage"], 0)
        self.assertEqual(record["recovery"]["kind"], "one-time-private-fixture-guard-stage1")
        self.assertEqual(record["recovery"]["second_blocked_sha256"],
                         hashlib.sha256(self.raw).hexdigest())
        guard.assert_called_once()
        self.assertIn("--syntax-check", run.call_args.args[0])
        installer.assert_called_once()
        with self.assertRaisesRegex(InstallBlocked, "already attempted"):
            provided.recover_private_fixture_guard_stage1()

    def test_fixture_guard_failed_preserves_all_journals(self):
        guard, run, installer = self.setup_mocks(guard_ok=False)
        with self.assertRaisesRegex(InstallBlocked, "not proven"):
            provided.recover_private_fixture_guard_stage1()
        self.assertEqual(self.journal.read_bytes(), self.raw)
        self.assertFalse((self.instance_dir/"private-fixture-recovery-intent.json").exists())
        run.assert_not_called()
        installer.assert_not_called()

    def test_changed_failure_gate_never_authorized(self):
        current = json.loads(self.journal.read_text())
        current["failure_gate"] = "Scenario #1 apply: Ansible rc=2; last_task=other"
        self._write(self.journal, current)
        guard, run, installer = self.setup_mocks()
        with self.assertRaisesRegex(InstallBlocked, "twice-blocked"):
            provided.recover_private_fixture_guard_stage1()
        guard.assert_not_called()
        run.assert_not_called()
        installer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
