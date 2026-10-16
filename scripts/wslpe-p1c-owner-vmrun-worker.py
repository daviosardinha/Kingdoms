#!/usr/bin/env python3
"""Unprivileged systemd worker: read-only exact WSLPE VMware inventory.

Never accepts lifecycle verbs, edits VMX or manages VMware networks.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kingdoms.wslpe_vmrun_recovery import worker_vmrun_read_only


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--vmx", required=True, type=Path)
    parser.add_argument("--vmrun", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    if not args.worker:
        return 1
    try:
        worker_vmrun_read_only(args.vmx, args.vmrun, args.result)
    except Exception:
        # Avoid emitting potentially sensitive host VMware inventory paths.
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
