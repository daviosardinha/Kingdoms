"""Static preflight and fail-closed contract for instrumented NORTH cold start."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/north-observed-cold-start.sh"


class NorthObservedColdStartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_bash_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_instance_and_missing_confirmation_do_not_change_lab(self):
        for args in (
            [],
            ["0da0a9-north-vmware"],
            ["0da0a9-north-vmware", "--run"],
            ["0da0a9-north-vmware", "--run", "--not-confirmed"],
            ["not-an-instance", "--run", "--confirm-one-cold-start"],
        ):
            with self.subTest(args=args):
                completed = subprocess.run(
                    ["bash", str(SCRIPT), *args],
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(completed.returncode, 2)
                self.assertIn("Usage:", completed.stderr)

    def test_exact_instance_and_network_owner_proof(self):
        for item in (
            "scripts/verify-test-source.sh",
            '"installed"',
            '"NORTH"',
            '"vmware"',
            'flock -n 9',
            'setup-vmware-networks.sh --north verify',
            '10.4.10.254/24',
            '"$ID"',
            "north-observed-cold-start-",
        ):
            self.assertIn(item, self.source)

    def test_one_cycle_only_with_baseline_before_stop(self):
        indices = [self.source.index(token) for token in (
            'stage 01-baseline validate',
            'stage 02-stop stop',
            'stage 03-start start',
            'stage 04-acceptance validate',
        )]
        self.assertEqual(indices, sorted(indices))
        self.assertEqual(self.source.count('stage 02-stop stop'), 1)
        self.assertEqual(self.source.count('stage 03-start start'), 1)
        self.assertIn('NORTH_RUNTIME_ACCEPTANCE=PASS', self.source)
        self.assertIn('instance status is installed', self.source)
        for forbidden in ('-t reset', '-t destroy', '-t install',
                          '-t snapshot', 'vagrant up', 'w32tm /resync'):
            self.assertNotIn(forbidden, self.source)

    def test_capture_covers_full_start_with_bounded_runtime_and_cleanup(self):
        self.assertIn('tcpdump -i vmnet10', self.source)
        self.assertIn('tcpdump -i vmnet10 -n -U -s 0 -w -', self.source)
        self.assertIn('> "$EVIDENCE/ntp.pcap"', self.source)
        self.assertNotIn('-w "$EVIDENCE/ntp.pcap"', self.source)
        self.assertIn("udp port 123 and (host 10.4.10.11 or host 10.4.10.22 or host 10.4.10.31)", self.source)
        self.assertIn('timeout --signal=INT --kill-after=5 1250', self.source)
        self.assertIn('kill -TERM "$CAP_PID"', self.source)
        self.assertIn('wait "$CAP_PID"', self.source)
        self.assertIn('trap', self.source)
        self.assertIn('ntp-decoded.txt', self.source)
        self.assertIn('ntp-directions.txt', self.source)
        self.assertIn('final-state', self.source)
        self.assertIn('tar -czf', self.source)


if __name__ == "__main__":
    unittest.main()
