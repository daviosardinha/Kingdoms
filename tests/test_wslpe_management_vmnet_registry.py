"""Only temporary Workstation library/VMX fixtures; never touch host VMware."""
import importlib.util
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from kingdoms.wslpe_management_vmnet_host_gate import (
    HostVmnetGateBlocked, RunningVmwareInventory,
)
from kingdoms.wslpe_management_vmnet_registry import (
    parse_workstation_library, referenced_vnets, audit_user_library,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/wslpe-management-vmnet-registry-audit.py"
spec = importlib.util.spec_from_file_location("wslpe_offline_library_cli", SCRIPT)
assert spec and spec.loader
CLI = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CLI)


class WorkstationLibraryAuditTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.base = Path(self.folder.name)
        self.fresh = self.base / "fresh"
        self.master = self.base / "master"
        self.fresh.mkdir()
        self.master.mkdir()
        self.fresh_vmx = self.fresh / "WSLPE.vmx"
        self.master_vmx = self.master / "MASTER.vmx"
        self.fresh_vmx.write_text(
            'ethernet0.connectionType = "nat"\n'
            'ethernet1.connectionType = "custom"\n'
            'ethernet1.vnet = "vmnet3"\n')
        self.master_vmx.write_text(
            'ethernet1.connectionType = "custom"\n'
            'ethernet1.vnet = "vmnet2"\n')
        workdir = self.base / ".vmware"
        workdir.mkdir()
        self.library = workdir / "inventory.vmls"
        self.library.write_text(self.format_library(self.fresh_vmx, self.master_vmx))
        self.roots = (self.fresh, self.master)
        self.running = RunningVmwareInventory(
            vmrun_count=2, process_count=2,
            vmx_paths=tuple(sorted((str(self.fresh_vmx), str(self.master_vmx))),
        )

    @staticmethod
    def format_library(*paths):
        return "..." + "\n" + "\n".join(
            f'vmlist{i}.config = "{p}"' for i, p in enumerate(paths)
        ) + "\n"

    def audit(self, roots=None, running=None):
        return audit_user_library(
            library=self.library, roots=self.roots if roots is None else roots,
            running=self.running if running is None else running,
            candidate_vmnet="vmnet4",
        )

    def test_existing_two_registered_guests_are_clear(self):
        result = self.audit()
        self.assertEqual(result.count, 2)
        self.assertEqual(result.outside_roots, ())
        self.assertEqual(result.running_not_in_library, ())

    def test_offline_registered_vm_claiming_vmnet4_blocks(self):
        offline = self.master / "OFFLINE.vmx"
        offline.write_text('ethernet2.vnet = "vmnet4"\n')
        self.library.write_text(self.format_library(
            self.fresh_vmx, self.master_vmx, offline))
        with self.assertRaisesRegex(HostVmnetGateBlocked, "already references"):
            self.audit()

    def test_foreign_registration_is_reported(self):
        foreign = self.base / "foreign.vmx"
        foreign.write_text('ethernet1.vnet = "vmnet42"\n')
        self.library.write_text(self.format_library(self.fresh_vmx, foreign))
        result = self.audit()
        self.assertEqual(result.outside_roots, (str(foreign),))
        self.assertEqual(result.running_not_in_library, (str(self.master_vmx),))

    def test_unlisted_running_vm_is_never_silently_approved(self):
        self.library.write_text(self.format_library(self.fresh_vmx))
        result = self.audit()
        self.assertEqual(result.running_not_in_library, (str(self.master_vmx),))

    def test_missing_or_symlinked_library_blocks(self):
        self.library.unlink()
        with self.assertRaisesRegex(HostVmnetGateBlocked, "missing"):
            self.audit()
        other = self.base / "real.vmls"
        other.write_text(self.format_library(self.fresh_vmx))
        self.library.symlink_to(other)
        with self.assertRaisesRegex(HostVmnetGateBlocked, "linked"):
            self.audit()

    def test_unparseable_or_duplicate_entries_fail_closed(self):
        for text in (
            'vmlist1.config = "relative.vmx"\n',
            f'vmlist0.config = "{self.fresh_vmx}"\nvmlist0.config = "{self.master_vmx}"',
            f'vmlist0.config = "{self.fresh_vmx}"\nvmlist1.config = "{self.fresh_vmx}"',
            'vmlist1.config = unquoted.vmx\n',
            "vmlist1.GuestOS = Windows\n",
        ):
            with self.subTest(text=text):
                with self.assertRaises(HostVmnetGateBlocked):
                    parse_workstation_library(text)

    def test_ambiguous_vmnet_and_custom_nic_block(self):
        for text in (
            'ethernet1.vnet = vmnet4\n',
            'ethernet1.vnet = "unknown"\n',
            'ethernet1.connectionType = "custom"\n',
        ):
            with self.subTest(text=text):
                with self.assertRaises(HostVmnetGateBlocked):
                    referenced_vnets(text)

    def test_valid_vnet_references_use_exact_names(self):
        self.assertEqual(
            referenced_vnets('ethernet1.vnet = "vmnet4"\n'),
            {"vmnet4"},
        )
        self.assertEqual(
            referenced_vnets('ethernet1.vnet = "vmnet40"\n'),
            {"vmnet40"},
        )

    def test_cli_reports_deferred_with_running_guests(self):
        with (mock.patch.object(CLI.Path, "home", return_value=self.base),
              mock.patch.object(CLI, "probe_running_vmware", return_value=self.running),
              redirect_stdout(StringIO()) as output):
            rc = CLI.main([
                "--workspace-root", str(self.fresh),
                "--workspace-root", str(self.master)])
        self.assertEqual(rc, 2)
        self.assertIn("[DEFERRED]", output.getvalue())
        self.assertIn("[LIBRARY] 2", output.getvalue())

    def test_cli_reports_other_owner_as_blocked(self):
        foreign = self.base / "foreign.vmx"
        foreign.write_text('ethernet0.vnet = "vmnet5"\n')
        self.library.write_text(self.format_library(self.fresh_vmx, foreign))
        with (mock.patch.object(CLI.Path, "home", return_value=self.base),
              mock.patch.object(CLI, "probe_running_vmware", return_value=self.running),
              redirect_stdout(StringIO()) as output):
            rc = CLI.main([
                "--workspace-root", str(self.fresh),
                "--workspace-root", str(self.master)])
        self.assertEqual(rc, 2)
        self.assertIn("[OTHER OWNER]", output.getvalue())
        self.assertIn("[BLOCKED]", output.getvalue())


if __name__ == "__main__":
    unittest.main()
