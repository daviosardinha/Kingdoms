"""Offline WSLPE maintenance suite; all VMX and registration fixtures temporary."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from kingdoms.wslpe_management_vmnet_transaction import NetworkTransactionBlocked

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/wslpe-management-vmnet-offline-native.py"
SPEC = importlib.util.spec_from_file_location("wslpe_offline_native_gate", PATH)
assert SPEC and SPEC.loader
OFF = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = OFF
SPEC.loader.exec_module(OFF)


class OfflineNativeMaintenanceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.instance = base / "bf5369-wslpe-vmware"
        self.instance.mkdir()
        provider = self.instance / "provider"
        provider.mkdir()
        registration = provider / ".vagrant/machines/WSLPE-WS01/vmware_desktop"
        registration.mkdir(parents=True)
        self.vmx = registration / "windows_10.vmx"
        self.vmx.write_text(
            'ethernet0.present = "TRUE"\n'
            'ethernet0.connectionType = "nat"\n'
            'ethernet1.present = "TRUE"\n'
            'ethernet1.connectionType = "custom"\n'
            'ethernet1.vnet = "vmnet3"\n')
        (registration / "id").write_text(str(self.vmx))
        self.manifest = self.instance / "instance.json"
        self.manifest.write_text(json.dumps({
            "id": self.instance.name,
            "lab": "WSLPE", "provider": "vmware",
            "provisioner": "local", "status": "ready for provisioning",
            "extensions": [], "ip_range": "172.28.232"
        }))
        self.library = base / "inventory.vmls"
        self.library.write_text(f'vmlist0.config = "{self.vmx}"\n')
        self.networking = base / "networking"
        self.networking.write_text(
            "VERSION=1,0\n"
            "answer VNET_3_DHCP no\n"
            "answer VNET_3_NAT no\n"
            "answer VNET_3_HOSTONLY_NETMASK 255.255.255.0\n"
            "answer VNET_3_HOSTONLY_SUBNET 172.28.232.0\n"
        )

    def check(self):
        return OFF.offline_native_contract(self.instance, self.library, self.networking)

    def test_offline_native_with_vmnet3_is_valid_without_vmrun(self):
        self.assertEqual(self.check(), (str(self.vmx), "vmnet3", "172.28.232.0/24"))

    def test_wrong_native_instance_id_is_denied(self):
        previous = json.loads(self.manifest.read_text())
        previous["id"] = "other"
        self.manifest.write_text(json.dumps(previous))
        with self.assertRaisesRegex(NetworkTransactionBlocked, "identity"):
            self.check()

    def test_wrong_lab_or_prefix_is_denied(self):
        for key, value in (("lab", "NORTH"), ("ip_range", "172.28.231")):
            data = json.loads(self.manifest.read_text())
            data[key] = value
            self.manifest.write_text(json.dumps(data))
            with self.assertRaisesRegex(NetworkTransactionBlocked, "identity"):
                self.check()
            data[key] = "WSLPE" if key == "lab" else "172.28.232"
            self.manifest.write_text(json.dumps(data))

    def test_unregistered_offline_vmx_is_denied(self):
        self.library.write_text(
            f'vmlist0.config = "{self.instance / "other.vmx"}"\n')
        with self.assertRaises(NetworkTransactionBlocked):
            self.check()

    def test_changed_exercise_network_is_denied(self):
        self.vmx.write_text(self.vmx.read_text().replace("vmnet3", "vmnet4"))
        with self.assertRaises((NetworkTransactionBlocked, ValueError)):
            self.check()

    def test_missing_network_metadata_is_denied(self):
        self.networking.write_text("VERSION=1,0\n")
        with self.assertRaises((NetworkTransactionBlocked, ValueError)):
            self.check()

    def test_symbolic_link_registration_is_denied(self):
        path = self.instance / "provider/.vagrant/machines/WSLPE-WS01/vmware_desktop/id"
        path.unlink()
        real = path.parent / "actual-id"
        real.write_text(str(self.vmx))
        path.symlink_to(real)
        with self.assertRaisesRegex(NetworkTransactionBlocked, "registration"):
            self.check()

    def test_stopped_vm_gate_has_no_runtime_mutation(self):
        text = PATH.read_text()
        for bad in ("vmrun -T ws start", "vmware-networks --start",
                    "vmrun -T ws stop", "subprocess.run("):
            self.assertNotIn(bad, text)


if __name__ == "__main__":
    unittest.main()
