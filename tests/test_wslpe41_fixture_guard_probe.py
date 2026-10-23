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
        self.assertEqual(args[0:4], [str(self.context.ansible), "-i", "localhost,", "--check"])
        self.assertEqual(args[args.index("--limit")+1], "localhost")
        self.assertEqual(args.count("@" + str(self.context.private_vars)), 1)
        self.assertEqual(args.count("-e"), 2)
        self.assertIn("[PASS] Actual controller-only fixture guard with private overlay", output)
        self.assertEqual(self.journal.read_bytes(), self.old)
        inventory.assert_called_once()

    def test_temp_controller_play_is_assert_only_without_secret_copy(self):
        import yaml
        original = self.journal.read_bytes()
        captured = []
        def inspect_command(args, **kwargs):
            source = Path(args[args.index("--limit") + 2])
            assert source.name == "controller-only.yml"
            assert source.exists()
            assert source.stat().st_mode & 0o077 == 0
            content = source.read_text()
            assert "Exercise the shared Windows LPE role" not in content
            assert "operator" not in content.lower()
            assert "windows_lpe_unattend_credentials" in content
            doc = yaml.safe_load(content)
            assert len(doc) == 1
            assert doc[0]["hosts"] == "localhost"
            assert doc[0]["vars"]["ansible_connection"] == "local"
            assert all("ansible.builtin.assert" in item for item in doc[0]["tasks"])
            checks = [t for t in doc[0]["tasks"]
                      if t["name"].startswith("Private fixture check ")]
            assert len(checks) == 8
            assert all(t.get("no_log") is True for t in checks)
            assert checks[0]["name"] == "Private fixture check PRIVATE_FIXTURE_FLAG"
            assert checks[-1]["name"] == "Private fixture check STORED_WINLOGON_FIXTURE_DEFINED"
            assert all(len(t["ansible.builtin.assert"]["that"]) == 1 for t in checks)
            captured.append(source)
            return SimpleNamespace(returncode=0, stderr="", stdout=(
                "TASK [Refuse source-visible fixture credentials in any non-status action]\\n"
                "TASK [Require the local learner secret for technique application]\\n"))
        self._run()
        with patch.object(probe.subprocess, "run", side_effect=inspect_command):
            self.assertTrue(probe.prove(report=lambda _: None))
        self.assertEqual(len(captured), 1)
        self.assertFalse(captured[0].exists())
        self.assertEqual(self.journal.read_bytes(), original)

    def test_early_ansible_failure_is_categorized_without_raw_stderr(self):
        diagnostic = probe._safe_ansible_failure(
            "ERROR! couldn't resolve module/action 'fake_module' "
            "secret-token-12345", "")
        self.assertIn("ANSIBLE_MODULE_UNAVAILABLE", diagnostic)
        self.assertNotIn("secret-token", diagnostic)
        self.assertIn("stderr_sha256=", diagnostic)

    def test_failed_controller_guard_blocks_without_journal_write(self):
        runner, _ = self._run(returncode=2, stdout=(
            "TASK [Refuse source-visible fixture credentials in any non-status action]\n"))
        with self.assertRaisesRegex(InstallBlocked, "controller-only Ansible fixture guard FAILED"):
            probe.prove()
        self.assertEqual(self.journal.read_bytes(), self.old)

    def test_sensitive_failed_condition_is_identified_without_secret_content(self):
        self._run(returncode=2, stdout=(
            "TASK [Private fixture check INSTANCE_IDENTITY_MATCH]\n"
            "fatal: [localhost]: FAILED! => censored\n"))
        with self.assertRaisesRegex(
            InstallBlocked, "failed_condition=INSTANCE_IDENTITY_MATCH"
        ) as raised:
            probe.prove()
        self.assertNotIn("password", str(raised.exception).lower())

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
