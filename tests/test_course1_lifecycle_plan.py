"""Offline lifecycle planning contracts; no VMware or installed-VM interaction."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

from goad.course1_lifecycle_plan import plan_lifecycle
from goad.course1_runtime_contract import COURSE1, FULL, ROUTER, ProfileNotReady, RuntimeRoster

ROOT = Path(__file__).resolve().parents[1]


def phases(plan):
    return [(phase.name, phase.machines) for phase in plan.phases]


class Course1LifecyclePlanningTests(unittest.TestCase):
    def test_full_start_matches_existing_six_vm_dependency_plan(self):
        plan = plan_lifecycle(FULL, "start")
        self.assertEqual(phases(plan), [
            ("router-management-ready", (ROUTER,)),
            ("interleaved-windows-start-and-ad-readiness", FULL.start_order),
        ])
        self.assertEqual(len(plan.management_hosts), 6)
        self.assertEqual(plan.execution, "BLOCKED_STATIC_PLAN_ONLY")

    def test_course1_start_exact_four(self):
        plan = plan_lifecycle(COURSE1, "start")
        self.assertEqual(phases(plan)[1][1], COURSE1.windows)
        self.assertEqual(set(dict(plan.management_hosts)), set(COURSE1.windows))
        self.assertNotIn("GOAD-DC03", str(plan.as_dict()))
        self.assertNotIn("GOAD-SRV03", str(plan.as_dict()))

    def test_target_start_requires_parent_and_child_before_workstation(self):
        plan = plan_lifecycle(COURSE1, "start", "GOAD-WS01")
        self.assertEqual(phases(plan)[1][1],
                         ("GOAD-DC01", "GOAD-DC02", "GOAD-WS01"))
        self.assertEqual(set(dict(plan.management_hosts)),
                         {"GOAD-DC01", "GOAD-DC02", "GOAD-WS01"})
        self.assertEqual(phases(plan_lifecycle(COURSE1, "start", ROUTER))[1][1], ())

    def test_legacy_shutdown_order_exactly_matches_provider(self):
        self.assertEqual(phases(plan_lifecycle(FULL, "stop")), [
            ("windows-shutdown", tuple(reversed(FULL.windows))),
            ("router-shutdown-after-windows-verified", (ROUTER,)),
        ])

    def test_reduced_shutdown_members_before_parent_and_router_last(self):
        self.assertEqual(phases(plan_lifecycle(COURSE1, "stop")), [
            ("windows-shutdown",
             ("GOAD-WS01", "GOAD-SRV02", "GOAD-DC02", "GOAD-DC01")),
            ("router-shutdown-after-windows-verified", (ROUTER,)),
        ])

    def test_reset_scope_is_exact_and_does_not_claim_execution(self):
        for roster in (FULL, COURSE1):
            plan = plan_lifecycle(roster, "reset")
            self.assertEqual(phases(plan)[0][1], (ROUTER,) + roster.windows)
            self.assertEqual(phases(plan)[1][1], roster.windows)
            self.assertEqual(plan.execution, "BLOCKED_STATIC_PLAN_ONLY")

    def test_legacy_network_mode_groups_remain_identical(self):
        self.assertEqual(phases(plan_lifecycle(FULL, "provisioning")), [
            ("domain-controllers-provisioning",
             ("GOAD-DC01", "GOAD-DC02", "GOAD-DC03")),
            ("domain-members-provisioning",
             ("GOAD-SRV02", "GOAD-SRV03", "GOAD-WS01")),
        ])
        self.assertEqual(phases(plan_lifecycle(FULL, "exercise")), [
            ("domain-members-exercise",
             ("GOAD-SRV02", "GOAD-SRV03", "GOAD-WS01")),
            ("domain-controllers-exercise",
             ("GOAD-DC02", "GOAD-DC03", "GOAD-DC01")),
        ])

    def test_course1_network_modes_exclude_essos(self):
        self.assertEqual(phases(plan_lifecycle(COURSE1, "provisioning")), [
            ("domain-controllers-provisioning", ("GOAD-DC01", "GOAD-DC02")),
            ("domain-members-provisioning", ("GOAD-SRV02", "GOAD-WS01")),
        ])
        self.assertEqual(phases(plan_lifecycle(COURSE1, "exercise")), [
            ("domain-members-exercise", ("GOAD-SRV02", "GOAD-WS01")),
            ("domain-controllers-exercise", ("GOAD-DC02", "GOAD-DC01")),
        ])

    def test_unknown_or_unapproved_inputs_fail_closed(self):
        with self.assertRaises(ProfileNotReady):
            plan_lifecycle(COURSE1, "delete")
        with self.assertRaises(ProfileNotReady):
            plan_lifecycle(COURSE1, "start", "GOAD-DC03")
        with self.assertRaises(ProfileNotReady):
            plan_lifecycle(COURSE1, "stop", "GOAD-WS01")
        forged = RuntimeRoster(
            name=COURSE1.name, windows=COURSE1.windows,
            start_order=COURSE1.start_order, dependencies=COURSE1.dependencies,
            management_hosts=COURSE1.management_hosts,
        )
        with self.assertRaises(ProfileNotReady):
            plan_lifecycle(forged, "start")

    def test_cli_is_explicitly_offline_and_never_claims_activation(self):
        proc = subprocess.run(
            [sys.executable, "-m", "goad.course1_lifecycle_plan", "--check",
             "--profile", COURSE1.name, "--action", "start",
             "--machine", "GOAD-WS01"],
            cwd=ROOT, check=False, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["execution"], "BLOCKED_STATIC_PLAN_ONLY")
        self.assertEqual(data["phases"][1]["machines"],
                         ["GOAD-DC01", "GOAD-DC02", "GOAD-WS01"])
        without_check = subprocess.run(
            [sys.executable, "-m", "goad.course1_lifecycle_plan",
             "--profile", COURSE1.name, "--action", "start"],
            cwd=ROOT, check=False, capture_output=True, text=True,
        )
        self.assertNotEqual(without_check.returncode, 0)

    def test_planner_does_not_integrate_with_live_lifecycle_or_mutate(self):
        source = (ROOT / "goad/course1_lifecycle_plan.py").read_text(encoding="utf-8")
        for forbidden in ("subprocess", "vmrun", "ansible-playbook", "vagrant up",
                          "os.system", "Path.write_text", "activate_profile"):
            self.assertNotIn(forbidden, source)
        live = (ROOT / "goad/provider/vagrant/vmware_kingdoms.py").read_text(
            encoding="utf-8")
        self.assertIn("if tuple(self.goad_nomad_windows) != FULL.windows:", live)
        self.assertIn("reduced lifecycle activation is not yet approved", live)


if __name__ == "__main__":
    unittest.main()
