"""Read-only Kingdoms lifecycle *planning*, never activation.

This module describes intended per-profile VM scopes for later controller
integration. It does not inspect an installed instance, grant profile approval,
execute Vagrant/VMware, or relax the fail-closed instance binding.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

from goad.course1_runtime_contract import COURSE1, FULL, ROUTER, ProfileNotReady, RuntimeRoster


@dataclass(frozen=True)
class PlanPhase:
    name: str
    machines: tuple[str, ...]


@dataclass(frozen=True)
class OfflineLifecyclePlan:
    profile: str
    action: str
    phases: tuple[PlanPhase, ...]
    management_hosts: tuple[tuple[str, str], ...]
    execution: str = "BLOCKED_STATIC_PLAN_ONLY"

    def as_dict(self) -> dict:
        return {
            "profile": self.profile,
            "action": self.action,
            "execution": self.execution,
            "phases": [
                {"name": phase.name, "machines": list(phase.machines)}
                for phase in self.phases
            ],
            "management_hosts": dict(self.management_hosts),
        }


def plan_lifecycle(
    roster: RuntimeRoster, action: str, machine: str | None = None
) -> OfflineLifecyclePlan:
    """Return immutable intended machine scopes, not executable operations.

    The full-GOAD order reflects the validated installed controllers, including
    their historical lab-mode exercise DC order. Nothing returned here is an
    activation authorization or an installed-instance binding.
    """
    if roster is not FULL and roster is not COURSE1:
        raise ProfileNotReady("only the two canonical offline roster definitions are accepted")

    if action not in ("start", "stop", "reset", "provisioning", "exercise"):
        raise ProfileNotReady("unsupported offline lifecycle action")
    if machine is not None and action != "start":
        raise ProfileNotReady("a machine target is supported only for start planning")

    dc = tuple(vm for vm in roster.windows if vm.startswith("GOAD-DC"))
    members = tuple(vm for vm in roster.windows if vm not in dc)

    if action == "start":
        windows = roster.requested_start(machine)
        phases = (
            PlanPhase("router-management-ready", (ROUTER,)),
            PlanPhase("interleaved-windows-start-and-ad-readiness", windows),
        )
        scoped = windows
    elif action == "stop":
        # The installed full-GOAD stop() iterates reversed canonical windows,
        # not reversed startup dependencies. Preserve that exact legacy order.
        windows = tuple(reversed(roster.windows))
        phases = (
            PlanPhase("windows-shutdown", windows),
            PlanPhase("router-shutdown-after-windows-verified", (ROUTER,)),
        )
        scoped = roster.windows
    elif action == "reset":
        # Snapshot pop may auto-start restored guests. The active controller
        # must handle recorded mode, stop any auto-started guests and perform
        # offline NIC normalization before a future reduced reset is allowed.
        phases = (
            PlanPhase("snapshot-scope-not-execution-order", (ROUTER,) + roster.windows),
            PlanPhase("restored-windows-requiring-mode-dependent-validation", roster.windows),
        )
        scoped = roster.windows
    elif action == "provisioning":
        phases = (
            PlanPhase("domain-controllers-provisioning", dc),
            PlanPhase("domain-members-provisioning", members),
        )
        scoped = roster.windows
    else:
        # Exact legacy exercise order: NORTH child DC, ESSOS DC (if present),
        # then forest-root DC, after member/workstation isolation.
        exercise_dcs = tuple(
            vm for vm in ("GOAD-DC02", "GOAD-DC03", "GOAD-DC01") if vm in dc
        )
        if set(exercise_dcs) != set(dc):
            raise ProfileNotReady("unrecognized domain controller in exercise plan")
        phases = (
            PlanPhase("domain-members-exercise", members),
            PlanPhase("domain-controllers-exercise", exercise_dcs),
        )
        scoped = roster.windows

    actual = tuple(vm for phase in phases for vm in phase.machines if vm != ROUTER)
    if any(vm not in roster.windows for vm in actual):
        raise ProfileNotReady("plan references a machine outside its profile")
    management = tuple(
        (vm, roster.management_hosts[vm]) for vm in roster.windows if vm in scoped
    )
    return OfflineLifecyclePlan(roster.name, action, phases, management)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="print a static plan only")
    parser.add_argument("--profile", choices=(FULL.name, COURSE1.name), required=True)
    parser.add_argument(
        "--action", choices=("start", "stop", "reset", "provisioning", "exercise"),
        required=True,
    )
    parser.add_argument("--machine", help="optional Windows VM or router for start")
    args = parser.parse_args()
    if not args.check:
        parser.error("--check is mandatory; lifecycle execution is not implemented")
    roster = FULL if args.profile == FULL.name else COURSE1
    try:
        plan = plan_lifecycle(roster, args.action, args.machine)
    except ProfileNotReady as exc:
        parser.exit(1, "[BLOCK] " + str(exc) + "\n")
    print(json.dumps(plan.as_dict(), indent=2))


if __name__ == "__main__":
    main()
