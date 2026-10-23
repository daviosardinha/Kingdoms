#!/usr/bin/env python3
"""One-time JEA #30 source-proof recovery on exact existing WSLPE41 VMware guest."""
from pathlib import Path
import argparse
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kingdoms.wslpe41_jea_stage_recovery import recover
from kingdoms.wslpe41_install_flow import InstallBlocked
from kingdoms.wslpe41_operator_management import ManagementBlocked
from kingdoms.wslpe41_management_nic import NicBlocked


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorize", default="", help="specific JEA source-proof authorization")
    args = parser.parse_args(argv)
    if args.authorize != "RECOVER-WSLPE41-JEA30-SOURCE-PROOF":
        print("[BLOCKED] Explicit JEA #30 source-proof recovery approval required")
        return 2
    print("[SCOPE] WSLPE41 JEA #30 source staging only; existing 56 proofs preserved", flush=True)
    try:
        result = recover()
        print("[RESULT] " + result, flush=True)
        return 0
    except (InstallBlocked, ManagementBlocked, NicBlocked, ValueError, OSError) as exc:
        print("[BLOCKED] " + type(exc).__name__ + ": " + str(exc)[:240], flush=True)
        print("[NO REPLAY] Do not rerun --start or JEA staging", flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
