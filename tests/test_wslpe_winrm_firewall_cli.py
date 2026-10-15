"""No-network, no-root tests of explicit WSLPE-only nft mutation guards."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

from test_wslpe_winrm_guard import nft_fixture

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "scripts/wslpe-winrm-firewall.py"
SPEC = importlib.util.spec_from_file_location("wslpe_firewall_cli", FILE)
assert SPEC and SPEC.loader
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)

LISTEN = ('LISTEN 0 20 0.0.0.0:2210 0.0.0.0:* '
          'users:(("vmnet-nat",pid=2162896,fd=9))\n')


def result(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class WslpeFirewallCliTests(unittest.TestCase):
    def test_missing_table_audit_fails_without_firewall_mutation(self):
        with patch.object(CLI, "native_port", return_value=(2210, "wslpe-1")), \
             patch.object(CLI.os, "geteuid", return_value=0), \
             patch.object(CLI, "run", side_effect=[
                 result(stdout=LISTEN),
                 result(returncode=1, stderr="No such file or directory"),
             ]) as runner, \
             patch.object(sys, "argv", ["script"]):
            self.assertEqual(CLI.main(), 1)
        self.assertEqual(runner.call_count, 2)
        self.assertFalse(any("-f" in call.args[0] for call in runner.call_args_list))

    def test_exact_confirmation_applies_one_rule_and_verifies(self):
        with patch.object(CLI, "native_port", return_value=(2210, "wslpe-1")), \
             patch.object(CLI.os, "geteuid", return_value=0), \
             patch.object(CLI, "run", side_effect=[
                 result(stdout=LISTEN),
                 result(returncode=1, stderr="No such file or directory"),
                 result(), result(stdout=nft_fixture()),
             ]) as runner, \
             patch.object(sys, "argv", ["script", "--apply", "--confirm-port", "2210"]):
            self.assertEqual(CLI.main(), 0)
        self.assertEqual(runner.call_count, 4)
        apply = runner.call_args_list[2]
        self.assertEqual(apply.args[0], ["nft", "-f", "-"])
        self.assertIn('tcp dport 2210 drop', apply.kwargs["data"])
        self.assertNotIn("vmnet8", apply.kwargs["data"])

    def test_wrong_explicit_port_never_applies(self):
        with patch.object(CLI, "native_port", return_value=(2210, "wslpe-1")), \
             patch.object(CLI.os, "geteuid", return_value=0), \
             patch.object(CLI, "run", side_effect=[
                 result(stdout=LISTEN),
                 result(returncode=1, stderr="No such file or directory"),
             ]) as runner, \
             patch.object(sys, "argv", ["script", "--apply", "--confirm-port", "2211"]):
            self.assertEqual(CLI.main(), 1)
        self.assertEqual(runner.call_count, 2)

    def test_unknown_owner_blocks_mutation_even_with_confirmation(self):
        with patch.object(CLI, "native_port", return_value=(2210, "wslpe-1")), \
             patch.object(CLI.os, "geteuid", return_value=0), \
             patch.object(CLI, "run", side_effect=[
                 result(stdout=LISTEN.replace("vmnet-nat", "python3")),
                 result(returncode=1, stderr="No such file or directory"),
             ]) as runner, \
             patch.object(sys, "argv", ["script", "--apply", "--confirm-port", "2210"]):
            self.assertEqual(CLI.main(), 1)
        self.assertEqual(runner.call_count, 2)

    def test_mismatched_existing_rule_cannot_be_overwritten(self):
        with patch.object(CLI, "native_port", return_value=(2210, "wslpe-1")), \
             patch.object(CLI.os, "geteuid", return_value=0), \
             patch.object(CLI, "run", side_effect=[
                 result(stdout=LISTEN), result(stdout=nft_fixture(port=2211)),
             ]) as runner, \
             patch.object(sys, "argv", ["script", "--apply", "--confirm-port", "2210"]):
            self.assertEqual(CLI.main(), 1)
        self.assertEqual(runner.call_count, 2)


if __name__ == "__main__":
    unittest.main()
