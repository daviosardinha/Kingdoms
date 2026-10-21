#!/usr/bin/env python3
"""READ ONLY: reconcile running VMware VMXs with guest process count.

This does not allocate vmnet4, stop VMware or approve shared-network changes.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kingdoms.wslpe_management_vmnet_host_gate import (
    HostVmnetGateBlocked, probe_running_vmware, scoped_candidate_free,
)
from kingdoms.wslpe_management_vmnet_transaction import (
    NetworkTransactionBlocked, _read_regular, MAX_NETWORKING_BYTES,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", action="append", required=True, type=Path,
                        help="Every known relevant running/registered VM workspace; repeat")
    parser.add_argument("--candidate-vmnet", default="vmnet4",
                        help="VMnet from the previous native read-only planner")
    args = parser.parse_args(argv)

    print("[READ ONLY] WSLPE VMware management host guest-inventory audit")
    print("[NO CHANGES] No VMware, host, guest, routing, or firewall mutation")
    roots = tuple(args.workspace_root)
    try:
        raw, _ = _read_regular(Path("/etc/vmware/networking"), MAX_NETWORKING_BYTES)
        scoped_candidate_free(raw.decode("utf-8"), roots, args.candidate_vmnet)
        before = probe_running_vmware(roots)
        after = probe_running_vmware(roots)
        if before != after:
            raise HostVmnetGateBlocked("VMware guest inventory changed during audit")
        print(f"[CONFIG SHA256] {hashlib.sha256(raw).hexdigest()}")
        print(f"[VMNET] {args.candidate_vmnet} unused in metadata and inspected workspaces")
        print(f"[INVENTORY] vmrun={after.vmrun_count} vmware-vmx={after.process_count}")
        print(f"[OWNERSHIP] All {after.vmrun_count} running VMXs covered by supplied workspaces")
        print("[NOT VERIFIED] Offline/third-party registrations outside supplied workspaces")
        print("[NOT VERIFIED] Windows operator connectivity or host-only network isolation")
        if after.vmrun_count:
            print(f"[DEFERRED] {after.vmrun_count} VMware guests are running; NO RESTART")
            return 2
        print("[AUDIT CLEAR] No running VMware guests; NOT an authorization to apply vmnet")
        return 0
    except (OSError, ValueError, UnicodeError, NetworkTransactionBlocked) as exc:
        print(f"[BLOCKED] Unable to establish safe management network inventory: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
