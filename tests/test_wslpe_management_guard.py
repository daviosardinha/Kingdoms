"""Three-port WSLPE NAT management guard source tests. No host writes."""
import json
from pathlib import Path
import unittest

from kingdoms import wslpe_management_guard as guard


MAPPING = {22: 2212, 5985: 2210, 5986: 2211}


def _rule(port):
    return {"rule": {
        "family": "inet", "table": guard.TABLE, "chain": guard.CHAIN,
        "comment": guard.COMMENT, "expr": [
            {"match": {
                "op": "!=", "left": {"meta": {"key": "iifname"}},
                "right": "lo"}},
            {"match": {
                "op": "==",
                "left": {"payload": {"protocol": "tcp", "field": "dport"}},
                "right": port}},
            {"drop": None},
        ],
    }}


def nft_fixture(mapping=MAPPING):
    return json.dumps({"nftables": [
        {"metainfo": {"version": "1.0", "json_schema_version": 1}},
        {"table": {"family": "inet", "name": guard.TABLE}},
        {"chain": {
            "family": "inet", "table": guard.TABLE,
            "name": guard.CHAIN, "type": "filter", "hook": "input",
            "prio": guard.PRIORITY, "policy": "accept"}},
        *[_rule(mapping[guest]) for guest in guard.GUEST_PORTS],
    ]})


class WslpeManagementGuardTests(unittest.TestCase):
    def test_real_vagrant_port_output_with_banner(self):
        text = (
            "The forwarded ports for the machine are listed below. Please note that\n"
            "these values may differ from values configured in the Vagrantfile if the\n"
            "provider supports automatic port collision detection and resolution.\n\n"
            "    5985 (guest) => 2210 (host)\n"
            "    5986 (guest) => 2211 (host)\n"
            "    22 (guest) => 2212 (host)\n"
        )
        self.assertEqual(guard.parse_vagrant_ports(text), MAPPING)

    def test_missing_duplicate_unknown_forwarding_blocked(self):
        valid = "\n".join(
            f"{guest} (guest) => {MAPPING[guest]} (host)"
            for guest in guard.GUEST_PORTS
        )
        for changed in (
            "",
            valid.replace("22 (guest) => 2212 (host)", ""),
            valid + "\n22 (guest) => 2222 (host)",
            valid + "\n3389 (guest) => 3389 (host)",
            valid.replace("2211 (host)", "2210 (host)"),
            valid.replace("2212 (host)", "80 (host)"),
            valid + "\nWARNING: unknown forwarding",
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    guard.parse_vagrant_ports(changed)

    def test_atomic_nft_batch_covers_exact_ports_and_keeps_existing_table(self):
        data = guard.firewall_batch(MAPPING)
        self.assertIn(f"add table inet {guard.TABLE}", data)
        self.assertIn(f"hook input priority {guard.PRIORITY}", data)
        for port in MAPPING.values():
            self.assertIn(f'meta iifname != "lo" tcp dport {port} drop', data)
        self.assertEqual(data.count("add rule inet"), 3)
        for forbidden in ("delete table", "flush ", "systemctl ", "vmware-", "kingdoms_wslpe_winrm"):
            self.assertNotIn(forbidden, data)

    def test_exact_firewall_json_passes(self):
        self.assertTrue(guard.verify_firewall_json(nft_fixture(), MAPPING))

    def test_firewall_wrong_policy_extra_rule_or_interface_fails(self):
        for mutation in ("chain", "table", "extra", "wrong_port", "wrong_interface",
                         "accept", "duplicate", "missing", "comment", "family"):
            with self.subTest(mutation=mutation):
                doc = json.loads(nft_fixture())
                if mutation == "chain":
                    doc["nftables"][2]["chain"]["hook"] = "forward"
                elif mutation == "table":
                    doc["nftables"][1]["table"]["name"] = "unrelated"
                elif mutation == "extra":
                    doc["nftables"].append(_rule(9999))
                elif mutation == "wrong_port":
                    doc["nftables"][3]["rule"]["expr"][1]["match"]["right"] = 9999
                elif mutation == "wrong_interface":
                    doc["nftables"][3]["rule"]["expr"][0]["match"]["right"] = "vmnet2"
                elif mutation == "accept":
                    doc["nftables"][3]["rule"]["expr"][2] = {"accept": None}
                elif mutation == "duplicate":
                    doc["nftables"][4] = _rule(2212)
                elif mutation == "missing":
                    doc["nftables"].pop()
                elif mutation == "comment":
                    doc["nftables"][3]["rule"]["comment"] = "unknown"
                else:
                    doc["nftables"][1]["table"]["family"] = "ip"
                self.assertFalse(guard.verify_firewall_json(json.dumps(doc), MAPPING))

    def test_mapping_mismatch_and_malformed_json_rejected(self):
        self.assertFalse(guard.verify_firewall_json("[]", MAPPING))
        self.assertFalse(guard.verify_firewall_json("garbage", MAPPING))
        self.assertFalse(guard.verify_firewall_json(nft_fixture(), {
            22: 2212, 5985: 2210, 5986: 2222,
        }))
        self.assertFalse(guard.verify_firewall_json(nft_fixture(), {
            22: 2212, 5985: 2210,
        }))
        for candidate in (
            {22: 2210, 5985: 2210, 5986: 2211},
            {22: 80, 5985: 2210, 5986: 2211},
            {22: "2212", 5985: 2210, 5986: 2211},
        ):
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    guard.firewall_batch(candidate)

    def test_listeners_all_three_unique_and_nat_owned(self):
        output = "".join(
            f'LISTEN 0 20 0.0.0.0:{port} 0.0.0.0:* '
            f'users:(("vmnet-nat",pid=19698,fd=9))\n'
            for port in MAPPING.values()
        )
        self.assertTrue(guard.verify_nat_listeners(output, MAPPING))
        for port in MAPPING.values():
            with self.subTest(port=port):
                self.assertFalse(guard.verify_nat_listeners(
                    output.replace(f"0.0.0.0:{port}", f"127.0.0.1:{port}"), MAPPING))
                self.assertFalse(guard.verify_nat_listeners(
                    output.replace(f"0.0.0.0:{port}", f"0.0.0.0:9{port}"), MAPPING))
        self.assertFalse(guard.verify_nat_listeners(output + output.splitlines()[0] + "\n", MAPPING))
        self.assertFalse(guard.verify_nat_listeners(output.replace("vmnet-nat", "python3"), MAPPING))

    def test_operator_script_preserves_legacy_and_no_hidden_changes(self):
        source = (Path(__file__).resolve().parents[1]
                  / "scripts/wslpe-management-firewall.py").read_text(encoding="utf-8")
        self.assertIn("--confirm-ports", source)
        self.assertIn("--workspace", source)
        self.assertIn("native_ports(workspace) != ports", source)
        self.assertIn("cwd=provider", source)
        for forbidden in (
            "delete table inet", "nft flush", "iptables -F",
            "vmware-networks --stop", "systemctl restart", "vmrun -T ws stop",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
