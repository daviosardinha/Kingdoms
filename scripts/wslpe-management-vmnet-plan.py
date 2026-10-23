#!/usr/bin/env python3
"""READ ONLY: confirm WSLPE management vmnet ownership and print proposed addition.

No --apply mode. Never writes /etc/vmware, starts/stops VMware or powers VMs.
A nonzero return is EXPECTED when the five NORTH VMs are still running.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kingdoms.wslpe_management_vmnet_plan import (
    candidate_plan, vmx_conflicts, native_exercise_binding, inventory,
    RESERVED,
)
from kingdoms.wslpe41_network_auto import select_available_prefix
from kingdoms.wslpe41_host_preflight import native_instance_prefixes

HOST_CHECKER = ROOT / "scripts/wslpe-check-host-network.py"
spec = importlib.util.spec_from_file_location("wslpe_management_vmnet_host_check", HOST_CHECKER)
if spec is None or spec.loader is None:
    raise SystemExit("[BLOCKED] Existing WSLPE host-network preflight not found")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

NETWORKING = Path("/etc/vmware/networking")
STAGE2 = ROOT / "scripts/wslpe-stage2-inspect.py"


def native_target(workspace: Path, networking: str) -> tuple[str, str]:
    """Resolve ONE existing WSLPE native guest through original registration."""
    spec = importlib.util.spec_from_file_location(
        "wslpe_native_management_source", STAGE2,
    )
    if spec is None or spec.loader is None:
        raise ValueError("Existing native WSLPE inspector unavailable")
    stage = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stage)
    instance, meta = stage.find_instance(workspace)
    vmx = stage.locate_registered_vm(instance)  # vmrun LIST, no guest mutation
    provider = (instance / "provider").resolve(strict=True)
    if (vmx.is_symlink() or not vmx.is_relative_to(provider)
            or meta.get("lab") != "WSLPE"):
        raise ValueError("Native WSLPE VMware registration is foreign")
    return native_exercise_binding(
        vmx.read_text(encoding="utf-8"), meta["ip_range"], networking,
    )


def next_free_management_vmnet(
    networking: str, roots: list[Path], exercise_vmnet: str,
) -> str:
    """Select the first unused vmnet without adopting any registered VMX."""
    occupied = set(inventory(networking))
    for number in range(2, 100):
        if (number in occupied or number in RESERVED
                or f"vmnet{number}" == exercise_vmnet):
            continue
        candidate = f"vmnet{number}"
        if not vmx_conflicts(roots, candidate):
            return candidate
    raise ValueError("No unclaimed management vmnet in inspected workspaces")


def vmware_running() -> int:
    try:
        result = subprocess.run(
            ["pgrep", "-c", "-x", "vmware-vmx"],
            text=True, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Cannot inspect running VMware guest processes") from exc
    if result.returncode == 1:
        return 0
    if result.returncode != 0:
        raise ValueError("Cannot establish running VMware guest count")
    return int(result.stdout.strip())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vmnet",
                        help="Legacy explicit management vmnet (without --native-workspace)")
    parser.add_argument("--management-prefix",
                        help="Legacy explicit prefix (without --native-workspace)")
    parser.add_argument("--native-workspace", type=Path,
                        help="Plan for ONE registered fresh native WSLPE guest")
    parser.add_argument("--workspace-root", type=Path, action="append", required=True,
                        help="Repeat for each other NORTH/WSLPE workspace root")
    args = parser.parse_args(argv)

    print("[WSLPE] Read-only VMware management vmnet allocation preflight")
    print("[NO CHANGES] No VMware, Windows, host, Vagrant, firewall or NORTH writes")
    try:
        roots = list(args.workspace_root)
        if args.native_workspace is not None:
            if args.vmnet is not None or args.management_prefix is not None:
                raise ValueError("Native mode automatically selects both candidates")
            roots.append(args.native_workspace)
        if len({p.resolve() for p in roots}) < 2:
            raise ValueError("At least two distinct NORTH/WSLPE workspace roots required")
        if any(p.is_symlink() or not p.is_dir() for p in roots):
            raise ValueError("Missing or linked VMware workspace; do not guess coverage")
        current = NETWORKING.read_text(encoding="utf-8")
        addresses = checker.run_ip("address", "show")
        routes = checker.run_ip("route", "show", "table", "all")
        if args.native_workspace is not None:
            exercise_vmnet, exercise_subnet = native_target(args.native_workspace, current)
            prefixes, _ = native_instance_prefixes(tuple(roots))
            management_prefix = select_available_prefix(
                addresses, routes, current, prefixes,
            )
            management_vmnet = next_free_management_vmnet(
                current, roots, exercise_vmnet,
            )
            print(f"[NATIVE] Exact WSLPE exercise: {exercise_vmnet} {exercise_subnet}")
            print(f"[PROPOSAL] Operator-only: {management_vmnet} {management_prefix}.0/24")
        else:
            if args.vmnet is None or args.management_prefix is None:
                raise ValueError("Specify both --vmnet and --management-prefix")
            exercise_vmnet, exercise_subnet = "vmnet2", "172.28.231.0/24"
            management_prefix, management_vmnet = args.management_prefix, args.vmnet
        subnet = checker.parse_prefix(management_prefix)
        new_text = candidate_plan(
            current, vmnet=management_vmnet, subnet=str(subnet),
            exercise_vmnet=exercise_vmnet, exercise_subnet=exercise_subnet,
        )
        _, collisions = checker.assess(subnet, addresses, routes, current)
        if collisions:
            raise ValueError("Live host collision: " + "; ".join(collisions))
        owners = vmx_conflicts(roots, management_vmnet)
        if owners:
            raise ValueError("Other VMX already references this vmnet: " + "; ".join(owners))
        running = vmware_running()
        before_digest = hashlib.sha256(current.encode("utf-8")).hexdigest()
        original = current.rstrip("\n") + "\n\n"
        if not new_text.startswith(original):
            raise ValueError("Proposal modified existing VMware metadata")
        print(f"[SOURCE] Current /etc/vmware/networking sha256={before_digest}")
        print("[SOURCE] Existing VMware network directives are preserved verbatim")
        print("[PASS] Proposed management subnet has no visible network collision")
        print("[PASS] No supplied workspace VMX references proposed management vmnet")
        print("[PROPOSED ONLY] Append the following lines after a maintenance review:")
        print(new_text[len(original):], end="")
        print("[NOT VERIFIED] All other offline VMware registrations, host-only isolation or Windows management")
        print("[NOT IMPLEMENTED] Host vmnet creation, persistence, Vagrant cutover, WinRM transport or NAT removal")
        if running:
            print(f"[DEFERRED] {running} VMware guest process(es) running - DO NOT CHANGE SHARED NETWORKING")
            return 2
        print("[SOURCE READY] No running VMware VMs detected; independent owner approval still required")
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print("[BLOCKED] Cannot establish isolated WSLPE vmnet candidate: " + str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
