#!/usr/bin/env python3
"""Repair or verify operator management on the existing bf5369 WSLPE guest only."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kingdoms.wslpe41_operator_management import ManagementBlocked, RECOVERY, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true", help="finish account/TLS/firewall handoff; preserve recovery")
    mode.add_argument("--verify", action="store_true", help="read-only fresh HTTPS and negative-path acceptance")
    args = parser.parse_args()
    try:
        run(apply=args.apply)
    except (Exception, KeyboardInterrupt) as exc:
        # Remote libraries can include secrets in exception text. Print only our
        # explicit safe diagnostics, otherwise the type and the recovery command.
        detail = str(exc) if isinstance(exc, ManagementBlocked) else type(exc).__name__
        print("[BLOCKED] " + detail, flush=True)
        print("State/credentials retained. No automatic retry or password rotation.")
        print("If Windows Prepare completed, console rollback is:")
        print(f"& '{RECOVERY}' -Mode Rollback")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
