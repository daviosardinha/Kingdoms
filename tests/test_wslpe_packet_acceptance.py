"""WSLPE controlled guest->owned-host packet-path proof source contracts.

All tests are local or mocked; none contacts guest/NORTH or installs nft rules.
"""
from contextlib import redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import MagicMock, patch

from kingdoms.wslpe_packet_path import (
    PORT, ControlledHostListener, parse_windows_probe,
    validate_target, windows_tcp_probe,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/wslpe-p1c-packet-acceptance.py"
SPEC = importlib.util.spec_from_file_location("wslpe_packet_acceptance", SCRIPT)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def remote_result(state="OPEN"):
    return (f"WSLPE_PACKET_MACHINE=WSLPE-WS01\n"
            f"WSLPE_PACKET_DOMAIN_FREE=TRUE\n"
            f"WSLPE_PACKET_TCP={state}\n").encode()


class WslpePacketAcceptanceTests(unittest.TestCase):
    def test_target_is_not_north_and_requires_exact_local_host(self):
        validate_target("172.28.231.1", "172.28.231.31",
                        "172.28.231.0/24", PORT)
        for host, guest, subnet, port in (
            ("10.4.10.1", "10.4.10.31", "10.4.10.0/24", PORT),
            ("172.28.231.1", "172.28.231.50", "172.28.231.0/24", PORT),
            ("172.28.231.1", "172.28.231.31", "172.28.0.0/16", PORT),
            ("172.28.231.31", "172.28.231.31", "172.28.231.0/24", PORT),
            ("172.28.231.1", "172.28.231.31", "172.28.231.0/24", 80),
        ):
            with self.subTest(host=host, guest=guest), self.assertRaises(ValueError):
                validate_target(host, guest, subnet, port)

    def test_windows_probes_only_one_exact_host_socket(self):
        ps = windows_tcp_probe("172.28.231.1")
        self.assertIn("BeginConnect('172.28.231.1', 47381", ps)
        self.assertIn("WSLPE-WS01", ps)
        self.assertIn("$machine.PartOfDomain", ps)
        self.assertIn("AsyncWaitHandle.WaitOne(2500", ps)
        self.assertIn("WSLPE_PACKET_TCP=OPEN", ps)
        self.assertIn("WSLPE_PACKET_TCP=CLOSED", ps)
        for bad in ("GOAD-WS01", "NORTH\\", "New-NetFirewallRule",
                    "Set-NetRoute", "Invoke-WebRequest", "Remove-Item",
                    "Restart-Computer", "Start-Process"):
            self.assertNotIn(bad, ps)

    def test_guest_probe_parser_fails_closed_on_ambiguous_markers(self):
        self.assertTrue(parse_windows_probe(0, remote_result("OPEN")))
        self.assertFalse(parse_windows_probe(0, remote_result("CLOSED")))
        for status, blob in (
            (1, remote_result()),
            (0, b"WSLPE_PACKET_TCP=OPEN\n"),
            (0, remote_result("OPEN") + b"WSLPE_PACKET_TCP=CLOSED\n"),
            (0, remote_result("OPEN") + b"WSLPE_PACKET_TCP=OPEN\n"),
            (0, remote_result("OPEN").replace(b"WSLPE-WS01", b"GOAD-WS01")),
            (0, b"A" * 4097),
        ):
            with self.subTest(status=status, blob=blob[:45]):
                with self.assertRaises(ValueError):
                    parse_windows_probe(status, blob)

    def test_positive_control_demands_remote_and_matching_guest_listener(self):
        listener = MagicMock()
        listener.count.side_effect = [0, 1]
        with redirect_stdout(StringIO()):
            MOD.verified_guest_connection(listener, lambda _ip: True, "172.28.231.1")
        with self.assertRaises(ValueError):
            MOD.verified_guest_connection(listener, lambda _ip: False, "172.28.231.1")

    def test_deny_requires_closed_socket_and_no_listener_accept(self):
        listener = MagicMock()
        listener.count.side_effect = [1, 1]
        with patch.object(MOD.time, "sleep"), redirect_stdout(StringIO()):
            MOD.verified_guest_deny(listener, lambda _ip: False, "172.28.231.1")
        listener.count.side_effect = [1, 2]
        with patch.object(MOD.time, "sleep"), self.assertRaises(ValueError):
            MOD.verified_guest_deny(listener, lambda _ip: False, "172.28.231.1")
        with self.assertRaises(ValueError):
            MOD.verified_guest_deny(listener, lambda _ip: True, "172.28.231.1")

    def test_default_baseline_does_not_enter_firewall_pilot(self):
        pilot = MagicMock()
        auth = MagicMock()
        pilot.local_preflight.return_value = (
            "candidate", "vmnet2", "172.28.231.1", "172.28.231.31"
        )
        auth.checked_certificate.return_value = ("172.28.231.31", b"der")
        listener = MagicMock()
        listener.__enter__.return_value = listener
        listener.count.side_effect = [0, 1]
        from contextlib import contextmanager
        @contextmanager
        def remote(*args):
            yield lambda host: True
        def import_module(path, name):
            return pilot if "pilot" in str(path) else auth
        with patch.object(MOD, "load", side_effect=import_module), \
             patch.object(MOD, "ControlledHostListener", return_value=listener), \
             patch.object(MOD, "authenticated_guest", side_effect=remote), \
             patch.object(MOD, "verified_guest_connection") as positive, \
             patch.dict("os.environ", {"SSH_CONNECTION": ""}), \
             patch.object(sys, "argv", ["packet.py"]), \
             redirect_stdout(StringIO()):
            self.assertEqual(MOD.main(), 0)
        pilot.pilot.assert_not_called()
        positive.assert_called_once()

    def test_live_three_phases_are_ordered_and_include_timer_removal(self):
        calls = []
        pilot = MagicMock()
        pilot.pilot.side_effect = lambda *a, **kw: calls.append("apply")
        pilot.installed_exact_policy.return_value = True
        pilot.check_https.return_value = True
        witness = MagicMock()
        with patch.object(MOD, "verified_guest_connection",
                          side_effect=lambda *args: calls.append("open")), \
             patch.object(MOD, "verified_guest_deny",
                          side_effect=lambda *args: calls.append("blocked")), \
             patch.object(MOD, "wait_for_table_removal",
                          side_effect=lambda *args: calls.append("removed")), \
             redirect_stdout(StringIO()):
            MOD.execute_phases(pilot, witness, lambda h: True,
                               "172.28.231.1", "vmnet2")
        self.assertEqual(calls, ["open", "apply", "blocked", "removed", "open"])
        pilot.pilot.assert_called_once_with(MOD.PILOT_SECONDS, remote=True)

    def test_source_never_targets_north_or_disconnects_nat(self):
        text = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("vmrun stop", "vagrant up", "ipconfig /release",
                          "10.4.10.11", "vmnet10", "lab-mode.sh",
                          "nft flush", "Set-NetFirewallRule", "Set-NetAdapter",
                          "server_cert_validation=\"ignore\""):
            self.assertNotIn(forbidden, text)
        self.assertIn("server_cert_validation=\"validate\"", text)
        self.assertIn("scoped_wslpe_resolution(", text)
        self.assertIn("pilot.pilot(PILOT_SECONDS, remote=True)", text)
        self.assertIn("rollback_now()", text)
        self.assertIn("--execute", text)


if __name__ == "__main__":
    unittest.main()
