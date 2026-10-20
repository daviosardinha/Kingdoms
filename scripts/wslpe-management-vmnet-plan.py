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

from kingdoms.wslpe_management_vmnet_plan import candidate_plan, vmx_conflicts

HOST_CHECKER = ROOT / "scripts/wslpe-check-host-network.py"
spec = importlib.util.spec_from_file_location("wslpe_management_vmnet_host_check", HOST_CHECKER)
if spec is None or spec.loader is None:
    raise SystemExit("[BLOCKED] Existing WSLPE host-network preflight not found")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

NETWORKING = Path("/etc/vmware/networking")


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
    parser.add_argument("--vmnet", required=True)
    parser.add_argument("--management-prefix", required=True,
                        help="Candidate IPv4 prefix, e.g. 172.28.232")
    parser.add_argument("--workspace-root", type=Path, action="append", required=True,
                        help="Repeat for NORTH and WSLPE original native workspace roots")
    args = parser.parse_args(argv)

    print("[WSLPE] Read-only VMware management vmnet allocation preflight")
    print("[NO CHANGES] No VMware, Windows, host, Vagrant, firewall or NORTH writes")
    try:
        if len(args.workspace_root) < 2:
            raise ValueError("Supply original NORTH and WSLPE workspace roots")
        subnet = checker.parse_prefix(args.management_prefix)
        current = NETWORKING.read_text(encoding="utf-8")
        new_text = candidate_plan(current, vmnet=args.vmnet, subnet=str(subnet))
        addresses = checker.run_ip("address", "show")
        routes = checker.run_ip("route", "show", "table", "all")
        _, collisions = checker.assess(subnet, addresses, routes, current)
        if collisions:
            raise ValueError("Live host collision: " + "; ".join(collisions))
        owners = vmx_conflicts(args.workspace_root, args.vmnet)
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
