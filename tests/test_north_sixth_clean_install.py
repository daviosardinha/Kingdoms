"""Static safety contracts for the destructive sixth clean NORTH repro runner.

Source-only: never execute VMware, Vagrant, host network or installer actions
in CI. Live teardown requires exact operator confirmation and host owner proof.
"""
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "north-sixth-clean-reinstall.sh"


class SixthNorthReproTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = RUNNER.read_text(encoding="utf-8")

    def test_bash_syntax_and_destructive_confirmation(self):
        result = subprocess.run(["bash", "-n", str(RUNNER)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(["bash", str(RUNNER)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("confirm-retire-bb3baf-and-reinstall", result.stderr)

    def test_exact_instance_and_previous_verified_backup_are_pinned(self):
        src = self.script
        self.assertIn('OLD="bb3baf-north-vmware"', src)
        self.assertIn("8aafc9-north-l37plsk3", src)
        self.assertIn("backup-verified.marker", src)
        self.assertIn("other-artifacts.sha256", src)
        self.assertIn("sha256sum -c other-artifacts.sha256", src)
        self.assertIn("original", src)
        self.assertIn("NORTH", src)
        self.assertIn('"not provided"', src)
        self.assertIn("GOAD-WS01", src)
        self.assertIn("GOAD-ROUTER", src)
        self.assertIn("No foreign", src.replace("no foreign", "No foreign") if False else
                      "No foreign" if "No foreign" in src else "Foreign running")
        self.assertNotIn("scripts/north-fifth-clean-install.sh", src)
        self.assertNotIn("scripts/north-one-shot-clean-reinstall.sh", src)

    def test_every_destructive_step_is_sequential_and_guarded(self):
        src = self.script
        order = [
            'bash scripts/verify-test-source.sh',
            'EXACT_FIFTH_NORTH_INSTANCE_AND_NO_FOREIGN_GUEST_CONFLICTS',
            'EXACT_NORTH_VMNET_OWNER',
            'PRIOR_FAILURE_EVIDENCE_PRESERVED',
            'stage 01-destroy-fifth',
            'ALL_FIFTH_NORTH_VMWARE_GUESTS_REMOVED',
            'stage 03-owner-retirement-plan',
            'stage 04-retire-north-vmnets',
            'FAILED_FIFTH_WORKSPACE_ARCHIVED',
            'stage 06-new-clean-install',
            'stage 08-new-runtime-validation',
        ]
        locations = [src.index(item) for item in order]
        self.assertEqual(locations, sorted(locations))
        self.assertIn('flock -n 9', src)
        self.assertIn('flock -u 9', src)
        self.assertIn("north-install-exclusive.lock", src)
        self.assertIn("vmrun", src)
        self.assertIn("inventory.vmls", src)
        self.assertIn("vmnet10", src)
        self.assertIn("vmnet20", src)
        self.assertIn("vmnet99", src)
        self.assertIn("course1_network_retire plan", src)
        self.assertIn("course1_network_retire apply", src)
        self.assertIn("scripts/north-install-observed.sh --new", src)
        self.assertIn('NORTH_RUNTIME_ACCEPTANCE=PASS', src)
        self.assertNotIn("rm -rf", src)
        self.assertNotIn("sudo rm", src)
        self.assertNotIn("git clean", src)
        self.assertNotIn("git reset --hard", src)
        self.assertNotIn("vmnet8", re.sub(r"#.*", "", src))

    def test_source_validation_rejects_untracked_or_modified_files(self):
        src = self.script
        self.assertIn('git status --porcelain --untracked-files=all', src)
        self.assertIn("verify-test-source.sh", src)
        self.assertIn("NORTH-owned", src)
        self.assertIn("provider_success", src)
        self.assertIn("install-timings", src)
        self.assertIn('"exercise"', src)

    def test_workspace_is_archived_not_deleted(self):
        self.assertIn('mv -- "$INSTANCE" "$EVIDENCE/retired-fifth-workspace"', self.script)
        self.assertNotIn("shutil.rmtree", self.script)
        self.assertNotIn("delete_old_workspace", self.script)


if __name__ == "__main__":
    unittest.main()
