"""Exact WSLPE offline recovery contract tests; temporary files only."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from kingdoms.wslpe_exact_restore import prepare_plan, inspect_recovery_state, atomic_restore_offline

SAMPLE = """ethernet0.present = "TRUE"
ethernet0.connectionType = "nat"
ethernet0.generatedAddress = "00:0c:29:01:bb:77"
ethernet1.present = "TRUE"
ethernet1.connectionType = "custom"
ethernet1.vnet = "vmnet2"
ethernet1.generatedAddress = "00:0c:29:01:bb:81"
ethernet1.startConnected = "TRUE"
"""

class OfflineRestoreTests(unittest.TestCase):
    @unittest.skipIf(os.geteuid() == 0, "non-root VMware user required")
    def test_copy_only_recovery(self):
        with TemporaryDirectory() as tmp:
            vmx = Path(tmp) / "windows_10.vmx"
            vmx.write_text(SAMPLE)
            plan = prepare_plan(vmx, vmx, "vmnet2", os.geteuid())
            self.assertEqual(inspect_recovery_state(plan, plan.candidate, running=False), "RESTORE_OFFLINE_CANDIDATE")
            self.assertRaises(ValueError, inspect_recovery_state, plan, plan.candidate, running=True)
            vmx.write_bytes(plan.candidate)
            self.assertEqual(atomic_restore_offline(plan, registered=vmx, still_running=False), "RESTORED_ORIGINAL_OFFLINE")
            self.assertEqual(vmx.read_bytes(), plan.original)

    @unittest.skipIf(os.geteuid() == 0, "non-root VMware user required")
    def test_reject_foreign_link_and_vmware_rewrite(self):
        with TemporaryDirectory() as tmp:
            vmx = Path(tmp) / "windows_10.vmx"
            vmx.write_text(SAMPLE)
            foreign = Path(tmp) / "other.vmx"
            foreign.write_text(SAMPLE)
            self.assertRaises(ValueError, prepare_plan, vmx, foreign, "vmnet2", os.geteuid())
            link = Path(tmp) / "link.vmx"
            link.symlink_to(vmx)
            self.assertRaises(ValueError, prepare_plan, link, vmx, "vmnet2", os.geteuid())
            plan = prepare_plan(vmx, vmx, "vmnet2", os.geteuid())
            vmx.write_bytes(plan.candidate + b'other.setting = "unexpected"\n')
            self.assertRaises(ValueError, atomic_restore_offline,
                              plan, registered=vmx, still_running=False)

    @unittest.skipIf(os.geteuid() == 0, "non-root VMware user required")
    def test_nonowner_cannot_restore(self):
        with TemporaryDirectory() as tmp:
            vmx = Path(tmp) / "windows_10.vmx"
            vmx.write_text(SAMPLE)
            plan = prepare_plan(vmx, vmx, "vmnet2", os.geteuid())
            vmx.write_bytes(plan.candidate)
            from unittest.mock import patch
            with patch("kingdoms.wslpe_exact_restore.os.geteuid", return_value=0):
                self.assertRaises(ValueError, atomic_restore_offline,
                                  plan, registered=vmx, still_running=False)
            self.assertEqual(vmx.read_bytes(), plan.candidate)

if __name__ == "__main__":
    unittest.main()
