"""Mock-only recovery tests: never start or change a VMware guest."""
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from goad.utils import CREATED, PROVIDED
from kingdoms import wslpe_stage1_repair as repair


class NativeStage1RepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.instance_dir = self.workspace / "bf5369-wslpe-vmware"
        self.provider_dir = self.instance_dir / "provider"
        self.provider_dir.mkdir(parents=True)
        (self.provider_dir / "Vagrantfile").write_text(
            'boxes=[{ :name => "WSLPE-WS01" }]\n'
            'v.enable_vmrun_ip_lookup = false\n', encoding="utf-8",
        )
        self.instance = SimpleNamespace(
            lab_name="WSLPE", provider_name="vmware", provisioner_name="local",
            ip_range="172.28.232", instance_path=str(self.instance_dir),
            instance_provider_path=str(self.provider_dir), extensions=[],
            status=CREATED,
        )
        self.instance.get_status = lambda: self.instance.status
        self.instance.set_status = Mock(side_effect=lambda status: setattr(
            self.instance, "status", status,
        ))
        self.provider = SimpleNamespace(
            lab_name="WSLPE", path=str(self.provider_dir),
            _winrm_forwarded_port=Mock(return_value=2200),
            _wait_winrm_ready=Mock(return_value=True),
            _ensure_vmware_tools=Mock(return_value=True),
            _guest_tools_healthy=Mock(return_value=True),
            _run_vagrant_bounded=Mock(return_value=True),
        )
        self.manager = SimpleNamespace(
            get_current_instance=lambda: self.instance,
            get_current_instance_provider=lambda: self.provider,
        )
        self.scripts = []
        def run_ps(script):
            self.scripts.append(script)
            if "WSLPE_STAGE1_EXERCISE_NIC=PASS" in script:
                proof = b"WSLPE_STAGE1_WINDOWS_NAT=PASS\nWSLPE_STAGE1_EXERCISE_NIC=PASS\n"
            else:
                proof = b"WSLPE_STAGE1_WINDOWS_NAT=PASS\n"
            return SimpleNamespace(status_code=0, std_out=proof)
        self.provider._winrm_session = Mock(
            return_value=SimpleNamespace(run_ps=run_ps),
        )

    def patches(self):
        stack = ExitStack()
        stack.enter_context(patch.object(
            repair.GoadPath, "get_project_path", return_value=str(self.root)))
        stack.enter_context(patch.object(
            repair.GoadPath, "get_workspace_path", return_value=str(self.workspace)))
        stack.enter_context(patch.object(
            repair, "inspect_vmware_guest", return_value=True))
        return stack

    def test_one_confirmed_native_repair_uses_original_vagrant_provisioners(self):
        with self.patches():
            self.assertTrue(repair.repair_native_wslpe_stage1(
                self.manager, confirmed=True))
        self.provider._ensure_vmware_tools.assert_called_once_with("WSLPE-WS01")
        self.provider._run_vagrant_bounded.assert_called_once_with(
            ["up", "WSLPE-WS01", "--provision"], timeout=600)
        self.provider._guest_tools_healthy.assert_called_once_with(2200)
        self.instance.set_status.assert_called_once_with(PROVIDED)
        self.assertEqual(len(self.scripts), 3 - 1)
        self.assertIn("172.28.232.31", self.scripts[-1])
        self.assertIn("WSLPE_STAGE1_WRONG_WINDOWS_GUEST", self.scripts[0])
        self.assertEqual(self.instance.status, PROVIDED)

    def test_no_operator_approval_never_runs_guest_or_vagrant(self):
        with self.patches():
            self.assertFalse(repair.repair_native_wslpe_stage1(
                self.manager, confirmed=False))
        self.provider._ensure_vmware_tools.assert_not_called()
        self.provider._run_vagrant_bounded.assert_not_called()

    def test_fails_closed_on_wrong_lab_or_prior_provided_status(self):
        for field, value in (("lab_name", "GOAD"), ("provider_name", "virtualbox"),
                             ("ip_range", "10.4.10"), ("status", PROVIDED)):
            before = getattr(self.instance, field)
            with self.subTest(field=field), self.patches():
                setattr(self.instance, field, value)
                self.assertFalse(repair.repair_native_wslpe_stage1(
                    self.manager, confirmed=True))
            setattr(self.instance, field, before)
        self.provider._ensure_vmware_tools.assert_not_called()

    def test_source_vagrantfile_drift_blocks_repair(self):
        (self.provider_dir / "Vagrantfile").write_text("unknown machine")
        with self.patches():
            self.assertFalse(repair.repair_native_wslpe_stage1(
                self.manager, confirmed=True))
        self.provider._ensure_vmware_tools.assert_not_called()

    def test_missing_vmware_registration_blocks_without_provisioning(self):
        with self.patches(), patch.object(
            repair, "inspect_vmware_guest", return_value=False,
        ):
            self.assertFalse(repair.repair_native_wslpe_stage1(
                self.manager, confirmed=True))
        self.provider._run_vagrant_bounded.assert_not_called()

    def test_tools_failure_blocks_vagrant_replay_and_status(self):
        self.provider._ensure_vmware_tools.return_value = False
        with self.patches():
            self.assertFalse(repair.repair_native_wslpe_stage1(
                self.manager, confirmed=True))
        self.provider._run_vagrant_bounded.assert_not_called()
        self.instance.set_status.assert_not_called()

    def test_unhealthy_service_blocks_vagrant_replay(self):
        self.provider._guest_tools_healthy.return_value = False
        with self.patches():
            self.assertFalse(repair.repair_native_wslpe_stage1(
                self.manager, confirmed=True))
        self.provider._run_vagrant_bounded.assert_not_called()

    def test_vagrant_failure_does_not_retry_or_mark_provided(self):
        self.provider._run_vagrant_bounded.return_value = False
        with self.patches():
            self.assertFalse(repair.repair_native_wslpe_stage1(
                self.manager, confirmed=True))
        self.provider._run_vagrant_bounded.assert_called_once()
        self.instance.set_status.assert_not_called()

    def test_missing_exercise_ip_does_not_mark_provided(self):
        def run_ps(script):
            return SimpleNamespace(
                status_code=0, std_out=b"WSLPE_STAGE1_WINDOWS_NAT=PASS\n")
        self.provider._winrm_session.return_value.run_ps = run_ps
        with self.patches():
            self.assertFalse(repair.repair_native_wslpe_stage1(
                self.manager, confirmed=True))
        self.provider._run_vagrant_bounded.assert_called_once()
        self.instance.set_status.assert_not_called()


if __name__ == "__main__":
    unittest.main()
