"""WSLPE-only P1-C host topology audit source and negative contracts."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/wslpe-p1c-topology-audit.py"
SPEC = importlib.util.spec_from_file_location("wslpe_p1c", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def vmx(vnet="vmnet2", nat="TRUE", ex="TRUE"):
    return (
        'ethernet0.present = "TRUE"\n'
        'ethernet0.connectionType = "nat"\n'
        f'ethernet0.startConnected = "{nat}"\n'
        'ethernet1.present = "TRUE"\n'
        'ethernet1.connectionType = "custom"\n'
        f'ethernet1.vnet = "{vnet}"\n'
        f'ethernet1.startConnected = "{ex}"\n'
    )


class WslpeP1cTests(unittest.TestCase):
    def test_exact_dedicated_vnet(self):
        self.assertEqual(M.validated_exercise_vnet(vmx()), "vmnet2")
        for name in ("vmnet1", "vmnet8", "vmnet10", "vmnet20",
                     "vmnet30", "vmnet99", "../../etc", ""):
            with self.subTest(name=name), self.assertRaises(ValueError):
                M.validated_exercise_vnet(vmx(vnet=name))

    def test_nat_and_exercise_nic_fail_closed(self):
        with self.assertRaises(ValueError):
            M.validated_exercise_vnet(vmx(nat="FALSE"))
        with self.assertRaises(ValueError):
            M.validated_exercise_vnet(vmx(ex="FALSE"))

    def test_host_interface_must_match_wslpe_subnet(self):
        records = [{"ifname": "vmnet2", "addr_info": [
            {"family": "inet", "local": "172.28.231.1", "prefixlen": 24}
        ]}]
        self.assertEqual(M.host_interface_ipv4(records, "vmnet2", "172.28.231"),
                         "172.28.231.1")
        for invalid in ([], [{"ifname": "vmnet10", "addr_info": []}],
                        [{"ifname": "vmnet2", "addr_info": [
                            {"family": "inet", "local": "10.4.10.1", "prefixlen": 24}
                        ]}]):
            with self.subTest(records=invalid), self.assertRaises(ValueError):
                M.host_interface_ipv4(invalid, "vmnet2", "172.28.231")

    def test_route_must_use_wslpe_vmnet(self):
        M.guest_route_device([{"dev": "vmnet2", "dst": "172.28.231.31"}], "vmnet2")
        with self.assertRaises(ValueError):
            M.guest_route_device([{"dev": "vmnet10"}], "vmnet2")

    def test_readonly_no_north_probe_or_mutation(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for marker in ("stage2.find_instance(", "stage2.locate_registered_vm(",
                       "check_exercise_mapping(", 'command_json("ip"',
                       "[RELEASE BLOCKED]", "[NOT VERIFIED]"):
            self.assertIn(marker, source)
        for forbidden in ("winrm.Session(", "vagrant up", "vmrun start",
                          "subprocess.Popen(", "nft -f", "iptables -A",
                          "lab-mode.sh", "Restart-Computer", "wmic "):
            self.assertNotIn(forbidden, source)

    def test_invalid_ip_inventory_is_fail_closed(self):
        with patch.object(M.subprocess, "run") as proc:
            proc.return_value.returncode = 0
            proc.return_value.stdout = "{}"
            with self.assertRaises(ValueError):
                M.command_json("ip", "-j", "-4", "address", "show", "dev", "vmnet2")


if __name__ == "__main__":
    unittest.main()
