"""Safety gates for the third NORTH fresh-install one-shot (source only)."""
import ast
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/north-third-clean-install.sh"


class NorthThirdFreshInstallSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_bash_syntax_and_embedded_python(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        bodies = re.findall(r"<<'PY'\n(.*?)\nPY(?:\n|$)", self.source, re.S)
        self.assertEqual(len(bodies), 6)
        for i, source in enumerate(bodies):
            with self.subTest(heredoc=i):
                ast.parse(source)

    def test_exact_target_main_and_confirmation(self):
        src = self.source
        for value in (
            'EXPECTED_ID="57bbec-north-vmware"',
            'EXPECTED_BRANCH="main"',
            "--confirm-third-install",
            "Usage: bash scripts/north-third-clean-install.sh --confirm-third-install",
            "bash scripts/verify-test-source.sh",
            "refs/remotes/origin/main",
            'meta.get("status")',
            'mode.read_text().strip() == "exercise"',
            'receipt.get("status") == "completed"',
            'receipt.get("provider_success") is True',
            "EXACT_INSTALLED_INSTANCE_AND_SUCCESS_RECEIPT",
            "NO_RUNNING_FOREIGN_GUESTS",
            "NO_REGISTERED_FOREIGN_NORTH_NETWORK_USERS",
            "VMWARE_GUI_CLOSED",
            "NORTH_FRESH_INSTALL_3=PASS",
        ):
            with self.subTest(value=value):
                self.assertIn(value, src)
        self.assertNotIn('7f61ea-north-vmware', src)
        self.assertNotIn('EXPECTED_BRANCH="fix/', src)
        self.assertNotIn('rm -rf', src)

    def test_preflight_and_destructive_stages_are_ordered(self):
        src = self.source
        order = [
            'stage "VERIFY SOURCE IS CLEAN AND EXACTLY origin/main"',
            'stage "VERIFY EXACT INSTALLED NORTH INSTANCE AND ALL OTHER VMWARE GUESTS"',
            'stage "ESTABLISH PRIVILEGED NETWORK RETIREMENT AUTHORIZATION"',
            'stage "DESTROY EXACT NORTH VAGRANT INSTANCE"',
            'stage "VERIFY VMWARE DESTROY BEFORE TOUCHING HOST NETWORKING"',
            'stage "PLAN EXACT NORTH NETWORK RETIREMENT (READ-ONLY)"',
            'stage "RETIRE EXACT OWNED NORTH VMNETS, PRESERVING FOREIGN CONFIGURATION"',
            'stage "VERIFY OLD OWNER AND NETWORKS ARE GONE"',
            'stage "REMOVE ONLY THE NOW-DESTROYED NORTH WORKSPACE"',
            'stage "ONE-COMMAND FRESH NORTH INSTALLATION"',
            'stage "DISCOVER AND CHECK NEW INSTANCE STATE"',
            'stage "RUN NORTH RUNTIME ACCEPTANCE"',
            'stage "FINAL STATUS AND INSTALL RECEIPT"',
        ]
        locations = [src.index(marker) for marker in order]
        self.assertEqual(locations, sorted(locations))
        self.assertLess(src.index("NO_RUNNING_FOREIGN_GUESTS"),
                        src.index('stage "DESTROY EXACT'))
        self.assertLess(src.index("VMWARE_GUI_CLOSED"),
                        src.index('stage "DESTROY EXACT'))
        self.assertLess(src.index('receipt.get("provider_success") is True'),
                        src.index('stage "DESTROY EXACT'))
        self.assertIn("shutil.rmtree(instance)", src)
        self.assertIn('bash ./goad.sh -t install -l NORTH -p vmware', src)
        self.assertIn('bash ./goad.sh -t validate -l NORTH -p vmware -i "$NEW_ID"', src)
        self.assertNotIn('native start "cold-', src)
        self.assertNotIn("nORTH_LIFECYCLE_RELIABILITY=PASS", src)

    def test_preserves_previous_evidence_and_install_receipt(self):
        src = self.source
        for marker in (
            '"$HOME/Kingdoms-evidence/north-lifecycle-H73tfcMF"',
            'cp -p "$INSTANCE/instance.json" "$LOGDIR/old-instance.json"',
            'cp -p "$INSTANCE"/install-timings/*.json "$LOGDIR/"',
            'printf \'[SOURCE] %s\\n\' "$(git rev-parse HEAD)"',
            'trap on_error ERR',
            'run_logged bash ./goad.sh -t destroy -l NORTH -p vmware -i "$EXPECTED_ID"',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, src)


if __name__ == "__main__":
    unittest.main()
