#!/usr/bin/env python3
"""Read-only exact WSLPE41 blocked scenario-#1 evidence inspection.

Does not fix or replay a stage, change source, remove a journal or apply any
Windows changes. Preserve both the failed journal and guest state for review.
"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kingdoms.wslpe41_first_stage_audit import inspect
from kingdoms.wslpe41_install_flow import InstallBlocked
from kingdoms.wslpe41_operator_management import ManagementBlocked
from kingdoms.wslpe41_management_nic import NicBlocked

if __name__ == "__main__":
    print("[MODE] READ ONLY | blocked scenario #1 apply | existing fresh VM")
    try:
        inspect()
        print("[PASS] WSLPE41_BLOCKED_STAGE1_AUDIT_COMPLETE")
    except (InstallBlocked, ManagementBlocked, NicBlocked, ValueError, OSError) as exc:
        # These classes use fixed programme-authored reasons; never report
        # remote stderr, the private inventory or operator credentials.
        print("[BLOCKED] " + type(exc).__name__ + ": " + str(exc)[:240])
        sys.exit(2)
