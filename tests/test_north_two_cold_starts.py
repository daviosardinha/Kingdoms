"""Guarded NORTH evidence + two cold-start runner, no live VMware access."""
from pathlib import Path
import ast
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/north-preserve-two-cold-starts.sh"


class NorthTwoColdStartsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = SCRIPT.read_text(encoding="utf-8")

    def test_shell_syntax_and_embedded_python(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        blocks = re.findall(r"<<'PY'\n(.*?)\nPY(?:\n|$)", self.src, re.S)
        self.assertEqual(len(blocks), 1)
        for block in blocks:
            ast.parse(block)

    def test_usage_refuses_implicit_cold_starts(self):
        for argv in ([], ["8aafc9-north-vmware"],
                     ["8aafc9-north-vmware", "--run"]):
            result = subprocess.run(["bash", str(SCRIPT), *argv],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("--confirm-two-cold-starts", result.stderr)

    def test_baseline_evidence_then_exactly_two_cycles(self):
        s = self.src
        expected = [
            "stage 00-source bash scripts/verify-test-source.sh",
            "stage 01-owner sudo -n bash scripts/setup-vmware-networks.sh",
            "validate 02-baseline-health",
            "preserve\n",
            "capture 03-before",
            "for cycle in 1 2;",
            'native stop "cold-$cycle-stop"',
            "all_stopped ||",
            'native start "cold-$cycle-start"',
            'validate "cold-$cycle-health"',
            "stage 04-owner-final",
            "NORTH_REPEATED_COLD_START=PASS",
        ]
        positions = [s.index(x) for x in expected]
        self.assertEqual(positions, sorted(positions))

    def test_scope_failclosed_evidence_and_no_snapshots(self):
        s = self.src
        for marker in (
            'ID="8aafc9-north-vmware"',
            'set -Eeuo pipefail',
            ".course1-phase03-acceptance.lock",
            "flock -n 9",
            "NORTH_REPEATED_COLD_START=NOT_CERTIFIED",
            "NORTH_RUNTIME_ACCEPTANCE=PASS",
            "instance status is installed",
            "NORTH_EVIDENCE_PRESERVED",
            "north-recovered-validation-20261025-120457.log",
            "capture failure-state",
            "NORTH_SNAPSHOT_RESTORE=NOT_TESTED",
            "NORTH_TWO_COLD_STARTS=PASS",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, s)
        for prohibited in (
            "native snapshot ", "native reset ", "-t install",
            "-t destroy", "vagrant snapshot", "vagrant up",
            "vmrun -T ws stop", "vmrun -T ws start",
            "rm -rf", "shutil.rmtree",
            "timeout bash ./goad.sh",
        ):
            with self.subTest(prohibited=prohibited):
                self.assertNotIn(prohibited, s)


if __name__ == "__main__":
    unittest.main()
