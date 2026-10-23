#!/usr/bin/env python3
"""Read-only audit of exact blocked WSLPE41 scenario #7 AlwaysInstallElevated."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kingdoms.wslpe41_stage7_readonly_audit import inspect
from kingdoms.wslpe41_install_flow import InstallBlocked
from kingdoms.wslpe41_operator_management import ManagementBlocked
from kingdoms.wslpe41_management_nic import NicBlocked

if __name__ == "__main__":
    print("[MODE] READ ONLY | scenario #7 apply | 6 validated scenarios preserved", flush=True)
    try:
        inspect()
        print("[PASS] WSLPE41_BLOCKED_STAGE7_AUDIT_COMPLETE", flush=True)
    except (InstallBlocked, ManagementBlocked, NicBlocked, ValueError, OSError) as exc:
        print(f"[BLOCKED] {type(exc).__name__}: {str(exc)[:240]}", flush=True)
        print("[PRESERVED] No recovery or stage replay performed", flush=True)
        sys.exit(2)
