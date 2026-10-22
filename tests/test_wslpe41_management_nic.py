"""Source tests for guarded, exact-fresh, powered-off third NIC transaction."""
from pathlib import Path
import json
import os
import stat
import tempfile
import unittest
from unittest import mock

from kingdoms import wslpe41_management_nic as nic

VMX = (
    '.encoding = "UTF-8"\n'
    'displayName = "provider: WSLPE-WS01"\n'
    'ethernet0.present = "TRUE"\n'
    'ethernet0.connectionType = "nat"\n'
    'ethernet0.startConnected = "TRUE"\n'
    'ethernet1.present = "TRUE"\n'
    'ethernet1.connectionType = "custom"\n'
    'ethernet1.vnet = "vmnet3"\n'
    'ethernet1.startConnected = "TRUE"\n'
).encode()


class Vmnet4ManagementNicTests(unittest.TestCase):
    def test_exact_slot2_added_without_changing_old_nics(self):
        result = nic.candidate_vmx(VMX)
        self.assertTrue(result.startswith(VMX))
        self.assertIn(b'ethernet2.vnet = "vmnet4"', result)
        self.assertIn(b'ethernet2.addressType = "generated"', result)
        nic.verify_layout(result, allow_management=True)

    def test_duplicate_existing_slot_or_foreign_network_refused(self):
        for original in (
            VMX + b'ethernet2.present = "FALSE"\n',
            VMX.replace(b'vmnet3', b'vmnet10'),
            VMX.replace(b'ethernet0.connectionType = "nat"',
                        b'ethernet0.connectionType = "custom"'),
            VMX.replace(b'ethernet1.present = "TRUE"',
                        b'ethernet1.present = "FALSE"'),
            VMX + b'ethernet3.present = "TRUE"\n',
            VMX[:-1],
        ):
            with self.subTest(original=original[-55:]):
                with self.assertRaises(nic.NicBlocked):
                    nic.candidate_vmx(original)

    def test_read_only_planner_identifies_exact_native_registration(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            instance = home / "kingdoms-wslpe41-fresh/workspace/bf5369-wslpe-vmware"
            path = instance / "provider/.vagrant/machines/WSLPE-WS01/vmware_desktop"
            path.mkdir(parents=True)
            vmx = path / "windows_10.vmx"
            vmx.write_bytes(VMX)
            (path / "id").write_text(str(vmx))
            (instance / "instance.json").write_text(json.dumps({
                "id": nic.INSTANCE, "lab": "WSLPE", "provider": "vmware",
                "provisioner": "local", "status": "ready for provisioning",
                "ip_range": "172.28.232", "extensions": []
            }))
            library = home / ".vmware/inventory.vmls"
            library.parent.mkdir()
            library.write_text(f'vmlist0.config = "{vmx}"\n')
            self.assertEqual(nic.identify(home).vmx, vmx)
            self.assertEqual(nic.identify(home).original, VMX)
            (path / "id").write_text(str(home / "kingdoms-lpe-standalone" / "old.vmx"))
            with self.assertRaises(nic.NicBlocked):
                nic.identify(home)

    def test_apply_creates_private_journal_and_modifies_exact_vmx(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            vmx = home / "windows_10.vmx"
            vmx.write_bytes(VMX)
            target = nic.Target(home / "instance", vmx, VMX,
                                __import__("hashlib").sha256(VMX).hexdigest())
            with (mock.patch.object(nic, "identify", return_value=target),
                  mock.patch.object(nic, "zero_vmware_guests") as zero,
                  mock.patch.object(nic, "host_operator_network_ready") as host):
                journal = nic.attach(home=home, expected_sha256=target.digest,
                                     approval=nic.APPROVAL)
                stored = json.loads(Path(journal).read_text())
                self.assertEqual(stored["status"], "committed")
                self.assertEqual(stored["original_sha256"], target.digest)
                self.assertEqual(Path(journal).stat().st_mode & 0o777, 0o600)
                self.assertEqual(Path(journal).parent.stat().st_mode & 0o777, 0o700)
                nic.verify_layout(vmx.read_bytes(), allow_management=True)
                self.assertEqual(vmx.read_bytes(), nic.candidate_vmx(VMX))
                zero.assert_called()
                host.assert_called_once()
                with self.assertRaisesRegex(nic.NicBlocked, "journal"):
                    nic.attach(home=home, expected_sha256=target.digest,
                               approval=nic.APPROVAL)

    def test_apply_refuses_wrong_hash_or_missing_approval_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            vmx = home / "guest.vmx"
            vmx.write_bytes(VMX)
            target = nic.Target(home / "instance", vmx, VMX,
                                __import__("hashlib").sha256(VMX).hexdigest())
            with (mock.patch.object(nic, "identify", return_value=target),
                  mock.patch.object(nic, "zero_vmware_guests"),
                  mock.patch.object(nic, "host_operator_network_ready")):
                for sha, approve in (
                    ("0"*64, nic.APPROVAL),
                    (target.digest, ""),
                ):
                    with self.assertRaises(nic.NicBlocked):
                        nic.attach(home=home, expected_sha256=sha, approval=approve)
                self.assertEqual(vmx.read_bytes(), VMX)
                self.assertFalse((home / ".local").exists())

    def test_all_guests_off_is_mandatory(self):
        def result(code, output):
            return mock.Mock(returncode=code, stdout=output, stderr=b"")
        with mock.patch.object(nic.subprocess, "run",
                               return_value=result(0, "Total running VMs: 1")):
            with self.assertRaisesRegex(nic.NicBlocked, "All VMware guests"):
                nic.zero_vmware_guests()
        with mock.patch.object(nic.subprocess, "run",
                               side_effect=[result(0, "Total running VMs: 0"), result(0, b"1")]):
            with self.assertRaisesRegex(nic.NicBlocked, "processes"):
                nic.zero_vmware_guests()

    def test_no_winrm_network_restart_or_other_vmx_write(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "kingdoms/wslpe41_management_nic.py").read_text()
        cli = (root / "scripts/wslpe41-attach-management-nic.py").read_text()
        for forbidden in ("vmware-networks --stop", "vmware-networks --start",
                          "vmrun -T ws start", "vmrun -T ws stop",
                          "ip route add", "New-NetIPAddress", "New-LocalUser",
                          "systemctl restart", "ansible-playbook"):
            self.assertNotIn(forbidden, source + cli)


if __name__ == "__main__":
    unittest.main()
