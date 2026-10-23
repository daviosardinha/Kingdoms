"""WSLPE-only vmnet-nat host firewall isolation, pure regression tests."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from kingdoms import wslpe_winrm_guard as guard


def nft_fixture(port=2210, *, host_only=True, effect=True):
    expression = [
        {"match": {
            "op": "!=",
            "left": {"meta": {"key": "iifname"}},
            "right": "lo" if host_only else "vmnet8",
        }},
        {"match": {
            "op": "==",
            "left": {"payload": {"protocol": "tcp", "field": "dport"}},
            "right": port,
        }},
        {"drop": None} if effect else {"accept": None},
    ]
    return json.dumps({
        "nftables": [
            {"table": {"family": "inet", "name": guard.TABLE, "handle": 1}},
            {"chain": {
                "family": "inet", "table": guard.TABLE,
                "name": guard.CHAIN, "type": "filter", "hook": "input",
                "prio": guard.PRIORITY, "policy": "accept", "handle": 2,
            }},
            {"rule": {
                "family": "inet", "table": guard.TABLE,
                "chain": guard.CHAIN, "comment": guard.COMMENT,
                "handle": 3, "expr": expression,
            }},
        ],
    })


class WslpeWinrmGuardTests(unittest.TestCase):
    def test_exact_port_drop_and_interface_are_required(self):
        self.assertTrue(guard.verify_firewall_json(nft_fixture(), 2210))
        self.assertFalse(guard.verify_firewall_json(nft_fixture(), 2211))
        self.assertFalse(guard.verify_firewall_json(nft_fixture(host_only=False), 2210))
        self.assertFalse(guard.verify_firewall_json(nft_fixture(effect=False), 2210))

    def test_missing_extra_or_modified_nftables_objects_fail_closed(self):
        base = json.loads(nft_fixture())
        self.assertFalse(guard.verify_firewall_json("not-json", 2210))
        self.assertFalse(guard.verify_firewall_json("{}", 2210))
        base["nftables"][1]["chain"]["hook"] = "forward"
        self.assertFalse(guard.verify_firewall_json(json.dumps(base), 2210))
        base = json.loads(nft_fixture())
        base["nftables"].append(base["nftables"][2])
        self.assertFalse(guard.verify_firewall_json(json.dumps(base), 2210))
        base = json.loads(nft_fixture())
        base["nftables"][2]["rule"]["comment"] = "SOMETHING_ELSE"
        self.assertFalse(guard.verify_firewall_json(json.dumps(base), 2210))

    def test_bounded_single_port_ipv4_ipv6_scope(self):
        batch = guard.firewall_batch(2210)
        self.assertIn("add table inet kingdoms_wslpe_winrm", batch)
        self.assertIn('meta iifname != "lo" tcp dport 2210 drop', batch)
        self.assertNotIn("vmnet8", batch)
        self.assertNotIn("flush", batch)
        self.assertNotIn("vmware-networks", batch)
        self.assertNotIn("GOAD", batch)
        for port in (-1, 0, 65536, None, "2210"):
            with self.subTest(port=port):
                with self.assertRaises(ValueError):
                    guard.firewall_batch(port)

    def test_atomic_migration_replaces_only_existing_exact_wslpe_rule(self):
        batch = guard.migrated_firewall_batch(nft_fixture(port=2210), 2210, 55985)
        self.assertEqual(
            batch,
            'replace rule inet kingdoms_wslpe_winrm local_winrm_only handle 3 '
            'meta iifname != "lo" tcp dport 55985 drop '
            'comment "KINGDOMS_WSLPE_WINRM"\n',
        )
        self.assertNotIn("delete table", batch)
        self.assertNotIn("flush", batch)
        self.assertNotIn("vmnet8", batch)

    def test_migration_rejects_wrong_old_port_and_ambiguous_rules(self):
        with self.assertRaises(ValueError):
            guard.migrated_firewall_batch(nft_fixture(2210), 2211, 55985)
        with self.assertRaises(ValueError):
            guard.migrated_firewall_batch(nft_fixture(2210), 2210, 2210)
        with self.assertRaises(ValueError):
            guard.migrated_firewall_batch(nft_fixture(host_only=False), 2210, 55985)
        for bad_handle in (None, 0, -1, "3", True):
            with self.subTest(handle=bad_handle):
                data = json.loads(nft_fixture())
                data["nftables"][2]["rule"]["handle"] = bad_handle
                with self.assertRaises(ValueError):
                    guard.migrated_firewall_batch(json.dumps(data), 2210, 55985)
        extra = json.loads(nft_fixture())
        extra["nftables"].append(extra["nftables"][2])
        with self.assertRaises(ValueError):
            guard.migrated_firewall_batch(json.dumps(extra), 2210, 55985)

    def test_privileged_owner_must_be_exact_vmnet_nat(self):
        output = (
            'LISTEN 0 20 0.0.0.0:2210 0.0.0.0:* '
            'users:(("vmnet-nat",pid=2162896,fd=9))\n'
        )
        self.assertTrue(guard.require_vmware_nat_owner(output, 2210))
        self.assertFalse(guard.require_vmware_nat_owner(output, 2211))
        self.assertFalse(guard.require_vmware_nat_owner(
            output.replace("vmnet-nat", "python3"), 2210
        ))
        self.assertFalse(guard.require_vmware_nat_owner(
            output.replace("0.0.0.0:2210", "127.0.0.1:2210"), 2210
        ))
        self.assertFalse(guard.require_vmware_nat_owner(output + output, 2210))

    def test_firewall_installer_never_manages_other_ports_or_vmware(self):
        src = (Path(__file__).resolve().parents[1] /
               "scripts/wslpe-winrm-firewall.py").read_text(encoding="utf-8")
        for forbidden in (
            '["vmrun", "-T", "ws", "stop"',
            "vmware-networks --stop",
            "iptables -F", "nft flush", "vagrant up", "vagrant reload",
            'delete table inet', "systemctl restart",
        ):
            self.assertNotIn(forbidden, src)
        self.assertIn("--confirm-port", src)
        self.assertIn('installed_guard(port)', src)
        self.assertIn("INSPECTOR.locate_registered_vm(instance)", src)


if __name__ == "__main__":
    unittest.main()
