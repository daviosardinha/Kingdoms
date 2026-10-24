"""Offline release guard for NORTH domain-time restart forensics.

No VM state change is authorized by diagnostic collection.
"""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY = (
    "scripts/diagnostics/diagnose-srv02-domain-time.sh",
    "scripts/diagnostics/diagnose-north-timeserv-advertising.sh",
    "scripts/diagnostics/diagnose-forest-root-time.sh",
)
RUNNER = "scripts/course1-diagnose-domain-time.sh"


class Course1TimeDiagnosticsTests(unittest.TestCase):
    def test_diagnostic_entrypoints_parse_as_bash(self):
        for path in (RUNNER, *LEGACY):
            with self.subTest(path=path):
                proc = subprocess.run(
                    ["bash", "-n", str(ROOT / path)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_existing_full_kingdoms_diagnostics_accept_explicit_north_inventory(self):
        for path in LEGACY:
            with self.subTest(path=path):
                script = (ROOT / path).read_text(encoding="utf-8")
                self.assertIn(
                    'DATA_INVENTORY="${KINGDOMS_DIAG_DATA_INVENTORY:-$ROOT/ad/GOAD/data/inventory}"',
                    script,
                )
                self.assertIn(
                    'PROVIDER_INVENTORY="${KINGDOMS_DIAG_PROVIDER_INVENTORY:-$ROOT/ad/GOAD/providers/vmware/inventory}"',
                    script,
                )
                self.assertIn('-i "$DATA_INVENTORY"', script)
                self.assertIn('-i "$PROVIDER_INVENTORY"', script)
                self.assertIn('changed_when: false', script)

    def test_north_diagnostic_runner_targets_only_existing_instance(self):
        script = (ROOT / RUNNER).read_text(encoding="utf-8")
        self.assertIn('KINGDOMS_DIAG_DATA_INVENTORY="$ROOT/ad/NORTH/data/inventory"', script)
        self.assertIn('KINGDOMS_DIAG_PROVIDER_INVENTORY="$ROOT/workspace/$INSTANCE/inventory"', script)
        self.assertIn('GOAD_LAB_PROFILE=NORTH', script)
        self.assertIn('GOAD_PROVIDER_DIR="$PROVIDER"', script)
        self.assertIn('scripts/lab-mode.sh', script)
        for path in LEGACY:
            self.assertIn(path, script)
        self.assertIn('NOTE: A diagnostic collection PASS is not a domain-time readiness PASS.', script)
        self.assertIn('north-domain-time-', script)

    def test_diagnostic_batch_does_not_reconfigure_windows_or_change_network_mode(self):
        script = (ROOT / RUNNER).read_text(encoding="utf-8")
        for action in (
            "enter_exercise_mode", "enter_provisioning_mode",
            "w32tm.exe /resync", "w32tm.exe /config",
            "Restart-Service", "Set-Service", "Set-ItemProperty",
            "snapshot push", "snapshot pop", "vagrant up",
            "scripts/lab-mode.sh exercise",
            "scripts/lab-mode.sh provisioning",
            "scripts/provisioning-routes.sh --north enable",
            "scripts/provisioning-routes.sh --north disable",
        ):
            with self.subTest(action=action):
                self.assertNotIn(action, script)
        self.assertIn('bash "$file" status', script)
        self.assertIn('timeout 210 bash "$file"', script)


if __name__ == "__main__":
    unittest.main()
