"""Offline-pinned owner verification is for one already-attested recovery run."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/course1-pinned-installed-owner.sh"
PREFLIGHT = ROOT / "scripts/course1-phase03-preflight.sh"
ACCEPT = ROOT / "scripts/course1-restart-acceptance.sh"


class Course1PinnedRecoverySourceTests(unittest.TestCase):
    def test_scripts_parse(self):
        for script in (HELPER, PREFLIGHT, ACCEPT):
            with self.subTest(script=script):
                result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_helper_requires_a_full_pin_and_explicit_provider(self):
        for args in ([], ["/tmp/anything", "bad"], ["relative/provider", "a" * 40]):
            with self.subTest(args=args):
                result = subprocess.run(["bash", str(HELPER), *args], capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)

    def test_offline_pin_checks_source_drift_and_live_host_owner(self):
        text = HELPER.read_text()
        for marker in (
            'git rev-parse --verify HEAD',
            "git rev-parse --verify '@{upstream}'",
            'git status --porcelain=v1',
            'rebuild/course1-from-kingdoms',
            'scripts/setup-vmware-networks.sh --north verify',
            'NORTH_PINNED_LOCAL_SOURCE_AND_OWNER=PASS',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)
        self.assertNotIn("git fetch", text.split("for cmd in git sudo;", 1)[1])
        for mutation in ("-t reset", "-t start", "vmrun start", "vmrun stop", "--north apply"):
            self.assertNotIn(mutation, text)

    def test_phase03_default_online_and_scoped_pinned_override(self):
        text = PREFLIGHT.read_text()
        self.assertIn('scripts/course1-rollout.sh --installed "$PROVIDER"', text)
        self.assertIn('scripts/course1-pinned-installed-owner.sh "$PROVIDER" "$PINNED_HEAD"', text)
        self.assertIn('PINNED_HEAD=""', text)
        self.assertIn('--pinned-head', text)
        for args in (
            ["ac9fda-north-vmware", "--pinned-head"],
            ["ac9fda-north-vmware", "--pinned-head", "bad"],
        ):
            with self.subTest(args=args):
                result = subprocess.run(["bash", str(PREFLIGHT), *args], capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)

    def test_parent_attests_online_once_before_native_vm_mutations(self):
        text = ACCEPT.read_text()
        source = text.index('step 00-installed 650 bash scripts/course1-rollout.sh --installed')
        pin = text.index('PINNED_HEAD="$(git rev-parse --verify HEAD)"')
        first_vm = text.index("for cycle in 1 2;")
        self.assertLess(source, pin)
        self.assertLess(pin, first_vm)
        self.assertIn('--pinned-head "$PINNED_HEAD"', text)
        self.assertIn('source_pin=$PINNED_HEAD', text)
        self.assertNotIn('native start post-restore', text)
