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

    def test_north_rbcd_preparation_shell_syntax_and_confirmation(self):
        for path in (
            "scripts/course1-phase03-acceptance.sh",
            "scripts/course1-phase03-rbcd-baseline.sh",
        ):
            check = subprocess.run(
                ["bash", "-n", str(ROOT / path)], capture_output=True, text=True
            )
            self.assertEqual(check.returncode, 0, check.stderr)
        invalid = subprocess.run(
            ["bash", str(ROOT / "scripts/course1-phase03-acceptance.sh"),
             "ac9fda-north-vmware", "--prepare-rbcd"],
            capture_output=True, text=True
        )
        self.assertEqual(invalid.returncode, 2)

    def test_rbcd_prepare_uses_private_per_run_capture_and_exact_inventory(self):
        runner = (ROOT / "scripts/course1-phase03-rbcd-baseline.sh").read_text()
        acceptance = (ROOT / "scripts/course1-phase03-acceptance.sh").read_text()
        self.assertIn("--prepare-rbcd --confirm", acceptance)
        self.assertIn('exec bash scripts/course1-phase03-rbcd-baseline.sh "$INSTANCE" --capture --confirm', acceptance)
        for token in (
            '.course1-phase03-acceptance.lock', 'flock -n 9',
            'scripts/course1-phase03-preflight.sh',
            "PHASE03_READONLY_ACCEPTANCE=PASS",
            'INSTANCE_INVENTORY="$ROOT/workspace/$INSTANCE/inventory"',
            'DATA_INVENTORY="$ROOT/ad/NORTH/data/inventory"',
            'mktemp -d',
            'chmod 700 "$EVIDENCE"',
            'KINGDOMS_PHASE03_RBCD_BASELINE="$BASELINE"',
            'scripts/phase03/capture-rbcd-baseline.sh',
            "PHASE03_RBCD_EXISTING=False",
            "PHASE03_RBCD_CANDIDATE_EXISTS=False",
            "PHASE03_RBCD_SELF_CAN_WRITE=True",
            "PHASE03_RBCD_BASELINE_CAPTURE=PASS",
            "PHASE03_RBCD_ACTIVE_ACCEPTANCE=NOT_TESTED",
            "sha256sum",
        ):
            with self.subTest(token=token):
                self.assertIn(token, runner)

    def test_rbcd_capture_does_not_claim_active_proof(self):
        runner = (ROOT / "scripts/course1-phase03-rbcd-baseline.sh").read_text()
        for forbidden in (
            "start-rbcd-stage1-add-computer.sh", "rollback-rbcd.sh",
            "prove-rbcd-s4u.sh", "--run-rbcd",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, runner)
        acceptance = (ROOT / "scripts/course1-phase03-acceptance.sh").read_text()
        self.assertNotIn("--run-rbcd", acceptance)
