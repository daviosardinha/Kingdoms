"""Operator-only Windows LPE VMware backend tests. No VMs are booted."""

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from kingdoms.windows_lpe_vmware import (
    EXPECTED_BOX,
    EXPECTED_VERSION,
    EXPECTED_VM,
    WindowsLpeVmwareAdapter,
)


class WindowsLpeVmwareBackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "courses/windows-lpe/standalone"
        self.project.mkdir(parents=True)
        (self.project / "Vagrantfile").write_text(
            'config.vm.define "' + EXPECTED_VM + '"\n'
            'guest.vm.box = "' + EXPECTED_BOX + '"\n'
            'guest.vm.box_version = "' + EXPECTED_VERSION + '"\n'
            'vmware.vmx["ethernet0.connectionType"] = "nat"\n'
            'vmware.vmx["ethernet1.present"] = "FALSE"\n'
            'vmware.vmx["ethernet2.present"] = "FALSE"\n',
            encoding="utf-8",
        )
        self.calls = []

        def runner(args, **kwargs):
            self.calls.append((tuple(args), kwargs))
            if args[0] == "ruby":
                result = "Syntax OK"
            elif args[1:] == ["plugin", "list"]:
                result = "vagrant-vmware-desktop (3.0.5, global)"
            elif args[1:] == ["box", "list"]:
                result = "mayfly/windows10 (vmware_desktop, 2024.01.06)"
            elif args[1:] == ["validate"]:
                result = "Vagrantfile validated."
            elif args[1:] == ["status"]:
                result = "kingdoms-lpe-ws01 not created"
            else:
                raise AssertionError(f"Unexpected command: {args}")
            return SimpleNamespace(returncode=0, stdout=result, stderr="")

        self.adapter = WindowsLpeVmwareAdapter(
            self.root,
            runner=runner,
            which=lambda binary: "/usr/bin/" + binary,
        )

    def test_preflight_checks_only_read_only_commands(self):
        result = self.adapter.preflight()
        self.assertTrue(result.ready, result.checks)
        self.assertEqual([args for args, _ in self.calls], [
            ("ruby", "-c", str(self.project / "Vagrantfile")),
            ("vagrant", "plugin", "list"),
            ("vagrant", "box", "list"),
            ("vagrant", "validate"),
        ])
        self.assertTrue(all(k["cwd"] == str(self.project) for _, k in self.calls))
        self.assertTrue(all(k["check"] is False for _, k in self.calls))
        self.assertTrue(all(k["capture_output"] is True for _, k in self.calls))
        self.assertFalse(any("up" in args for args, _ in self.calls))

    def test_status_never_checks_or_modifies_north_provider(self):
        result = self.adapter.vm_status()
        self.assertTrue(result.ready)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0], ("vagrant", "status"))
        self.assertIn("not created", result.checks[-1])

    def test_rejects_host_mutating_commands_even_from_internal_caller(self):
        with self.assertRaisesRegex(ValueError, "refused"):
            self.adapter._run(["vagrant", "up"])
        with self.assertRaisesRegex(ValueError, "refused"):
            self.adapter._run(["vagrant", "destroy", "-f"])
        self.assertEqual(self.calls, [])

    def test_missing_or_modified_vm_definition_blocks_before_tool_use(self):
        file = self.project / "Vagrantfile"
        file.unlink()
        result = self.adapter.preflight()
        self.assertFalse(result.ready)
        self.assertFalse(self.calls)
        file.write_text(
            'config.vm.define "kingdoms-lpe-ws01"\n'
            'vmware.vmx["ethernet0.connectionType"] = "nat"\n'
            'vmnet10\n',
            encoding="utf-8",
        )
        result = self.adapter.preflight()
        self.assertFalse(result.ready)
        self.assertFalse(self.calls)

    def test_box_absence_fails_closed_without_validating_project(self):
        self.adapter._runner = lambda args, **kw: SimpleNamespace(
            returncode=0, stdout=(
                "Syntax OK" if args[0] == "ruby"
                else "vagrant-vmware-desktop (3.0.5)" if args[1:] == ["plugin", "list"]
                else "other/windows (vmware_desktop, 1.0)"
            ), stderr="",
        )
        result = self.adapter.preflight()
        self.assertFalse(result.ready)
        self.assertTrue(any("pinned Windows" in x for x in result.checks))

    def test_missing_tools_fails_before_subprocess(self):
        self.adapter._which = lambda binary: None
        result = self.adapter.preflight()
        self.assertFalse(result.ready)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
