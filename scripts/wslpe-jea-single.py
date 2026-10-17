#!/usr/bin/env python3
"""JEA #30 source plan; fail closed for WinRM-based apply/reset.

Windows PowerShell 5.1 does NOT implement Register-PSSessionConfiguration
-NoServiceRestart. Calling endpoint registration from its own WinRM session
can stop the transport, as confirmed in the WSLPE-WS01 event log.
The dedicated out-of-band lifecycle is NOT yet implemented or authorized.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kingdoms.wslpe45_batch_operator import index_rows, controller_source_blockers

EXPECTED_ID = "jea_role_capability_misconfig"

def local_candidate() -> dict:
    row = next((r for r in index_rows() if r["number"] == 30), None)
    if (not row or row["id"] != EXPECTED_ID or row["source_ci"] != "passed"
            or row["status"] != "candidate"):
        raise ValueError("JEA #30 is not source-qualified")
    path = ROOT / row["playbook"]
    if path.is_symlink() or not path.is_file():
        raise ValueError("Dedicated JEA source missing")
    import yaml
    plays = yaml.safe_load(path.read_text(encoding="utf-8"))
    if (not isinstance(plays, list) or len(plays) != 2
            or [p.get("hosts") for p in plays] != ["localhost", "wslpe"]
            or controller_source_blockers(path, plays)):
        raise ValueError("JEA #30 source dependencies or scope invalid")
    remote_pre = plays[1].get("pre_tasks", [])
    if (not remote_pre or
            remote_pre[0].get("ansible.builtin.fail") is None or
            remote_pre[0].get("when") !=
            "(wslpe_45_action | default('')) in ['apply', 'reset']"):
        raise ValueError("Required remote JEA registration guard absent")
    module = (ROOT / "ansible/files/wslpe45/WslpeJea.psm1").read_text(
        encoding="utf-8")
    if (not all(x in module for x in (
            "Register-PSSessionConfiguration", "Unregister-PSSessionConfiguration",
            "-NoServiceRestart"))):
        raise ValueError("JEA source contract changed")
    return row

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="blocked on PowerShell 5.1/WinRM")
    p.add_argument("--recovery-rehearsed", action="store_true",
                   help="legacy approval is NOT authorization to mutate JEA through WinRM")
    args = p.parse_args()
    print("KINGDOMS WSLPE | JEA #30 REMOTE MUTATION SAFETY GATE", flush=True)
    try:
        local_candidate()
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"[BLOCKED] JEA source guard failed: {type(exc).__name__}", flush=True)
        return 2
    print("[PASS] JEA #30 source remains scoped to the standalone WSLPE guest")
    if args.apply or args.recovery_rehearsed:
        print("[BLOCKED] PowerShell 5.1 JEA registration can stop WinRM; "
              "remote apply/reset prohibited", flush=True)
        print("[NO CHANGES] Existing JEA endpoint and all Windows guests untouched")
        return 2
    print("[PLAN ONLY] Source checks passed; no Windows, VMware, WinRM or NORTH actions")
    print("[NEXT] Implement/test independent local-console JEA endpoint lifecycle")
    print("[NO CHANGES] Existing JEA installation preserved")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
