"""WSLPE-only P1-C bounded firewall pilot: no live host changes in tests."""
from contextlib import redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/wslpe-p1c-host-filter-pilot.py"
SPEC = importlib.util.spec_from_file_location("wslpe_p1c_host_pilot", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class WslpeHostPilotTests(unittest.TestCase):
    def test_default_is_preview_and_never_arms_or_applies(self):
        with patch.object(M, "local_preflight", return_value=("candidate", "vmnet2", "172.28.231.1", "172.28.231.31")), \
             patch.object(M, "arm_rollback") as timer, \
             patch.object(M, "sudo_nft") as nft, \
             patch.object(sys, "argv", ["wslpe-p1c-host-filter-pilot.py"]), \
             redirect_stdout(StringIO()):
            self.assertEqual(M.main(), 0)
            timer.assert_not_called()
            nft.assert_not_called()

    def test_pilot_must_have_exact_confirmation_and_bounded_time(self):
        for args in (
            ["--pilot"],
            ["--pilot", "--confirm", "YES"],
            ["--pilot", "--confirm", M.CONFIRM, "--seconds", "30"],
            ["--pilot", "--confirm", M.CONFIRM, "--seconds", "301"],
            ["--rollback"],
        ):
            with self.subTest(args=args), \
                 patch.object(sys, "argv", ["pilot.py", *args]), \
                 patch.object(M, "local_preflight") as preflight, \
                 redirect_stdout(StringIO()):
                self.assertEqual(M.main(), 1)
                preflight.assert_not_called()

    def test_ssh_execution_fails_closed_without_explicit_remote_flag(self):
        with patch.dict("os.environ", {
            "SSH_CONNECTION": "198.51.100.24 55000 192.168.1.60 22"
        }), patch.object(M, "pilot") as pilot, \
             patch.object(sys, "argv", [
                 "pilot.py", "--pilot", "--confirm", M.CONFIRM, "--seconds", "120"
             ]), redirect_stdout(StringIO()):
            self.assertEqual(M.main(), 1)
            pilot.assert_not_called()

    def test_remote_pilot_requires_explicit_flag_and_ssh_session(self):
        with patch.dict("os.environ", {
            "SSH_CONNECTION": "198.51.100.24 55000 192.168.1.60 22"
        }), patch.object(M, "pilot") as pilot, \
             patch.object(sys, "argv", [
                 "pilot.py", "--pilot", "--remote", "--confirm",
                 M.CONFIRM, "--seconds", "120"
             ]), redirect_stdout(StringIO()):
            self.assertEqual(M.main(), 0)
            pilot.assert_called_once_with(120, remote=True)

    def test_remote_preflight_proves_host_timer_without_installation(self):
        with patch.object(M, "local_preflight", return_value=(
            "candidate", "vmnet2", "172.28.231.1", "172.28.231.31"
        )), patch.object(M, "remote_preflight") as preflight, \
             patch.object(M, "sudo_nft") as nft, \
             patch.object(sys, "argv", [
                 "pilot.py", "--remote-preflight"
             ]), redirect_stdout(StringIO()) as output:
            self.assertEqual(M.main(), 0)
            preflight.assert_called_once_with("vmnet2", "172.28.231.1")
            nft.assert_not_called()
            self.assertIn("REMOTE_WSLPE_ROLLBACK_PREFLIGHT=TRUE", output.getvalue())

    def test_verify_rollback_fails_if_table_remains(self):
        with patch.object(M, "nft_json", return_value=[
            {"table": {"family": "inet", "name": M.TABLE}}
        ]), patch.object(M, "check_https") as https, \
             patch.object(sys, "argv", [
                 "pilot.py", "--verify-rollback"
             ]), redirect_stdout(StringIO()):
            self.assertEqual(M.main(), 1)
            https.assert_not_called()

    def test_verify_rollback_requires_authenticated_https(self):
        with patch.object(M, "nft_json", return_value=[]), \
             patch.object(M, "check_https", return_value=False), \
             patch.object(sys, "argv", [
                 "pilot.py", "--verify-rollback"
             ]), redirect_stdout(StringIO()):
            self.assertEqual(M.main(), 1)
        with patch.object(M, "nft_json", return_value=[]), \
             patch.object(M, "check_https", return_value=True), \
             patch.object(sys, "argv", [
                 "pilot.py", "--verify-rollback"
             ]), redirect_stdout(StringIO()):
            self.assertEqual(M.main(), 0)

    def test_pilot_arms_rollback_before_installing_rules(self):
        order = []
        def check_https():
            order.append("https")
            return True
        def arm(seconds, timer_id):
            self.assertEqual(seconds, 180)
            self.assertTrue(timer_id)
            order.append("timer")
            return "rollback-test.timer"
        def nft(*args, payload=None):
            self.assertEqual(args, ("-f", "-"))
            self.assertEqual(payload, "candidate")
            order.append("nft-apply")
            return SimpleNamespace(returncode=0)
        with patch.object(M, "local_preflight", return_value=("candidate", "vmnet2", "172.28.231.1", "172.28.231.31")), \
             patch.object(M, "check_https", side_effect=check_https), \
             patch.object(M, "arm_rollback", side_effect=arm), \
             patch.object(M, "sudo_nft", side_effect=nft), \
             patch.object(M, "installed_exact_policy", return_value=True), \
             redirect_stdout(StringIO()):
            M.pilot(180)
        self.assertEqual(order, ["https", "timer", "nft-apply", "https"])

    def test_lost_management_triggers_exact_scoped_rollback(self):
        with patch.object(M, "local_preflight", return_value=("candidate", "vmnet2", "172.28.231.1", "172.28.231.31")), \
             patch.object(M, "check_https", side_effect=[True, False]), \
             patch.object(M, "arm_rollback", return_value="rollback-test.timer"), \
             patch.object(M, "sudo_nft", return_value=SimpleNamespace(returncode=0)), \
             patch.object(M, "installed_exact_policy", return_value=True), \
             patch.object(M, "rollback_now") as rollback, \
             redirect_stdout(StringIO()):
            with self.assertRaises(ValueError):
                M.pilot(180)
            rollback.assert_called_once_with()

    def test_installed_policy_acceptance_rejects_unknown_table_objects(self):
        sample = [
            {"table": {"family": "inet", "name": M.TABLE}},
            {"chain": {"family": "inet", "table": M.TABLE, "name": M.INPUT_CHAIN,
                       "hook": "input", "prio": -75}},
            {"chain": {"family": "inet", "table": M.TABLE, "name": M.FORWARD_CHAIN,
                       "hook": "forward", "prio": -75}},
        ]
        for chain, comment, action in (
            (M.INPUT_CHAIN, "WSLPE operator reply only", "accept"),
            (M.INPUT_CHAIN, "WSLPE guest to Kali blocked", "drop"),
            (M.FORWARD_CHAIN, "WSLPE guest forwarding blocked", "drop"),
            (M.FORWARD_CHAIN, "WSLPE cross-network ingress blocked", "drop"),
        ):
            sample.append({"rule": {
                "family": "inet", "table": M.TABLE, "chain": chain,
                "comment": comment,
                "expr": [{"match": {"right": "vmnet2"}}, {action: None}],
            }})
        with patch.object(M, "nft_json", return_value=sample):
            self.assertTrue(M.installed_exact_policy("vmnet2"))
        with patch.object(M, "nft_json", return_value=sample + [
            {"rule": {"family": "inet", "table": M.TABLE, "chain": M.INPUT_CHAIN}}
        ]):
            with self.assertRaises(ValueError):
                M.installed_exact_policy("vmnet2")

    def test_unreadable_nft_ruleset_is_not_treated_as_absent(self):
        with patch.object(M, "nft_json", side_effect=ValueError("not readable")):
            with self.assertRaises(ValueError):
                M.installed_exact_policy("vmnet2")

    def test_timed_rollback_only_targets_exact_wslpe_table(self):
        calls = []
        def fake_cmd(args, **kwargs):
            calls.append(args)
            return SimpleNamespace(returncode=0, stdout="active\n")
        with patch.object(M, "cmd", side_effect=fake_cmd), \
             patch.object(M.shutil, "which", return_value="/usr/sbin/nft"):
            unit = M.arm_rollback(180, "test1234")
        self.assertEqual(unit, "kingdoms-wslpe-fw-rollback-test1234.timer")
        command = calls[0]
        self.assertEqual(command[:3], ["sudo", "-n", "systemd-run"])
        self.assertIn("--on-active=180s", command)
        self.assertEqual(command[-5:], [
            "/usr/sbin/nft", "delete", "table", "inet", M.TABLE
        ])
        self.assertEqual(calls[1][-2:], ["is-active", unit])

    def test_no_shared_host_flush_north_commands_or_secret_literal(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for prohibited in (
            "flush ruleset", "vmrun stop", "vmrun start", "vagrant destroy",
            "lab-mode.sh", "iptables -F", "vmnet10", "vmnet20",
            "10.4.10.11", "ansible_password=", "Set-NetFirewallRule",
        ):
            self.assertNotIn(prohibited, source)
        for required in ("--on-active=", "checked = sudo_nft(",
                         "check_https()", "rollback_now()", "exact_rollback()",
                         "installed_exact_policy()", "no action against NORTH"):
            self.assertIn(required, source)


if __name__ == "__main__":
    unittest.main()
