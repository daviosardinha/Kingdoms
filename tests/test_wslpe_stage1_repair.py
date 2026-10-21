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
        machine = (
            self.provider_dir / ".vagrant" / "machines" / "WSLPE-WS01"
            / "vmware_desktop"
        )
        self.vmx = machine / "native-uuid" / "windows_10.vmx"
        self.vmx.parent.mkdir(parents=True)
        self.vmx.write_text(
            'ethernet0.connectionType = "nat"\n'
            'ethernet0.generatedAddress = "00:0C:29:2F:D7:5B"\n',
            encoding="utf-8",
        )
        (machine / "id").write_text(str(self.vmx), encoding="utf-8")
        self.provider = SimpleNamespace(
            lab_name="WSLPE", path=str(self.provider_dir),
            _vmx_path=Mock(return_value=str(self.vmx)),
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
        stack.enter_context(patch.object(
            repair, "_ensure_registered_guest_running", return_value=True))
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
        self.assertEqual(len(self.scripts), 3)
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
            repair, "_ensure_registered_guest_running", return_value=False,
        ):
            self.assertFalse(repair.repair_native_wslpe_stage1(
                self.manager, confirmed=True))
        self.provider._run_vagrant_bounded.assert_not_called()

    def test_powered_off_existing_guest_starts_once_from_exact_registration(self):
        self.assertEqual(repair._registered_guest_vmx(self.provider), self.vmx)
        calls = []
        def command(argv, **kwargs):
            calls.append(argv)
            if argv == ["vmrun", "-T", "ws", "list"]:
                return SimpleNamespace(returncode=0, stdout="Total running VMs: 0\n")
            if argv == ["vagrant", "status", "WSLPE-WS01"]:
                return SimpleNamespace(
                    returncode=0, stdout="WSLPE-WS01   not running (vmware_desktop)\n")
            if argv == ["vmrun", "-T", "ws", "start", str(self.vmx), "nogui"]:
                return SimpleNamespace(returncode=0, stdout="")
            raise AssertionError("unexpected mutation/read: " + str(argv))

        with patch.object(repair.subprocess, "run", side_effect=command), patch.object(
            repair, "inspect_vmware_guest", return_value=True
        ) as inspect:
            self.assertTrue(repair._ensure_registered_guest_running(self.provider))
        self.assertEqual(calls, [
            ["vmrun", "-T", "ws", "list"],
            ["vagrant", "status", "WSLPE-WS01"],
            ["vmrun", "-T", "ws", "list"],
            ["vmrun", "-T", "ws", "start", str(self.vmx), "nogui"],
        ])
        inspect.assert_called_once_with(self.provider)

    def test_running_registered_guest_does_not_start_again(self):
        self.assertEqual(repair._registered_guest_vmx(self.provider), self.vmx)
        with patch.object(repair.subprocess, "run", return_value=SimpleNamespace(
            returncode=0, stdout=f"Total running VMs: 1\n{self.vmx}\n",
        )) as runner, patch.object(repair, "inspect_vmware_guest", return_value=True):
            self.assertTrue(repair._ensure_registered_guest_running(self.provider))
        runner.assert_called_once_with(
            ["vmrun", "-T", "ws", "list"], capture_output=True,
            text=True, check=False, timeout=30,
        )

    def test_vagrant_uncertain_or_not_created_refuses_start(self):
        for state in ("not created", "saved", "aborted", "running"):
            with self.subTest(state=state):
                def command(argv, **kwargs):
                    if argv == ["vmrun", "-T", "ws", "list"]:
                        return SimpleNamespace(
                            returncode=0, stdout="Total running VMs: 0\n")
                    if argv == ["vagrant", "status", "WSLPE-WS01"]:
                        return SimpleNamespace(
                            returncode=0, stdout=f"WSLPE-WS01 {state} (vmware_desktop)\n")
                    raise AssertionError("must not start an unknown guest")
                with patch.object(repair.subprocess, "run", side_effect=command):
                    self.assertFalse(repair._ensure_registered_guest_running(self.provider))

    def test_vagrant_failure_and_changed_inventory_refuse_start(self):
        responses = [
            SimpleNamespace(returncode=0, stdout="Total running VMs: 0\n"),
            SimpleNamespace(
                returncode=0, stdout="WSLPE-WS01 not running (vmware_desktop)\n"),
            SimpleNamespace(returncode=0, stdout="Total running VMs: 1\n/tmp/other.vmx\n"),
        ]
        with patch.object(repair.subprocess, "run", side_effect=responses) as runner:
            self.assertFalse(repair._ensure_registered_guest_running(self.provider))
        self.assertEqual(runner.call_count, 3)

    def test_foreign_or_symlinked_registration_never_starts_guest(self):
        registration = (
            self.provider_dir / ".vagrant" / "machines" / "WSLPE-WS01"
            / "vmware_desktop" / "id"
        )
        original = registration.read_text()
        registration.write_text(str(self.provider_dir / "foreign.vmx"))
        with patch.object(repair.subprocess, "run", side_effect=AssertionError(
            "vmrun must not be called on a foreign VMX"
        )):
            self.assertIsNone(repair._registered_guest_vmx(self.provider))
        registration.write_text(original)
        registration.unlink()
        registration.symlink_to(self.vmx)
        self.assertIsNone(repair._registered_guest_vmx(self.provider))

    def test_failed_vmrun_start_is_never_retried(self):
        def command(argv, **kwargs):
            if argv == ["vmrun", "-T", "ws", "list"]:
                return SimpleNamespace(returncode=0, stdout="Total running VMs: 0\n")
            if argv == ["vagrant", "status", "WSLPE-WS01"]:
                return SimpleNamespace(
                    returncode=0, stdout="WSLPE-WS01 not running (vmware_desktop)\n")
            if argv[:4] == ["vmrun", "-T", "ws", "start"]:
                return SimpleNamespace(returncode=1, stdout="", stderr="powered off")
            raise AssertionError("unexpected operation")
        with patch.object(repair.subprocess, "run", side_effect=command) as run:
            self.assertFalse(repair._ensure_registered_guest_running(self.provider))
        self.assertEqual(sum(argv[0][3] == "start" for argv in run.call_args_list), 1)

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

    def test_registration_mac_must_be_known_before_any_tools_change(self):
        self.provider._vmx_path.return_value = str(self.provider_dir / "unknown.vmx")
        with self.patches():
            self.assertFalse(repair.repair_native_wslpe_stage1(
                self.manager, confirmed=True))
        self.provider._ensure_vmware_tools.assert_not_called()
        self.provider._run_vagrant_bounded.assert_not_called()

    def test_proof_binds_windows_default_route_adapter_to_registered_vmx_mac(self):
        with self.patches():
            self.assertTrue(repair.repair_native_wslpe_stage1(
                self.manager, confirmed=True))
        self.assertTrue(all("000C292FD75B" in script for script in self.scripts))
        self.assertTrue(all("WSLPE_STAGE1_WRONG_NATIVE_NAT_ADAPTER" in script
                            for script in self.scripts))

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
