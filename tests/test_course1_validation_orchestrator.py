"""Regression contract for the one-command NORTH source and host validator.

Only shell -n and --help are executed, never any live validation stage.
"""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate-course1.sh"


class Course1UnifiedValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_bash_syntax(self):
        completed = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            capture_output=True, text=True, check=False, timeout=8,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_help_is_available_without_git_or_vmware(self):
        completed = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            cwd=ROOT, capture_output=True, text=True, check=False, timeout=8,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--skip-host", completed.stdout)
        self.assertIn("READ-ONLY", completed.stdout.upper())

    def test_dynamically_discovers_every_python_unit_test(self):
        self.assertIn("python3 -m unittest discover -s tests -p 'test_*.py'",
                      self.source)
        self.assertIn('Path("tests").glob("test_*.py")', self.source)

    def test_preserves_kingdoms_original_source_validation(self):
        self.assertIn("scripts/verify-test-source.sh", self.source)
        self.assertIn("scripts/validate-goad-kingdoms-install-source.sh",
                      self.source)
        self.assertIn("python3 -m goad.course1_source_preflight", self.source)

    def test_checks_default_and_alternate_network_topologies(self):
        for required in (
            "10.5.0.0/16", "north=11", "sevenkingdoms=21", "management=98",
            "goad.kingdoms_topology", "goad.course1_artifact_render",
            "provisioning-routes.sh --north plan",
            "setup-vmware-networks.sh --north plan",
            "setup-vmware-networks.sh --north hostaddr-plan",
        ):
            self.assertIn(required, self.source)

    def test_clean_host_check_is_the_last_validation_stage(self):
        live = self.source.index(
            'stage "Live READ-ONLY clean-host vmnet/IP/VMX collision check"'
        )
        self.assertIn("python3 -m goad.course1_network_preflight",
                      self.source[live:])
        self.assertNotIn("\nstage ", self.source[live + 6:])
        self.assertIn("if (( SKIP_HOST )); then", self.source)

    def test_no_vm_network_or_systemd_mutating_actions(self):
        for dangerous in (
            "vmware-networks --start", "vmware-networks --stop",
            "vagrant up", "vagrant destroy", "systemctl start",
            "ip route add", "ip -4 addr add", "iptables -A",
            "nft -f", "ansible-playbook ",
        ):
            self.assertNotIn(dangerous, self.source)
        self.assertIn("Runtime VM creation and network writes: DISABLED",
                      self.source)

    def test_failing_stage_retains_log_and_halts(self):
        self.assertIn('FAILURE=1', self.source)
        self.assertIn('tail -n 100 "$logfile"', self.source)
        self.assertIn('log directory: %s', self.source)
        self.assertIn('exit 1', self.source)
        self.assertIn("trap cleanup EXIT", self.source)

    def test_source_only_mode_skips_live_vmware_inspection(self):
        self.assertIn("--skip-host|--source-only) SKIP_HOST=1", self.source)
        self.assertIn("if (( SKIP_HOST )); then", self.source)
        self.assertIn("Live clean-host collision check", self.source)

    def test_unknown_argument_fails_before_ever_reaching_live_host(self):
        completed = subprocess.run(
            ["bash", str(SCRIPT), "--bad-option"],
            cwd=ROOT, capture_output=True, text=True, check=False, timeout=8,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("Unknown argument", completed.stderr)


if __name__ == "__main__":
    unittest.main()
