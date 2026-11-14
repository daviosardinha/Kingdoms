"""Source-only checks for PURPLE Sliver's limited privileged DNS port capability."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/purple-sliver-dns-bind-capability.sh"


class PurpleSliverDnsCapabilityTests(unittest.TestCase):
    def test_shell_is_valid(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    def test_only_pinned_purple_c2_binary_can_gain_binding_capability(self):
        content = SCRIPT.read_text()
        for token in (
            "172.28.233.60",
            "purple-c2",
            'id -un',
            "sliver-server",
            "6c54ea94961f15de22bb765911b850d054e66f69069e4b799ab7cc3134e8ef36",
            "sha256sum",
            "cap_net_bind_service=+ep",
            "/usr/sbin/getcap",
            "PURPLE_SLIVER_DNS_BIND_CAPABILITY_READY=1",
        ):
            with self.subTest(token=token):
                self.assertIn(token, content)
        for dangerous in ("chmod 777", "setcap -r /", "sysctl -w",
                          "ip_unprivileged_port_start=", "vagrant destroy", "vagrant up"):
            self.assertNotIn(dangerous, content)
        self.assertIn("--apply", content)
        self.assertIn("--verify", content)


if __name__ == "__main__":
    unittest.main()
