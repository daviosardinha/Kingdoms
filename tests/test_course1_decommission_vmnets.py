"""Pure and mocked tests for precisely scoped VMware network removal."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts/course1-decommission-vmnets.py"
spec = importlib.util.spec_from_file_location("decommission_vmnets", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class VmnetRemovalTests(unittest.TestCase):
    def test_approved_seven_removed_and_unrelated_preserved(self):
        before = (
            "answer VNET_1_HOSTONLY_SUBNET 192.168.200.0\n"
            "answer VNET_8_NAT yes\n"
            "answer VNET_10_HOSTONLY_SUBNET 10.4.10.0\n"
            "answer VNET_11_HOSTONLY_SUBNET 10.41.10.0\n"
            "answer VNET_12_HOSTONLY_SUBNET 10.41.20.0\n"
            "answer VNET_13_HOSTONLY_SUBNET 10.41.99.0\n"
            "answer VNET_20_HOSTONLY_SUBNET 10.4.20.0\n"
            "answer VNET_30_HOSTONLY_SUBNET 10.4.30.0\n"
            "answer VNET_99_HOSTONLY_SUBNET 10.4.99.0\n"
            "answer VNET_42_HOSTONLY_SUBNET 172.16.42.0\n"
        )
        after, removed = mod.render(before)
        self.assertEqual(removed, {10, 11, 12, 13, 20, 30, 99})
        mod.check_targets(before, after, removed)
        self.assertIn("VNET_1_", after)
        self.assertIn("VNET_8_", after)
        self.assertIn("VNET_42_", after)
        self.assertNotIn("VNET_10_", after)

    def test_no_retired_networks_is_noop(self):
        before = "answer VNET_8_NAT yes\n"
        after, removed = mod.render(before)
        self.assertEqual(before, after)
        with self.assertRaisesRegex(RuntimeError, "nothing to remove"):
            mod.check_targets(before, after, removed)

    def test_running_vm_blocks(self):
        with patch.object(mod, "shell", return_value=subprocess.CompletedProcess(
                [], 0, "Total running VMs: 1\n/path/guest.vmx\n", "")):
            with self.assertRaisesRegex(RuntimeError, "not exactly zero"):
                mod.no_running_guests()

    def test_active_vmware_process_blocks(self):
        with patch.object(mod, "shell", side_effect=[
            subprocess.CompletedProcess([], 0, "Total running VMs: 0\n", ""),
            subprocess.CompletedProcess([], 0, "123\n", ""),
        ]):
            with self.assertRaisesRegex(RuntimeError, "processes still exist"):
                mod.no_running_guests()

    def test_registered_vm_on_target_vmnet_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".vmware").mkdir()
            vmx = root / "another.vmx"
            vmx.write_text('ethernet1.vnet = "vmnet10"\n')
            (root / ".vmware/inventory.vmls").write_text(
                f'vmlist2.config = "{vmx}"\n')
            self.assertEqual(mod.powered_off_inventory_conflicts(root),
                             [f"Registered VM uses retired vmnet: {vmx}"])

    def test_stale_missing_vm_is_not_foreign_attachment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".vmware").mkdir()
            (root / ".vmware/inventory.vmls").write_text(
                'vmlist2.config = "/not-present/vm.vmx"\n')
            self.assertEqual(mod.powered_off_inventory_conflicts(root), [])


if __name__ == "__main__":
    unittest.main()
