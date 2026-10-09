"""Bind read-only Kingdoms lifecycle plans to an installed VMware instance.

An arbitrary --profile selector must never confer authority. A genuine
Course 1 preview or unknown/deviating machine roster is rejected by the
existing instance-binding gate before planning can succeed.

This module never executes lifecycle actions; the hardened provider remains
the only authority for installed-reference VM/network operations.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from goad.course1_instance_binding import inspect_instance_binding
from goad.course1_lifecycle_plan import OfflineLifecyclePlan, plan_lifecycle
from goad.course1_runtime_contract import FULL, ProfileNotReady


def plan_bound_instance(
    provider_dir: str | Path, action: str, machine: str | None = None
) -> OfflineLifecyclePlan:
    """Inspect the *concrete* provider Vagrantfile and return a legacy plan.

    Strictly reference-only until a separately audited Course 1 activation
    contract exists. Does not alter disk files, runtime state or guest power.
    """
    profile = inspect_instance_binding(provider_dir)
    if profile is not FULL:
        raise ProfileNotReady("only validated reference Kingdoms instances can be planned")
    return plan_lifecycle(profile, action, machine)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-provider", required=True,
                        help="Existing instance provider directory with Vagrantfile")
    parser.add_argument(
        "--action", required=True,
        choices=("start", "stop", "reset", "provisioning", "exercise")
    )
    parser.add_argument("--machine", help="optional start target, including GOAD-ROUTER")
    args = parser.parse_args()
    try:
        plan = plan_bound_instance(args.check_provider, args.action, args.machine)
    except (ProfileNotReady, OSError, UnicodeError) as exc:
        parser.exit(1, "[BLOCK] " + str(exc) + "\n")
    result = plan.as_dict()
    result["binding"] = "VERIFIED_REFERENCE_INSTANCE"
    result["activation"] = "NOT_AUTHORIZED_BY_THIS_CHECK"
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
