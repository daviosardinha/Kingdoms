import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WpadRestoreSourceTests(unittest.TestCase):
    def setUp(self):
        self.script = (ROOT / "scripts" / "phase03" / "restore-wpad-baseline.sh").read_text()

    def test_restore_is_bounded_and_uses_exact_baseline_as_success_oracle(self):
        for token in (
            'WPAD_RESTORE_ATTEMPTS:-2',
            'WPAD_RESTORE_TIMEOUT_SECONDS:-60',
            'WPAD_VERIFY_TIMEOUT_SECONDS:-45',
            'phase03-wpad-restore-baseline.yml',
            'verify-wpad-reset.sh',
            'PHASE03_WPAD_RESTORE_COMPLETE=True',
            'exact verification remains authoritative',
        ):
            self.assertIn(token, self.script)

        self.assertIn('case "$restore_rc" in', self.script)
        self.assertIn('124|137)', self.script)
        self.assertIn('if timeout --kill-after=5 "$VERIFY_TIMEOUT_SECONDS" bash "$VERIFY_SCRIPT"; then', self.script)
        self.assertNotIn('phase03-trigger-ws01-renew6.yml', self.script)

    def test_restore_refuses_to_run_while_mitm6_is_active(self):
        self.assertIn("mitm6 is still active; stop the WPAD attack runtime before restoring WS01", self.script)

    def test_restore_does_not_modify_lab_lifecycle_or_ipv4(self):
        for forbidden in (
            "lab-mode.sh",
            "Restart-Computer",
            "shutdown.exe",
            "Disable-NetAdapter",
            "Enable-NetAdapter",
            "Set-NetIPAddress",
            "New-NetIPAddress",
            "Remove-NetIPAddress",
            "vmrun",
        ):
            self.assertNotIn(forbidden, self.script)

    def test_restore_shell_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(ROOT / "scripts" / "phase03" / "restore-wpad-baseline.sh")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
