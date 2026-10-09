"""Instance-bound lifecycle planning and fail-closed controller contracts."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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
