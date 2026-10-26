"""Offline verification of installed NORTH Purple overlay compatibility."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from goad import purple_vmware_network as network

BASE = (
    "answer VNET_8_DHCP yes\n"
    "answer VNET_8_NAT yes\n"
    "answer VNET_8_HOSTONLY_SUBNET 192.168.213.0\n"
    "answer VNET_8_HOSTONLY_NETMASK 255.255.255.0\n"
)


class PurpleNorthCompatTests(unittest.TestCase):
    def test_north_gate_requires_receipt(self):
        code = Path(__file__).resolve().parents[1].joinpath(
            "goad/course1_host_network_apply.py"
        ).read_text()
        self.assertIn('purple_receipt.exists() or purple_receipt.is_symlink()', code)
        self.assertIn('authorized_strip(', code)
        self.assertIn('north_observed, saved.read_bytes(), layout', code)

    def test_known_overlay_only(self):
        config = network.append_vmnet(BASE).encode()
        self.assertIn(BASE, network.strip_checked_overlay(config).decode())
        with self.assertRaises(network.PurpleNetworkError):
            network.strip_checked_overlay(
                config + b"answer VNET_40_NAT yes\n"
            )
        with self.assertRaises(network.PurpleNetworkError):
            network.strip_checked_overlay(
                config + b"answer VNET_40_HOSTONLY_SUBNET 192.168.10.0\n"
            )

    def test_root_attestation_tied_to_original_north_owner(self):
        owner_bytes = b'{"profile":"NORTH"}'
        config = network.append_vmnet(BASE).encode()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            backup = root / "purple-demo" / "networking.original"
            backup.parent.mkdir()
            backup.write_bytes(BASE.encode())
            backup.chmod(0o600)
            receipt = root / "kingdoms-purple-owner.json"
            receipt.write_text(json.dumps({
                "schema": "kingdoms.purple.vmnet.v1",
                "provider": "/north/provider",
                "purple_provider": "/purple/provider",
                "north_owner_sha256": hashlib.sha256(owner_bytes).hexdigest(),
                "network_before_sha256": hashlib.sha256(BASE.encode()).hexdigest(),
                "network_after_sha256": hashlib.sha256(config).hexdigest(),
                "vmnet": "vmnet40",
                "subnet": "192.168.240.0/24",
                "backup": str(backup),
            }))
            receipt.chmod(0o600)
            with patch.object(network, "BACKUPS", root):
                network.authorized_strip(
                    config, owner_bytes, receipt=receipt,
                    north_provider="/north/provider",
                    purple_provider="/purple/provider", uid=os.geteuid()
                )
                with self.assertRaises(network.PurpleNetworkError):
                    network.authorized_strip(
                        config, b"changed", receipt=receipt,
                        uid=os.geteuid()
                    )

if __name__ == "__main__":
    unittest.main()
