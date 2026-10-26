"""Offline-only checks for Purple Team additive VMware networking.

These tests NEVER edit /etc/vmware, restart networking, or launch a VM.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from goad import purple_vmware_network as purple


BASE = (
    "answer VNET_8_DHCP yes\n"
    "answer VNET_8_NAT yes\n"
    "answer VNET_8_HOSTONLY_SUBNET 192.168.213.0\n"
    "answer VNET_8_HOSTONLY_NETMASK 255.255.255.0\n"
)


class PurpleVmwareNetworkTests(unittest.TestCase):
    def test_render_is_additive(self):
        output = purple.append_vmnet(BASE)
        self.assertTrue(output.startswith(BASE))
        self.assertEqual(output.count("answer VNET_40_DHCP no"), 1)
        self.assertIn("answer VNET_40_VIRTUAL_ADAPTER yes", output)
        self.assertIn("answer VNET_40_HOSTONLY_SUBNET 192.168.240.0", output)

    def test_reject_existing_vmnet(self):
        with self.assertRaises(purple.PurpleNetworkError):
            purple.append_vmnet(BASE + "answer VNET_40_NAT no\n")

    def test_reject_overlapping_vmware_subnet(self):
        with self.assertRaises(purple.PurpleNetworkError):
            purple.append_vmnet(
                BASE + "answer VNET_3_HOSTONLY_SUBNET 192.168.240.0\n"
                + "answer VNET_3_HOSTONLY_NETMASK 255.255.255.0\n"
            )

    def test_reject_extra_vmnet40_directive(self):
        proposal = purple.append_vmnet(BASE).encode()
        with self.assertRaises(purple.PurpleNetworkError):
            purple.strip_checked_overlay(proposal + b"answer VNET_40_BRIDGE yes\n")

    def test_reject_duplicate_vmnet40_setting(self):
        proposal = purple.append_vmnet(BASE).encode()
        with self.assertRaises(purple.PurpleNetworkError):
            purple.strip_checked_overlay(proposal + b"answer VNET_40_NAT no\n")

    def test_allow_only_known_optional_hostaddr_removal(self):
        proposal = purple.append_vmnet(BASE).encode()
        self.assertIn(BASE, purple.strip_checked_overlay(proposal).decode())
        normalized = proposal.replace(
            b"answer VNET_40_HOSTONLY_HOSTADDR 192.168.240.1\n", b""
        )
        purple.strip_checked_overlay(normalized)
        with self.assertRaises(purple.PurpleNetworkError):
            purple.strip_checked_overlay(
                proposal.replace(b"HOSTONLY_HOSTADDR 192.168.240.1",
                                 b"HOSTONLY_HOSTADDR 192.168.240.7")
            )

    def test_attestation_is_bound_to_north_and_purple_owner(self):
        north_owner = b'{"profile":"NORTH"}'
        config = purple.append_vmnet(BASE).encode()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            backup = root / "purple-test" / "networking.original"
            backup.parent.mkdir()
            backup.write_bytes(BASE.encode())
            backup.chmod(0o600)
            receipt = root / "kingdoms-purple-owner.json"
            record = {
                "schema": "kingdoms.purple.vmnet.v1",
                "provider": "/test/north",
                "purple_provider": "/test/purple",
                "north_owner_sha256": hashlib.sha256(north_owner).hexdigest(),
                "network_before_sha256": hashlib.sha256(BASE.encode()).hexdigest(),
                "network_after_sha256": hashlib.sha256(config).hexdigest(),
                "vmnet": "vmnet40",
                "subnet": "192.168.240.0/24",
                "backup": str(backup),
            }
            receipt.write_text(json.dumps(record))
            receipt.chmod(0o600)
            with patch.object(purple, "BACKUPS", root):
                result = purple.authorized_strip(
                    config, north_owner, receipt=receipt,
                    north_provider="/test/north",
                    purple_provider="/test/purple", uid=os.geteuid()
                )
                self.assertIn(BASE, result.decode())
                with self.assertRaises(purple.PurpleNetworkError):
                    purple.authorized_strip(
                        config, b"changed North owner", receipt=receipt,
                        north_provider="/test/north", uid=os.geteuid()
                    )
                with self.assertRaises(purple.PurpleNetworkError):
                    purple.authorized_strip(
                        config, north_owner, receipt=receipt,
                        purple_provider="/test/foreign", uid=os.geteuid()
                    )
                with self.assertRaises(purple.PurpleNetworkError):
                    purple.authorized_strip(
                        config + b"answer VNET_40_DHCP yes\n",
                        north_owner, receipt=receipt, uid=os.geteuid()
                    )

    def test_provider_hook_is_purple_only(self):
        root = Path(__file__).resolve().parents[1]
        vmware = (root / "goad" / "provider" / "vagrant" / "vmware.py").read_text()
        self.assertIn("if self.lab_name == 'PURPLE':", vmware)
        self.assertIn("'goad.purple_vmware_network', 'ensure'", vmware)
        north = (root / "goad" / "course1_host_network_apply.py").read_text()
        self.assertIn("authorized_strip(", north)
        self.assertIn("if purple_receipt.exists() or purple_receipt.is_symlink()", north)


if __name__ == "__main__":
    unittest.main()
