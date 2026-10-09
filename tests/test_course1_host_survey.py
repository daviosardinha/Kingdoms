"""Unit tests for read-only VMware host survey parsers and coverage flags."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goad import course1_host_survey as survey


class Course1HostSurveyTests(unittest.TestCase):
    def test_network_config_parses_ids_and_subnet_hints(self):
        raw = "\n".join([
            "answer VNET_1_VIRTUAL_ADAPTER yes",
            "answer VNET_8_HOSTONLY_SUBNET 192.168.99.0",
            "answer VNET_99_HOSTONLY_SUBNET 10.4.99.0",
            "add_bridge_mapping eth0 0",
        ])
        names, hints = survey.parse_vmware_networking(raw)
        self.assertEqual(names, ["vmnet1", "vmnet8", "vmnet99"])
        self.assertEqual(hints, [
            {"vmnet": "vmnet8", "subnet_address": "192.168.99.0"},
            {"vmnet": "vmnet99", "subnet_address": "10.4.99.0"},
        ])

    def test_vmnet_order_is_numeric(self):
        self.assertEqual(sorted(["vmnet99", "vmnet8", "vmnet10"],
                                key=survey.vmnet_order),
                         ["vmnet8", "vmnet10", "vmnet99"])

    def test_host_addresses_ipv4_only(self):
        rows = [
            {"ifname": "vmnet10", "operstate": "UP", "addr_info": [
                {"family": "inet", "local": "10.4.10.254", "prefixlen": 24},
                {"family": "inet6", "local": "fe80::1", "prefixlen": 64},
            ]},
            {"ifname": "lo", "operstate": "UNKNOWN", "addr_info": [
                {"family": "inet", "local": "127.0.0.1", "prefixlen": 8}
            ]},
        ]
        self.assertEqual(survey.parse_ip_addresses(json.dumps(rows)), [
            {"interface": "lo", "state": "UNKNOWN", "ipv4": ["127.0.0.1/8"]},
            {"interface": "vmnet10", "state": "UP",
             "ipv4": ["10.4.10.254/24"]},
        ])

    def test_host_routes_normalized_without_raw_output(self):
        source = [
            {"dst": "10.4.10.0/24", "dev": "vmnet10", "protocol": "kernel",
             "prefsrc": "10.4.10.254"},
            {"dst": "default", "gateway": "192.0.2.1", "dev": "eth0"},
        ]
        normalized = survey.parse_ip_routes(json.dumps(source))
        self.assertEqual(normalized[0]["destination"], "10.4.10.0/24")
        self.assertEqual(normalized[0]["source"], "10.4.10.254")
        self.assertNotIn("protocol", normalized[0])

    def test_vmrun_list_parse_and_count_gate(self):
        result = survey.parse_vmrun_list("Total running VMs: 2\n/tmp/a/a.vmx\n/tmp/b/b.vmx\n")
        self.assertEqual([p.name for p in result], ["a.vmx", "b.vmx"])
        with self.assertRaises(ValueError):
            survey.parse_vmrun_list("Total running VMs: 2\n/tmp/a/a.vmx\n")
        with self.assertRaises(ValueError):
            survey.parse_vmrun_list("Unknown VM list\n/tmp/a/a.vmx\n")

    def test_vmx_network_settings_do_not_leak_other_vm_properties(self):
        text = "\n".join([
            'ethernet0.connectionType = "nat"',
            'ethernet0.generatedAddress = "00:50:56:10:99:01"',
            'ethernet1.vnet = "vmnet10"',
            'ethernet1.address = "02:44:10:00:01:01"',
            'ethernet1.startConnected = "TRUE"',
            'guestinfo.password = "never-display-this"',
            'displayName = "Secret machine"',
        ])
        adapters = survey.parse_vmx_adapters(text)
        self.assertEqual(adapters[0]["connectionType"], "nat")
        self.assertEqual(adapters[1]["vnet"], "vmnet10")
        self.assertEqual(adapters[1]["address"], "02:44:10:00:01:01")
        self.assertNotIn("never-display-this", json.dumps(adapters))
        self.assertNotIn("Secret machine", json.dumps(adapters))

    def test_running_vm_identity_detects_reference_mac_and_masks_path(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "GOAD-DC02.vmx"
            path.write_text('ethernet1.address = "00:50:56:20:10:11"\n',
                            encoding="utf-8")
            record = survey.running_guest_summary(
                path, frozenset({"00:50:56:20:10:11"})
            )
            self.assertTrue(record["readable"])
            self.assertTrue(record["reference_mac_match"])
            self.assertNotIn(str(path), json.dumps(record))
            self.assertEqual(len(record["vmx_identifier"]), 12)

    def test_missing_vm_is_partial_not_safe_to_allocate(self):
        with tempfile.TemporaryDirectory() as folder:
            vm = Path(folder) / "missing.vmx"
            info = survey.running_guest_summary(vm, frozenset())
            self.assertFalse(info["readable"])
            self.assertIsNone(info["reference_mac_match"])

    def mocked_host(self, *, incomplete_route=False, vmx_unreadable=False):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "vmware").mkdir()
        (root / "dev").mkdir()
        (root / "vmware" / "vmnet77").mkdir()
        (root / "dev" / "vmnet99").touch()
        (root / "networking").write_text(
            "answer VNET_77_HOSTONLY_SUBNET 10.77.0.0\n", encoding="utf-8"
        )
        vmx = root / "machine.vmx"
        if not vmx_unreadable:
            vmx.write_text(
                'ethernet1.vnet = "vmnet77"\n'
                'ethernet1.address = "00:50:56:20:10:11"\n',
                encoding="utf-8"
            )
        addresses = json.dumps([{"ifname": "vmnet77", "operstate": "UP",
                                 "addr_info": [{"family": "inet",
                                                "local": "10.77.0.1",
                                                "prefixlen": 24}]}])
        routes = json.dumps([{"dst": "10.77.0.0/24", "dev": "vmnet77"}])
        outputs = {
            ("ip", "-j", "address", "show"): (addresses, None),
            ("ip", "-j", "route", "show", "table", "all"):
                (None, "route probe failed") if incomplete_route else (routes, None),
            ("vmrun", "-T", "ws", "list"):
                (f"Total running VMs: 1\n{vmx}\n", None),
        }
        return root, outputs

    def run_mocked(self, incomplete_route=False, vmx_unreadable=False):
        root, outputs = self.mocked_host(incomplete_route=incomplete_route,
                                         vmx_unreadable=vmx_unreadable)
        with patch.object(survey, "VMWARE_ROOT", root / "vmware"), \
             patch.object(survey, "DEVICE_ROOT", root / "dev"), \
             patch.object(survey, "NETWORKING", root / "networking"), \
             patch.object(survey, "_query",
                          side_effect=lambda cmd: outputs[tuple(cmd)]):
            return survey.host_survey()

    def test_complete_survey_reports_observation_only(self):
        report = self.run_mocked()
        self.assertEqual(report["status"], "OBSERVED_SNAPSHOT")
        self.assertIn("vmnet77", report["observed_vmnets"])
        self.assertIn("vmnet99", report["observed_vmnets"])
        self.assertEqual(report["running_vm_count"], 1)
        self.assertTrue(report["running_vms"][0]["reference_mac_match"])
        self.assertFalse(report["deployment_authorized"])
        self.assertFalse(report["candidate_allocation_authorized"])
        self.assertTrue(report["no_changes_performed"])

    def test_failed_host_route_inspection_is_incomplete(self):
        report = self.run_mocked(incomplete_route=True)
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertFalse(report["coverage"]["ip_routes"])
        self.assertFalse(report["candidate_allocation_authorized"])

    def test_unreadable_running_vmx_does_not_claim_complete(self):
        report = self.run_mocked(vmx_unreadable=True)
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertFalse(report["coverage"]["vmrun_running"])
        self.assertIsNone(report["running_vms"][0]["reference_mac_match"])

    def test_invalid_json_parsers_fail(self):
        with self.assertRaises(ValueError):
            survey.parse_ip_routes('{"not":"a list"}')
        with self.assertRaises(ValueError):
            survey.parse_ip_addresses("{}")

    def test_compact_summary_does_not_include_vmx_adapter_inventory(self):
        report = self.run_mocked()
        compact = survey.compact_report(report)
        self.assertEqual(compact["running_vm_count"], 1)
        self.assertEqual(compact["running_vmx_readable"], 1)
        self.assertIn("vmnet77", compact["observed_vmnets"])
        self.assertNotIn("running_vms", compact)
        self.assertNotIn("ipv4_routes", compact)
        self.assertFalse(compact["deployment_authorized"])

    def test_no_destructive_host_commands(self):
        code = (survey.__file__ and Path(survey.__file__).read_text(encoding="utf-8"))
        self.assertIn('["vmrun", "-T", "ws", "list"]', code)
        self.assertIn('["ip", "-j", "address", "show"]', code)
        self.assertNotIn("os.system", code)
        self.assertNotIn("Path.write_text", code)
        self.assertNotIn("vagrant up", code)
        self.assertNotIn("vmrun stop", code)
        self.assertNotIn("ip link set", code)


if __name__ == "__main__":
    unittest.main()
