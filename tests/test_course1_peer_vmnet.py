"""Source-only WSLPE peer ownership and NORTH vmnet rejection tests."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from goad.kingdoms_topology import load_course1_topology
from goad.course1_peer_vmnet import (
    SCHEMA, verified_wslpe_peer_additions,
)
from goad.course1_vmnet_config import (
    NetworkPlanError, render_vmnet_config, verify_owned_vmnet_runtime,
)


class WslpePeerVmnetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.provider = self.root / "provider"
        self.provider.mkdir()
        self.vagrant = self.provider / "Vagrantfile"
        self.vagrant.write_text(
            'boxes = [{ :name => "WSLPE-WS01", :ip => "172.28.231.31" }]\n',
            encoding="utf-8",
        )
        self.vmx = (self.provider / ".vagrant/machines/WSLPE-WS01"
                    / "vmware_desktop/session/windows_10.vmx")
        self.vmx.parent.mkdir(parents=True)
        self.vmx.write_text(
            'ethernet0.connectionType = "nat"\n'
            'ethernet1.connectionType = "custom"\n'
            'ethernet1.vnet = "vmnet2"\n',
            encoding="utf-8",
        )
        self.peer_file = self.root / "peer.json"
        self.record = {
            "schema": SCHEMA,
            "vmx": str(self.vmx),
            "vmx_sha256": hashlib.sha256(self.vmx.read_bytes()).hexdigest(),
            "vagrantfile": str(self.vagrant),
            "vagrantfile_sha256": hashlib.sha256(self.vagrant.read_bytes()).hexdigest(),
            "vmnet": "vmnet2",
            "subnet": "172.28.231.0/24",
            "host_address": "172.28.231.1",
            "guest_address": "172.28.231.31",
            "host_ports": {"5985": 2210, "5986": 2211, "22": 2212},
        }
        self.write_record()
        self.layout = load_course1_topology()
        self.base = (
            "VERSION=1,0\n"
            "answer VNET_8_DHCP yes\n"
            "answer VNET_8_HOSTONLY_NETMASK 255.255.255.0\n"
            "answer VNET_8_HOSTONLY_SUBNET 192.168.213.0\n"
            "answer VNET_8_NAT yes\n"
            "answer VNET_8_VIRTUAL_ADAPTER yes\n"
        ).encode()
        self.owned = render_vmnet_config(self.base.decode(), self.layout).encode()
        original = [
            line for line in self.owned.decode().splitlines()
            if line and not line.startswith("#")
            and "HOSTONLY_HOSTADDR" not in line
        ]
        self.runtime_prefix = "\n".join(reversed(original)) + "\n"

    def write_record(self):
        self.peer_file.write_text(json.dumps(self.record), encoding="utf-8")
        self.peer_file.chmod(0o600)

    def approved(self):
        return verified_wslpe_peer_additions(
            self.peer_file, owner_uid=os.getuid(), inspect_host=False,
            original_baseline=self.base,
        )

    def runtime(self, extra=""):
        return (
            self.runtime_prefix + "\n".join(sorted(self.approved())) + "\n" + extra
        ).encode()

    def test_no_peer_auto_discovery_or_untrusted_approval(self):
        expected = self.approved()
        self.assertEqual(len(expected), 8)
        with self.assertRaises(NetworkPlanError):
            verify_owned_vmnet_runtime(self.owned, self.runtime(), self.base, self.layout)
        self.assertNotIn("answer VNET_2_NAT yes", expected)

    def test_verified_peer_is_exact_and_preserves_north_owner(self):
        original = self.owned
        notices = verify_owned_vmnet_runtime(
            self.owned, self.runtime(), self.base, self.layout,
            peer_additions=self.approved(),
        )
        self.assertTrue(any("peer" in x for x in notices))
        self.assertEqual(self.owned, original)

    def test_real_operator_vmnet2_and_vmnet8_forwarding_shape(self):
        """Regress the observed NORTH drift with verified WSLPE peer ownership.

        The 2026-10-20 host diagnosis showed VMware-reordered NORTH vmnets,
        foreign vmnet1/vmnet8 hash rotation, a new vmnet2 exercise subnet,
        WSLPE 2210/2211/2212 and independent vmnet8 Vagrant forwards.
        No foreign forward is authorized by the WSLPE peer record.
        """
        foreign = (
            "add_nat_portfwd 8 tcp 2200 192.168.213.245 5985\\n"
            "add_nat_portfwd 8 tcp 2201 192.168.213.245 5986\\n"
            "add_nat_portfwd 8 tcp 2202 192.168.213.245 22\\n"
            "add_nat_portfwd 8 tcp 2203 192.168.213.246 5985\\n"
            "add_nat_portfwd 8 tcp 2204 192.168.213.246 5986\\n"
            "add_nat_portfwd 8 tcp 2205 192.168.213.246 22\\n"
            "add_nat_portfwd 8 tcp 2206 192.168.213.247 5985\\n"
            "add_nat_portfwd 8 tcp 2207 192.168.213.247 5986\\n"
            "add_nat_portfwd 8 tcp 2208 192.168.213.247 22\\n"
            "add_nat_portfwd 8 tcp 2209 192.168.213.244 22\\n"
            "add_nat_portfwd 8 tcp 2222 192.168.213.244 22\\n"
            "add_nat_portfwd 8 tcp 55985 192.168.213.244 5985\\n"
            "add_nat_portfwd 8 tcp 55986 192.168.213.244 5986\\n"
        ).replace("\\\\n", "\\n")
        current = self.runtime(foreign)
        self.assertIn(b"answer VNET_2_HOSTONLY_SUBNET 172.28.231.0", current)
        self.assertIn(b"add_nat_portfwd 8 tcp 2210 172.28.231.31 5985", current)
        with self.assertRaisesRegex(NetworkPlanError, "Unexpected new VMware networking directive"):
            verify_owned_vmnet_runtime(self.owned, current, self.base, self.layout)
        result = verify_owned_vmnet_runtime(
            self.owned, current, self.base, self.layout,
            peer_additions=self.approved(),
        )
        self.assertTrue(result)
        for bad in (
            "answer VNET_2_NAT yes\\n",
            "add_nat_portfwd 8 tcp 2213 172.28.231.31 3389\\n",
        ):
            with self.subTest(bad=bad), self.assertRaises(NetworkPlanError):
                verify_owned_vmnet_runtime(
                    self.owned, current + bad.replace("\\\\n", "\\n").encode(),
                    self.base, self.layout, peer_additions=self.approved(),
                )

    def test_extra_directive_fails_even_with_peer(self):
        for unexpected in (
            "answer VNET_2_NAT yes\n",
            "answer VNET_2_DHCP yes\n",
            "answer VNET_10_NAT yes\n",
            "answer VNET_3_HOSTONLY_SUBNET 10.4.10.0\n",
            "add_nat_portfwd 8 tcp 2213 10.4.10.11 5985\n",
            "add_nat_portfwd 8 tcp 2213 172.28.231.31 3389\n",
            "add_nat_portfwd 8 tcp 2213 172.28.231.31 5985\n",
            "add_nat_portfwd 8 udp 2213 172.28.231.31 22\n",
            "add_nat_portfwd 8 tcp 2210 192.168.213.40 22\n",
        ):
            with self.subTest(line=unexpected):
                with self.assertRaises(NetworkPlanError):
                    verify_owned_vmnet_runtime(
                        self.owned, self.runtime(unexpected), self.base, self.layout,
                        peer_additions=self.approved(),
                    )

    def test_missing_peer_declaration_and_changed_north_settings_fail(self):
        for removal in (
            "answer VNET_2_DHCP no",
            "add_nat_portfwd 8 tcp 2210 172.28.231.31 5985",
        ):
            with self.subTest(removed=removal):
                body = self.runtime().decode().replace(removal + "\n", "")
                with self.assertRaises(NetworkPlanError):
                    verify_owned_vmnet_runtime(
                        self.owned, body.encode(), self.base, self.layout,
                        peer_additions=self.approved(),
                    )
        altered = self.runtime().replace(
            b"answer VNET_20_VIRTUAL_ADAPTER no",
            b"answer VNET_20_VIRTUAL_ADAPTER yes",
        )
        with self.assertRaises(NetworkPlanError):
            verify_owned_vmnet_runtime(
                self.owned, altered, self.base, self.layout, peer_additions=self.approved()
            )

    def test_peer_must_have_original_network_baseline(self):
        with self.assertRaisesRegex(NetworkPlanError, "not authenticated"):
            verified_wslpe_peer_additions(
                self.peer_file, owner_uid=os.getuid(), inspect_host=False,
            )

    def test_root_owner_permissions_and_symlinks(self):
        self.peer_file.chmod(0o644)
        with self.assertRaises(NetworkPlanError):
            self.approved()
        self.peer_file.chmod(0o600)
        self.record["vmx_sha256"] = "f" * 64
        self.write_record()
        with self.assertRaises(NetworkPlanError):
            self.approved()
        self.record["vmx_sha256"] = hashlib.sha256(self.vmx.read_bytes()).hexdigest()
        self.write_record()
        self.vmx.write_text(self.vmx.read_text() + 'ethernet1.vnet = "vmnet2"\n')
        with self.assertRaises(NetworkPlanError):
            self.approved()
        self.vmx.write_text(
            'ethernet0.connectionType = "nat"\n'
            'ethernet1.connectionType = "custom"\n'
            'ethernet1.vnet = "vmnet2"\n')
        self.record["vmx_sha256"] = hashlib.sha256(self.vmx.read_bytes()).hexdigest()
        self.write_record()
        link = self.root / "peer-symlink.json"
        link.symlink_to(self.peer_file)
        with self.assertRaises(NetworkPlanError):
            verified_wslpe_peer_additions(
                link, owner_uid=os.getuid(), inspect_host=False,
                original_baseline=self.base,
            )

    def test_unsafe_peer_identity_and_forwarding_rejected(self):
        for key, value in (
            ("vmnet", "vmnet10"),
            ("vmnet", "vmnet8"),
            ("subnet", "10.4.10.0/24"),
            ("subnet", "192.168.213.0/24"),
            ("guest_address", "172.28.231.0"),
            ("host_address", "172.28.231.31"),
            ("host_ports", {"5985": 2210, "5986": 2210, "22": 2212}),
            ("host_ports", {"5985": 2210, "5986": 2211}),
            ("host_ports", {"5985": 80, "5986": 2211, "22": 2212}),
        ):
            with self.subTest(field=key, value=value):
                old = self.record[key]
                self.record[key] = value
                self.write_record()
                with self.assertRaises(NetworkPlanError):
                    self.approved()
                self.record[key] = old
                self.write_record()

    def test_not_a_usable_attestation_without_live_host_interface(self):
        # Host interface validation is independent of JSON source correctness.
        from unittest.mock import patch
        with patch("goad.course1_peer_vmnet._host_interface",
                   side_effect=NetworkPlanError("wrong actual host address")):
            with self.assertRaisesRegex(NetworkPlanError, "wrong actual host address"):
                verified_wslpe_peer_additions(
                    self.peer_file, owner_uid=os.getuid(), inspect_host=True,
                    original_baseline=self.base,
                )

    def test_record_is_never_created_implicitly(self):
        self.assertIsNone(verified_wslpe_peer_additions(
            self.root / "missing.json", owner_uid=os.getuid(), inspect_host=False,
        ))
        self.assertFalse((self.root / "missing.json").exists())


if __name__ == "__main__":
    unittest.main()
