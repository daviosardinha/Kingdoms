#!/usr/bin/env python3
"""Exact-registered WSLPE systemd recovery worker.

Default mode is read-only verify. --restore is a mutating emergency
operation intended ONLY for a separately approved and armed root-owned
systemd timer. This script does not arm any timer or change firewall/NAT.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kingdoms.wslpe_rollback_worker import recover_from_pinned_bundle

STAGE = ROOT / "scripts/wslpe-stage2-inspect.py"


def stage_module():
    spec = importlib.util.spec_from_file_location("wslpe_rollback_stage2", STAGE)
    if spec is None or spec.loader is None:
        raise ValueError("Exact WSLPE registration helper unavailable")
    stage = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stage)
    return stage


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--approved-sha256", required=True)
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    print("KINGDOMS WSLPE | EXACT-REGISTERED VMX ROLLBACK WORKER", flush=True)
    try:
        if args.restore:
            # A systemd environment variable is not an authorization
            # boundary: an owner could spoof INVOCATION_ID in a shell.
            # Until a root-owned, independently pinned approval unit and
            # host boot-guard are installed and live-proven, this executable
            # intentionally has NO mutating entrypoint.
            raise ValueError("Real VMX restoration is not armed in this release")
        vmrun = shutil.which("vmrun")
        if not vmrun:
            raise ValueError("No VMware Workstation owner executable")
        result = recover_from_pinned_bundle(
            bundle=args.bundle, digest=args.approved_sha256,
            stage=stage_module(), vmrun=vmrun, owner=os.geteuid(),
            authorized=args.restore,
        )
        print(f"[PASS] WSLPE_APPROVED_RECOVERY_STATE={result}")
        if not args.restore:
            print("[NO CHANGES] Verified only; no VMware lifecycle operations")
        return 0
    except Exception as exc:
        # Do not print path-containing/credential-containing lower-level errors.
        print(f"[BLOCKED] WSLPE recovery gate: {type(exc).__name__}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
