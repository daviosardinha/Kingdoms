"""Source-only qualification for NORTH UDP/123 passive diagnostics."""
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
        result = subprocess.run(
            ["bash", "-n", str(TARGET)], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_target_ownership_and_passive_capture_contract(self):
        src = self.source
        for marker in (
            "north-vmware",
            "GOAD_LAB_PROFILE=NORTH",
            "bash scripts/lab-mode.sh status",
            "vmrun -T ws list",
            "--north verify",
            "10.4.10.254/24",
            "BPF=",
            "host 10.4.10.22 and host 10.4.10.11",
            "tcpdump -i vmnet10",
            '-w - "$BPF"',
            "NORTH_NTP_PASSIVE_CAPTURE_COMPLETED",
            "Capture completion does not imply NTP synchronization success",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, src)

    def test_no_mutation_in_executable_source(self):
        executable = "\n".join(
            line for line in self.source.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        for banned in (
            "vagrant up", "vagrant destroy", "vmrun -T ws start",
            "vmrun -T ws stop", "vmrun -T ws snapshot",
            "vmrun -T ws reset", "ip route add", "ip route del",
            "w32tm /resync", "w32tm /config", "w32tm.exe /resync",
            "Restart-Service", "Reset-ComputerMachinePassword",
            "iptables -",
        ):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, executable)


if __name__ == "__main__":
    unittest.main()
