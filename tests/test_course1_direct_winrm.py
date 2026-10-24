"""NORTH direct WinRM first-boot unit tests; no VMware or Windows changes."""
from __future__ import annotations

from ipaddress import IPv4Network
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from goad import course1_direct_winrm as direct


class FakeWinRMSession:
    def __init__(self):
        self.steps = 0
        self.setup_scripts = []
        self.provisioned = False
        self.fail_identity = False

    def run_ps(self, script):
        if "ConvertTo-Json -Depth 5 -Compress" in script:
            macs = ["005056202010", "000C29285F3A"]
            if self.fail_identity:
                macs[0] = "005056202022"
            result = json.dumps({
                "Hostname": "WIN-DC01",
                "Windows": True,
                "PowerShell": 5,
                "Tools": True,
                "Adapters": [{"Mac": mac, "Index": index, "Name": f"Ethernet{index}"}
                             for index, mac in enumerate(macs)]
            })
            return Mock(status_code=0, std_out=result.encode(), std_err=b"")
        if "NORTH_DIRECT_FIRST_BOOT_READY" in script:
            ok = self.provisioned
            return Mock(
                status_code=0 if ok else 1,
                std_out=b"NORTH_DIRECT_FIRST_BOOT_READY" if ok else b"",
                std_err=b"not yet configured" if not ok else b""
            )
        if "NORTH_SOURCE_SCRIPT_COMPLETED" in script:
            self.setup_scripts.append(script)
            if len(self.setup_scripts) == 2:
                self.provisioned = True
            return Mock(status_code=0, std_out=b"NORTH_SOURCE_SCRIPT_COMPLETED",
                        std_err=b"")
        return Mock(status_code=1, std_out=b"", std_err=b"unknown script")


class NorthDirectRecoveryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.provider = self.root / "5a533e-north-vmware" / "provider"
        state = self.provider / ".vagrant/machines/GOAD-DC01/vmware_desktop"
        uuid = state / "my-uuid"
        uuid.mkdir(parents=True)
        self.vmx = uuid / "WindowsServer2019.vmx"
        self.vmx.write_text(
            'ethernet0.connectionType = "nat"\n'
            'ethernet0.present = "TRUE"\n'
            'ethernet0.generatedAddress = "00:0c:29:28:5f:3a"\n'
            'ethernet1.connectionType = "custom"\n'
            'ethernet1.present = "TRUE"\n'
            'ethernet1.vnet = "vmnet20"\n'
            'ethernet1.address = "00:50:56:20:20:10"\n',
            encoding="utf-8")
        (state / "id").write_text(str(self.vmx), encoding="utf-8")
        self.session = FakeWinRMSession()
        self.runner = patch.object(direct, "_command", side_effect=self.commands)
        self.runner.start()
        self.addCleanup(self.runner.stop)

    def commands(self, args, **kwargs):
        if args[:4] == ["vmrun", "-T", "ws", "list"]:
            return Mock(returncode=0, stdout="Total running VMs: 1\n"+str(self.vmx)+"\n")
        if args[:4] == ["vmrun", "-T", "ws", "getGuestIPAddress"]:
            return Mock(returncode=0, stdout="192.168.213.133\n")
        if args[:4] == ["ip", "-4", "-o", "addr"]:
            return Mock(returncode=0, stdout="10: vmnet8 inet 192.168.213.1/24\n")
        if args[:4] == ["ip", "-4", "route", "get"]:
            return Mock(returncode=0, stdout="192.168.213.133 dev vmnet8 src 192.168.213.1\n")
        raise AssertionError(f"unexpected command: {args!r}")

    def test_exact_vmx_and_mac_match(self):
        vmx, guest, values = direct.owned_guest(self.provider, "GOAD-DC01")
        self.assertEqual(vmx, self.vmx)
        self.assertEqual(guest["address"], "10.4.20.10")
        self.assertEqual(values["ethernet1.address"], "00:50:56:20:20:10")

    def test_reject_guest_from_other_vm_registration(self):
        state = self.provider / ".vagrant/machines/GOAD-DC01/vmware_desktop"
        (state / "id").write_text("/tmp/unrelated.vmx")
        with self.assertRaisesRegex(direct.NorthGuestRecoveryBlocked, "belong"):
            direct.owned_guest(self.provider, "GOAD-DC01")

    def test_reject_modified_lab_mac_before_contact(self):
        contents = self.vmx.read_text()
        self.vmx.write_text(contents.replace("00:50:56:20:20:10", "00:50:56:20:20:11"))
        with self.assertRaisesRegex(direct.NorthGuestRecoveryBlocked, "contract"):
            direct.owned_guest(self.provider, "GOAD-DC01")

    def test_reject_wrong_winrm_guest_mac(self):
        self.session.fail_identity = True
        with patch.object(direct, "_authenticated_session", return_value=self.session), \
             patch.object(direct.socket, "create_connection", return_value=Mock()):
            with self.assertRaisesRegex(direct.NorthGuestRecoveryBlocked, "identity proof"):
                direct.prove_guest(self.provider, "GOAD-DC01")

    def test_reject_wrong_nat_route(self):
        old_commands = self.commands
        def wrong_route(args, **kwargs):
            if args[:4] == ["ip", "-4", "route", "get"]:
                return Mock(returncode=0, stdout="192.168.213.133 dev wlan0\n")
            return old_commands(args, **kwargs)
        with patch.object(direct, "_command", side_effect=wrong_route):
            with self.assertRaisesRegex(direct.NorthGuestRecoveryBlocked, "NAT IP not proven"):
                direct._vmx_nat_ip(self.vmx, IPv4Network("192.168.213.0/24"), timeout=0.1)

    def test_sources_are_replayed_only_after_exact_guest_proof(self):
        with patch.object(direct, "_authenticated_session", return_value=self.session), \
             patch.object(direct.socket, "create_connection", return_value=Mock()):
            self.assertTrue(direct.recover_north_first_boot(self.provider, "GOAD-DC01"))
        self.assertTrue(self.session.provisioned)
        self.assertEqual(len(self.session.setup_scripts), 2)
        self.assertIn("-ip '10.4.20.10' '10.4.20.1' '00:50:56:20:20:10'",
                      self.session.setup_scripts[-1].replace("& $script ", "-ip "))
        self.assertTrue(direct.prove_canonical_guest)

    def test_installed_guest_is_not_reprovisioned(self):
        self.session.provisioned = True
        with patch.object(direct, "_authenticated_session", return_value=self.session), \
             patch.object(direct.socket, "create_connection", return_value=Mock()):
            self.assertTrue(direct.recover_north_first_boot(self.provider, "GOAD-DC01"))
        self.assertEqual(self.session.setup_scripts, [])


if __name__ == "__main__":
    unittest.main()
