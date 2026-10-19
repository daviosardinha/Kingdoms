"""Offline WSLPE41 full-clone preflight tests; never contact real VMware."""
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("wslpe41_clone_audit",ROOT/"scripts/wslpe41-clone-audit.py")
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class CloneAuditTests(unittest.TestCase):
    def fixture(self, root):
        master=root/"master"
        master.mkdir()
        original=master/"windows10.vmx"
        original.write_text('displayName = "WSLPE-WS01"\n')
        candidate=root/"working-clone"
        candidate.mkdir()
        disk=candidate/"disk.vmdk"
        disk.write_text('CID=11111111\nparentCID=ffffffff\ncreateType="monolithicSparse"\n')
        vmx=candidate/"clone.vmx"
        vmx.write_text('ethernet0.present = "TRUE"\n'
                       'ethernet0.startConnected = "FALSE"\n'
                       'scsi0:0.fileName = "disk.vmdk"\n')
        return original,vmx,disk

    def test_disconnected_full_clone_is_candidate_only(self):
        with TemporaryDirectory() as temp:
            master,clone,_=self.fixture(Path(temp))
            result=audit.vmx_inventory(clone,master)
            self.assertEqual(result["nics"],1)
            self.assertEqual(result["vmdks"],1)

    def test_connected_clone_or_linked_disk_refused(self):
        with TemporaryDirectory() as temp:
            master,clone,disk=self.fixture(Path(temp))
            good=clone.read_text()
            for text in (
                good.replace('"FALSE"','"TRUE"'),
                good.replace('ethernet0.startConnected = "FALSE"\n',''),
                good.replace('disk.vmdk','../master/parent.vmdk'),
            ):
                clone.write_text(text)
                with self.assertRaises(ValueError):
                    audit.vmx_inventory(clone,master)
            clone.write_text(good)
            disk.write_text('CID=22222222\nparentCID=abcdef01\nparentFileNameHint="parent.vmdk"\n')
            with self.assertRaises(ValueError):
                audit.vmx_inventory(clone,master)
            disk.write_text('CID=22222222\nparentCID=ffffffff\n')
            self.assertEqual(audit.vmx_inventory(clone,master)["nics"],1)

    def test_running_candidate_is_refused(self):
        with TemporaryDirectory() as temp:
            original,clone,_=self.fixture(Path(temp))
            audit.powered_off(clone,original,'Total running VMs: 0\n')
            with self.assertRaises(ValueError):
                audit.powered_off(clone,original,'Total running VMs: 1\n'+str(clone)+'\n')

    def test_master_vmx_cannot_be_clone(self):
        with TemporaryDirectory() as temp:
            master,clone,_=self.fixture(Path(temp))
            with self.assertRaises(ValueError):
                audit.vmx_inventory(master,master)

    def test_audit_does_not_mutate_vmware_or_guest(self):
        src=(ROOT/"scripts/wslpe41-clone-audit.py").read_text()
        for forbidden in ('"start"', '"stop"', '"revertToSnapshot"', '"deleteSnapshot"',
                          '"clone"', '"snapshot", str(', 'ansible-playbook'):
            self.assertNotIn(forbidden,src)
        self.assertIn('"vmrun","-T","ws","list"',src)


if __name__=="__main__":
    unittest.main()
