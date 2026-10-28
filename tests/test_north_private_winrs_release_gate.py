"""Release policy: native WinRS is isolated from public PR execution.

The private runner workflow is a TEMPLATE (not an active public workflow),
and it checks out an immutable reviewed source commit. Ordinary hosted PR
CI must retain all Linux source gates and native PowerShell parser tests.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / ".github/workflows/north-native-nat-retirement.yml"
PRIVATE = ROOT / "ci/private-winrs-runner/north-winrs-private.yml"
HELPER = ROOT / "ansible/files/north-parent-winrs.ps1"
NATIVE = ROOT / "tests/test_north_parent_winrs.ps1"


class NorthPrivateWinrsReleaseGateTests(unittest.TestCase):
    def test_public_workflow_runs_offline_gates_not_native_fixture(self):
        src = PUBLIC.read_text(encoding="utf-8")
        self.assertIn("windows-parent-epr-parser:", src)
        self.assertIn("source-gates:", src)
        self.assertIn("test_north_private_winrs_runner_gate.ps1", src)
        self.assertNotIn("\n  windows-parent-winrs:", src)
        self.assertNotIn("run: ./tests/test_north_parent_winrs.ps1", src)
        self.assertNotIn("runs-on: [self-hosted", src)

    def test_private_template_is_not_a_public_actions_workflow(self):
        self.assertTrue(PRIVATE.is_file())
        self.assertNotIn(".github/workflows/", str(PRIVATE))
        text = PRIVATE.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("pull_request:", text)
        self.assertNotIn("pull_request_target:", text)
        self.assertIn("self-hosted", text)
        self.assertIn("kingdoms-winrs-ci", text)
        self.assertIn("NK-WINRS-CI", text)
        self.assertIn("daviosardinha/Kingdoms-WinRS-CI", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("KINGDOMS_NORTH_PRIVATE_WINRS_RUNNER: '1'", text)
        self.assertIn("./tests/test_north_parent_winrs.ps1", text)
        self.assertIn("ref: fdfcb64871f481f467f130ae8b744dfbeba3f1ac", text)

    def test_fixture_rejects_public_selfhost_and_real_training_guests(self):
        helper = HELPER.read_text(encoding="utf-8")
        native = NATIVE.read_text(encoding="utf-8")
        self.assertIn("function Test-NorthParentWinRSCiFixture", helper)
        self.assertIn("Test-NorthParentWinRSCiFixture", native)
        self.assertIn("GITHUB_REPOSITORY -eq 'daviosardinha/Kingdoms-WinRS-CI'", helper)
        self.assertIn("COMPUTERNAME -ceq 'NK-WINRS-CI'", helper)
        self.assertIn("'KINGSLANDING'", helper)
        self.assertIn("'WINTERFELL'", helper)
        self.assertIn("KINGDOMS_NORTH_PRIVATE_WINRS_RUNNER -eq '1'", helper)
        self.assertIn("https://kingslanding.sevenkingdoms.local:5986/wsman", helper)
        self.assertIn("SessionFlagUseNegotiate()", helper)


if __name__ == "__main__":
    unittest.main()
