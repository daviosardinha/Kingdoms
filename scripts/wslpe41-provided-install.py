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
from kingdoms.wslpe41_provided_install import install, diagnose, recover_clean_blocked_stage1, recover_private_fixture_guard_stage1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--start", action="store_true",
                      help="start the 83-stage journal on already registered fresh VM")
    mode.add_argument("--resume", action="store_true",
                      help="continue only after Windows-console JEA #30 witness")
    mode.add_argument("--status", action="store_true",
                      help="inspect exact provided install journal without scenario writes")
    mode.add_argument("--diagnose", action="store_true",
                      help="read-only preflight with specific failed gate and journal check")
    mode.add_argument("--recover-clean-stage1", action="store_true",
                      help="one approved recovery of exact BLOCKED stage1 after independent Windows absence")
    mode.add_argument("--recover-private-fixture-stage1", action="store_true",
                      help="specific second recovery after controller-only credential guard PASS")
    parser.add_argument("--authorize", default="",
                        help="mandatory confirmation START-EXISTING-WSLPE41 before --start")
    args = parser.parse_args(argv)
    if args.start and args.authorize != "START-EXISTING-WSLPE41":
        print("[BLOCKED] Exact existing-guest installation authorization required")
        return 2
    if args.recover_clean_stage1 and args.authorize != "RECOVER-EMPTY-WSLPE41-STAGE1":
        print("[BLOCKED] Exact one-time stage1 recovery authorization required")
        return 2
    if args.recover_private_fixture_stage1 and args.authorize != "RECOVER-WSLPE41-PRIVATE-FIXTURE-GUARD":
        print("[BLOCKED] Specific private-fixture recovery authorization required")
        return 2
    if not (args.start or args.recover_clean_stage1 or args.recover_private_fixture_stage1) and args.authorize:
        print("[BLOCKED] --authorize belongs only to --start or --recover-clean-stage1")
        return 2
    selection = ("recover-private-fixture-stage1" if args.recover_private_fixture_stage1 else
                 "recover-clean-stage1" if args.recover_clean_stage1 else
                 "diagnose" if args.diagnose else "start" if args.start else
                 "resume" if args.resume else "status")
    print("[SCOPE] Existing bf5369-wslpe-vmware ONLY; NORTH and old WSLPE excluded", flush=True)
    print("[MODE] " + selection + " | one journal | 41 scenarios / 83 stages", flush=True)
    try:
        if args.diagnose:
            return 0 if diagnose() else 2
        if args.recover_private_fixture_stage1:
            result = recover_private_fixture_guard_stage1()
        elif args.recover_clean_stage1:
            result = recover_clean_blocked_stage1()
        else:
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
    except InstallBlocked as exc:
        # InstallBlocked is raised with a fixed program-authored safety reason;
        # do not forward Ansible stdout/stderr or credential contents.
        reason = str(exc).replace("\\r", " ").replace("\\n", " ")[:240]
        print("[BLOCKED] WSLPE41 installation invariant: " + reason, flush=True)
        print("[PRESERVED] Review journal and gate before considering --start", flush=True)
        return 2
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"[BLOCKED] Provided WSLPE41 stage installer: {type(exc).__name__}", flush=True)
        print("[PRESERVED] Journal/guest/credentials unchanged by any automatic retry", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
