"""Safety and syntax qualification for guarded fourth NORTH clean installation.

Source-only: no VMware, sudo, network changes or Vagrant calls.
"""
import ast
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/north-fourth-clean-install.sh"


class NorthFourthInstallSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_bash_and_embedded_python(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        blocks = re.findall(r"<<'PY'\n(.*?)\nPY(?:\n|$)", self.source, re.S)
        self.assertEqual(len(blocks), 6)
        for idx, block in enumerate(blocks):
            with self.subTest(block=idx):
                ast.parse(block)

    def test_exact_failed_receipt_and_source_contract(self):
        src = self.source
        markers = (
            'EXPECTED_ID="fc7714-north-vmware"',
            'EXPECTED_BRANCH="main"',
            'bash scripts/verify-test-source.sh',
            'refs/remotes/origin/main',
            'Usage: bash scripts/north-fourth-clean-install.sh --confirm-fourth-install',
            'receipt.get("status") == "failed"',
            'receipt.get("provider_success") is False',
            'not receipt.get("ansible_phases")',
            'receipt.get("instance_id") == identity',
            'Vagrant first creation GOAD-DC02',
            'p.get("outcome") == "failed"',
            'meta.get("status")',
            'NO_RUNNING_FOREIGN_GUESTS',
            'NO_REGISTERED_FOREIGN_NORTH_NETWORK_USERS',
            'VMWARE_GUI_CLOSED',
            'NORTH_FRESH_INSTALL_4=PASS',
            'NORTH_RUNTIME_ACCEPTANCE=PASS',
        )
        for marker in markers:
            with self.subTest(marker=marker):
                self.assertIn(marker, src)
        self.assertNotIn("7f61ea-north-vmware", src)
        self.assertNotIn("57bbec-north-vmware", src)
        self.assertNotIn("rm -rf", src)

    def test_fail_closed_order_before_destroy_and_install(self):
        src = self.source
        stages = (
            'stage "VERIFY MERGED MAIN SOURCE AND EXACT UPSTREAM COMMIT"',
            'stage "VERIFY EXACT FAILED NORTH INSTANCE AND ALL OTHER VMWARE GUESTS"',
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
        )
        positions = [src.index(stage) for stage in stages]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(src.index('receipt.get("instance_id") == identity'),
                        src.index('stage "DESTROY EXACT'))
        self.assertLess(src.index('NO_RUNNING_FOREIGN_GUESTS'),
                        src.index('stage "DESTROY EXACT'))
        self.assertLess(src.index('VMWARE_GUI_CLOSED'),
                        src.index('stage "DESTROY EXACT'))
        self.assertIn("shutil.rmtree(instance)", src)
        self.assertIn('bash ./goad.sh -t install -l NORTH -p vmware', src)
        self.assertIn('bash ./goad.sh -t validate -l NORTH -p vmware -i "$NEW_ID"', src)
        self.assertNotIn('cold-1-start', src)
        self.assertNotIn('native reset', src)


if __name__ == "__main__":
    unittest.main()
