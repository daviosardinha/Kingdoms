"""WSLPE remote operator safety and independent host rollback self-test.

All tests are mocks; no timer, nftables, VMware or guest is contacted.
"""
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from kingdoms.wslpe_remote_operator import (
    ssh_management_path, host_timer_smoke_test,
)

ROOT = Path(__file__).resolve().parents[1]


def result(rc=0, stdout=""):
    return SimpleNamespace(returncode=rc, stdout=stdout)


class WslpeRemoteOperatorTests(unittest.TestCase):
    def test_ssh_path_via_separate_operator_interface_passes(self):
        calls = []
        def execute(args, **kwargs):
            calls.append(args)
            return result(stdout='[{"dst":"198.51.100.24","dev":"wlp2s0","prefsrc":"192.168.1.60"}]')
        env = {"SSH_CONNECTION": "198.51.100.24 53212 192.168.1.60 22"}
        self.assertEqual(
            ssh_management_path("vmnet2", "172.28.231.0/24", env, execute),
            "wlp2s0",
        )
        self.assertEqual(calls, [["ip", "-j", "-4", "route", "get", "198.51.100.24"]])

    def test_ssh_on_exercise_subnet_fails_closed_without_route_query(self):
        for ssh in (
            "172.28.231.1 52000 192.168.1.60 22",
            "192.168.1.10 52000 172.28.231.1 22",
            "127.0.0.1 52000 192.168.1.60 22",
            "ssh malformed",
            "2001:db8::1 52000 2001:db8::2 22",
        ):
            with self.subTest(ssh=ssh):
                with patch("kingdoms.wslpe_remote_operator.command") as runner:
                    with self.assertRaises(ValueError):
                        ssh_management_path(
                            "vmnet2", "172.28.231.0/24",
                            {"SSH_CONNECTION": ssh},
                            runner,
                        )
                    runner.assert_not_called()

    def test_ssh_return_route_must_be_separate_and_unique(self):
        env = {"SSH_CONNECTION": "198.51.100.24 53212 192.168.1.60 22"}
        for routes in (
            '[{"dev":"vmnet2"}]',
            '[{"dev":"vmnet2"},{"dev":"wlp2s0"}]',
            '[{"dev":"wlp2s0","prefsrc":"172.28.231.1"}]',
            '[{"dev":"wlp2s0"}]',
            '{}',
            'malformed',
        ):
            with self.subTest(routes=routes), self.assertRaises(ValueError):
                ssh_management_path(
                    "vmnet2", "172.28.231.0/24", env,
                    lambda args: result(stdout=routes),
                )

    def test_host_systemd_timer_actually_fires_and_cleans_only_marker(self):
        calls = []
        checks = [1, 1, 0]
        def executor(args, **kwargs):
            calls.append(args)
            if args[2:4] == ["/usr/bin/test", "-f"]:
                return result(rc=checks.pop(0))
            if args[2:4] == ["systemctl", "is-active"]:
                return result(stdout="active\n")
            return result()
        sleeps = []
        with patch("kingdoms.wslpe_remote_operator.uuid.uuid4") as mockuuid:
            mockuuid.return_value.hex = "abcdef0123456789zzzzzz"
            unit = host_timer_smoke_test(executor, lambda n: sleeps.append(n))
        self.assertEqual(unit, "kingdoms-wslpe-remote-check-abcdef0123456789")
        self.assertEqual(sleeps, [1, 1])
        self.assertEqual(calls[0][0:3], ["sudo", "-n", "systemd-run"])
        self.assertEqual(calls[0][-2:], [
            "/usr/bin/touch",
            "/run/kingdoms-wslpe-remote-check-abcdef0123456789.done",
        ])
        self.assertEqual(calls[-1], [
            "sudo", "-n", "/usr/bin/rm", "-f", "--",
            "/run/kingdoms-wslpe-remote-check-abcdef0123456789.done",
        ])

    def test_failing_host_timer_is_never_treated_as_proven(self):
        calls = []
        def executor(args, **kwargs):
            calls.append(args)
            if args[2:4] == ["/usr/bin/test", "-f"]:
                return result(rc=1)
            if args[2:4] == ["systemctl", "is-active"]:
                return result(stdout="active\n")
            return result()
        with self.assertRaises(ValueError):
            host_timer_smoke_test(executor, lambda _: None)
        self.assertEqual(calls[-1][2:5], ["/usr/bin/rm", "-f", "--"])

    def test_sentinel_cleanup_failure_blocks_pilot(self):
        def execute(args, **kwargs):
            if args[2:4] == ["systemctl", "is-active"]:
                return result(stdout="active\\n")
            if args[2:4] == ["/usr/bin/test", "-f"]:
                return result()
            if args[2:5] == ["/usr/bin/rm", "-f", "--"]:
                return result(rc=1)
            return result()
        with self.assertRaises(ValueError):
            host_timer_smoke_test(execute, lambda _: None)

    def test_source_contains_no_general_firewall_or_north_mutations(self):
        script = (ROOT / "kingdoms/wslpe_remote_operator.py").read_text()
        pilot = (ROOT / "scripts/wslpe-p1c-host-filter-pilot.py").read_text()
        for required in ("ssh_management_path(", "host_timer_smoke_test(",
                         '"--remote-preflight"', '"--remote"',
                         "Remote SSH pilot requires --remote",
                         "remote_preflight(vmnet, host)"):
            self.assertIn(required, pilot + script)
        for forbidden in ("flush ruleset", "vagrant up", "vmrun stop", "lab-mode.sh",
                          "sudo nft -f", "iptables -A", "vmnet10", "10.4.10.11",
                          "ansible_password="):
            self.assertNotIn(forbidden, script + pilot)


if __name__ == "__main__":
    unittest.main()
