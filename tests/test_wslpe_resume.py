"""Mock-only native Kingdoms WSLPE resume acceptance.

No VMware or Vagrant subprocess is executed by this test module. The only
mutating operation authorized by the tested function is the existing
provider's single-machine "vagrant up WSLPE-WS01 --no-provision" adapter.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from goad.utils import PROVIDED
from kingdoms import wslpe_resume as RESUME


class WslpeNativeResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.provider_dir = self.workspace / "d986ad-wslpe-vmware" / "provider"
        self.provider_dir.mkdir(parents=True)
        self.vmx = self.provider_dir / ".vagrant/machines/WSLPE-WS01/vmware_desktop" / "uuid" / "windows_10.vmx"
        self.vmx.parent.mkdir(parents=True)
        self.vmx.write_text("displayName = WSLPE-WS01", encoding="utf-8")
        (self.vmx.parent.parent / "id").write_text(str(self.vmx), encoding="utf-8")
        (self.provider_dir / "Vagrantfile").write_text(
            ('boxes = [{:name => "WSLPE-WS01", :ip => "172.28.231.31"}]\n'
             'target.vm.communicator = "winrm"\n'
             'target.vm.network :private_network, ip: box[:ip]\n'),
            encoding="utf-8"
        )
        self.command = SimpleNamespace(run_vagrant=Mock(return_value=True))
        self.provider = SimpleNamespace(
            lab_name="WSLPE", path=str(self.provider_dir),
            command=self.command,
        )
        self.instance = SimpleNamespace(
            lab_name="WSLPE", provider_name="vmware",
            provisioner_name="local", extensions=[],
            instance_path=str(self.provider_dir.parent),
            instance_provider_path=str(self.provider_dir),
            get_status=lambda: PROVIDED,
        )
        self.manager = SimpleNamespace(
            get_current_instance=lambda: self.instance,
            get_current_instance_provider=lambda: self.provider,
        )
        self.running_north = str(self.root / "north" / "windows_10.vmx")
        self.status = (
            "Current machine states:\n\n"
            "WSLPE-WS01    not running (vmware_desktop)\n"
            "\nThe VM is powered off.\n"
        )

    @staticmethod
    def response(stdout, code=0):
        return SimpleNamespace(returncode=code, stdout=stdout, stderr="")

    def context(self, *, before=None, state=None, after=None):
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(
            RESUME.GoadPath, "get_project_path", return_value=str(self.root)
        ))
        stack.enter_context(patch.object(
            RESUME.GoadPath, "get_workspace_path", return_value=str(self.workspace)
        ))
        seq = [
            self.response(before if before is not None else
                          f"Total running VMs: 1\n{self.running_north}\n"),
            self.response(state if state is not None else self.status),
            self.response(after if after is not None else
                          f"Total running VMs: 2\n{self.running_north}\n{self.vmx}\n"),
        ]
        call = stack.enter_context(patch.object(
            RESUME.subprocess, "run", side_effect=seq
        ))
        return stack, call

    def test_existing_stopped_vm_only_is_resumed_once_without_provisioning(self):
        stack, calls = self.context()
        with stack:
            self.assertTrue(RESUME.resume_existing_wslpe(
                self.manager, confirmed=True
            ))
        self.command.run_vagrant.assert_called_once_with(
            ["up", "WSLPE-WS01", "--no-provision"], str(self.provider_dir)
        )
        self.assertEqual(calls.call_count, 3)
        self.assertEqual(self.instance.get_status(), PROVIDED)

    def test_resume_uses_temporary_direct_winrm_and_restores_environment(self):
        original_file = self.provider_dir / "Vagrantfile"
        original_source = original_file.read_text(encoding="utf-8")
        prior_override = os.environ.get("VAGRANT_VAGRANTFILE")

        def check_command(args, cwd):
            self.assertEqual(args, ["up", "WSLPE-WS01", "--no-provision"])
            self.assertEqual(cwd, str(self.provider_dir))
            temporary_name = os.environ.get("VAGRANT_VAGRANTFILE")
            self.assertTrue(temporary_name)
            temporary = self.provider_dir / temporary_name
            self.assertTrue(temporary.is_file())
            source = temporary.read_text(encoding="utf-8")
            self.assertIn("target.winrm.host = box[:ip]", source)
            self.assertIn("target.winrm.port = 5985", source)
            self.assertNotIn("target.winrm.host =", original_file.read_text())
            return True

        self.command.run_vagrant.side_effect = check_command
        stack, _ = self.context()
        with stack:
            self.assertTrue(RESUME.resume_existing_wslpe(
                self.manager, confirmed=True
            ))
        self.assertEqual(original_file.read_text(), original_source)
        self.assertEqual(os.environ.get("VAGRANT_VAGRANTFILE"), prior_override)
        self.assertEqual(list(self.provider_dir.glob("Vagrantfile.wslpe-resume-*")), [])

    def test_resume_does_not_use_ambiguous_vagrantfile(self):
        (self.provider_dir / "Vagrantfile").write_text(
            'boxes = [{:name => "WSLPE-WS01"}]', encoding="utf-8"
        )
        stack, _ = self.context()
        with stack:
            self.assertFalse(RESUME.resume_existing_wslpe(
                self.manager, confirmed=True
            ))
        self.command.run_vagrant.assert_not_called()
        self.assertEqual(list(self.provider_dir.glob("Vagrantfile.wslpe-resume-*")), [])

    def test_missing_confirmation_never_looks_at_vm_or_provider(self):
        self.assertFalse(RESUME.resume_existing_wslpe(
            self.manager, confirmed=False
        ))
        self.command.run_vagrant.assert_not_called()

    def test_no_loaded_guest_or_north_provider_fails_closed(self):
        self.manager.get_current_instance = lambda: None
        self.assertFalse(RESUME.resume_existing_wslpe(
            self.manager, confirmed=True
        ))
        self.manager.get_current_instance = lambda: self.instance
        self.provider.lab_name = "GOAD"
        self.assertFalse(RESUME.resume_existing_wslpe(
            self.manager, confirmed=True
        ))
        self.command.run_vagrant.assert_not_called()

    def test_vagrant_registration_missing_or_north_vmx_fails_closed(self):
        register = self.vmx.parent.parent / "id"
        register.unlink()
        stack, calls = self.context()
        with stack:
            self.assertFalse(RESUME.resume_existing_wslpe(
                self.manager, confirmed=True
            ))
        calls.assert_not_called()
        register.write_text(str(self.root / "GOAD-WS01.vmx"))
        stack, calls = self.context()
        with stack:
            self.assertFalse(RESUME.resume_existing_wslpe(
                self.manager, confirmed=True
            ))
        self.command.run_vagrant.assert_not_called()

    def test_powered_on_or_wrong_vagrant_state_does_not_call_provider(self):
        for state in (
            "WSLPE-WS01    running (vmware_desktop)",
            "WSLPE-WS01    not created (vmware_desktop)",
            "WSLPE-WS01    saved (vmware_desktop)",
            "WSLPE-WS01    not running (virtualbox)",
        ):
            with self.subTest(state=state):
                stack, _ = self.context(state=state)
                with stack:
                    self.assertFalse(RESUME.resume_existing_wslpe(
                        self.manager, confirmed=True
                    ))
        self.command.run_vagrant.assert_not_called()

    def test_exact_registered_guest_already_running_blocks(self):
        listing = f"Total running VMs: 2\n{self.running_north}\n{self.vmx}\n"
        stack, _ = self.context(before=listing)
        with stack:
            self.assertFalse(RESUME.resume_existing_wslpe(
                self.manager, confirmed=True
            ))
        self.command.run_vagrant.assert_not_called()

    def test_broken_vmware_inventory_count_blocks(self):
        stack, _ = self.context(before="Total running VMs: 3\n" + self.running_north)
        with stack:
            self.assertFalse(RESUME.resume_existing_wslpe(
                self.manager, confirmed=True
            ))
        self.command.run_vagrant.assert_not_called()

    def test_vm_bringup_failed_is_not_retried(self):
        self.command.run_vagrant.return_value = False
        stack, _ = self.context()
        with stack:
            self.assertFalse(RESUME.resume_existing_wslpe(
                self.manager, confirmed=True
            ))
        self.command.run_vagrant.assert_called_once()

    def test_post_resume_vmware_identity_mismatch_is_not_marked_ready(self):
        stack, _ = self.context(after=f"Total running VMs: 1\n{self.running_north}\n")
        with stack:
            self.assertFalse(RESUME.resume_existing_wslpe(
                self.manager, confirmed=True
            ))
        self.command.run_vagrant.assert_called_once()
        self.assertEqual(self.instance.get_status(), PROVIDED)

    def test_wrong_workspace_or_symlink_fails_without_lifecycle(self):
        foreign = self.root / "foreign"
        foreign.mkdir()
        self.instance.instance_path = str(foreign)
        stack, calls = self.context()
        with stack:
            self.assertFalse(RESUME.resume_existing_wslpe(
                self.manager, confirmed=True
            ))
        calls.assert_not_called()
        self.command.run_vagrant.assert_not_called()


if __name__ == "__main__":
    unittest.main()
