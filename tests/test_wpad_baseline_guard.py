import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "phase03" / "validate-wpad-baseline.py"
CHECK = ROOT / "scripts" / "phase03" / "check-wpad-permanent-prereqs.sh"
RESTORE = ROOT / "scripts" / "phase03" / "restore-wpad-baseline.sh"
CAPTURE = ROOT / "ansible" / "phase03-wpad-baseline.yml"


class WpadBaselineGuardTests(unittest.TestCase):
    attacker = "fe80::250:56ff:fec0:a"

    def run_guard(self, ipv6, dns):
        data = {
            "Version": 1,
            "Target": "WS01",
            "IPv4": "10.4.10.31",
            "InterfaceAlias": "Ethernet1",
            "InterfaceIndex": 6,
            "IPv6Addresses": [
                {
                    "Address": addr,
                    "PrefixLength": 64,
                    "AddressState": "Preferred",
                    "PrefixOrigin": "WellKnown",
                    "SuffixOrigin": "Link",
                }
                for addr in ipv6
            ],
            "IPv6DnsServers": dns,
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "baseline.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return subprocess.run(
                [
                    "python3",
                    str(GUARD),
                    str(path),
                    "--target-ip",
                    "10.4.10.31",
                    "--attacker-v6",
                    self.attacker,
                ],
                capture_output=True,
                text=True,
            )

    def test_clean_baseline_is_accepted(self):
        result = self.run_guard(["fe80::7b99:b9f8:fede:ac4%6"], [])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PHASE03_WPAD_BASELINE_GUARD_VALID=True", result.stdout)

    def test_mitm6_derived_target_ipv6_is_rejected(self):
        result = self.run_guard(
            ["fe80::10:4:10:31%6", "fe80::7b99:b9f8:fede:ac4%6"],
            [],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("contains mitm6-derived target IPv6", result.stderr)

    def test_attacker_dns_is_rejected(self):
        result = self.run_guard(
            ["fe80::7b99:b9f8:fede:ac4%6"],
            [self.attacker],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("contains attacker IPv6 DNS", result.stderr)

    def test_capture_is_transactional_and_guarded_before_install(self):
        text = CHECK.read_text()
        self.assertIn("phase03-wpad-baseline.candidate.", text)
        self.assertIn('PHASE03_WPAD_BASELINE_DEST="$CANDIDATE"', text)
        self.assertIn('python3 "$BASELINE_GUARD"', text)
        self.assertIn('mv -f "$CANDIDATE" "$BASELINE"', text)
        self.assertLess(
            text.index('python3 "$BASELINE_GUARD"'),
            text.index('mv -f "$CANDIDATE" "$BASELINE"'),
        )

    def test_restore_refuses_untrusted_baseline_before_mutation(self):
        text = RESTORE.read_text()
        self.assertIn("===== VALIDATE TRUSTED BASELINE =====", text)
        self.assertIn("captured WPAD baseline is unsafe; refusing rollback", text)
        self.assertLess(
            text.index('python3 "$BASELINE_GUARD"'),
            text.index("===== PHASE 03 WPAD BASELINE RESTORE ====="),
        )

    def test_capture_playbook_supports_candidate_destination(self):
        text = CAPTURE.read_text()
        self.assertIn("PHASE03_WPAD_BASELINE_DEST", text)
        self.assertIn("phase03_wpad_baseline_dest", text)


if __name__ == "__main__":
    unittest.main()
