"""WSLPE management vmnet planning tests. No host, VMware or guest operations."""
from contextlib import redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from kingdoms.wslpe_management_vmnet_plan import candidate_plan, inventory, vmx_conflicts, native_exercise_binding

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/wslpe-management-vmnet-plan.py"
spec = importlib.util.spec_from_file_location("wslpe_management_vmnet_plan_cli", SCRIPT)
assert spec and spec.loader
CLI = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CLI)

HOST_CONFIG = (
    "VERSION=1,0\n"
    "answer VNET_1_HOSTONLY_SUBNET 172.16.195.0\n"
    "answer VNET_1_HOSTONLY_NETMASK 255.255.255.0\n"
    "answer VNET_2_DHCP no\n"
    "answer VNET_2_NAT no\n"
    "answer VNET_2_HOSTONLY_NETMASK 255.255.255.0\n"
    "answer VNET_2_HOSTONLY_SUBNET 172.28.231.0\n"
    "answer VNET_2_VIRTUAL_ADAPTER yes\n"
    "answer VNET_8_NAT yes\n"
    "answer VNET_8_HOSTONLY_SUBNET 192.168.213.0\n"
    "answer VNET_8_HOSTONLY_NETMASK 255.255.255.0\n"
    "answer VNET_10_DHCP no\n"
    "answer VNET_10_HOSTONLY_SUBNET 10.4.10.0\n"
    "answer VNET_10_HOSTONLY_NETMASK 255.255.255.0\n"
    "answer VNET_20_HOSTONLY_SUBNET 10.4.20.0\n"
    "answer VNET_20_HOSTONLY_NETMASK 255.255.255.0\n"
    "answer VNET_99_HOSTONLY_SUBNET 10.4.99.0\n"
    "answer VNET_99_HOSTONLY_NETMASK 255.255.255.0\n"
    "add_nat_portfwd 8 tcp 2210 172.28.231.31 5985\n"
)


class VmnetPlanTests(unittest.TestCase):
    def test_additive_vmnet3_preview_preserves_every_existing_line(self):
        proposed = candidate_plan(HOST_CONFIG, vmnet="vmnet3", subnet="172.28.232.0/24")
        self.assertTrue(proposed.startswith(HOST_CONFIG))
        self.assertEqual(proposed.count("answer VNET_3_"), 6)
        self.assertIn("answer VNET_3_HOSTONLY_HOSTADDR 172.28.232.254", proposed)
        self.assertIn("answer VNET_3_NAT no", proposed)
        self.assertIn("answer VNET_3_DHCP no", proposed)
        self.assertIn("answer VNET_3_VIRTUAL_ADAPTER yes", proposed)
        self.assertIn("add_nat_portfwd 8 tcp 2210 172.28.231.31 5985", proposed)

    def test_reserved_existing_and_overlapping_vmnets_blocked(self):
        for vmnet, subnet in (
            ("vmnet10", "172.28.232.0/24"),
            ("vmnet99", "172.28.232.0/24"),
            ("vmnet8", "172.28.232.0/24"),
            ("vmnet3", "172.28.231.0/24"),
            ("vmnet3", "10.4.50.0/24"),
            ("vmnet3", "192.168.213.0/24"),
            ("vmnet bad", "172.28.232.0/24"),
            ("vmnet3", "172.28.232.0/16"),
        ):
            with self.subTest(vmnet=vmnet, subnet=subnet):
                with self.assertRaises(ValueError):
                    candidate_plan(HOST_CONFIG, vmnet=vmnet, subnet=subnet)
        with self.assertRaisesRegex(ValueError, "already exists"):
            candidate_plan(HOST_CONFIG + "answer VNET_3_DHCP no\n", vmnet="vmnet3",
                           subnet="172.28.232.0/24")

    def test_missing_or_drifted_exercise_network_fails_closed(self):
        for text in (
            HOST_CONFIG.replace("answer VNET_2_NAT no", "answer VNET_2_NAT yes"),
            HOST_CONFIG.replace("answer VNET_2_DHCP no", "answer VNET_2_DHCP yes"),
            HOST_CONFIG.replace("172.28.231.0", "172.28.240.0"),
            HOST_CONFIG.replace("answer VNET_2_HOSTONLY_NETMASK 255.255.255.0", ""),
        ):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    candidate_plan(text, vmnet="vmnet3", subnet="172.28.232.0/24")

    def test_duplicate_partial_invalid_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            inventory(HOST_CONFIG + "answer VNET_2_NAT yes\n")
        with self.assertRaisesRegex(ValueError, "Malformed"):
            inventory(HOST_CONFIG + "answer VNET_3_DHCP\n")

    def test_registered_vmx_never_adopted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            north, wslpe = root / "north", root / "wslpe"
            north.mkdir()
            wslpe.mkdir()
            (north / "NORTH.vmx").write_text('ethernet1.vnet = "vmnet10"\n')
            (wslpe / "WSLPE.vmx").write_text('ethernet1.vnet = "vmnet2"\n')
            self.assertEqual(vmx_conflicts([north, wslpe], "vmnet3"), [])
            (north / "NORTH.vmx").write_text('ethernet2.vnet = "vmnet3"\n')
            self.assertEqual(vmx_conflicts([north, wslpe], "vmnet3"),
                             [str(north / "NORTH.vmx")])
            with self.assertRaisesRegex(ValueError, "missing or unsafe"):
                vmx_conflicts([north, root / "absent"], "vmnet3")

    def test_live_guest_blocks_any_change_and_prints_only_proposal(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            f = base / "networking"
            f.write_text(HOST_CONFIG)
            north, wslpe = base / "north", base / "wslpe"
            north.mkdir()
            wslpe.mkdir()
            (north / "NORTH.vmx").write_text('ethernet1.vnet = "vmnet10"\n')
            (wslpe / "WSLPE.vmx").write_text('ethernet1.vnet = "vmnet2"\n')
            argv = ["--vmnet", "vmnet3", "--management-prefix", "172.28.232",
                    "--workspace-root", str(north), "--workspace-root", str(wslpe)]
            with (mock.patch.object(CLI, "NETWORKING", f),
                  mock.patch.object(CLI.checker, "run_ip", return_value=[]),
                  mock.patch.object(CLI, "vmware_running", return_value=5),
                  redirect_stdout(StringIO()) as capture):
                code = CLI.main(argv)
            self.assertEqual(code, 2)
            self.assertIn("[DEFERRED] 5 VMware guest process(es) running", capture.getvalue())
            self.assertIn("answer VNET_3_DHCP no", capture.getvalue())
            self.assertEqual(f.read_text(), HOST_CONFIG)
            with (mock.patch.object(CLI, "NETWORKING", f),
                  mock.patch.object(CLI.checker, "run_ip", return_value=[]),
                  mock.patch.object(CLI, "vmware_running", return_value=0),
                  redirect_stdout(StringIO()) as capture):
                code = CLI.main(argv)
            self.assertEqual(code, 0)
            self.assertIn("[SOURCE READY]", capture.getvalue())
            self.assertEqual(f.read_text(), HOST_CONFIG)

    def test_new_native_vmnet3_exercise_yields_independent_vmnet4_proposal(self):
        current = HOST_CONFIG + (
            "answer VNET_3_DHCP no\n"
            "answer VNET_3_NAT no\n"
            "answer VNET_3_HOSTONLY_NETMASK 255.255.255.0\n"
            "answer VNET_3_HOSTONLY_SUBNET 172.28.232.0\n"
        )
        vmx = (
            'ethernet0.connectionType = "nat"\n'
            'ethernet0.startConnected = "TRUE"\n'
            'ethernet0.present = "TRUE"\n'
            'ethernet1.connectionType = "custom"\n'
            'ethernet1.present = "TRUE"\n'
            'ethernet1.vnet = "vmnet3"\n'
        )
        selected = native_exercise_binding(vmx, "172.28.232", current)
        self.assertEqual(selected, ("vmnet3", "172.28.232.0/24"))
        candidate = candidate_plan(
            current, vmnet="vmnet4", subnet="172.28.233.0/24",
            exercise_vmnet=selected[0], exercise_subnet=selected[1],
        )
        self.assertTrue(candidate.startswith(current))
        self.assertIn("answer VNET_4_HOSTONLY_SUBNET 172.28.233.0", candidate)
        with self.assertRaises(ValueError):
            native_exercise_binding(vmx, "172.28.231", current)
        with self.assertRaises(ValueError):
            candidate_plan(
                current, vmnet="vmnet4", subnet="172.28.232.0/24",
                exercise_vmnet=selected[0], exercise_subnet=selected[1],
            )
        with self.assertRaises(ValueError):
            candidate_plan(
                current, vmnet="vmnet3", subnet="172.28.233.0/24",
                exercise_vmnet=selected[0], exercise_subnet=selected[1],
            )

    def test_native_guest_source_planner_defers_while_vms_running(self):
        current = HOST_CONFIG + (
            "answer VNET_3_DHCP no\n"
            "answer VNET_3_NAT no\n"
            "answer VNET_3_HOSTONLY_NETMASK 255.255.255.0\n"
            "answer VNET_3_HOSTONLY_SUBNET 172.28.232.0\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            networking = base / "networking"
            networking.write_text(current)
            north, fresh = base / "north", base / "fresh"
            north.mkdir()
            fresh.mkdir()
            (north / "NORTH.vmx").write_text('ethernet1.vnet = "vmnet10"\n')
            (fresh / "WSLPE.vmx").write_text('ethernet1.vnet = "vmnet3"\n')
            (fresh / "instance.json").write_text(
                '{"ip_range":"172.28.232"}\n'
            )
            argv = [
                "--native-workspace", str(fresh),
                "--workspace-root", str(north),
            ]
            with (mock.patch.object(CLI, "NETWORKING", networking),
                  mock.patch.object(CLI, "native_target",
                                    return_value=("vmnet3", "172.28.232.0/24")),
                  mock.patch.object(CLI.checker, "run_ip", return_value=[]),
                  mock.patch.object(CLI, "vmware_running", return_value=2),
                  redirect_stdout(StringIO()) as capture):
                self.assertEqual(CLI.main(argv), 2)
            output = capture.getvalue()
            self.assertIn("[NATIVE] Exact WSLPE exercise: vmnet3 172.28.232.0/24", output)
            self.assertIn("[PROPOSAL] Operator-only: vmnet4 172.28.233.0/24", output)
            self.assertIn("[DEFERRED] 2 VMware guest process(es) running", output)
            self.assertEqual(networking.read_text(), current)

    def test_planner_exposes_no_apply_or_vmware_mutation(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("add_argument(\"--apply\"", text)
        for dangerous in ("vmware-networks --stop", "vmware-networks --start",
                          "vagrant up", "vmrun -T ws stop", "iptables -F",
                          "nft -f"):
            self.assertNotIn(dangerous, text)
        self.assertIn('NETWORKING.read_text(encoding="utf-8")', text)


if __name__ == "__main__":
    unittest.main()
