"""Safety and syntax qualification for the NORTH one-shot reset entry point.

Source-only: no VMware, sudo, Vagrant, network, or filesystem mutations.
"""
from __future__ import annotations

import ast
from pathlib import Path
import re
import subprocess
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/north-one-shot-clean-reinstall.sh"


class NorthOneShotSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_bash_parses_and_python_heredocs_compile(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
        bodies = re.findall(r"<<'PY'\n(.*?)\nPY(?:\n|$)", self.source, re.S)
        self.assertEqual(len(bodies), 5)
        for index, body in enumerate(bodies):
            with self.subTest(heredoc=index):
                ast.parse(body)

    def test_strict_exact_owner_and_operator_confirmation(self):
        src = self.source
        for expected in (
            'EXPECTED_ID="7f61ea-north-vmware"',
            'EXPECTED_BRANCH="fix/north-one-command-fresh-install-bootstrap"',
            '--confirm-reset',
            'provider_success") is False',
            'meta.get("status")',
            'NO_RUNNING_FOREIGN_GUESTS',
            'NO_REGISTERED_FOREIGN_NORTH_NETWORK_USERS',
            'VMWARE_GUI_CLOSED',
            'if not vmx.is_file()',
        ):
            with self.subTest(check=expected):
                self.assertIn(expected, src)
        self.assertNotIn('rm -rf', src)
        self.assertNotIn('vagrant global-status --prune', src)
        self.assertNotIn('vmware-networks --stop', src)

    def test_destroy_then_plan_apply_then_fresh_install_then_validate(self):
        src = self.source
        ordered = [
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
        positions = [src.index(value) for value in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("set -Eeuo pipefail", src)
        self.assertIn("trap on_error ERR", src)
        self.assertIn('shutil.rmtree(instance)', src)
        self.assertIn('run_logged bash ./goad.sh -t install -l NORTH -p vmware', src)

    def test_no_destructive_step_without_safety_preflight(self):
        src = self.source
        self.assertLess(src.index('NO_RUNNING_FOREIGN_GUESTS'),
                        src.index('stage "DESTROY EXACT'))
        self.assertLess(src.index('VMWARE_GUI_CLOSED'),
                        src.index('stage "DESTROY EXACT'))
        self.assertLess(src.index('status") == "failed"'),
                        src.index('stage "DESTROY EXACT'))
        self.assertLess(src.index('stage "VERIFY VMWARE DESTROY'),
                        src.index('stage "PLAN EXACT'))
        self.assertLess(src.index('stage "VERIFY OLD OWNER'),
                        src.index('shutil.rmtree(instance)'))


if __name__ == "__main__":
    unittest.main()
