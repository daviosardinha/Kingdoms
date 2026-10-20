"""Kingdoms NORTH's three-vmnet plan: zero host writes and fail-closed ownership."""
import unittest
from pathlib import Path

from goad.course1_vmnet_config import (NetworkPlanError, network_plan,
                                       render_vmnet_config, verify_vmnet_config,
                                       known_vmware_hostaddr_normalization,
                                       verify_owned_vmnet_runtime)
from goad.kingdoms_topology import load_course1_topology


BASELINE = (
    "VERSION=1,0\n"
    "answer VNET_1_HOSTONLY_SUBNET 192.168.56.0\n"
    "answer VNET_1_HOSTONLY_NETMASK 255.255.255.0\n"
    "answer VNET_8_NAT yes\n"
    "# user-owned config must remain exactly as written\n"
)


class Course1VmnetPlanTests(unittest.TestCase):
    def setUp(self):
        self.layout = load_course1_topology()

    def test_preserves_every_existing_foreign_line_byte_for_byte(self):
        generated = render_vmnet_config(BASELINE, self.layout)
        self.assertTrue(generated.startswith(BASELINE))
        self.assertEqual(generated.count("answer VNET_1_HOSTONLY_SUBNET"), 1)
        self.assertEqual(generated.count("answer VNET_8_NAT yes"), 1)
        self.assertIn("# user-owned config must remain exactly as written", generated)

    def test_default_config_has_only_three_course1_networks(self):
        generated = render_vmnet_config(BASELINE, self.layout)
        for number, network, visible in (
            (10, "10.4.10.0", "yes"),
            (20, "10.4.20.0", "no"),
            (99, "10.4.99.0", "yes"),
        ):
            self.assertIn(f"answer VNET_{number}_HOSTONLY_SUBNET {network}", generated)
            self.assertIn(f"answer VNET_{number}_VIRTUAL_ADAPTER {visible}", generated)
            self.assertIn(f"answer VNET_{number}_DHCP no", generated)
            self.assertIn(f"answer VNET_{number}_NAT no", generated)
        self.assertIn("answer VNET_10_HOSTONLY_HOSTADDR 10.4.10.254", generated)
        self.assertIn("answer VNET_99_HOSTONLY_HOSTADDR 10.4.99.254", generated)
        self.assertNotIn("VNET_20_HOSTONLY_HOSTADDR", generated)
        self.assertNotIn("VNET_30_", generated)
        self.assertNotIn("ESSOS", generated)

    def test_10_5_custom_vmnet_config_from_same_topology(self):
        network = load_course1_topology(
            "10.5.0.0/16", {"north": 11, "sevenkingdoms": 21, "management": 98}
        )
        generated = render_vmnet_config(BASELINE, network)
        self.assertIn("answer VNET_11_HOSTONLY_SUBNET 10.5.10.0", generated)
        self.assertIn("answer VNET_21_HOSTONLY_SUBNET 10.5.20.0", generated)
        self.assertIn("answer VNET_98_HOSTONLY_SUBNET 10.5.99.0", generated)
        self.assertIn("answer VNET_11_HOSTONLY_HOSTADDR 10.5.10.254", generated)
        self.assertNotIn("VNET_10_", generated)
        self.assertNotIn("VNET_30_", generated)

    def test_reused_network_id_blocks_addition(self):
        original = BASELINE + "answer VNET_10_DHCP no\n"
        with self.assertRaisesRegex(NetworkPlanError, "already allocated"):
            render_vmnet_config(original, self.layout)

    def test_reused_network_id_even_if_subnet_differs_blocks(self):
        original = BASELINE + "answer VNET_20_HOSTONLY_SUBNET 172.20.20.0\n"
        with self.assertRaisesRegex(NetworkPlanError, "already allocated"):
            render_vmnet_config(original, self.layout)

    def test_foreign_vmware_network_overlap_blocks(self):
        original = BASELINE + "answer VNET_55_HOSTONLY_SUBNET 10.4.10.0\n"
        with self.assertRaisesRegex(NetworkPlanError, "overlaps"):
            render_vmnet_config(original, self.layout)

    def test_foreign_broad_netmask_overlap_blocks_requested_subnet(self):
        # 10.4.0.0/16 includes North even though its first /24 is not 10.4.10.
        original = (
            BASELINE
            + "answer VNET_55_HOSTONLY_SUBNET 10.4.0.0\n"
            + "answer VNET_55_HOSTONLY_NETMASK 255.255.0.0\n"
        )
        with self.assertRaisesRegex(NetworkPlanError, "overlaps"):
            render_vmnet_config(original, self.layout)

    def test_duplicate_foreign_netmask_is_rejected(self):
        original = (
            BASELINE
            + "answer VNET_55_HOSTONLY_SUBNET 10.6.10.0\n"
            + "answer VNET_55_HOSTONLY_NETMASK 255.255.255.0\n"
            + "answer VNET_55_HOSTONLY_NETMASK 255.255.0.0\n"
        )
        with self.assertRaisesRegex(NetworkPlanError, "Duplicate existing"):
            render_vmnet_config(original, self.layout)

    def test_invalid_existing_vmware_subnet_fails_closed(self):
        original = BASELINE + "answer VNET_55_HOSTONLY_SUBNET not-an-ip\n"
        with self.assertRaisesRegex(NetworkPlanError, "Invalid existing"):
            render_vmnet_config(original, self.layout)

    def test_missing_baseline_is_refused(self):
        for original in ("", "  \n"):
            with self.subTest(original=original):
                with self.assertRaisesRegex(NetworkPlanError, "Missing VMware networking"):
                    render_vmnet_config(original, self.layout)

    def test_plan_return_has_hash_and_no_hosts_mutated(self):
        result = network_plan(baseline=BASELINE)
        self.assertEqual(result["profile"], "NORTH")
        self.assertEqual(result["network_base"], "10.4.0.0/16")
        self.assertEqual(len(result["segment_settings"]), 3)
        self.assertNotEqual(result["baseline_sha256"], result["proposed_sha256"])
        self.assertTrue(result["proposed_text"].startswith(BASELINE))
        self.assertIn("READ-ONLY", result["mode"])

    def test_original_kingdoms_script_retained_and_north_plan_explicit(self):
        source = (Path(__file__).resolve().parents[1] /
                  "scripts/setup-vmware-networks.sh").read_text()
        self.assertIn('if [[ "' + '$' + '{1:-}" == "--north" ]]', source)
        self.assertIn("python3 -m goad.course1_vmnet_config", source)
        self.assertIn("readonly HOSTADDR_HELPER=", source)
        self.assertIn('    30: {"subnet": "10.4.30.0"', source)
        self.assertIn('configure_addr vmnet10 10.4.10.254/24', source)
        self.assertIn('configure_addr vmnet99 10.4.99.254/24', source)


    def test_vmware_optional_hostaddr_normalization_rejects_foreign_edits(self):
        proposed = render_vmnet_config(BASELINE, self.layout).encode()
        only_north = proposed.replace(
            b"answer VNET_10_HOSTONLY_HOSTADDR 10.4.10.254\n", b""
        )
        both = only_north.replace(
            b"answer VNET_99_HOSTONLY_HOSTADDR 10.4.99.254\n", b""
        )
        for variant in (proposed, only_north, both):
            with self.subTest(variant=len(variant)):
                self.assertTrue(known_vmware_hostaddr_normalization(
                    proposed, variant, self.layout,
                ))
        self.assertFalse(known_vmware_hostaddr_normalization(
            proposed, both + b"# another administrator changed VMware settings\n", self.layout,
        ))
        self.assertFalse(known_vmware_hostaddr_normalization(
            proposed, proposed.replace(b"VNET_20_VIRTUAL_ADAPTER no",
                                       b"VNET_20_VIRTUAL_ADAPTER yes"), self.layout,
        ))

    def test_config_check_accepts_expected_three_networks(self):
        output = render_vmnet_config(BASELINE, self.layout)
        findings = verify_vmnet_config(output, self.layout)
        self.assertEqual(len(findings), 3)
        self.assertTrue(all("Kingdoms topology" in x for x in findings))

    def test_config_check_refuses_unexpected_parent_host_interface(self):
        output = render_vmnet_config(BASELINE, self.layout)
        altered = output.replace(
            "answer VNET_20_VIRTUAL_ADAPTER no",
            "answer VNET_20_VIRTUAL_ADAPTER yes",
        )
        with self.assertRaisesRegex(NetworkPlanError, "mismatch"):
            verify_vmnet_config(altered, self.layout)

    def test_config_check_refuses_nat_or_dhcp_enable(self):
        output = render_vmnet_config(BASELINE, self.layout)
        for key in ("NAT", "DHCP"):
            with self.subTest(key=key):
                altered = output.replace(f"answer VNET_10_{key} no",
                                         f"answer VNET_10_{key} yes")
                with self.assertRaisesRegex(NetworkPlanError, "mismatch"):
                    verify_vmnet_config(altered, self.layout)

    def test_vmware_stripping_optional_hostaddr_keeps_config_only_valid(self):
        output = render_vmnet_config(BASELINE, self.layout)
        altered = output.replace(
            "answer VNET_10_HOSTONLY_HOSTADDR 10.4.10.254\n", ""
        )
        self.assertEqual(len(verify_vmnet_config(altered, self.layout)), 3)

    def test_original_kingdoms_check_script_preserved_with_explicit_north(self):
        source = (Path(__file__).resolve().parents[1] /
                  "scripts/check-vmware-networks.sh").read_text()
        expected_dispatch = 'if [[ "' + '$' + '{1:-}" == "--north" ]]'
        self.assertIn(expected_dispatch, source)
        self.assertIn("python3 -m goad.course1_vmnet_config check", source)
        self.assertIn("'30 10.4.30.0 no ESSOS'", source)
        self.assertIn("GOAD_NOMAD design", source)

    def vmware_post_vagrant_fixture(self):
        baseline = (
            "VERSION=1,0\n"
            "answer VNET_1_DHCP yes\n"
            "answer VNET_1_DHCP_CFG_HASH " + "A" * 40 + "\n"
            "answer VNET_1_HOSTONLY_NETMASK 255.255.255.0\n"
            "answer VNET_1_HOSTONLY_SUBNET 172.16.195.0\n"
            "answer VNET_1_NAT no\n"
            "answer VNET_1_VIRTUAL_ADAPTER yes\n"
            "answer VNET_8_DHCP yes\n"
            "answer VNET_8_DHCP_CFG_HASH " + "B" * 40 + "\n"
            "answer VNET_8_HOSTONLY_NETMASK 255.255.255.0\n"
            "answer VNET_8_HOSTONLY_SUBNET 192.168.213.0\n"
            "answer VNET_8_NAT yes\n"
            "answer VNET_8_VIRTUAL_ADAPTER yes\n"
        )
        owned = render_vmnet_config(baseline, self.layout).encode("utf-8")
        lines = [
            ln for ln in owned.decode().splitlines()
            if ln and not ln.lstrip().startswith("#")
            and "VNET_10_HOSTONLY_HOSTADDR" not in ln
            and "VNET_99_HOSTONLY_HOSTADDR" not in ln
        ]
        # Vagrant/VMware rewrites declaration order and ephemeral foreign keys.
        runtime = "\n".join(sorted(lines, reverse=True)) + "\n"
        runtime = runtime.replace("A" * 40, "C" * 40).replace("B" * 40, "D" * 40)
        runtime += (
            "add_nat_portfwd 8 tcp 2200 192.168.213.244 22 \n"
            "add_nat_portfwd 8 tcp 55985 192.168.213.244 5985 \n"
            "add_nat_portfwd 8 tcp 55986 192.168.213.244 5986 \n"
        )
        return baseline.encode(), owned, runtime.encode()

    def test_post_vagrant_accepts_real_vmware_normalization_and_forwards(self):
        baseline, owned, runtime = self.vmware_post_vagrant_fixture()
        findings = verify_owned_vmnet_runtime(owned, runtime, baseline, self.layout)
        self.assertEqual(len(findings), 2)

    def test_post_vagrant_still_rejects_isolation_and_foreign_subnet_drift(self):
        baseline, owned, runtime = self.vmware_post_vagrant_fixture()
        original = runtime.decode()
        for before, after in (
            ("VNET_20_VIRTUAL_ADAPTER no", "VNET_20_VIRTUAL_ADAPTER yes"),
            ("VNET_10_NAT no", "VNET_10_NAT yes"),
            ("VNET_99_DHCP no", "VNET_99_DHCP yes"),
            ("VNET_1_HOSTONLY_SUBNET 172.16.195.0",
             "VNET_1_HOSTONLY_SUBNET 172.16.196.0"),
            ("VNET_8_HOSTONLY_SUBNET 192.168.213.0",
             "VNET_8_HOSTONLY_SUBNET 10.4.10.0"),
        ):
            with self.subTest(change=before):
                self.assertIn(before, original)
                altered = original.replace(before, after, 1).encode()
                with self.assertRaises(NetworkPlanError):
                    verify_owned_vmnet_runtime(owned, altered, baseline, self.layout)

    def test_post_vagrant_rejects_unauthorized_or_malformed_nat_rules(self):
        baseline, owned, runtime = self.vmware_post_vagrant_fixture()
        for extra in (
            "add_nat_portfwd 10 tcp 2222 10.4.10.11 22\n",
            "add_nat_portfwd 8 tcp 2222 10.4.10.11 22\n",
            "add_nat_portfwd 8 tcp 2222 192.168.213.244 3389\n",
            "add_nat_portfwd 8 udp 2222 192.168.213.244 22\n",
            "add_nat_portfwd 8 tcp 2222 192.168.213.0 22\n",
            "add_nat_portfwd 8 tcp 0 192.168.213.244 22\n",
            "add_nat_portfwd 8 tcp 2200 192.168.213.250 22\n",
            "answer VNET_20_HOSTONLY_HOSTADDR 10.4.20.254\n",
            "answer VNET_10_NEW_UNREVIEWED yes\n",
            "add_nat_portfwd 8 tcp invalid 192.168.213.244 22\n",
        ):
            with self.subTest(extra=extra.strip()):
                with self.assertRaises(NetworkPlanError):
                    verify_owned_vmnet_runtime(owned, runtime + extra.encode(),
                                               baseline, self.layout)

    def test_post_vagrant_missing_owned_setting_or_dhcp_hash_is_rejected(self):
        baseline, owned, runtime = self.vmware_post_vagrant_fixture()
        altered = runtime.replace(b"answer VNET_8_NAT yes\n", b"")
        with self.assertRaises(NetworkPlanError):
            verify_owned_vmnet_runtime(owned, altered, baseline, self.layout)
        altered_hash = runtime.replace(b"C" * 40, b"C" * 39)
        with self.assertRaises(NetworkPlanError):
            verify_owned_vmnet_runtime(owned, altered_hash, baseline, self.layout)
        missing_hash = runtime.replace(b"answer VNET_1_DHCP_CFG_HASH " + b"C" * 40 + b"\n", b"")
        with self.assertRaises(NetworkPlanError):
            verify_owned_vmnet_runtime(owned, missing_hash, baseline, self.layout)

    def test_config_module_is_no_write_and_has_no_runtime_commands(self):
        source = (Path(__file__).resolve().parents[1] /
                  "goad/course1_vmnet_config.py").read_text()
        for forbidden in (
            "subprocess.", "systemctl", "vmware-networks --",
            ".write_text(", "os.replace(", "ip route add",
            "rmtree(", "unlink(", "open('w'",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
