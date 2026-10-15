"""Mock/fixture-only tests for WSLPE Stage 2 guest inspection.

No VMware, Vagrant, WinRM or Windows commands are executed by these tests.
"""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/wslpe-stage2-inspect.py"
SPEC = importlib.util.spec_from_file_location("wslpe_stage2_inspector", SOURCE)
assert SPEC and SPEC.loader
STAGE2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STAGE2)


def guest_data():
    return {
        "Name": "WSLPE-WS01", "ProductType": 1,
        "OSCaption": "Microsoft Windows 10 Pro",
        "WindowsVersion": "10.0.19045", "WindowsBuild": "19045",
        "DomainJoined": False, "UAC": 1,
        "Firewall": [
            {"Name": "Domain", "Enabled": True},
            {"Name": "Private", "Enabled": True},
            {"Name": "Public", "Enabled": True},
        ],
        "DefenderService": True, "DefenderAntivirus": True,
        "IPv4": [
            {"IPAddress": "192.168.213.104", "InterfaceIndex": 11, "PrefixLength": 24},
            {"IPAddress": "172.28.231.31", "InterfaceIndex": 12, "PrefixLength": 24},
        ],
        "Interfaces": [
            {"Name": "Ethernet0", "InterfaceIndex": 11, "Status": "Up"},
            {"Name": "Ethernet1", "InterfaceIndex": 12, "Status": "Up"},
        ],
        "DefaultRoutes": [
            {"InterfaceIndex": 11, "NextHop": "192.168.213.2"}
        ],
        "LearnerExists": False,
    }


def manifest(name):
    return {
        "id": name, "lab": "WSLPE", "provider": "vmware",
        "provisioner": "local", "status": "ready for provisioning",
        "ip_range": "172.28.231", "extensions": [], "is_default": False,
    }


class WslpeStage2InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.instance = self.workspace / "wslpe-fixture"
        self.instance.mkdir()
        (self.instance / "instance.json").write_text(
            json.dumps(manifest(self.instance.name)), encoding="utf-8"
        )

    def test_exact_native_provided_instance(self):
        found, info = STAGE2.find_instance(self.workspace)
        self.assertEqual(found, self.instance)
        self.assertEqual(info["status"], "ready for provisioning")
        self.assertEqual(info["ip_range"], "172.28.231")

    def test_rejects_duplicate_instance_or_wrong_lab_status(self):
        other = self.workspace / "wslpe-other"
        other.mkdir()
        (other / "instance.json").write_text(
            json.dumps(manifest(other.name)), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "Exactly one"):
            STAGE2.find_instance(self.workspace)
        (other / "instance.json").unlink()
        original = manifest(self.instance.name)
        original["status"] = "installed"
        (self.instance / "instance.json").write_text(json.dumps(original))
        with self.assertRaisesRegex(ValueError, "status"):
            STAGE2.find_instance(self.workspace)

    def test_refuses_symlinked_workspace(self):
        other = self.root / "other"
        other.mkdir()
        link = self.root / "linked"
        link.symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            STAGE2.find_instance(link)

    def test_parse_actual_vmware_adapter_types(self):
        vmx_text = '''
ethernet0.present = "TRUE"
ethernet0.connectionType = "nat"
ethernet0.generatedAddress = "00:0c:29:00:11:22"
ethernet1.present = "TRUE"
ethernet1.connectionType = "custom"
ethernet1.vnet = "vmnet2"
ethernet2.present = "FALSE"
ethernet2.connectionType = "nat"
'''
        adapters = STAGE2.vmx_network_adapters(vmx_text)
        self.assertEqual(len(adapters), 2)
        self.assertEqual(adapters[0]["type"], "nat")
        self.assertEqual(adapters[1]["vnet"], "vmnet2")

    def test_exact_vm_registration_checked_against_vmrun(self):
        state = (self.instance / "provider/.vagrant/machines/WSLPE-WS01"
                 "/vmware_desktop")
        state.mkdir(parents=True)
        vmx = self.root / "windows_10.vmx"
        vmx.write_text("displayName = WSLPE")
        (state / "id").write_text(str(vmx))
        with patch.object(STAGE2, "read_command", return_value=(
            f"Total running VMs: 1\n{vmx}\n"
        )) as command:
            self.assertEqual(STAGE2.locate_registered_vm(self.instance), vmx)
        command.assert_called_once_with(["vmrun", "-T", "ws", "list"])

    def test_north_vmx_registration_blocked_without_vmrun(self):
        state = (self.instance / "provider/.vagrant/machines/WSLPE-WS01"
                 "/vmware_desktop")
        state.mkdir(parents=True)
        vmx = self.root / "GOAD-WS01.vmx"
        vmx.write_text("NORTH fixture")
        (state / "id").write_text(str(vmx))
        with patch.object(STAGE2, "read_command",
                          side_effect=AssertionError("do not inspect vmrun")):
            with self.assertRaisesRegex(ValueError, "NORTH"):
                STAGE2.locate_registered_vm(self.instance)

    def test_vagrant_port_inspection_is_read_only(self):
        port_output = "5985 (guest) => 55985 (host)\n"
        with patch.object(STAGE2, "read_command",
                          return_value=port_output) as command:
            self.assertEqual(STAGE2.forwarded_winrm_port(self.instance), 55985)
        self.assertEqual(
            command.call_args.args[0],
            ["vagrant", "port", "WSLPE-WS01"],
        )

    def test_winrm_forwarding_bound_only_to_loopback(self):
        listeners = (
            "LISTEN 0 128 127.0.0.1:55985 0.0.0.0:*\n"
            "LISTEN 0 128 [::1]:55985 [::]:*\n"
        )
        with patch.object(STAGE2, "read_command",
                          return_value=listeners) as command:
            scope = STAGE2.inspect_management_port_binding(55985)
            self.assertIn("127.0.0.1", scope)
            self.assertIn("::1", scope)
            command.assert_called_once_with(["ss", "-H", "-ltn"])

    def test_winrm_wildcard_binding_fails_closed(self):
        for host in ("0.0.0.0", "*", "[::]", "192.168.76.160"):
            with self.subTest(host=host), patch.object(
                STAGE2, "read_command",
                return_value=f"LISTEN 0 128 {host}:55985 0.0.0.0:*\n",
            ):
                with self.assertRaisesRegex(ValueError, "exposed"):
                    STAGE2.inspect_management_port_binding(55985)

    def test_unproven_winrm_port_bind_fails_closed(self):
        with patch.object(STAGE2, "read_command",
                          return_value="LISTEN 0 128 127.0.0.1:44000 0.0.0.0:*"):
            with self.assertRaisesRegex(ValueError, "Cannot establish"):
                STAGE2.inspect_management_port_binding(55985)

    def test_guest_baseline_and_distinct_nat_exercise_ips_pass(self):
        ok, failed = STAGE2.evaluate_windows(guest_data(), "172.28.231")
        self.assertEqual(failed, [])
        self.assertGreaterEqual(len(ok), 7)

    def test_guest_domain_join_firewall_and_exercise_default_route_block(self):
        guest = guest_data()
        guest["DomainJoined"] = True
        guest["Firewall"][1]["Enabled"] = False
        guest["DefaultRoutes"] = [{"InterfaceIndex": 12, "NextHop": "172.28.231.1"}]
        passed, failed = STAGE2.evaluate_windows(guest, "172.28.231")
        self.assertTrue(any("Active Directory" in text for text in failed))
        self.assertTrue(any("firewall" in text.lower() for text in failed))
        self.assertTrue(any("default" in text.lower() for text in failed))
        self.assertTrue(passed)

    def test_other_windows_versions_cannot_masquerade_as_win10(self):
        guest = guest_data()
        guest["OSCaption"] = "Microsoft Windows 11 Pro"
        _, failed = STAGE2.evaluate_windows(guest, "172.28.231")
        self.assertTrue(any("Windows 10" in x for x in failed))

    def test_guest_wrong_ip_and_disabled_defender_block(self):
        guest = guest_data()
        guest["IPv4"] = [{"IPAddress": "172.28.230.31",
                          "InterfaceIndex": 12, "PrefixLength": 24}]
        guest["DefenderAntivirus"] = False
        _, failed = STAGE2.evaluate_windows(guest, "172.28.231")
        self.assertTrue(any("172.28.231.31" in x for x in failed))
        self.assertTrue(any("Defender" in x for x in failed))

    def test_windows_probe_script_contains_only_read_operations(self):
        powershell = STAGE2.WINDOWS_READ_ONLY.lower()
        for forbidden in (
            "set-net", "new-net", "remove-net", "new-localuser",
            "set-itemproperty", "new-item", "invoke-expression",
            "restart-computer", "stop-service", "start-process",
        ):
            self.assertNotIn(forbidden, powershell)
        self.assertIn("convertto-json", powershell)
        self.assertIn("get-mpcomputerstatus", powershell)


if __name__ == "__main__":
    unittest.main()
