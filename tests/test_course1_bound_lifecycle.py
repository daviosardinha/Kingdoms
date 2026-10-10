"""Instance-bound lifecycle planning and fail-closed controller contracts."""
import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from goad.course1_bound_lifecycle import plan_bound_instance
from goad.course1_runtime_contract import FULL, ProfileNotReady

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "ad/GOAD/providers/vmware/Vagrantfile").read_text(encoding="utf-8")


class BoundKingdomsLifecycleTests(unittest.TestCase):
    def fake(self, content=SOURCE, manifest=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name)
        (path / "Vagrantfile").write_text(content, encoding="utf-8")
        if manifest is not None:
            (path / ".kingdoms-profile.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
        return path

    def test_installed_six_guest_start_matches_dependency_closure(self):
        p = self.fake()
        plan = plan_bound_instance(p, "start", "GOAD-WS01")
        self.assertEqual(plan.profile, FULL.name)
        self.assertEqual(plan.phases[1].machines,
                         ("GOAD-DC01", "GOAD-DC02", "GOAD-WS01"))
        self.assertEqual(dict(plan.management_hosts)["GOAD-WS01"], "10.4.10.31")

    def test_reference_shutdown_order_preserved(self):
        plan = plan_bound_instance(self.fake(), "stop")
        self.assertEqual(plan.phases[0].machines, tuple(reversed(FULL.windows)))
        self.assertEqual(plan.phases[1].machines, ("GOAD-ROUTER",))

    def test_reference_snapshot_scope_includes_all_reference_guests(self):
        plan = plan_bound_instance(self.fake(), "reset")
        self.assertEqual(plan.phases[0].machines, ("GOAD-ROUTER",) + FULL.windows)

    def test_course1_four_guest_vagrantfile_rejected(self):
        text = SOURCE.replace(':name => "GOAD-DC03"', ':name => "DISABLED-DC03"')
        text = text.replace(':name => "GOAD-SRV03"', ':name => "DISABLED-SRV03"')
        with self.assertRaises(ProfileNotReady):
            plan_bound_instance(self.fake(text), "start")

    def test_preview_marker_rejected_even_with_full_roster(self):
        marker = {"profile": "course1-fall-of-the-north",
                  "state": "PREVIEW_ONLY_NOT_INSTALLABLE",
                  "windows_machines": ["GOAD-DC01", "GOAD-DC02",
                                       "GOAD-SRV02", "GOAD-WS01"]}
        with self.assertRaises(ProfileNotReady):
            plan_bound_instance(self.fake(manifest=marker), "start")

    def test_invalid_machine_and_action_blocked(self):
        path = self.fake()
        with self.assertRaises(ProfileNotReady):
            plan_bound_instance(path, "start", "GOAD-DC99")
        with self.assertRaises(ProfileNotReady):
            plan_bound_instance(path, "destroy")

    def test_missing_provider_rejected_without_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ProfileNotReady):
                plan_bound_instance(Path(temp), "start")
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_native_north_provider_has_four_guest_bound_plan_only(self):
        import shutil
        from goad.instance import LabInstance
        from goad.utils import VMWARE, PROVISIONING_LOCAL
        from goad.kingdoms_vmware_profile import north_binding
        with tempfile.TemporaryDirectory(prefix="kingdoms-north-bound-") as temp:
            root = Path(temp)
            (root / "provider").mkdir()
            inst = object.__new__(LabInstance)
            inst.lab_name = "NORTH"
            inst.provider_name = VMWARE
            inst.provisioner_name = PROVISIONING_LOCAL
            inst.ip_range = "10.41.10"
            inst.instance_path = str(root)
            inst.instance_provider_path = str(root / "provider")
            inst.extensions = []
            inst._create_vagrantfile()
            inst._stage_north_vmware_assets()
            shutil.copyfile(ROOT / "ad/NORTH/providers/vmware/inventory", root / "inventory")
            shutil.copyfile(ROOT / "ad/NORTH/data/inventory_disable_vagrant",
                            root / "inventory_disable_vagrant")
            plan = plan_bound_instance(root / "provider", "start", "GOAD-WS01", lab_name="NORTH")
            self.assertEqual(plan.phases[1].machines,
                             ("GOAD-DC01", "GOAD-DC02", "GOAD-WS01"))
            self.assertEqual(dict(plan.management_hosts)["GOAD-WS01"], "10.41.10.31")
            self.assertEqual(plan.execution, "BLOCKED_STATIC_PLAN_ONLY")
            stopped = plan_bound_instance(root / "provider", "stop", lab_name="NORTH")
            self.assertEqual(set(stopped.phases[0].machines),
                             set(north_binding().roster.windows))
            self.assertNotIn("GOAD-SRV03", stopped.phases[0].machines)
            proc = subprocess.run(
                [sys.executable, "-m", "goad.course1_bound_lifecycle",
                 "--check-provider", str(root / "provider"),
                 "--lab", "NORTH", "--action", "start", "--machine", "GOAD-WS01"],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = json.loads(proc.stdout)
            self.assertEqual(result["binding"], "VERIFIED_NORTH_SOURCE_ONLY")
            self.assertEqual(result["activation"], "NOT_AUTHORIZED_BY_THIS_CHECK")

    def test_north_binding_refuses_reference_provider_and_untrusted_lab(self):
        with self.assertRaises(ProfileNotReady):
            plan_bound_instance(self.fake(), "start", lab_name="NORTH")
        with self.assertRaises(ProfileNotReady):
            plan_bound_instance(self.fake(), "start", lab_name="ESSOS")

    def test_cli_only_plans_and_cannot_activate(self):
        provider = self.fake()
        original = (provider / "Vagrantfile").read_bytes()
        command = [sys.executable, "-m", "goad.course1_bound_lifecycle",
                   "--check-provider", str(provider), "--action", "exercise"]
        proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["binding"], "VERIFIED_REFERENCE_INSTANCE")
        self.assertEqual(result["activation"], "NOT_AUTHORIZED_BY_THIS_CHECK")
        self.assertEqual(result["execution"], "BLOCKED_STATIC_PLAN_ONLY")
        self.assertEqual(original, (provider / "Vagrantfile").read_bytes())

    def test_provider_preflights_before_router_or_vm_mutations(self):
        text = (ROOT / "goad/provider/vagrant/vmware_kingdoms.py").read_text(encoding="utf-8")
        start = text.split("    def _start_existing_instance(", 1)[1].split(
            "    def _bring_up_router(", 1
        )[0]
        self.assertLess(start.index('start_plan = self._validated_kingdoms_legacy_plan("start", vm_name)'),
                        start.index("if not self._sync_goad_nomad_inventories():"))
        self.assertIn("start_order = list(start_plan.phases[1].machines)", start)
        stop = text.split("    def stop(self):", 1)[1].split(
            "    def _restore_exercise_nic_contract_offline(", 1
        )[0]
        self.assertLess(stop.index('stop_plan = self._validated_kingdoms_legacy_plan("stop")'),
                        stop.index("running = self._running_instance_vms()"))
        self.assertIn("for machine in stop_plan.phases[0].machines:", stop)
        reset = text.split("    def reset(self):", 1)[1].split("    def install(self):", 1)[0]
        self.assertLess(reset.index('self._validated_kingdoms_legacy_plan("reset")'),
                        reset.index("['snapshot', 'pop', '--no-delete', '--no-start']"))
        self.assertIn("reduced lifecycle activation is not yet approved", text)

    @staticmethod
    def north_reset_harness():
        """Execute the actual provider reset method without importing WinRM/VMware.

        The offline source suite intentionally uses system Python; the full
        provider imports pywinrm, a runtime-only dependency. Extract only the
        committed method AST and execute it with mocked I/O boundaries.
        """
        source = ROOT / "goad/provider/vagrant/vmware_kingdoms.py"
        module = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        provider_class = next(
            node for node in module.body
            if isinstance(node, ast.ClassDef) and node.name == "GoadKingdomsVmwareProvider"
        )
        reset = next(
            node for node in provider_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "reset"
        )
        provider_class.body = [reset]
        provider_class.bases = [ast.Name(id="object", ctx=ast.Load())]
        provider_class.keywords = []
        provider_class.decorator_list = []
        module.body = [provider_class]
        scope = {"Log": Mock()}
        exec(compile(ast.fix_missing_locations(module), str(source), "exec"), scope)
        provider = scope["GoadKingdomsVmwareProvider"]()
        provider.lab_name = "NORTH"
        provider._north_runtime_allowed = Mock(return_value=True)
        provider._require_full_goad_instance_binding = Mock(return_value=True)
        provider._verify_north_instance_sources = Mock(return_value=True)
        provider._validated_kingdoms_legacy_plan = Mock(return_value=object())
        provider._run_vagrant_bounded = Mock(return_value=True)
        provider.get_runtime_mode = Mock(return_value="exercise")
        provider._running_instance_vms = Mock(return_value=[])
        provider._restore_exercise_nic_contract_offline = Mock(return_value=True)
        return provider

    def test_north_reset_refuses_bad_instance_before_snapshot_mutation(self):
        provider = self.north_reset_harness()
        provider._verify_north_instance_sources.return_value = False
        self.assertFalse(provider.reset())
        provider._run_vagrant_bounded.assert_not_called()
        provider._running_instance_vms.assert_not_called()

    def test_north_reset_uses_hardened_snapshot_and_exercise_isolation(self):
        provider = self.north_reset_harness()
        self.assertTrue(provider.reset())
        provider._run_vagrant_bounded.assert_called_once_with(
            ["snapshot", "pop", "--no-delete", "--no-start"], timeout=900
        )
        provider._running_instance_vms.assert_called_once()
        provider._restore_exercise_nic_contract_offline.assert_called_once()

    @staticmethod
    def north_pre_guest_harness():
        """Run committed NORTH pre-guest methods without requiring pywinrm."""
        source = ROOT / "goad/provider/vagrant/vmware_kingdoms.py"
        module = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        provider_class = next(
            node for node in module.body
            if isinstance(node, ast.ClassDef) and node.name == "GoadKingdomsVmwareProvider"
        )
        provider_class.body = [
            node for node in provider_class.body
            if isinstance(node, ast.FunctionDef) and node.name in (
                "_prepare_north_pre_guest_network",
                "_rollback_north_pre_guest_bootstrap",
            )
        ]
        if len(provider_class.body) != 2:
            raise AssertionError("NORTH bootstrap methods are missing")
        provider_class.bases = [ast.Name(id="object", ctx=ast.Load())]
        provider_class.keywords = []
        provider_class.decorator_list = []
        module.body = [provider_class]
        scope = {"Log": Mock(), "subprocess": Mock()}
        exec(compile(ast.fix_missing_locations(module), str(source), "exec"), scope)
        provider = scope["GoadKingdomsVmwareProvider"]()
        provider.lab_name = "NORTH"
        provider._north_runtime_allowed = Mock(return_value=True)
        provider._verify_north_instance_sources = Mock(return_value=True)
        provider._apply_router_policy = Mock(return_value=True)
        provider._enable_provisioning_routes = Mock(return_value=True)
        provider._script = Mock(return_value="/tmp/isolated-north-helper")
        scope["subprocess"].run.return_value.returncode = 0
        return provider, scope["subprocess"]

    def test_north_install_prepares_routes_before_first_windows_vagrant_up(self):
        source = (ROOT / "goad/provider/vagrant/vmware_kingdoms.py").read_text()
        install = source.split("    def install(self):", 1)[1].split(
            "    def _ensure_installed_member_time_policy(", 1
        )[0]
        router = install.index("if not self._bring_up_router():")
        north_routes = install.index(
            "if self.lab_name == 'NORTH' and not self._prepare_north_pre_guest_network():"
        )
        first_windows = install.index("for machine in self.goad_nomad_windows:")
        self.assertLess(router, north_routes)
        self.assertLess(north_routes, first_windows)

    def test_north_pre_guest_routes_follow_router_policy_and_check_binding(self):
        provider, subprocess_mock = self.north_pre_guest_harness()
        sequence = Mock()
        sequence.attach_mock(provider._apply_router_policy, "policy")
        sequence.attach_mock(provider._enable_provisioning_routes, "routes")
        self.assertTrue(provider._prepare_north_pre_guest_network())
        self.assertEqual(sequence.mock_calls, [
            call.policy("provisioning"), call.routes(),
        ])
        provider._north_runtime_allowed.assert_called_once()
        provider._verify_north_instance_sources.assert_called_once()
        subprocess_mock.run.assert_not_called()

    def test_north_pre_guest_fails_closed_if_route_enable_fails(self):
        provider, subprocess_mock = self.north_pre_guest_harness()
        provider._enable_provisioning_routes.return_value = False
        self.assertFalse(provider._prepare_north_pre_guest_network())
        self.assertEqual(provider._apply_router_policy.call_args_list, [
            call("provisioning"), call("exercise"),
        ])
        subprocess_mock.run.assert_called_once_with(
            ["sudo", "-n", "bash", "/tmp/isolated-north-helper", "disable"],
            check=False, timeout=30,
        )

    def test_north_pre_guest_fails_closed_if_router_policy_fails(self):
        provider, subprocess_mock = self.north_pre_guest_harness()
        provider._apply_router_policy.side_effect = [False, True]
        self.assertFalse(provider._prepare_north_pre_guest_network())
        provider._enable_provisioning_routes.assert_not_called()
        subprocess_mock.run.assert_called_once()

    def test_north_rollback_reports_incomplete_cleanup(self):
        provider, subprocess_mock = self.north_pre_guest_harness()
        subprocess_mock.run.return_value.returncode = 1
        self.assertFalse(provider._rollback_north_pre_guest_bootstrap())
        provider._apply_router_policy.assert_called_once_with("exercise")

    def test_go_references_do_not_enter_north_pre_guest_bootstrap(self):
        provider, subprocess_mock = self.north_pre_guest_harness()
        provider.lab_name = "GOAD"
        self.assertTrue(provider._prepare_north_pre_guest_network())
        provider._north_runtime_allowed.assert_not_called()
        provider._verify_north_instance_sources.assert_not_called()
        provider._apply_router_policy.assert_not_called()
        provider._enable_provisioning_routes.assert_not_called()
        subprocess_mock.run.assert_not_called()

    @staticmethod
    def north_first_router_harness():
        """Exercise real provider first-router boot path with no live VMware."""
        source = ROOT / "goad/provider/vagrant/vmware_kingdoms.py"
        module = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        provider_class = next(
            node for node in module.body
            if isinstance(node, ast.ClassDef) and node.name == "GoadKingdomsVmwareProvider"
        )
        router = next(
            node for node in provider_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "_bring_up_router"
        )
        provider_class.body = [router]
        provider_class.bases = [ast.Name(id="object", ctx=ast.Load())]
        provider_class.keywords = []
        provider_class.decorator_list = []
        module.body = [provider_class]
        process = Mock()
        process.run.return_value.returncode = 0
        clock = SimpleNamespace(monotonic=Mock(side_effect=[0, 0]), sleep=Mock())
        scope = {"Log": Mock(), "subprocess": process, "time": clock,
                 "os": __import__("os")}
        exec(compile(ast.fix_missing_locations(module), str(source), "exec"), scope)
        provider = scope["GoadKingdomsVmwareProvider"]()
        provider.lab_name = "NORTH"
        provider.get_runtime_mode = Mock(return_value="unknown")
        provider.command = Mock()
        provider.command.run_vagrant.return_value = True
        provider.path = "/tmp/c1-isolated/provider"
        provider._vmx_path = Mock(return_value="/tmp/c1-isolated/router.vmx")
        provider._running_instance_vms = Mock(return_value=["GOAD-ROUTER"])
        provider._script = Mock(side_effect=lambda x: "/tmp/isolated_" + x.replace("/", "_"))
        provider._provider_env = Mock(return_value={"KINGDOMS_VMWARE_LAB": "NORTH"})
        provider.kingdoms_vmware_binding = SimpleNamespace(router_management="10.41.99.1")
        return provider, process

    def test_north_first_router_boot_rechecks_hostaddrs_and_router_ssh(self):
        provider, process = self.north_first_router_harness()
        self.assertTrue(provider._bring_up_router())
        provider.command.run_vagrant.assert_called_once_with(
            ["up", "GOAD-ROUTER"], provider.path
        )
        calls = [args.args[0] for args in process.run.call_args_list]
        self.assertEqual(calls[0], [
            "sudo", "-n", "systemctl", "restart",
            "kingdoms-north-vmnet-hostaddrs.service",
        ])
        self.assertEqual(calls[1], [
            "bash", "/tmp/isolated_course1_kingdoms-north-vmnet-hostaddrs", "status",
        ])
        # The provider passes the logical helper name to _script();
        # production maps it to the NORTH-specific course1 helper. Our mock
        # deliberately exposes that logical name rather than resolving paths.
        provider._script.assert_any_call("router-ssh.sh")
        self.assertEqual(calls[2][0:2], [
            "bash", "/tmp/isolated_router-ssh.sh",
        ])
        self.assertEqual(len(calls), 3)
        self.assertFalse(any(args and args[0] == "vmrun" for args in calls))

    def test_north_first_router_failure_never_reaches_host_mutation(self):
        provider, process = self.north_first_router_harness()
        provider.command.run_vagrant.return_value = False
        self.assertFalse(provider._bring_up_router())
        process.run.assert_not_called()
        provider._running_instance_vms.assert_not_called()

    def test_north_first_router_host_repair_failure_blocks_winrm_boot(self):
        provider, process = self.north_first_router_harness()
        process.run.return_value.returncode = 1
        self.assertFalse(provider._bring_up_router())
        self.assertEqual(process.run.call_count, 1)
        self.assertEqual(
            process.run.call_args.args[0][-1],
            "kingdoms-north-vmnet-hostaddrs.service",
        )

    def test_north_installed_router_does_not_reenter_vagrant(self):
        provider, process = self.north_first_router_harness()
        provider.get_runtime_mode.return_value = "exercise"
        self.assertTrue(provider._bring_up_router())
        provider.command.run_vagrant.assert_not_called()
        self.assertEqual(process.run.call_count, 3)

    def test_reference_fresh_router_boot_remains_legacy_vagrant_only(self):
        provider, process = self.north_first_router_harness()
        provider.lab_name = "GOAD"
        self.assertTrue(provider._bring_up_router())
        provider.command.run_vagrant.assert_called_once_with(
            ["up", "GOAD-ROUTER"], provider.path
        )
        process.run.assert_not_called()
        provider._running_instance_vms.assert_not_called()

    @staticmethod
    def north_pilot_mutation_guard_harness():
        """Execute the committed direct-call guard without pywinrm imports."""
        source = ROOT / "goad/provider/vagrant/vmware_kingdoms.py"
        module = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        cls = next(node for node in module.body
                   if isinstance(node, ast.ClassDef)
                   and node.name == "GoadKingdomsVmwareProvider")
        method = next(node for node in cls.body
                      if isinstance(node, ast.FunctionDef)
                      and node.name == "_north_runtime_allowed")
        cls.body = [method]
        cls.bases = [ast.Name(id="object", ctx=ast.Load())]
        cls.keywords = []
        cls.decorator_list = []
        module.body = [cls]
        scope = {"Log": Mock()}
        exec(compile(ast.fix_missing_locations(module), str(source), "exec"), scope)
        provider = scope["GoadKingdomsVmwareProvider"]()
        provider.lab_name = "NORTH"
        provider.path = "/tmp/disposable-north/provider"
        provider.kingdoms_vmware_binding = SimpleNamespace(segmented_install_enabled=True)
        provider._verify_north_instance_sources = Mock(return_value=True)
        provider._check_segmented_instance_conflicts = Mock(return_value=True)
        return provider

    def test_north_pilot_direct_provider_requires_bound_source_and_collision_survey(self):
        provider = self.north_pilot_mutation_guard_harness()
        self.assertTrue(provider._north_runtime_allowed())
        provider._verify_north_instance_sources.assert_called_once()
        provider._check_segmented_instance_conflicts.assert_called_once()
        provider.path = None
        provider._verify_north_instance_sources.reset_mock()
        provider._check_segmented_instance_conflicts.reset_mock()
        self.assertFalse(provider._north_runtime_allowed())
        provider._verify_north_instance_sources.assert_not_called()
        provider._check_segmented_instance_conflicts.assert_not_called()

    def test_north_pilot_direct_provider_rejects_drift_and_collision(self):
        provider = self.north_pilot_mutation_guard_harness()
        provider._verify_north_instance_sources.return_value = False
        self.assertFalse(provider._north_runtime_allowed())
        provider._check_segmented_instance_conflicts.assert_not_called()
        provider._verify_north_instance_sources.return_value = True
        provider._check_segmented_instance_conflicts.return_value = False
        self.assertFalse(provider._north_runtime_allowed())
        provider.kingdoms_vmware_binding.segmented_install_enabled = False
        provider._verify_north_instance_sources.reset_mock()
        provider._check_segmented_instance_conflicts.reset_mock()
        self.assertFalse(provider._north_runtime_allowed())
        provider._verify_north_instance_sources.assert_not_called()
        provider._check_segmented_instance_conflicts.assert_not_called()

    @staticmethod
    def north_first_install_harness():
        """Exercise actual install control flow with all VMware I/O mocked."""
        source = ROOT / "goad/provider/vagrant/vmware_kingdoms.py"
        module = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        cls = next(node for node in module.body
                   if isinstance(node, ast.ClassDef)
                   and node.name == "GoadKingdomsVmwareProvider")
        method = next(node for node in cls.body
                      if isinstance(node, ast.FunctionDef) and node.name == "install")
        cls.body = [method]
        cls.bases = [ast.Name(id="object", ctx=ast.Load())]
        cls.keywords = []
        cls.decorator_list = []
        module.body = [cls]
        process = Mock()
        process.run.return_value.returncode = 0
        os_stub = SimpleNamespace(path=SimpleNamespace(isfile=lambda p: True))
        scope = {"Log": Mock(), "subprocess": process, "os": os_stub}
        exec(compile(ast.fix_missing_locations(module), str(source), "exec"), scope)
        provider = scope["GoadKingdomsVmwareProvider"]()
        provider.lab_name = "NORTH"
        provider.path = "/tmp/pilot-north/provider"
        provider.command = Mock()
        provider.command.run_vagrant.return_value = True
        provider.goad_nomad_windows = ["GOAD-DC01"]
        for attr in (
            "_north_runtime_allowed", "prepare_install",
            "_sync_goad_nomad_inventories", "_sync_goad_nomad_vagrantfile_compatibility",
            "_bring_up_router", "_prepare_north_pre_guest_network", "_ensure_vmware_tools",
            "_authenticated_guest_recovery_ready", "_recover_failed_windows_vagrant_up",
            "_rollback_north_pre_guest_bootstrap",
        ):
            setattr(provider, attr, Mock(return_value=True))
        provider._script = Mock(return_value="/tmp/course1-route-helper")
        return provider, process

    def test_failed_north_windows_first_boot_rolls_back_routes(self):
        provider, process = self.north_first_install_harness()
        provider._ensure_vmware_tools.return_value = False
        provider._authenticated_guest_recovery_ready.return_value = False
        self.assertFalse(provider.install())
        provider._rollback_north_pre_guest_bootstrap.assert_called_once()
        process.run.assert_not_called()

    def test_successful_north_handoff_preserves_routes_for_ansible(self):
        provider, process = self.north_first_install_harness()
        self.assertTrue(provider.install())
        provider._prepare_north_pre_guest_network.assert_called_once()
        provider._rollback_north_pre_guest_bootstrap.assert_not_called()
        process.run.assert_called_once()

    def test_reference_failed_install_does_not_run_north_rollback(self):
        provider, process = self.north_first_install_harness()
        provider.lab_name = "GOAD"
        provider._ensure_vmware_tools.return_value = False
        provider._authenticated_guest_recovery_ready.return_value = False
        self.assertFalse(provider.install())
        provider._prepare_north_pre_guest_network.assert_not_called()
        provider._rollback_north_pre_guest_bootstrap.assert_not_called()

    @staticmethod
    def north_ansible_first_boot_harness():
        """Compile real Ansible handoff and provider guard without pywinrm."""
        ansible_path = ROOT / "goad/provisioner/ansible/ansible.py"
        ansible_ast = ast.parse(
            ansible_path.read_text(encoding="utf-8"), filename=str(ansible_path)
        )
        ansible_class = next(
            node for node in ansible_ast.body
            if isinstance(node, ast.ClassDef) and node.name == "Ansible"
        )
        methods = [
            node for node in ansible_class.body
            if isinstance(node, ast.FunctionDef) and node.name in (
                "_kingdoms_install_profile", "run"
            )
        ]
        if len(methods) != 2:
            raise AssertionError("Real Ansible profile selector or run method missing")
        provider_path = ROOT / "goad/provider/vagrant/vmware_kingdoms.py"
        provider_ast = ast.parse(
            provider_path.read_text(encoding="utf-8"), filename=str(provider_path)
        )
        provider_class = next(
            node for node in provider_ast.body
            if isinstance(node, ast.ClassDef)
            and node.name == "GoadKingdomsVmwareProvider"
        )
        bootstrap = next(
            node for node in provider_class.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_fresh_install_bootstrap_pending"
        )
        scope = {"time": __import__("time"), "Log": Mock()}
        code = ast.Module(body=methods + [bootstrap], type_ignores=[])
        exec(compile(ast.fix_missing_locations(code), str(ansible_path), "exec"), scope)
        profile = {
            "instance_id": "disposable-north", "provider_success": True,
            "status": "awaiting_ansible", "ansible_phases": [],
            "started": 0, "_path": "/tmp/unwritten-install-timing.json",
        }
        provider = SimpleNamespace(
            _kingdoms_install_profile=profile,
            _north_runtime_allowed=Mock(return_value=True),
            is_goad_nomad_segmented=Mock(return_value=True),
            get_runtime_mode=Mock(return_value="unknown"),
            _save_install_profile=Mock(return_value=True),
        )
        from types import MethodType
        provider._fresh_install_bootstrap_pending = MethodType(
            scope["_fresh_install_bootstrap_pending"], provider,
        )
        controller = SimpleNamespace(
            lab_name="NORTH", provider=provider,
            instance_path="/tmp/disposable-north",
            _active_install_profile=None,
            _save_install_profile=provider._save_install_profile,
            _emit_kingdoms_install_timing=Mock(),
        )
        controller._kingdoms_install_profile = MethodType(
            scope["_kingdoms_install_profile"], controller,
        )
        controller._run = Mock(
            side_effect=lambda playbook, install_profile:
                provider._fresh_install_bootstrap_pending()
        )
        controller.run = MethodType(scope["run"], controller)
        return controller, provider, profile

    def test_north_fresh_install_handoff_enters_pre_ad_bootstrap_before_playbooks(self):
        from goad.course_catalog import NORTH_PILOT_ENV, NORTH_PILOT_ID
        controller, provider, profile = self.north_ansible_first_boot_harness()
        with patch.dict(os.environ, {NORTH_PILOT_ENV: NORTH_PILOT_ID}):
            self.assertTrue(controller.run())
        controller._run.assert_called_once()
        self.assertEqual(controller._run.call_args.args[1], profile)
        self.assertEqual(profile["status"], "completed")
        provider._north_runtime_allowed.assert_called_once()

    def test_north_fresh_handoff_rejects_wrong_instance_and_missing_approval(self):
        from goad.course_catalog import NORTH_PILOT_ENV, NORTH_PILOT_ID
        controller, provider, profile = self.north_ansible_first_boot_harness()
        with patch.dict(os.environ, {NORTH_PILOT_ENV: "invalid"}):
            self.assertIsNone(controller._kingdoms_install_profile())
        with patch.dict(os.environ, {NORTH_PILOT_ENV: NORTH_PILOT_ID}):
            profile["instance_id"] = "other-instance"
            self.assertIsNone(controller._kingdoms_install_profile())
            profile["instance_id"] = "disposable-north"
            profile["provider_success"] = False
            self.assertIsNone(controller._kingdoms_install_profile())
            profile["provider_success"] = True
            self.assertIs(controller._kingdoms_install_profile(), profile)
            provider.get_runtime_mode.return_value = "provisioning"
            profile["status"] = "ansible_running"
            self.assertFalse(provider._fresh_install_bootstrap_pending())

    def test_reference_install_profile_selection_still_accepts_goad(self):
        controller, provider, profile = self.north_ansible_first_boot_harness()
        controller.lab_name = "GOAD"
        profile["instance_id"] = "reference-instance"
        self.assertIs(controller._kingdoms_install_profile(), profile)
        provider._north_runtime_allowed.assert_not_called()

    def test_provider_planner_checks_legacy_hosts_and_roster(self):
        src = (ROOT / "goad/provider/vagrant/vmware_kingdoms.py").read_text(encoding="utf-8")
        method = src.split("    def _validated_kingdoms_legacy_plan(", 1)[1].split(
            "    def start_vm(", 1
        )[0]
        self.assertIn("tuple(self.goad_nomad_windows) != FULL.windows", method)
        self.assertIn("dict(self.management_hosts) != dict(FULL.management_hosts)", method)
        self.assertIn("plan_bound_instance(self.path, action, machine)", method)


if __name__ == "__main__":
    unittest.main()
