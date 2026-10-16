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

    def test_guest_creation_requires_explicit_operator_consent(self):
        result = self.adapter.create_guest(confirmed=False)
        self.assertFalse(result.ready)
        self.assertIn("confirmation", result.checks[0])
        self.assertEqual(self.calls, [])

    def test_guest_creation_is_single_scoped_vagrant_up(self):
        state = {"booted": False}
        def runner(args, **kwargs):
            self.calls.append((tuple(args), kwargs))
            if args[0] == "ruby":
                return SimpleNamespace(returncode=0, stdout="Syntax OK", stderr="")
            if args[1:] == ["plugin", "list"]:
                output = "vagrant-vmware-desktop (3.0.5, global)"
            elif args[1:] == ["box", "list"]:
                output = "mayfly/windows10 (vmware_desktop, 2024.01.06)"
            elif args[1:] == ["validate"]:
                output = "Vagrantfile validated"
            elif args[1:] == ["status"]:
                output = (
                    "kingdoms-lpe-ws01 running (vmware_desktop)"
                    if state["booted"]
                    else "kingdoms-lpe-ws01 not created (vmware_desktop)"
                )
            elif args == ["vagrant", "up", EXPECTED_VM, "--provider=vmware_desktop"]:
                self.assertFalse(kwargs["capture_output"])
                state["booted"] = True
                return SimpleNamespace(returncode=0, stdout=None, stderr=None)
            else:
                self.fail("unexpected command " + repr(args))
            return SimpleNamespace(returncode=0, stdout=output, stderr="")
        self.adapter._runner = runner
        result = self.adapter.create_guest(confirmed=True)
        self.assertTrue(result.ready, result.checks)
        self.assertIn("guest created and running", result.checks[0])
        mutations = [
            args for args, _ in self.calls if args[1:2] == ("up",)
        ]
        self.assertEqual(
            mutations, [("vagrant", "up", EXPECTED_VM, "--provider=vmware_desktop")]
        )
        self.assertTrue(all(k["cwd"] == str(self.project) for _, k in self.calls))
        self.assertFalse(any("destroy" in args for args, _ in self.calls))

    def test_guest_creation_refuses_ambiguous_or_existing_state(self):
        def state_runner(args, **kwargs):
            if args[0] == "ruby":
                stdout = "Syntax OK"
            elif args[1:] == ["plugin", "list"]:
                stdout = "vagrant-vmware-desktop (3.0.5, global)"
            elif args[1:] == ["box", "list"]:
                stdout = "mayfly/windows10 (vmware_desktop, 2024.01.06)"
            elif args[1:] == ["validate"]:
                stdout = "Vagrantfile validated"
            elif args[1:] == ["status"]:
                stdout = "kingdoms-lpe-ws01 running (vmware_desktop)"
            else:
                self.fail("VM creation attempted in ambiguous state")
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        self.adapter._runner = state_runner
        result = self.adapter.create_guest(confirmed=True)
        self.assertFalse(result.ready)
        self.assertIn("ambiguous VM state", result.checks[0])

    def test_guest_creation_refuses_stale_vagrant_machine_state(self):
        provider = (
            self.project / ".vagrant/machines" / EXPECTED_VM / "vmware_desktop"
        )
        provider.mkdir(parents=True)
        (provider / "id").write_text("registered-vm-id", encoding="utf-8")
        result = self.adapter.create_guest(confirmed=True)
        self.assertFalse(result.ready)
        self.assertTrue(any("partial Vagrant VM state" in line for line in result.checks))
        self.assertFalse(any(args[1:2] == ("up",) for args, _ in self.calls))

    def test_status_generated_empty_vagrant_state_does_not_block_creation(self):
        # The directory alone is not evidence of a registered Vagrant VM.
        provider = (
            self.project / ".vagrant/machines" / EXPECTED_VM / "vmware_desktop"
        )
        provider.mkdir(parents=True)
        (provider / "index_uuid").write_text("vagrant-index", encoding="utf-8")
        def inspect_only(args, **kwargs):
            # Track the attempted subprocess before returning, including a
            # deliberately failed Vagrant up. The previous mock returned
            # early and hid the invocation from the safety assertion.
            self.calls.append((tuple(args), kwargs))
            if args[0] == "ruby":
                output = "Syntax OK"
            elif args[1:] == ["plugin", "list"]:
                output = "vagrant-vmware-desktop (3.0.5, global)"
            elif args[1:] == ["box", "list"]:
                output = "mayfly/windows10 (vmware_desktop, 2024.01.06)"
            elif args[1:] == ["validate"]:
                output = "Vagrantfile validated"
            elif args[1:] == ["status"]:
                output = "kingdoms-lpe-ws01 not created (vmware_desktop)"
            elif args[1:2] == ["up"]:
                return SimpleNamespace(returncode=1, stdout="", stderr="")
            else:
                self.fail("unexpected command " + repr(args))
            return SimpleNamespace(returncode=0, stdout=output, stderr="")
        self.adapter._runner = inspect_only
        result = self.adapter.create_guest(confirmed=True)
        self.assertFalse(result.ready)
        self.assertIn("returned 1", result.checks[0])
        self.assertTrue(any(args[1:2] == ("up",) for args, _ in self.calls))

    def test_unexpected_state_metadata_fails_closed(self):
        provider = (
            self.project / ".vagrant/machines" / EXPECTED_VM / "vmware_desktop"
        )
        provider.mkdir(parents=True)
        (provider / "unexpected.lock").write_text("unknown", encoding="utf-8")
        result = self.adapter.create_guest(confirmed=True)
        self.assertFalse(result.ready)
        self.assertTrue(any("partial Vagrant VM state" in line for line in result.checks))

    def test_guest_creation_refuses_symlinked_vagrant_state(self):
        state = self.project / ".vagrant"
        state.symlink_to(self.root, target_is_directory=True)
        result = self.adapter.create_guest(confirmed=True)
        self.assertFalse(result.ready)
        self.assertTrue(any("symlink" in line for line in result.checks))

    def test_guest_creation_refuses_symlinked_machine_state_directory(self):
        state = self.project / ".vagrant"
        state.mkdir()
        (state / "machines").symlink_to(self.root, target_is_directory=True)
        result = self.adapter.create_guest(confirmed=True)
        self.assertFalse(result.ready)
        self.assertTrue(any("symlink" in line for line in result.checks))
        self.assertFalse(any(args[1:2] == ("up",) for args, _ in self.calls))

    def test_boot_failure_fails_without_attempted_cleanup_or_retry(self):
        def runner(args, **kwargs):
            self.calls.append((tuple(args), kwargs))
            if args[0] == "ruby":
                out = "Syntax OK"
            elif args[1:] == ["plugin", "list"]:
                out = "vagrant-vmware-desktop (3.0.5, global)"
            elif args[1:] == ["box", "list"]:
                out = "mayfly/windows10 (vmware_desktop, 2024.01.06)"
            elif args[1:] == ["validate"]:
                out = "Vagrantfile validated"
            elif args[1:] == ["status"]:
                out = "kingdoms-lpe-ws01 not created (vmware_desktop)"
            elif args[1:2] == ["up"]:
                return SimpleNamespace(returncode=1, stdout=None, stderr=None)
            else:
                self.fail("Unexpected cleanup/command")
            return SimpleNamespace(returncode=0, stdout=out, stderr="")
        self.adapter._runner = runner
        result = self.adapter.create_guest(confirmed=True)
        self.assertFalse(result.ready)
        self.assertIn("returned 1", result.checks[0])
        self.assertEqual(
            len([c for c in self.calls if c[0][1:2] == ("up",)]), 1
        )

    def test_missing_tools_fails_before_subprocess(self):
        self.adapter._which = lambda binary: None
        result = self.adapter.preflight()
        self.assertFalse(result.ready)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
