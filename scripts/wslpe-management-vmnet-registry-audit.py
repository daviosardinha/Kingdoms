#!/usr/bin/env python3
"""Read-only VMware Workstation USER library / offline VMnet4 ownership audit."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kingdoms.wslpe_management_vmnet_host_gate import (
    HostVmnetGateBlocked, probe_running_vmware,
)
from kingdoms.wslpe_management_vmnet_registry import audit_user_library


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, action="append", required=True,
                        help="All current Kingdoms/WSLPE VM workspaces (repeat)")
    parser.add_argument("--candidate-vmnet", default="vmnet4")
    args = parser.parse_args(argv)
    roots = tuple(args.workspace_root)
    print("[READ ONLY] VMware Workstation per-user offline VMX library audit")
    print("[NO CHANGES] VMware library, VMXs, networks and guests remain untouched")
    try:
        before = probe_running_vmware(roots)
        result = audit_user_library(
            library=Path.home() / ".vmware" / "inventory.vmls",
            roots=roots, running=before, candidate_vmnet=args.candidate_vmnet)
        after = probe_running_vmware(roots)
        if before != after:
            raise HostVmnetGateBlocked("Running VMware inventory changed during audit")
        print(f"[LIBRARY] {result.count} Workstation entries inspected")
        print(f"[CANDIDATE] No registered library VMX references {args.candidate_vmnet}")
        print(f"[RUNNING] vmrun={after.vmrun_count} vmware-vmx={after.process_count}")
        for path in result.outside_roots:
            print(f"[OTHER OWNER] Registered VMX outside supplied workspaces: {path}")
        for path in result.running_not_in_library:
            print(f"[NOT IN LIBRARY] Running VMX not listed in user inventory: {path}")
        print("[LIMIT] User library only; not global proof of all offline/unregistered VMXs")
        if result.outside_roots or result.running_not_in_library:
            print("[BLOCKED] Workstation library/VMX coverage needs operator review")
            return 2
        if after.vmrun_count:
            print("[DEFERRED] Guests still running; NO NETWORK RESTART")
            return 2
        print("[LIBRARY CLEAR] No inspected library claim; still NO permission to apply vmnet")
        return 0
    except (OSError, ValueError, UnicodeError) as exc:
        print(f"[BLOCKED] Workstation library audit incomplete: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
