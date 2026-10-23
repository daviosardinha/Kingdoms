#!/usr/bin/env python3
"""Attach vmnet4 only to powered-off, registered fresh WSLPE41 guest.

Normal user (stark); never run as root. --plan is read-only; --apply
requires exact pinned VMX SHA256 and independent explicit approval.
Does NOT boot Windows, configure the guest IPv4 or enable WinRM.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kingdoms.wslpe41_management_nic import (
    APPROVAL, NicBlocked, TARGET_GUEST, VMNET,
    attach, candidate_vmx, identify, host_operator_network_ready,
    zero_vmware_guests,
)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true",
                      help="Read-only offline exact guest and NIC candidate")
    mode.add_argument("--apply", action="store_true",
                      help="Append new third NIC into exact powered-off VMX")
    p.add_argument("--expected-sha256", help="Read-only planned original VMX SHA256")
    p.add_argument("--approve", default="", help="Exact per-VM mutation approval")
    args = p.parse_args(argv)

    try:
        if args.plan and (args.approve or args.expected_sha256):
            raise NicBlocked("Planning must be read-only, without authorization parameters")
        if args.apply and (not args.expected_sha256 or args.approve != APPROVAL):
            raise NicBlocked("Original VMX hash and explicit approval are mandatory")
        zero_vmware_guests()
        host_operator_network_ready()
        target = identify(Path.home())
        proposed = candidate_vmx(target.original)
        print("[SCOPE] Fresh native bf5369-wslpe-vmware ONLY")
        print("[VMX] " + str(target.vmx))
        print("[ORIGINAL VMX SHA256] " + target.digest)
        print("[NEW VMX SHA256] " + __import__("hashlib").sha256(proposed).hexdigest())
        print("[NIC0] NAT bootstrap preserved")
        print("[NIC1] vmnet3 learner exercise preserved")
        print("[NIC2] vmnet4 dedicated management candidate")
        print("[GUEST PLANNED] " + TARGET_GUEST + "; not configured")
        if args.plan:
            print("[PLAN PASS] Exact offline management adapter attachment ready")
            print("[NO CHANGES] VMware guest, Windows and host networking unchanged")
            return 0
        journal = attach(home=Path.home(), expected_sha256=args.expected_sha256,
                         approval=args.approve)
        print("[COMMITTED] Third NIC added to exact offline native WSLPE VMX")
        print("[JOURNAL] " + journal)
        print("[NOT DONE] Windows IP, HTTPS/5986, operator auth, isolation and 41 scenarios")
        return 0
    except (NicBlocked, OSError, ValueError, KeyError) as exc:
        print("[BLOCKED] WSLPE management NIC: " + str(exc))
        print("[NO AUTOMATIC RESTART] Leave VMs off if journal or VMX state is uncertain")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
