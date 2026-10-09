"""One-command NORTH readiness: UX and fail-closed source guard regressions."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts/course1/check-install-readiness.sh"


class NorthReadinessDashboardTests(unittest.TestCase):
    def test_single_entrypoint_syntax(self):
        result = subprocess.run(["bash", "-n", str(CHECK)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_help_describes_readonly_full_and_cached_mode(self):
        result = subprocess.run(["bash", str(CHECK), "--help"],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--refresh", result.stdout)
        self.assertIn("resurvey", result.stdout)

    def test_dashboard_caches_only_source_but_resurveys_live_vmware(self):
        content = CHECK.read_text()
        self.assertIn('git status --porcelain', content)
        self.assertIn('validate-course1.sh --survey-host', content)
        self.assertIn("offline-pass.txt", content)
        self.assertIn("goad.course1_host_survey --check --json-only", content)
        self.assertIn("inspect_network_phase", content)
        self.assertIn("registered_inventory_complete", content)

    def test_dashboard_never_authorizes_premature_install(self):
        content = CHECK.read_text()
        self.assertIn('PREVIEW_ONLY_NOT_INSTALLABLE', content)
        self.assertIn('refuse_course_mutation', content)
        self.assertIn('PreviewCourseProvider', content)
        self.assertIn('RESULT: NOT INSTALLABLE YET', content)
        self.assertTrue(content.rstrip().endswith("exit 2"))
        for forbidden in ("vmrun -T ws start", "vmrun -T ws stop",
                          "vagrant up", "sudo bash scripts/setup-vmware-networks.sh"):
            self.assertNotIn(forbidden, content)


if __name__ == "__main__":
    unittest.main()
