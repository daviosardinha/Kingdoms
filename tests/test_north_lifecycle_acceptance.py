"""NORTH lifecycle qualification source contract. No live VM actions."""
from pathlib import Path
import ast
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts/north-lifecycle-acceptance.sh"


class NorthLifecycleAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = TARGET.read_text(encoding="utf-8")

    def test_shell_and_python_syntax(self):
        run = subprocess.run(["bash","-n",str(TARGET)],capture_output=True,text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        scripts = re.findall(r"<<'PY'\n(.*?)\nPY(?:\n|$)", self.script, re.S)
        self.assertEqual(len(scripts),2)
        for body in scripts:
            ast.parse(body)

    def test_explicit_authorization_evidence_lock_and_no_external_timeout(self):
        for word in (
            "--confirm-restore-data-loss", ".course1-phase03-acceptance.lock",
            "flock -n 9", "verify-test-source.sh", "--north verify",
            "NORTH_RUNTIME_ACCEPTANCE=PASS", "NORTH_LIFECYCLE_RELIABILITY=PASS",
            "RESTART_RESTORE_RELIABILITY=PASS",
            "RESTART_RESTORE_RELIABILITY=NOT_CERTIFIED",
            'native() {', 'sudo -n -v', 'native reset 05-snapshot-restore',
        ):
            self.assertIn(word, self.script)
        self.assertNotIn("timeout bash ./goad.sh", self.script)
        self.assertNotIn("vagrant snapshot pop", self.script)
        self.assertNotIn("vmrun -T ws revertToSnapshot", self.script)
        self.assertNotIn("rm -rf", self.script)
        self.assertNotIn("-t install",self.script)
        self.assertNotIn("-t destroy",self.script)

    def test_ordered_two_cold_start_cycles_snapshot_restore_and_checks(self):
        stages=[
            "validate 02-initial-health",
            'for cycle in 1 2;',
            'native stop "cold-$cycle-stop"',
            'stopped',
            'native start "cold-$cycle-start"',
            'validate "cold-$cycle-health"',
            "native snapshot 03-snapshot-create",
            "validate 04-post-snapshot-health",
            "NORTH_SNAPSHOT_CREATE=PASS",
            "native reset 05-snapshot-restore",
            "validate 06-post-restore-health",
            "NORTH_SNAPSHOT_RESTORE=PASS",
            "RESTART_RESTORE_RELIABILITY=PASS",
        ]
        positions=[self.script.index(marker) for marker in stages]
        self.assertEqual(positions,sorted(positions))
        self.assertIn('set -Eeuo pipefail',self.script)
        self.assertIn('len(new)!=len(old)+1',self.script)
        self.assertIn('not vmx.resolve().is_relative_to(vm_dir.resolve())',self.script)

    def test_help_refuses_implicit_lifecycle_actions(self):
        for args in ([], ["57bbec-north-vmware"], ["57bbec-north-vmware","--run"]):
            r=subprocess.run(["bash",str(TARGET),*args],capture_output=True,text=True)
            self.assertEqual(r.returncode,2)
            self.assertIn("--confirm-restore-data-loss",r.stderr)


if __name__ == "__main__":
    unittest.main()
