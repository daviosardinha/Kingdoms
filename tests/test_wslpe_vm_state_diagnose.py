"""Fixture-only tests for native WSLPE registration and running VM state.

No VMware / Vagrant subprocess is actually executed in these tests.
"""
import importlib.util
import json
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "wslpe_vm_state_diag", ROOT / "scripts/wslpe-vm-state-diagnose.py"
)
assert SPEC and SPEC.loader
DIAG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIAG)


class WslpeVmStateTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.instance = Path(self.tmp.name) / "instance"
        self.id_file = (
            self.instance / "provider/.vagrant/machines/WSLPE-WS01"
            / "vmware_desktop/id"
        )
        self.id_file.parent.mkdir(parents=True)
        self.vmx = Path(self.tmp.name) / "wslpe" / "windows_10.vmx"
        self.vmx.parent.mkdir()
        self.vmx.write_text("displayName = WSLPE\n")
        self.id_file.write_text(str(self.vmx), encoding="utf-8")

    def test_registered_vmx_read_only(self):
        self.assertEqual(DIAG.registered_vmx(self.instance), self.vmx)
        self.assertTrue(self.vmx.is_file())

    def test_registration_missing_or_symlinked_is_blocked(self):
        self.id_file.unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            DIAG.registered_vmx(self.instance)
        self.id_file.symlink_to(self.vmx)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            DIAG.registered_vmx(self.instance)

    def test_registration_must_not_point_to_north(self):
        self.id_file.write_text("/lab/GOAD-WS01.vmx")
        with self.assertRaisesRegex(ValueError, "NORTH"):
            DIAG.registered_vmx(self.instance)

    def test_vmrun_inventory_normalized_and_checked(self):
        listing = f"Total running VMs: 1\n{self.vmx}\n"
        self.assertEqual(DIAG.parse_vmrun(listing), [self.vmx])
        with self.assertRaisesRegex(ValueError, "count"):
            DIAG.parse_vmrun("Total running VMs: 2\n" + str(self.vmx))
        with self.assertRaisesRegex(ValueError, "valid"):
            DIAG.parse_vmrun("invalid inventory")

    def test_exact_absence_and_filename_mismatch_are_distinct(self):
        self.assertEqual(DIAG.evaluate_registration(self.vmx, [self.vmx]),
                         ("MATCHED", 1))
        self.assertEqual(DIAG.evaluate_registration(self.vmx, []),
                         ("NOT_IN_RUNNING_INVENTORY", 0))
        other = Path(self.tmp.name) / "elsewhere" / self.vmx.name
        # A matching basename is not evidence of VM identity. The full
        # registered VMX path is what matters.
        self.assertEqual(DIAG.evaluate_registration(self.vmx, [other]),
                         ("NOT_IN_RUNNING_INVENTORY", 0))
        self.assertEqual(DIAG.evaluate_registration(self.vmx,
                         [self.vmx, self.vmx]), ("AMBIGUOUS", 2))

    def test_diagnostic_runs_only_read_only_vmware_vagrant_commands(self):
        source = (ROOT / "scripts/wslpe-vm-state-diagnose.py").read_text()
        self.assertIn('["vmrun", "-T", "ws", "list"]', source)
        self.assertIn('["vagrant", "status", MACHINE]', source)
        for forbidden in (
            '["vagrant", "up"',
            '["vagrant", "reload"',
            '["vagrant", "destroy"',
            '["vmrun", "-T", "ws", "start"',
            '["vmrun", "-T", "ws", "stop"',
            "set_status(", "unlink(", "rename(",
        ):
            self.assertNotIn(forbidden, source)

    def test_nonzero_readonly_subprocess_is_not_retried(self):
        from types import SimpleNamespace
        with patch.object(DIAG.subprocess, "run", return_value=SimpleNamespace(
            returncode=1, stdout="", stderr="unavailable"
        )) as subprocess:
            self.assertEqual(DIAG.run_read_only(["vmrun", "-T", "ws", "list"]),
                             (1, "", "unavailable"))
        subprocess.assert_called_once()
        self.assertTrue(subprocess.call_args.kwargs["capture_output"])


if __name__ == "__main__":
    import unittest
    unittest.main()
