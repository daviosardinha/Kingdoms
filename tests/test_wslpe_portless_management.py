"""WSLPE zero-host-forward management target tests; no guest/host writes."""
import unittest
from pathlib import Path

from kingdoms.wslpe_portless_management import (
    lifecycle_blockers, source_blockers,
)

ROOT = Path(__file__).resolve().parents[1]


def nic(slot, role, vmnet=None, connected=True):
    content = [
        f'ethernet{slot}.connectionType = "{role}"',
        f'ethernet{slot}.startConnected = "{"TRUE" if connected else "FALSE"}"',
        f'ethernet{slot}.present = "TRUE"',
    ]
    if vmnet:
        content.append(f'ethernet{slot}.vnet = "{vmnet}"')
    return "\n".join(content) + "\n"


VALID = (
    nic(0, "nat", connected=False)
    + nic(1, "custom", "vmnet2")
    + nic(2, "custom", "vmnet3")
)
NETS = {
    "vmnet2": "172.28.231.0/24",
    "vmnet3": "172.28.232.0/24",
    "vmnet8": "192.168.213.0/24",
    "vmnet10": "10.4.10.0/24",
    "vmnet99": "10.4.99.0/24",
}


class PortlessManagementContractTests(unittest.TestCase):
    def test_future_separate_operator_and_exercise_nics(self):
        self.assertEqual(source_blockers(VALID, NETS), [])

    def test_existing_two_nic_vagrant_layout_is_not_accepted(self):
        old = nic(0, "nat") + nic(1, "custom", "vmnet2")
        blockers = source_blockers(old, NETS)
        self.assertIn("three exact adapter slots", blockers[0])

    def test_bootstrap_nat_must_be_disconnected_and_never_erased(self):
        for text in (
            VALID.replace('ethernet0.startConnected = "FALSE"',
                          'ethernet0.startConnected = "TRUE"'),
            VALID.replace('ethernet0.connectionType = "nat"',
                          'ethernet0.connectionType = "bridged"'),
        ):
            with self.subTest(text=text):
                self.assertTrue(source_blockers(text, NETS))

    def test_management_must_not_be_on_exercise_or_north_vmnet(self):
        for text in (
            VALID.replace('ethernet2.vnet = "vmnet3"', 'ethernet2.vnet = "vmnet2"'),
            VALID.replace('ethernet2.vnet = "vmnet3"', 'ethernet2.vnet = "vmnet10"'),
            VALID.replace('ethernet2.vnet = "vmnet3"', 'ethernet2.vnet = "vmnet8"'),
            VALID.replace('ethernet2.vnet = "vmnet3"', 'ethernet2.vnet = "vmnet1"'),
            VALID.replace('ethernet2.connectionType = "custom"',
                          'ethernet2.connectionType = "nat"'),
        ):
            with self.subTest(text=text):
                self.assertTrue(source_blockers(text, NETS))

    def test_overlapping_or_missing_subnet_fails(self):
        for changes in (
            {"vmnet3": "172.28.231.0/24"},
            {"vmnet3": "10.4.50.0/24"},
            {"vmnet3": "172.28.232.0/16"},
            {"vmnet8": "172.28.232.0/24"},
        ):
            with self.subTest(changes=changes):
                self.assertTrue(source_blockers(VALID, {**NETS, **changes}))
        self.assertTrue(source_blockers(VALID, {"vmnet2": NETS["vmnet2"]}))

    def test_duplicate_malformed_and_excess_adapter_rejected(self):
        self.assertTrue(source_blockers(VALID + 'ethernet2.vnet = "vmnet3"\n', NETS))
        self.assertTrue(source_blockers(VALID + nic(3, "custom", "vmnet4"), NETS))
        self.assertTrue(source_blockers("", NETS))

    def test_live_portless_gate_needs_independent_proofs(self):
        opts = dict(
            native_vagrant_forwards={},
            historical_nat_host_ports={2210, 2211, 2212},
            currently_listening_ports=set(),
            direct_operator_authentication_proven=True,
            management_service_separated=True,
            operator_host_isolated=True,
            no_peer_guest_sharing=True,
            vmware_boot_order_guard_proven=True,
            rollback_verified=True,
        )
        self.assertEqual(lifecycle_blockers(**opts), [])
        for key, value in (
            ("native_vagrant_forwards", {22: 2212}),
            ("currently_listening_ports", {2210}),
            ("direct_operator_authentication_proven", False),
            ("management_service_separated", False),
            ("operator_host_isolated", False),
            ("no_peer_guest_sharing", False),
            ("vmware_boot_order_guard_proven", False),
            ("rollback_verified", False),
        ):
            with self.subTest(gate=key):
                broken = {**opts, key: value}
                self.assertTrue(lifecycle_blockers(**broken))

    def test_source_preview_has_no_vmware_or_firewall_mutators(self):
        path = ROOT / "scripts/wslpe-portless-preview.py"
        source = path.read_text(encoding="utf-8")
        for forbidden in (
            "vmrun -T ws stop", "vmrun -T ws start",
            "vagrant up", "vagrant destroy", "nft -f", "nft flush",
            "vmware-networks --stop", "iptables -F",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("stage2.find_instance(root)", source)
        self.assertIn("source_blockers", source)
        self.assertIn("--workspace", source)


if __name__ == "__main__":
    unittest.main()
