"""Source-only regression for read-only NORTH restart/snapshot inventory."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/course1-restart-preflight.sh"


class Course1RestartPreflightTests(unittest.TestCase):
    def test_shell_syntax(self):
        check = subprocess.run(
            ["bash", "-n", str(SCRIPT)], capture_output=True, text=True
        )
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_requires_selected_installed_north_instance(self):
        invalid = subprocess.run(
            ["bash", str(SCRIPT)], capture_output=True, text=True
        )
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("NORTH-instance-id", invalid.stderr)

    def test_reuses_original_owner_and_single_run_lock(self):
        text = SCRIPT.read_text()
        for marker in (
            "scripts/course1-rollout.sh --installed",
            ".course1-phase03-acceptance.lock",
            "flock -n 9",
            '"$MODE")" == exercise',
            "sudo -n -v",
            "GOAD_LAB_PROFILE=NORTH GOAD_PROVIDER_DIR=",
            "scripts/lab-mode.sh status",
            "NORTH_RESTART_PREFLIGHT=PASS",
            "NORTH_SNAPSHOT_RESTORE=NOT_TESTED",
            "NORTH_REPEATED_COLD_START=NOT_TESTED",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_inventory_exactly_four_windows_and_router(self):
        text = SCRIPT.read_text()
        self.assertIn(
            "for machine in GOAD-DC01 GOAD-DC02 GOAD-SRV02 GOAD-WS01 GOAD-ROUTER;",
            text
        )
        self.assertNotIn("GOAD-DC03", text)
        self.assertNotIn("GOAD-SRV03", text)
        self.assertIn("vmrun -T ws listSnapshots", text)
        self.assertIn("count >= 1", text)
        self.assertIn('ethernet0\\.startConnected', text)

    def test_inspect_never_changes_vm_or_snapshot_state(self):
        text = SCRIPT.read_text()
        for forbidden in (
            "vmrun -T ws start", "vmrun -T ws stop",
            "vmrun -T ws revertToSnapshot", "snapshot pop",
            "snapshot delete", "scripts/lab-mode.sh exercise",
            "scripts/lab-mode.sh provisioning", "-t reset", "-t stop", "-t start",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)
