"""Read-only tests for an explicit, scoped NORTH vmnet8 retirement attestation."""
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from goad.course1_host_network_apply import (
    NorthSetupError, require_clean_native_nat_baseline, reviewed_nat_retirements,
)


class RetiredNatAttestationTests(unittest.TestCase):
    def sample(self, base, provider):
        return {
            "schema": "kingdoms.north.retired-nat.v1",
            "provider": provider,
            "baseline_sha256": hashlib.sha256(base).hexdigest(),
            "reviewed_prior_owner": "ac9fda-north-vmware",
            "removed_rules": [
                "add_nat_portfwd 8 tcp 2200 192.168.213.249 5985",
                "add_nat_portfwd 8 tcp 2201 192.168.213.249 5986",
                "add_nat_portfwd 8 tcp 2202 192.168.213.249 22",
            ],
        }

    def test_absent_attestation_defaults_to_no_retirement(self):
        with TemporaryDirectory() as d:
            self.assertIsNone(reviewed_nat_retirements(
                "/tmp/instance/provider", b"baseline",
                source=Path(d)/"absent.json", owner_uid=os.geteuid()
            ))

    def test_exact_operator_reviewed_record(self):
        with TemporaryDirectory() as d:
            path = Path(d) / "attest.json"
            baseline = b"VMware baseline\n"
            provider = "/tmp/exact-north/provider"
            expected = self.sample(baseline, provider)
            path.write_text(json.dumps(expected))
            path.chmod(0o600)
            result = reviewed_nat_retirements(
                provider, baseline, source=path, owner_uid=os.geteuid()
            )
            self.assertEqual(result, frozenset(expected["removed_rules"]))
            for key, bad in (
                ("baseline_sha256", "0"*64),
                ("provider", "/tmp/wrong/provider"),
                ("reviewed_prior_owner", "../../wrong"),
                ("schema", "unreviewed"),
            ):
                with self.subTest(key=key):
                    record = dict(expected)
                    record[key] = bad
                    path.write_text(json.dumps(record))
                    with self.assertRaises(NorthSetupError):
                        reviewed_nat_retirements(
                            provider, baseline, source=path, owner_uid=os.geteuid()
                        )

    def test_duplicate_extra_rules_and_unsafe_file_refused(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "attest.json"
            baseline = b"VMware baseline\n"
            provider = "/tmp/exact-north/provider"
            sample = self.sample(baseline, provider)
            for rules in ([], sample["removed_rules"] * 2,
                          ["add_nat_portfwd 8 tcp 2200 192.168.213.249 5985"] * 2):
                with self.subTest(rules=rules):
                    p.write_text(json.dumps({**sample, "removed_rules": rules}))
                    p.chmod(0o600)
                    with self.assertRaises(NorthSetupError):
                        reviewed_nat_retirements(
                            provider, baseline, source=p, owner_uid=os.geteuid()
                        )
            p.write_text(json.dumps(sample))
            p.chmod(0o644)
            with self.assertRaises(NorthSetupError):
                reviewed_nat_retirements(provider, baseline, source=p,
                                        owner_uid=os.geteuid())
            p.chmod(0o600)
            link = Path(d) / "link.json"
            link.symlink_to(p)
            with self.assertRaises(Exception):
                reviewed_nat_retirements(provider, baseline, source=link,
                                        owner_uid=os.geteuid())

    def test_fresh_install_blocks_stale_nat_before_expensive_boot(self):
        good = "answer VNET_8_NAT yes\n"
        require_clean_native_nat_baseline(good)
        for dirty in (
            good + "add_nat_portfwd 8 tcp 2200 192.168.213.249 5985\n",
            good + "add_nat_portfwd 8 tcp 2210 172.28.231.31 5985\n",
        ):
            with self.assertRaisesRegex(NorthSetupError, "pre-existing NAT forwards"):
                require_clean_native_nat_baseline(dirty)


if __name__ == "__main__":
    unittest.main()
