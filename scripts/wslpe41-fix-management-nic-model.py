#!/usr/bin/env python3
"""Repair only fresh WSLPE vmnet4 adapter's legacy VMware device model.

Run as normal VMware Workstation owner, not root. --plan may read a running
guest; --apply requires ZERO running VMware guests and explicit SHA/approval.
No VMware services, NORTH, historical WSLPE, other adapters or Windows
settings are changed. The original committed NIC journal remains intact.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kingdoms import wslpe41_management_nic as nic
from kingdoms import wslpe41_management_nic_model as model


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--plan", action="store_true", help="Read-only pinned model repair preflight")
    modes.add_argument("--apply", action="store_true", help="Edit exact offline fresh VMX after approval")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--approve", default="")
    args = parser.parse_args(argv)
    try:
        if args.plan and (args.expected_sha256 or args.approve):
            raise nic.NicBlocked("Read-only plan cannot carry mutation authorization")
        if args.apply:
            journal = model.apply(Path.home(), expected_sha256=args.expected_sha256 or "",
                                  approval=args.approve)
            print("[COMMITTED] Exact fresh WSLPE ethernet2.virtualDev=e1000e")
            print("[JOURNAL] " + journal)
            print("[UNCHANGED] ethernet0 NAT, ethernet1 vmnet3, vmnet4, generated MAC and NORTH")
            print("[NEXT] Boot only fresh WSLPE and verify Windows NIC 00-0C-29-2F-D7-6F")
            return 0
        target, new = model.plan(Path.home())
        print("[READ ONLY] Exact fresh powered-on/off VMware NIC-model inspection")
        print("[TARGET] " + str(target.vmx))
        print("[CURRENT SHA256] " + target.digest)
        print("[PROPOSED SHA256] " + hashlib.sha256(new).hexdigest())
        print("[CURRENT NIC] vmnet4 MAC " + model.EXPECTED_MAC + " missing virtualDev")
        print("[PROPOSED NIC] vmnet4 e1000e; same MAC and subnet")
        print("[NO CHANGES] VMX, Windows, guest power, VMware networks and other labs untouched")
        print("[PLAN PASS] WSLPE_MANAGEMENT_E1000E_MODEL_READY")
        return 0
    except (OSError, ValueError, nic.NicBlocked) as exc:
        print("[BLOCKED] WSLPE management e1000e: " + str(exc))
        print("[NO AUTOMATIC RETRY] Preserve registered VMX and journals")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
