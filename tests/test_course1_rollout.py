"""Source-only regressions for the five-stage, single-entrypoint NORTH gate.

Never run the real validator or invoke VMware/Ansible from this unit suite.
"""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/course1-rollout.sh"


class Course1RolloutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SCRIPT.read_text(encoding="utf-8")

    def run_mode(self, *args):
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=ROOT, capture_output=True, text=True, timeout=12, check=False,
        )

    def test_bash_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT)], capture_output=True, text=True,
            timeout=8, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_plan_reports_all_five_gates_and_fails_closed(self):
        result = self.run_mode("--plan")
        self.assertEqual(result.returncode, 3, result.stderr)
        for index in range(1, 6):
            self.assertIn(f"[{index:02d}]", result.stdout)
        self.assertIn("LIVE APPLY BLOCKED", result.stdout)
        self.assertIn("NOT EXECUTED", result.stdout)
        self.assertIn("No VMware, Vagrant, Ansible", result.stdout)

    def test_deploy_refuses_without_running_validator(self):
        result = self.run_mode("--deploy")
        self.assertEqual(result.returncode, 3)
        self.assertIn("deployment remains disabled", result.stderr)
        self.assertNotIn("UNIFIED SOURCE & HOST VALIDATION", result.stdout)

    def test_help_documents_single_command_and_safety(self):
        result = self.run_mode("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--all", result.stdout)
        self.assertIn("--prepare", result.stdout)
        self.assertIn("--source", result.stdout)
        self.assertIn("--plan", result.stdout)
        self.assertIn("--deploy", result.stdout)
        self.assertIn("NEVER creates VMs", result.stdout)

    def test_invalid_arguments_do_not_execute_any_actions(self):
        for args in [("--unknown",), ("--plan", "--deploy")]:
            with self.subTest(args=args):
                result = self.run_mode(*args)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("UNIFIED SOURCE & HOST VALIDATION", result.stdout)

    def test_all_and_source_reuse_existing_complete_validation(self):
        self.assertIn("bash scripts/validate-course1.sh\n", self.text)
        self.assertIn("bash scripts/validate-course1.sh --skip-host", self.text)
        self.assertIn("def _course1_unwired(self):", self.text)
        self.assertIn("return self.lab_name in ('GOAD', 'NORTH')", self.text)

    def test_prepare_reuses_full_validator_before_existing_instance_manager(self):
        self.assertIn('--all || "$MODE" == --prepare', self.text)
        self.assertIn('bash ./goad.sh -t prepare-north -l NORTH -p vmware', self.text)
        self.assertLess(
            self.text.index('bash scripts/validate-course1.sh'),
            self.text.index('bash ./goad.sh -t prepare-north -l NORTH -p vmware'),
        )
        self.assertNotIn('--north apply', self.text)

    def test_no_live_mutating_commands_exist(self):
        for token in (
            "vmware-networks --stop", "vmware-networks --start",
            "vagrant up", "vagrant destroy", "systemctl enable",
            "systemctl start", "ip route add", "ip addr add",
            "ansible-playbook ", "sudo ",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, self.text)


if __name__ == "__main__":
    unittest.main()
