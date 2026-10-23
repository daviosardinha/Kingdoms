#!/usr/bin/env python3
"""One-time journal-preserving stage7 learner profile recovery for the exact WSLPE41 VM."""
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kingdoms.wslpe41_stage7_profile_recovery import recover
from kingdoms.wslpe41_install_flow import InstallBlocked
from kingdoms.wslpe41_operator_management import ManagementBlocked
from kingdoms.wslpe41_management_nic import NicBlocked

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorize", default="", help="exact stage7 approval marker")
    args = parser.parse_args(argv)
    if args.authorize != "RECOVER-WSLPE41-STAGE7-PROFILE":
        print("[BLOCKED] Explicit stage7-only recovery authorization required", flush=True)
        return 2
    print("[SCOPE] Existing WSLPE41 VM ONLY; six validated scenarios and old journals retained", flush=True)
    try:
        result = recover()
        print("[RESULT] " + result, flush=True)
        return 0
    except (InstallBlocked, ManagementBlocked, NicBlocked, OSError, ValueError) as exc:
        print("[BLOCKED] " + type(exc).__name__ + ": " + str(exc)[:240], flush=True)
        print("[PRESERVED] No automatic retry; review exact journal and profile state", flush=True)
        return 2

if __name__ == "__main__":
    sys.exit(main())
