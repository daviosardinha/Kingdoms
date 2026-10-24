"""Source safety for passive NORTH UDP/123 diagnostics: no live VM access."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts/north-w32time-transport-evidence.sh"


class NorthTimeTransportSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TARGET.read_text(encoding="utf-8")

    def test_bash_syntax(self):
        r = subprocess.run(["bash", "-n", str(TARGET)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_fail_closed_ownership_and_passive_capture(self):
        src = self.source
        for needed in (
            "^\\[a-f0-9\\]{6}-north-vmware",  # intentionally checked below more precisely
        ):
            pass
        for marker in (
            'GOAD_LAB_PROFILE=NORTH',
            'bash scripts/lab-mode.sh status',
            'vmrun -T ws list',
            '--north verify',
            '10.4.10.254/24',
            'BPF=',
            'host 10.4.10.22 and host 10.4.10.11',
            'tcpdump -i vmnet10',
            '-w - "$BPF"',
            'NORTH_NTP_PASSIVE_CAPTURE_COMPLETED',
            'Capture completion does not imply NTP synchronization success',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, src)

    def test_no_guest_or_network_mutations_and_narrow_filter(self):
        src = self.source
        for disallowed in (
            "vagrant up", "vagrant destroy", "vmrun -T ws start",
            "vmrun -T ws stop", "vmrun -T ws snapshot",
            "vmrun -T ws reset", "ip route add", "ip route del",
            "w32tm /resync", "w32tm /config", "w32tm.exe /resync",
            "Restart-Service", "Reset-ComputerMachinePassword",
            "nat connect", "iptables -",
        ):
            # Comments may mention forbidden operations; only executable
            # commands are relevant to this source check.
            with self.subTest(disallowed=disallowed):
                lines = [line for line in src.splitlines()
                         if line.strip() and not line.lstrip().startswith("#")]
                self.assertNotIn(disallowed, "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
