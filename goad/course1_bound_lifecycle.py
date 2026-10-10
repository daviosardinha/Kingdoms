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
from goad.kingdoms_vmware_profile import north_binding
from goad.north_native_instance import inspect_north_instance_assets


def plan_bound_instance(
    provider_dir: str | Path, action: str, machine: str | None = None,
    lab_name: str = "GOAD",
) -> OfflineLifecyclePlan:
    """Read-only dependency plan for a concrete, source-verified instance.

    GOAD keeps the historical six-guest contract. NORTH is only recognized
    if the REAL Kingdoms-generated instance matches every native source
    identity; this does not confer installation or VM runtime authority.
    """
    if lab_name == "GOAD":
        profile = inspect_instance_binding(provider_dir)
        if profile is not FULL:
            raise ProfileNotReady("only validated reference Kingdoms instances can be planned")
        return plan_lifecycle(profile, action, machine)
    if lab_name == "NORTH":
        verified = inspect_north_instance_assets(provider_dir)
        if verified["runtime_authorized"]:
            raise ProfileNotReady("NORTH source binding cannot grant runtime authorization")
        return plan_lifecycle(north_binding().roster, action, machine)
    raise ProfileNotReady("unknown Kingdoms runtime lab identity")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-provider", required=True,
                        help="Existing instance provider directory with Vagrantfile")
    parser.add_argument(
        "--action", required=True,
        choices=("start", "stop", "reset", "provisioning", "exercise")
    )
    parser.add_argument("--machine", help="optional start target, including GOAD-ROUTER")
    parser.add_argument("--lab", choices=("GOAD", "NORTH"), default="GOAD",
                        help="explicit lab identity; never authorizes VM lifecycle")
    args = parser.parse_args()
    try:
        plan = plan_bound_instance(args.check_provider, args.action, args.machine,
                                   lab_name=args.lab)
    except (ProfileNotReady, OSError, UnicodeError) as exc:
        parser.exit(1, "[BLOCK] " + str(exc) + "\n")
    result = plan.as_dict()
    result["binding"] = (
        "VERIFIED_REFERENCE_INSTANCE" if args.lab == "GOAD"
        else "VERIFIED_NORTH_SOURCE_ONLY"
    )
    result["activation"] = "NOT_AUTHORIZED_BY_THIS_CHECK"
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
