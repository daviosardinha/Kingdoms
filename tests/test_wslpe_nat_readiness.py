"""WSLPE-only NAT readiness contracts; no live VMware, firewall or guest writes."""
import importlib.util
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
from kingdoms.wslpe_nat_readiness import (
    mac_normal, vmx_snapshot, windows_snapshot, cutover_blockers,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/wslpe-p1c-nat-readiness-audit.py"
SPEC = importlib.util.spec_from_file_location("wslpe_nat_audit", SCRIPT)
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


VMX = """
ethernet0.present = "TRUE"
ethernet0.connectionType = "nat"
ethernet0.generatedAddress = "00:0c:29:01:bb:77"
ethernet1.present = "TRUE"
ethernet1.connectionType = "custom"
ethernet1.vnet = "vmnet2"
ethernet1.generatedAddress = "00:0c:29:01:bb:81"
"""

def guest_data():
    return {
        "Machine": "WSLPE-WS01", "DomainJoined": False,
        "Adapters": [
            {"Mac": "00-0C-29-01-BB-77", "Index": 6, "Status": "Up"},
            {"Mac": "00-0C-29-01-BB-81", "Index": 8, "Status": "Up"},
        ],
        "IPv4": [
            {"Address": "192.168.213.248", "Index": 6, "Prefix": 24},
            {"Address": "172.28.231.31", "Index": 8, "Prefix": 24},
        ],
        "IPv6": [{"Address": "fe80::a", "Index": 8, "Prefix": 64}],
        "DefaultRoutes4": [{"Index": 6}],
        "DefaultRoutes6": [],
    }


class WslpeNatReadinessTests(unittest.TestCase):
    def test_normalized_mac_is_exactly_48_bit(self):
        self.assertEqual(mac_normal("00-0C-29-01-BB-77"), "000c2901bb77")
        for value in ("invalid", "00:0c:29", "", "00:11:22:33:44:gg", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                mac_normal(value)

    def test_vmx_requires_exact_two_separate_registered_adapters(self):
        result = vmx_snapshot(VMX, "vmnet2")
        self.assertEqual(result["nat_mac"], "000c2901bb77")
        self.assertEqual(result["exercise_mac"], "000c2901bb81")
        self.assertEqual(result["exercise_vmnet"], "vmnet2")
        with self.assertRaises(ValueError):
            vmx_snapshot(VMX.replace('"vmnet2"', '"vmnet10"'), "vmnet2")
        with self.assertRaises(ValueError):
            vmx_snapshot(VMX.replace('connectionType = "nat"',
                                     'connectionType = "custom"'), "vmnet2")
        with self.assertRaises(ValueError):
            vmx_snapshot(VMX + '\nethernet2.present = "TRUE"\n', "vmnet2")
        with self.assertRaises(ValueError):
            vmx_snapshot(VMX.replace("00:0c:29:01:bb:81",
                                     "00:0c:29:01:bb:77"), "vmnet2")

    def test_windows_nic_guest_mac_route_and_ipv6_evidence(self):
        result = windows_snapshot(guest_data(), vmx_snapshot(VMX, "vmnet2"),
                                  "172.28.231.1", "172.28.231.31")
        self.assertEqual(result["exercise_index"], 8)
        self.assertEqual(result["nat_index"], 6)
        self.assertEqual(result["nat_default_route_count"], 1)
        self.assertTrue(result["vulnerable_exercise_ipv6"])

    def test_guest_must_be_exact_standalone_machine(self):
        for modified in ({"Machine": "GOAD-WS01"}, {"DomainJoined": True}):
            guest = guest_data()
            guest.update(modified)
            with self.assertRaises(ValueError):
                windows_snapshot(guest, vmx_snapshot(VMX, "vmnet2"),
                                 "172.28.231.1", "172.28.231.31")

    def test_guest_exercise_route_or_ip_mismatch_fails_closed(self):
        for patch_data in (
            {"DefaultRoutes4": [{"Index": 8}]},
            {"DefaultRoutes6": [{"Index": 8}]},
            {"IPv4": [{"Address": "172.28.231.33", "Index": 8, "Prefix": 24}]},
            {"IPv6": "bad"},
        ):
            guest = guest_data()
            guest.update(patch_data)
            with self.assertRaises(ValueError):
                windows_snapshot(guest, vmx_snapshot(VMX, "vmnet2"),
                                 "172.28.231.1", "172.28.231.31")

    def test_release_does_not_promote_at_attached_nat(self):
        blockers = cutover_blockers(True, False, False, False)
        self.assertEqual(len(blockers), 4)
        self.assertFalse(cutover_blockers(False, True, True, True))

    def test_main_fails_closed_before_guest_calls_when_vmx_identity_missing(self):
        with patch.object(M, "imported") as imported, redirect_stdout(StringIO()) as observed:
            imported.side_effect = ValueError("WSLPE VMX missing")
            self.assertEqual(M.main(), 1)
            self.assertIn("[BLOCKED] ValueError", observed.getvalue())

    def test_source_checks_only_wslpe_without_mutations(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for token in (
            "auth.checked_certificate(", "auth.scoped_wslpe_resolution(",
            "local_preflight()", "vmx_snapshot(", "windows_snapshot(",
            "Get-NetIPAddress -AddressFamily IPv6",
            "Get-NetRoute -AddressFamily IPv6",
            "WSLPE_NAT_CUTOVER_AUTHORIZED=FALSE",
            "REMAINING_GATES",
        ):
            self.assertIn(token, source)
        forbidden = (
            "vmrun stop", "vmrun start", "nft -f", "nft add", "vagrant up",
            "startConnected=FALSE", "Set-NetAdapter", "Disable-NetAdapter",
            "New-LocalUser", "restart-computer", "lab-mode.sh", "vmnet10",
            "10.4.10.11", "iptables -A",
        )
        for item in forbidden:
            with self.subTest(item=item):
                self.assertNotIn(item, source)
        self.assertIn('server_cert_validation="validate"', source)


if __name__ == "__main__":
    unittest.main()
