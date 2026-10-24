"""NORTH direct WinRM first-boot unit tests; no VMware or Windows changes."""
from __future__ import annotations

from ipaddress import IPv4Network
import base64
import hashlib
import re
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, MagicMock, patch

from goad import course1_direct_winrm as direct


class FakeWinRMSession:
    def __init__(self):
        self.setup_scripts = []
        self.provisioned = False
        self.fail_identity = False
        self.fail_at_chunk = 0
        self.chunks_seen = 0
        self.staged_bytes = bytearray()
        self.stage_removed = False
        self.commands = []

    def run_ps(self, script):
        self.commands.append(script)
        # The real pywinrm wraps all powershell commands as -EncodedCommand.
        # Enforce the small-command contract so a regression cannot recreate
        # the actual HTTP 500 "filename or extension is too long" failure.
        if len(script) > 3300:
            raise RuntimeError("Windows remoting command too large")
        if "ConvertTo-Json -Depth 5 -Compress" in script:
            macs = ["005056202010", "000C29285F3A"]
            if self.fail_identity:
                macs[0] = "005056202022"
            result = json.dumps({
                "Hostname": "WIN-DC01",
                "Windows": True,
                "PowerShell": 5,
                "Tools": True,
                "Adapters": [
                    {"Mac": mac, "Index": index, "Name": f"Ethernet{index}",
                     "IPv4": ["192.168.213.133"] if mac == "000C29285F3A" else []}
                    for index, mac in enumerate(macs)
                ]
            })
            return Mock(status_code=0, std_out=result.encode(), std_err=b"")
        if "NORTH_DIRECT_FIRST_BOOT_READY" in script:
            ok = self.provisioned
            return Mock(
                status_code=0 if ok else 1,
                std_out=b"NORTH_DIRECT_FIRST_BOOT_READY" if ok else b"",
                std_err=b"not yet configured" if not ok else b""
            )
        if "NORTH_STAGE_BEGIN" in script:
            self.staged_bytes = bytearray()
            self.stage_removed = False
            return Mock(status_code=0, std_out=b"NORTH_STAGE_BEGIN", std_err=b"")
        if "NORTH_STAGE_CHUNK" in script:
            self.chunks_seen += 1
            if self.chunks_seen == self.fail_at_chunk:
                return Mock(status_code=1, std_out=b"", std_err=b"chunk failed")
            match = re.search(r"FromBase64String\('([A-Za-z0-9+/=]+)'\)", script)
            assert match is not None
            self.staged_bytes.extend(base64.b64decode(match.group(1)))
            return Mock(status_code=0, std_out=b"NORTH_STAGE_CHUNK", std_err=b"")
        if "NORTH_STAGE_REMOVED" in script:
            self.stage_removed = True
            self.staged_bytes.clear()
            return Mock(status_code=0, std_out=b"NORTH_STAGE_REMOVED", std_err=b"")
        if "NORTH_SOURCE_SCRIPT_COMPLETED" in script:
            assert "Get-FileHash" in script
            digest = hashlib.sha256(self.staged_bytes).hexdigest().upper()
            assert digest in script
            assert f"$file.Length -ne {len(self.staged_bytes)}" in script
            self.setup_scripts.append((script, bytes(self.staged_bytes)))
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
             patch.object(direct.socket, "create_connection", return_value=MagicMock()):
            with self.assertRaisesRegex(direct.NorthGuestRecoveryBlocked, "MAC.*proof"):
                direct.prove_guest(self.provider, "GOAD-DC01")

    def test_forwarded_winrm_seeds_nat_when_vix_ip_fails(self):
        with patch.object(direct, "_vmx_nat_ip", side_effect=AssertionError(
                    "VMware VIX must not gate authenticated forwarded bootstrap")), \
             patch.object(direct, "_authenticated_session", return_value=self.session) as connect, \
             patch.object(direct.socket, "create_connection", return_value=MagicMock()):
            _session, nat_ip, guest = direct.prove_guest(
                self.provider, "GOAD-DC01", forwarded_port=55985
            )
        self.assertEqual(nat_ip, "192.168.213.133")
        self.assertEqual(guest["address"], "10.4.20.10")
        self.assertEqual(connect.call_args_list[0].args, ("127.0.0.1",))
        self.assertEqual(connect.call_args_list[0].kwargs, {"port": 55985})
        self.assertEqual(connect.call_args_list[1].args, ("192.168.213.133",))

    def test_forwarded_wrong_lab_mac_aborts_without_vix_or_provision(self):
        self.session.fail_identity = True
        with patch.object(direct, "_vmx_nat_ip") as vix, \
             patch.object(direct, "_authenticated_session", return_value=self.session), \
             patch.object(direct.socket, "create_connection", return_value=MagicMock()):
            with self.assertRaisesRegex(
                direct.NorthGuestIdentityMismatch, "MAC.*proof"
            ):
                direct.prove_guest(
                    self.provider, "GOAD-DC01", forwarded_port=55985
                )
        vix.assert_not_called()
        self.assertEqual(self.session.setup_scripts, [])

    def test_forwarded_nat_ip_must_route_on_vmnet8(self):
        def wrong_route(args, **kwargs):
            if args[:4] == ["ip", "-4", "route", "get"]:
                return Mock(returncode=0, stdout="192.168.213.133 dev wlan0\n")
            return self.commands(args, **kwargs)
        with patch.object(direct, "_command", side_effect=wrong_route), \
             patch.object(direct, "_vmx_nat_ip",
                          side_effect=direct.NorthGuestRecoveryBlocked("VIX offline")), \
             patch.object(direct, "_authenticated_session", return_value=self.session), \
             patch.object(direct.socket, "create_connection", return_value=MagicMock()):
            with self.assertRaisesRegex(
                direct.NorthGuestRecoveryBlocked, "Neither VMware vmnet8 DHCP lease nor VIX NAT IP"
            ):
                direct.prove_guest(
                    self.provider, "GOAD-DC01", forwarded_port=55985
                )
        self.assertEqual(self.session.setup_scripts, [])

    def _nat_lease(self, *, mac="00:0c:29:28:5f:3a",
                   ip="192.168.213.133", ends="2035/10/24 20:00:00",
                   state="active"):
        path = self.root / "vmnet8-dhcp.leases"
        path.write_text(
            "lease " + ip + " {\n"
            " starts 6 2026/10/24 13:00:00;\n"
            " ends 3 " + ends + ";\n"
            " hardware ethernet " + mac + ";\n"
            " binding state " + state + ";\n"
            "}\n",
            encoding="utf-8",
        )
        return path

    def test_dhcp_lease_recovers_when_forward_and_vix_both_down(self):
        lease = self._nat_lease()
        with patch.object(direct, "_NAT_DHCP_LEASE_FILES", (lease,)), \
             patch.object(direct, "_vmx_nat_ip") as vix, \
             patch.object(direct, "_authenticated_session", return_value=self.session), \
             patch.object(direct.socket, "create_connection",
                          side_effect=[OSError("forward refused"), MagicMock()]):
            _session, nat_ip, guest = direct.prove_guest(
                self.provider, "GOAD-DC01", forwarded_port=55985,
            )
        self.assertEqual(nat_ip, "192.168.213.133")
        self.assertEqual(guest["address"], "10.4.20.10")
        vix.assert_not_called()
        self.assertTrue(any("ConvertTo-Json" in c for c in self.session.commands))

    def test_dhcp_lease_rejects_foreign_mac_without_guest_connection(self):
        lease = self._nat_lease(mac="00:0c:29:99:99:99")
        with patch.object(direct, "_NAT_DHCP_LEASE_FILES", (lease,)):
            self.assertIsNone(direct._vmware_nat_lease_ip(
                {"ethernet0.generatedaddress": "00:0c:29:28:5f:3a"},
                IPv4Network("192.168.213.0/24")
            ))

    def test_dhcp_lease_rejects_expired_and_released(self):
        from datetime import datetime, timezone
        last_year = str(datetime.now(timezone.utc).year - 1)
        lease = self._nat_lease(ends=last_year + "/01/01 00:00:00")
        with patch.object(direct, "_NAT_DHCP_LEASE_FILES", (lease,)):
            self.assertIsNone(direct._vmware_nat_lease_ip(
                {"ethernet0.generatedaddress": "00:0c:29:28:5f:3a"},
                IPv4Network("192.168.213.0/24")
            ))
        lease = self._nat_lease(state="free")
        with patch.object(direct, "_NAT_DHCP_LEASE_FILES", (lease,)):
            self.assertIsNone(direct._vmware_nat_lease_ip(
                {"ethernet0.generatedaddress": "00:0c:29:28:5f:3a"},
                IPv4Network("192.168.213.0/24")
            ))

    def test_dhcp_lease_rejects_address_outside_nat_vmnet(self):
        lease = self._nat_lease(ip="192.168.214.40")
        with patch.object(direct, "_NAT_DHCP_LEASE_FILES", (lease,)):
            self.assertIsNone(direct._vmware_nat_lease_ip(
                {"ethernet0.generatedaddress": "00:0c:29:28:5f:3a"},
                IPv4Network("192.168.213.0/24")
            ))

    def test_dhcp_lease_refuses_symlinked_journal(self):
        original = self._nat_lease()
        alias = self.root / "alias.leases"
        alias.symlink_to(original)
        with patch.object(direct, "_NAT_DHCP_LEASE_FILES", (alias,)):
            self.assertIsNone(direct._vmware_nat_lease_ip(
                {"ethernet0.generatedaddress": "00:0c:29:28:5f:3a"},
                IPv4Network("192.168.213.0/24")
            ))

    def test_unavailable_forwarded_port_falls_back_to_vix(self):
        # The preceding NORTH guest failed with absent forwarded ports.
        # Keep direct VIX recovery functional for that opposite combination.
        with patch.object(direct, "_authenticated_session", return_value=self.session), \
             patch.object(direct.socket, "create_connection",
                          side_effect=[OSError("localhost refused"), MagicMock()]):
            _session, nat_ip, _guest = direct.prove_guest(
                self.provider, "GOAD-DC01", forwarded_port=55985
            )
        self.assertEqual(nat_ip, "192.168.213.133")

    def test_forwarded_winrm_guest_nic_ip_outside_vmnet8(self):
        original = direct._verified_identity
        def mutate(session, values, machine):
            nic = original(session, values, machine)
            nic["IPv4"] = ["169.254.88.9"]
            return nic
        with patch.object(direct, "_verified_identity", side_effect=mutate), \
             patch.object(direct, "_vmx_nat_ip",
                          side_effect=direct.NorthGuestRecoveryBlocked("VIX offline")), \
             patch.object(direct, "_authenticated_session", return_value=self.session), \
             patch.object(direct.socket, "create_connection", return_value=MagicMock()):
            with self.assertRaisesRegex(
                direct.NorthGuestRecoveryBlocked, "outside owned vmnet8"
            ):
                direct.prove_guest(
                    self.provider, "GOAD-DC01", forwarded_port=55985
                )

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
             patch.object(direct.socket, "create_connection", return_value=MagicMock()):
            self.assertTrue(direct.recover_north_first_boot(self.provider, "GOAD-DC01"))
        self.assertTrue(self.session.provisioned)
        self.assertEqual(len(self.session.setup_scripts), 2)
        self.assertIn("-File $p '10.4.20.10' '10.4.20.1' '00:50:56:20:20:10'",
                      self.session.setup_scripts[-1][0])
        self.assertEqual(
            self.session.setup_scripts[0][1],
            (direct.ROOT / "vagrant/ConfigureRemotingForAnsible.ps1").read_bytes()
        )
        self.assertEqual(
            self.session.setup_scripts[1][1],
            (direct.ROOT / "vagrant/fix_ip.ps1").read_bytes()
        )
        self.assertTrue(self.session.stage_removed)
        self.assertGreater(self.session.chunks_seen, 2)

        self.assertTrue(direct.prove_canonical_guest)

    def test_partial_transfer_is_cleaned_without_running_script(self):
        self.session.fail_at_chunk = 2
        with patch.object(direct, "_authenticated_session", return_value=self.session), \
             patch.object(direct.socket, "create_connection", return_value=MagicMock()):
            with self.assertRaisesRegex(
                direct.NorthGuestRecoveryBlocked, "Direct guest operation failed"
            ):
                direct.recover_north_first_boot(self.provider, "GOAD-DC01")
        self.assertTrue(self.session.stage_removed)
        self.assertEqual(self.session.setup_scripts, [])

    def test_wrong_source_path_refused_before_winrm(self):
        with self.assertRaisesRegex(
            direct.NorthGuestRecoveryBlocked, "Unexpected Vagrant provisioning script"
        ):
            direct._execute_source(self.session, self.root / "unexpected.ps1")
        self.assertEqual(self.session.commands, [])

    def test_unexpected_script_arguments_refused(self):
        with self.assertRaisesRegex(
            direct.NorthGuestRecoveryBlocked, "argument count"
        ):
            direct._execute_source(
                self.session, direct.ROOT / "vagrant/fix_ip.ps1", ()
            )
        self.assertEqual(self.session.commands, [])

    def test_large_script_is_chunked_and_exact_hash_verified(self):
        original = (direct.ROOT / "vagrant/ConfigureRemotingForAnsible.ps1").read_bytes()
        assert len(original) > 4096
        direct._execute_source(
            self.session, direct.ROOT / "vagrant/ConfigureRemotingForAnsible.ps1"
        )
        self.assertEqual(self.session.setup_scripts[0][1], original)
        self.assertTrue(self.session.stage_removed)
        self.assertGreater(self.session.chunks_seen, len(original)//2048)
        self.assertLessEqual(max(map(len, self.session.commands)), 3300)

    def test_installed_guest_is_not_reprovisioned(self):
        self.session.provisioned = True
        with patch.object(direct, "_authenticated_session", return_value=self.session), \
             patch.object(direct.socket, "create_connection", return_value=MagicMock()):
            self.assertTrue(direct.recover_north_first_boot(self.provider, "GOAD-DC01"))
        self.assertEqual(self.session.setup_scripts, [])


if __name__ == "__main__":
    unittest.main()
