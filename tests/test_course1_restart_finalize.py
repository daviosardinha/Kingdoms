"""Source checks for read-only NORTH restart evidence reconciliation."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/course1-restart-finalize.sh"


class Course1RestartFinalizeTests(unittest.TestCase):
    def test_parser_and_arguments(self):
        check = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stderr)
        invalid = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(invalid.returncode, 2)

    def test_never_mutates_lab_or_overwrites_original_summary(self):
        source = SCRIPT.read_text()
        for forbidden in (
            "goad.sh", "vmrun ", "git fetch", "git pull", "--north apply",
            "snapshot pop", "snapshot push", "-t stop", "-t reset", "-t start",
        ):
            # Comments explaining absence of mutation are not executable.
            executable = "\n".join(x for x in source.splitlines() if not x.lstrip().startswith("#"))
            self.assertNotIn(forbidden, executable)
        self.assertIn("reconciled-recovery-acceptance.txt", source)
        self.assertIn('refusing overwrite', source)

    def test_requires_original_failure_and_independent_restored_pass(self):
        source = SCRIPT.read_text()
        for required in (
            'PASS | $stage |',
            'FAIL | restored-readiness rc=1',
            'RESTART_RESTORE_RELIABILITY=NOT_CERTIFIED',
            'Could not resolve host: github.com',
            'PHASE03_READONLY_ACCEPTANCE=PASS',
            '"$NEW" -nt "$OLD"',
            "== 11",
            '00-owner.log',
            'NORTH_REPEATED_COLD_START=PASS',
            'NORTH_SNAPSHOT_RESTORE=PASS',
            'NORTH_POST_RESTORE_READINESS=PASS',
            'RESTART_RESTORE_RELIABILITY=PASS',
            'RECOVERY_EVIDENCE_RECONCILIATION=PASS',
        ):
            with self.subTest(required=required):
                self.assertIn(required, source)
