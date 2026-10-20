"""Behavioral VMware coexistence tests; never touch the real host."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from goad.vmware_coexistence import (
    CoexistenceError, network_inventory, owner_record, load_owner_records,
    plan_instance, choose_course_network_base, north_source_install_plan,
)

VMWARE = (
    "VERSION=1,0\n"
    "answer VNET_1_HOSTONLY_SUBNET 192.168.56.0\n"
    "answer VNET_1_HOSTONLY_NETMASK 255.255.255.0\n"
    "answer VNET_8_HOSTONLY_SUBNET 192.168.213.0\n"
    "answer VNET_8_HOSTONLY_NETMASK 255.255.255.0\n"
    "answer VNET_8_NAT yes\n"
)
NORTH = {"north": "10.4.10.0/24", "sevenkingdoms": "10.4.20.0/24",
         "management": "10.4.99.0/24"}
KINGDOMS = {"north": "10.4.10.0/24", "sevenkingdoms": "10.4.20.0/24",
            "essos": "10.4.30.0/24", "management": "10.4.99.0/24"}
WSLPE = {"exercise": "172.28.231.0/24", "management": "172.28.232.0/24"}


def rendered(plan):
    """Simulate strictly additive host networking, preserving its original lines."""
    data = []
    for spec in plan["segments"].values():
        n = int(spec["vmnet"][5:])
        data.extend((
            f"answer VNET_{n}_DHCP no",
            f"answer VNET_{n}_NAT no",
            f"answer VNET_{n}_HOSTONLY_NETMASK 255.255.255.0",
            f"answer VNET_{n}_HOSTONLY_SUBNET {spec['cidr'].split('/')[0]}",
        ))
    return "\n".join(data) + "\n"


def committed(plan):
    return owner_record(plan["profile"], plan["provider"], plan["segments"])


class SharedVMwareTests(unittest.TestCase):
    def plan(self, profile, provider, source=VMWARE, owners=(), **kwargs):
        spec = {"NORTH": NORTH, "KINGDOMS": KINGDOMS, "WSLPE": WSLPE}[profile]
        return plan_instance(profile, provider, spec, source, owners=owners, **kwargs)

    def test_fresh_host_deterministic_assignment_and_unchanged_ips(self):
        for profile, provider, expected in (
            ("NORTH", "/instances/north", ("vmnet10", "vmnet20", "vmnet99")),
            ("KINGDOMS", "/instances/all", ("vmnet10", "vmnet20", "vmnet30", "vmnet99")),
            ("WSLPE", "/instances/lpe", ("vmnet2", "vmnet3")),
        ):
            with self.subTest(profile=profile):
                plan = self.plan(profile, provider)
                self.assertEqual(tuple(s["vmnet"] for s in plan["segments"].values()), expected)
                self.assertEqual(tuple(s["cidr"] for s in plan["segments"].values()),
                                 tuple({"NORTH": NORTH, "KINGDOMS": KINGDOMS, "WSLPE": WSLPE}[profile].values()))
                self.assertFalse(plan["host_mutation"])

    def test_occupied_preferred_ids_dynamically_remap_without_ip_renumbering(self):
        source = VMWARE + (
            "answer VNET_2_HOSTONLY_SUBNET 172.20.2.0\n"
            "answer VNET_2_HOSTONLY_NETMASK 255.255.255.0\n"
            "answer VNET_10_HOSTONLY_SUBNET 172.20.10.0\n"
            "answer VNET_10_HOSTONLY_NETMASK 255.255.255.0\n"
        )
        north = self.plan("NORTH", "/instances/north", source)
        lpe = self.plan("WSLPE", "/instances/lpe", source)
        self.assertNotEqual(north["segments"]["north"]["vmnet"], "vmnet10")
        self.assertNotEqual(lpe["segments"]["exercise"]["vmnet"], "vmnet2")
        self.assertEqual(north["segments"]["north"]["cidr"], "10.4.10.0/24")
        self.assertEqual(lpe["segments"]["exercise"]["cidr"], "172.28.231.0/24")
        self.assertEqual(self.plan("NORTH", "/instances/north", source), north)

    def test_second_ad_lab_selects_10_5_without_mutating_original(self):
        full = self.plan("KINGDOMS", "/instances/full")
        existing = VMWARE + rendered(full)
        next_base = choose_course_network_base("NORTH", existing,
                                                owners=(committed(full),))
        self.assertEqual(next_base, "10.5.0.0/16")
        self.assertEqual(choose_course_network_base("KINGDOMS", VMWARE),
                         "10.4.0.0/16")
        north = {role: cidr.replace("10.4.", "10.5.") for role, cidr in NORTH.items()}
        next_plan = plan_instance("NORTH", "/instances/north", north, existing,
                                  owners=(committed(full),))
        self.assertEqual(next_plan["segments"]["north"]["cidr"], "10.5.10.0/24")
        self.assertNotEqual(next_plan["segments"]["north"]["vmnet"], "vmnet10")
        self.assertEqual(full["segments"]["north"]["cidr"], "10.4.10.0/24")

    def test_real_north_renderer_uses_10_5_addresses_and_independent_vmnets(self):
        full = self.plan("KINGDOMS", "/instances/full")
        source = VMWARE + rendered(full)
        result = north_source_install_plan("/instances/north", source,
                                           owners=(committed(full),))
        self.assertEqual(result["network_base"], "10.5.0.0/16")
        self.assertFalse(result["install_enabled"])
        topo = result["topology"]
        self.assertEqual(topo["windows"]["GOAD-DC02"]["address"], "10.5.10.11")
        self.assertEqual(topo["windows"]["GOAD-DC01"]["address"], "10.5.20.10")
        self.assertEqual(topo["segments"]["management"]["host_address"], "10.5.99.254")
        self.assertTrue(set(int(s["vmnet"][5:]) for s in topo["segments"].values())
                        .isdisjoint({10, 20, 30, 99, 1, 8}))
        assets = result["rendered_artifacts"]
        self.assertIn('10.5.10.11', assets["providers/vmware/Vagrantfile"])
        self.assertIn('10.5.20.10', assets["providers/vmware/inventory"])
        self.assertIn('10.5.10.1', assets["providers/vmware/router/provision.sh"])
        self.assertIn("ip saddr 10.5.10.11 ip daddr 10.5.20.10",
                      assets["providers/vmware/router/nftables/exercise.nft"])

    def test_subnet_candidate_skips_external_routes_and_host_addresses(self):
        self.assertEqual(choose_course_network_base(
            "NORTH", VMWARE, routes=["10.4.0.0/16"],
            host_addresses=["10.5.15.10"]), "10.6.0.0/16")
        self.assertEqual(choose_course_network_base(
            "NORTH", VMWARE, preferred=5, maximum=5), "10.5.0.0/16")
        with self.assertRaisesRegex(CoexistenceError, "No collision-free"):
            choose_course_network_base("NORTH", VMWARE, preferred=4,
                                       maximum=4, routes=["10.4.0.0/16"])

    def test_subnet_selection_not_invoked_for_existing_lifecycle(self):
        first = self.plan("KINGDOMS", "/instances/full")
        source = VMWARE + rendered(first)
        existing = self.plan("KINGDOMS", "/instances/full",
                             source, (committed(first),))
        self.assertEqual(existing["segments"], first["segments"])
        self.assertEqual(existing["status"], "EXISTING_VERIFIED")

    def test_north_then_wslpe_retains_peer_network_and_ownership(self):
        first = self.plan("NORTH", "/instances/north")
        source = VMWARE + rendered(first)
        second = self.plan("WSLPE", "/instances/wslpe", source, (committed(first),))
        self.assertEqual(second["segments"]["exercise"]["vmnet"], "vmnet2")
        self.assertEqual(second["segments"]["management"]["vmnet"], "vmnet3")
        self.assertEqual(self.plan("NORTH", "/instances/north", source, (committed(first),))["segments"], first["segments"])

    def test_wslpe_then_north_retains_peer_network_and_ownership(self):
        first = self.plan("WSLPE", "/instances/wslpe")
        source = VMWARE + rendered(first)
        second = self.plan("NORTH", "/instances/north", source, (committed(first),))
        self.assertEqual(second["segments"]["north"]["vmnet"], "vmnet10")

    def test_full_kingdoms_and_wslpe_in_both_orders(self):
        for first, second in (("KINGDOMS", "WSLPE"), ("WSLPE", "KINGDOMS")):
            with self.subTest(order=(first, second)):
                a = self.plan(first, "/instances/" + first.lower())
                b = self.plan(second, "/instances/" + second.lower(),
                              VMWARE + rendered(a), (committed(a),))
                self.assertTrue(set(s["vmnet"] for s in a["segments"].values()).isdisjoint(
                    s["vmnet"] for s in b["segments"].values()))

    def test_kingdoms_north_overlapping_ip_and_all_three_fail_closed(self):
        for first, second in (("KINGDOMS", "NORTH"), ("NORTH", "KINGDOMS")):
            a = self.plan(first, "/instances/" + first.lower())
            with self.assertRaisesRegex(CoexistenceError, "overlaps"):
                self.plan(second, "/instances/" + second.lower(),
                          VMWARE + rendered(a), (committed(a),))
        # WSLPE does not solve the full/NORTH routed 10.4.x.x conflict.
        a = self.plan("WSLPE", "/instances/wslpe")
        b = self.plan("NORTH", "/instances/north",
                      VMWARE + rendered(a), (committed(a),))
        with self.assertRaisesRegex(CoexistenceError, "overlaps"):
            self.plan("KINGDOMS", "/instances/full",
                      VMWARE + rendered(a) + rendered(b), (committed(a), committed(b)))

    def test_existing_instance_networks_stable_after_lifecycle_cycles(self):
        a = self.plan("WSLPE", "/instances/lpe")
        source = VMWARE + rendered(a)
        owner = committed(a)
        for _ in range(5):
            planned = self.plan("WSLPE", "/instances/lpe", source, (owner,))
            self.assertEqual(planned["status"], "EXISTING_VERIFIED")
            self.assertEqual(planned["segments"], a["segments"])

    def test_registered_orphan_and_host_vmnets_never_adopted(self):
        plan = self.plan("WSLPE", "/instances/lpe", registered_vmx=(
            'ethernet1.vnet = "vmnet2"\n', 'ethernet2.vnet = "vmnet3"\n'))
        self.assertNotIn("vmnet2", (v["vmnet"] for v in plan["segments"].values()))
        self.assertNotIn("vmnet3", (v["vmnet"] for v in plan["segments"].values()))
        self.assertNotEqual(self.plan("WSLPE", "/instances/lpe", link_names=["vmnet2"])["segments"]["exercise"]["vmnet"], "vmnet2")

    def test_missing_partial_or_conflicting_metadata_is_blocked(self):
        for text in ("", VMWARE + "answer VNET_2_DHCP\n",
                     VMWARE + "answer VNET_2_HOSTONLY_SUBNET 10.5.0.0\n",
                     VMWARE + "answer VNET_2_DHCP no\nanswer VNET_2_DHCP yes\n",
                     VMWARE + "add_nat_portfwd 8 tcp 2210 1.1.1.1 22\n" +
                     "add_nat_portfwd 8 tcp 2210 1.1.1.2 22\n"):
            with self.subTest(source=text), self.assertRaises(CoexistenceError):
                network_inventory(text)

    def test_host_routes_and_adapter_subnet_collision_is_blocked(self):
        for kw in ({"routes": ["10.4.0.0/16"]}, {"host_addresses": ["10.4.10.254"]}):
            with self.assertRaisesRegex(CoexistenceError, "overlaps"):
                self.plan("NORTH", "/instances/north", **kw)
        with self.assertRaises(CoexistenceError):
            self.plan("NORTH", "/instances/north", routes=["not-a-route"])

    def test_owner_cannot_claim_unknown_or_modified_network(self):
        p = self.plan("NORTH", "/instances/north")
        owner = committed(p)
        with self.assertRaisesRegex(CoexistenceError, "does not match"):
            self.plan("WSLPE", "/instances/lpe", VMWARE, (owner,))
        with self.assertRaisesRegex(CoexistenceError, "isolation"):
            self.plan("WSLPE", "/instances/lpe",
                      VMWARE + rendered(p).replace("VNET_10_NAT no", "VNET_10_NAT yes"),
                      (owner,))
        with self.assertRaisesRegex(CoexistenceError, "Two owners claim"):
            self.plan("WSLPE", "/instances/lpe", VMWARE + rendered(p),
                      (owner, owner_record("NORTH", "/instances/copy", p["segments"])))

    def test_owner_registry_file_permissions_and_corrupt_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.chmod(root, 0o700)
            p = root / "north.json"
            record = committed(self.plan("NORTH", "/instances/north"))
            p.write_text(json.dumps(record), encoding="utf-8")
            os.chmod(p, 0o600)
            self.assertEqual(load_owner_records(root, os.geteuid()), [record])
            os.chmod(p, 0o644)
            with self.assertRaisesRegex(CoexistenceError, "permissions"):
                load_owner_records(root, os.geteuid())
            os.chmod(p, 0o600)
            p.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(CoexistenceError, "Invalid"):
                load_owner_records(root, os.geteuid())

    def test_owner_never_overwritten_and_uninstall_is_scoped_to_self(self):
        first = self.plan("NORTH", "/instances/north")
        second = self.plan("WSLPE", "/instances/lpe",
                           VMWARE + rendered(first), (committed(first),))
        source = VMWARE + rendered(first) + rendered(second)
        # NORTH's records and networks must remain valid after removing WSLPE.
        retained = source.replace(rendered(second), "")
        self.assertEqual(self.plan("NORTH", "/instances/north", retained,
                                   (committed(first),))["status"], "EXISTING_VERIFIED")
        # A destructive or incomplete uninstall cannot silently invalidate NORTH.
        broken = retained.replace("answer VNET_10_NAT no", "")
        with self.assertRaises(CoexistenceError):
            self.plan("NORTH", "/instances/north", broken, (committed(first),))


if __name__ == "__main__":
    unittest.main()
