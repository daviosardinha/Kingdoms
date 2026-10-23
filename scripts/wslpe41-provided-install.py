#!/usr/bin/env python3
"""ONE existing KINGDOMS WSLPE41 guest: guarded 41/83 scenario installation.

--start requires explicit approval and records each Windows stage once.
The installer pauses at JEA #30 for an *interactive elevated VMware console*
operation; --resume never re-runs completed stages or launches another VM.
An interruption/failure is locked for review, not automatically retried.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kingdoms.wslpe41_management_nic import NicBlocked
from kingdoms.wslpe41_install_flow import InstallBlocked
from kingdoms.wslpe41_provided_install import install


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--start", action="store_true",
                      help="start the 83-stage journal on already registered fresh VM")
    mode.add_argument("--resume", action="store_true",
                      help="continue only after Windows-console JEA #30 witness")
    mode.add_argument("--status", action="store_true",
                      help="inspect exact provided install journal without scenario writes")
    parser.add_argument("--authorize", default="",
                        help="mandatory confirmation START-EXISTING-WSLPE41 before --start")
    args = parser.parse_args(argv)
    if args.start and args.authorize != "START-EXISTING-WSLPE41":
        print("[BLOCKED] Exact existing-guest installation authorization required")
        return 2
    if not args.start and args.authorize:
        print("[BLOCKED] --authorize belongs only to --start")
        return 2
    selection = "start" if args.start else "resume" if args.resume else "status"
    print("[SCOPE] Existing bf5369-wslpe-vmware ONLY; NORTH and old WSLPE excluded", flush=True)
    print("[MODE] " + selection + " | one journal | 41 scenarios / 83 stages", flush=True)
    try:
        result = install(selection)
        if result == "PAUSED":
            print("[JEA HANDOFF] Only interactive VMware-console action is permitted next")
        return 0
    except NicBlocked as exc:
        # Only the purpose-built VMware host/VMX guard raises NicBlocked.
        # Its messages contain fixed gate names and non-secret file metadata,
        # never credentials or raw subprocess stderr. Surface the precise gate
        # so an expired sudo session is not mistaken for a VMX/NIC regression.
        detail = str(exc)
        print("[BLOCKED] WSLPE41 exact VMware safety gate: "
              + (detail[:320] if detail else "unspecified"), flush=True)
        if detail == "Host maintenance guard failed: sudo":
            print("[ACTION] Refresh Kali sudo authorization with 'sudo -v'; "
                  "then recheck the existing vmnet4 keeper", flush=True)
        print("[NO SCENARIOS] Inspect original journal before retrying --start", flush=True)
        return 2
    except (InstallBlocked, ValueError, OSError, RuntimeError) as exc:
        print(f"[BLOCKED] Provided WSLPE41 stage installer: {type(exc).__name__}", flush=True)
        print("[PRESERVED] Journal/guest/credentials unchanged by any automatic retry", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
