"""Source tests: fixture overlay is proved through an Ansible localhost-only preflight."""
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from kingdoms import wslpe41_fixture_guard_probe as probe
from kingdoms import wslpe41_provided_install as provided
from kingdoms.wslpe41_install_flow import InstallBlocked


class FixtureGuardProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "state"
        self.journal = self.root / probe.INSTANCE / "provided-install.json"
        self.journal.parent.mkdir(parents=True)
        self.journal.write_text(json.dumps({
            "schema": probe.SCHEMA,
            "instance": probe.INSTANCE, "status": "BLOCKED", "next_stage": 0,
            "proofs": [], "inflight": {"number": 1, "stage": "apply"},
            "failure_gate": "Scenario #1 apply: Ansible rc=2; last_task=Refuse source-visible fixture credentials in any non-status action; stdout_sha256_prefix=123456789abc",
        }))
        self.old = self.journal.read_bytes()
        self.context = SimpleNamespace(
            ansible=Path("/tmp/test/ansible-playbook"),
            inventory=Path("/tmp/test/inventory.yml"),
            private_vars=Path("/tmp/test/private-vars.yml"),
            expected_address="172.28.232.31",
            management_address="172.28.233.31",
            identity=SimpleNamespace(instance_id=probe.INSTANCE),
        )

    def _run(self, *, returncode=0, stdout=None):
        if stdout is None:
            stdout = ("TASK [Require a single WSLPE target and exact approved action]\n"
                      "TASK [Restrict the unified fresh installer to its exact standalone Windows target]\n"
                      "TASK [Refuse source-visible fixture credentials in any non-status action]\n"
                      "TASK [Require the local learner secret for technique application]\n")
        from contextlib import ExitStack
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(probe, "STATE_ROOT", self.root))
        stack.enter_context(patch.object(probe, "_preflight",
                                         return_value=(self.context, "operator", "learner")))
        stack.enter_context(patch.object(probe, "_environment",
                                         return_value={"ANSIBLE_NOCOLOR": "1"}))
        inventory = stack.enter_context(patch.object(probe, "_inventory"))
        runner = stack.enter_context(patch.object(
            probe.subprocess, "run", return_value=SimpleNamespace(
                returncode=returncode, stdout=stdout, stderr="")))
        return runner, inventory

    def test_only_localhost_and_private_vars_with_no_guest(self):
        runner, inventory = self._run()
        output = []
        self.assertTrue(probe.prove(report=output.append))
        args = runner.call_args.args[0]
        self.assertEqual(args[0:2], [str(self.context.ansible), "--check"])
        self.assertEqual(args[args.index("--limit")+1], "localhost")
        self.assertEqual(args.count("@" + str(self.context.private_vars)), 1)
        self.assertEqual(args.count("-e"), 2)
        self.assertIn("[PASS] Actual controller-only fixture guard with private overlay", output)
        self.assertEqual(self.journal.read_bytes(), self.old)
        inventory.assert_called_once()

    def test_failed_controller_guard_blocks_without_journal_write(self):
        runner, _ = self._run(returncode=2, stdout=(
            "TASK [Refuse source-visible fixture credentials in any non-status action]\n"))
        with self.assertRaisesRegex(InstallBlocked, "controller-only Ansible fixture guard FAILED"):
            probe.prove()
        self.assertEqual(self.journal.read_bytes(), self.old)

    def test_unrelated_or_missing_journal_refused_without_ansible(self):
        runner, _ = self._run()
        info = json.loads(self.journal.read_text())
        info["inflight"]["number"] = 2
        self.journal.write_text(json.dumps(info))
        with self.assertRaisesRegex(InstallBlocked, "exact second blocked"):
            probe.prove()
        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
