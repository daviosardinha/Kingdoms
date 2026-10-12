"""Offline contract: capture and rollback must read one exact baseline path."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]

class RBCDBaselinePathTests(unittest.TestCase):
    def test_script_syntax_and_same_path_contract(self):
        for name in ("capture-rbcd-baseline.sh", "rollback-rbcd.sh"):
            file = ROOT / "scripts" / "phase03" / name
            check = subprocess.run(["bash", "-n", str(file)], capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertIn('export KINGDOMS_PHASE03_RBCD_BASELINE="$BASELINE"', file.read_text())

    def test_wrappers_resolve_the_same_environment_fallback(self):
        for name in ("capture-rbcd-baseline.sh", "rollback-rbcd.sh"):
            src = (ROOT / "scripts" / "phase03" / name).read_text()
            self.assertIn('BASELINE="${BASELINE:-${KINGDOMS_PHASE03_RBCD_BASELINE:-', src)

    def test_playbooks_use_one_explicit_environment_path(self):
        for name in ("phase03-rbcd-baseline.yml", "phase03-rbcd-rollback.yml"):
            src = (ROOT / "ansible" / name).read_text()
            self.assertIn("lookup('env','KINGDOMS_PHASE03_RBCD_BASELINE')", src)
            self.assertIn("phase03_rbcd_baseline_path", src)
        self.assertIn(
            'dest: "{{ phase03_rbcd_baseline_path }}"',
            (ROOT / "ansible/phase03-rbcd-baseline.yml").read_text(),
        )
