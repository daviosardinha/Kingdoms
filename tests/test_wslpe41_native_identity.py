"""Exact native WSLPE VMX identity checks, all filesystem fixtures mocked."""
import json
from pathlib import Path
import tempfile
import unittest

from kingdoms.wslpe41_host_preflight import HostEvidenceBlocked
from kingdoms.wslpe41_native_identity import inspect_native_registration


class NativeIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.instance = root / "workspace" / "wslpe41-001"
        machine = (self.instance / "provider" / ".vagrant" / "machines"
                   / "WSLPE-WS01" / "vmware_desktop")
        machine.mkdir(parents=True)
        self.vmx = machine / "Windows10.vmx"
        self.vmx.write_text('displayName = "WSLPE-WS01"\n')
        (machine / "id").write_text(str(self.vmx))
        self.manifest = self.instance / "instance.json"
        self.data = {
            "id": self.instance.name,
            "lab": "WSLPE", "provider": "vmware", "provisioner": "local",
            "ip_range": "172.28.232", "status": "ready for provisioning",
            "extensions": [],
        }
        self.save()
        self.running = f"Total running VMs: 1\n{self.vmx}\n"

    def save(self):
        self.manifest.write_text(json.dumps(self.data))

    def test_unique_provided_native_guest_is_registration_only(self):
        proof = inspect_native_registration(self.instance, self.running)
        self.assertEqual(proof.guest_address, "172.28.232.31")
        self.assertEqual(proof.subnet, "172.28.232.0/24")
        self.assertIn("NOT fresh-build proof", proof.source)
        self.assertEqual(proof.instance_id, "wslpe41-001")

    def test_rejects_wrong_lab_and_domain_inventory(self):
        self.data["lab"] = "NORTH"
        self.save()
        with self.assertRaises(HostEvidenceBlocked):
            inspect_native_registration(self.instance, self.running)

    def test_rejects_unprovided_guest(self):
        self.data["status"] = "not provided"
        self.save()
        with self.assertRaises(HostEvidenceBlocked):
            inspect_native_registration(self.instance, self.running)

    def test_rejects_domain_network(self):
        self.data["ip_range"] = "10.4.10"
        self.save()
        with self.assertRaises(HostEvidenceBlocked):
            inspect_native_registration(self.instance, self.running)

    def test_rejects_guest_outside_native_provider(self):
        foreign = Path(self.temp.name) / "master.vmx"
        foreign.write_text("test")
        vmid = self.vmx.parent / "id"
        vmid.write_text(str(foreign))
        with self.assertRaisesRegex(HostEvidenceBlocked, "escapes"):
            inspect_native_registration(self.instance,
                f"Total running VMs: 1\n{foreign}\n")

    def test_rejects_unregistered_guest(self):
        with self.assertRaisesRegex(HostEvidenceBlocked, "not uniquely running"):
            inspect_native_registration(self.instance, "Total running VMs: 0\n")

    def test_rejects_linked_vmx(self):
        source = Path(self.temp.name) / "linked-target.vmx"
        source.write_text("test")
        self.vmx.unlink()
        self.vmx.symlink_to(source)
        with self.assertRaisesRegex(HostEvidenceBlocked, "nonlinked"):
            inspect_native_registration(self.instance, self.running)

    def test_rejects_mismatched_manifest_identity(self):
        self.data["id"] = "wslpe41-old-master"
        self.save()
        with self.assertRaisesRegex(HostEvidenceBlocked, "not an exact"):
            inspect_native_registration(self.instance, self.running)


if __name__ == "__main__":
    unittest.main()
