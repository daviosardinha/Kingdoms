"""Instance-bound lifecycle planning and fail-closed controller contracts."""
import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

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
