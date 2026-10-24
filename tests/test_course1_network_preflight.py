"""No host mutations: tests for strict Kingdoms NORTH vmnet/IP/MAC gates."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goad.course1_artifact_render import render_course1_artifacts
from goad.course1_network_preflight import (
    NetworkConflict, inactive_vmware, inspect_network_files,
    inspect_vmware_library, inspect_live,
)
from goad.kingdoms_topology import load_course1_topology


class NetworkOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.planned = load_course1_topology()
        cls.artifacts = render_course1_artifacts()

    def test_empty_lab_network_is_allowed_in_pure_read_only_inspector(self):
        inspect_network_files(
            self.planned,
            "answer VNET_1_HOSTONLY_SUBNET 192.168.100.0\n"
            "answer VNET_8_NAT yes\n",
            [{"ifname": "vmnet1"}, {"ifname": "vmnet8"}, {"ifname": "eth0"}],
            [{"ifname": "eth0", "addr_info": [
                {"family": "inet", "local": "192.168.213.10", "prefixlen": 24}
            ]}],
            [{"dst": "default", "gateway": "192.168.213.1"},
             {"dst": "192.168.213.0/24", "dev": "eth0"}],
        )

    def test_configured_requested_vmnet_refuses(self):
        with self.assertRaisesRegex(NetworkConflict, "IDs already exist"):
            inspect_network_files(
                self.planned, "answer VNET_10_DHCP no\n", [], [], []
            )

    def test_live_requested_vmnet_refuses_even_without_settings(self):
        with self.assertRaisesRegex(NetworkConflict, "interfaces already exist"):
            inspect_network_files(
                self.planned, "", [{"ifname": "vmnet20"}], [], []
            )

    def test_occupied_host_address_refuses(self):
        with self.assertRaisesRegex(NetworkConflict, "already occupies"):
            inspect_network_files(
                self.planned, "", [],
                [{"ifname": "eth2", "addr_info": [
                    {"family": "inet", "local": "10.4.10.254", "prefixlen": 24}
                ]}], []
            )

    def test_existing_host_route_into_protected_zone_refuses(self):
        with self.assertRaisesRegex(NetworkConflict, "overlaps"):
            inspect_network_files(
                self.planned, "", [], [],
                [{"dst": "10.4.20.0/24", "dev": "tun0"}]
            )

    def test_broad_vpn_route_overlapping_requested_subnet_refuses(self):
        with self.assertRaisesRegex(NetworkConflict, "overlaps"):
            inspect_network_files(
                self.planned, "", [], [],
                [{"dst": "10.4.0.0/16", "dev": "wg0"}]
            )

    def test_registered_foreign_vmnet_refuses(self):
        path = "/home/stark/another-lab/server.vmx"
        reg = f'vmlist12.config = "{path}"\n'
        with self.assertRaisesRegex(NetworkConflict, "conflicting vmnet/MAC"):
            inspect_vmware_library(
                self.planned, self.artifacts, reg,
                {path: 'ethernet1.vnet = "vmnet10"\n'}
            )

    def test_registered_foreign_mac_refuses_even_on_other_vmnet(self):
        path = "/home/stark/other.vmx"
        from goad.course1_artifact_render import MAC_PATTERN
        mac = MAC_PATTERN.findall(
            self.artifacts["providers/vmware/Vagrantfile"]
        )[0]
        with self.assertRaisesRegex(NetworkConflict, "conflicting vmnet/MAC"):
            inspect_vmware_library(
                self.planned, self.artifacts,
                f'vmlist12.config = "{path}"\n',
                {path: f'ethernet1.vnet = "vmnet55"\n'
                       f'ethernet1.address = "{mac}"\n'}
            )

    def test_missing_registered_vm_cannot_be_assumed_safe(self):
        path = "/other/missing.vmx"
        with self.assertRaisesRegex(NetworkConflict, "cannot be inspected"):
            inspect_vmware_library(
                self.planned, self.artifacts,
                f'vmlist4.config = "{path}"\n', {}
            )

    def test_only_unrelated_registered_guests_are_allowed(self):
        path = "/other/clean.vmx"
        inspect_vmware_library(
            self.planned, self.artifacts,
            f'vmlist22.config = "{path}"\n',
            {path: 'ethernet1.vnet = "vmnet55"\n'
                   'ethernet1.address = "00:50:56:00:ab:cd"\n'}
        )

    def test_vmware_running_guest_refuses(self):
        with patch("goad.course1_network_preflight.command",
                   return_value="Total running VMs: 1\n/tmp/a.vmx\n"):
            with self.assertRaisesRegex(NetworkConflict, "running guests"):
                inactive_vmware()

    def test_vmware_gui_refuses_even_when_no_guest_runs(self):
        with patch("goad.course1_network_preflight.command",
                   return_value="Total running VMs: 0\n"), patch(
                       "goad.course1_network_preflight.subprocess.run",
                       side_effect=[
                           subprocess.CompletedProcess([], 1, "", ""),
                           subprocess.CompletedProcess([], 0, "123\n", ""),
                       ]
                   ):
            with self.assertRaisesRegex(NetworkConflict, "vmware is active"):
                inactive_vmware()

    def test_missing_networking_file_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp, patch(
            "goad.course1_network_preflight.inactive_vmware"
        ):
            with self.assertRaisesRegex(NetworkConflict, "absent"):
                inspect_live(networking=Path(temp)/"missing", library=Path(temp)/"none")

    def test_inspection_has_no_write_or_vm_creation_actions(self):
        text = (Path(__file__).resolve().parents[1] /
                "goad/course1_network_preflight.py").read_text()
        for forbidden in ("write_text(", "open('w'", "vmware-networks --start",
                          "vagrant up", "ip route add", "ip route replace",
                          "shutil.rmtree(", "systemctl start"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
