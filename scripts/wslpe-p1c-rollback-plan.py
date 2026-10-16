#!/usr/bin/env python3
"""Read-only WSLPE systemd rollback plan: NO files, units, VMs or nft writes."""
from __future__ import annotations
import importlib.util
from hashlib import sha256
from pathlib import Path
import pwd
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kingdoms.wslpe_exact_restore import prepare_plan
from kingdoms.wslpe_recovery_bundle import encode_bundle
from kingdoms.wslpe_rollback_timer_plan import make_timer_preview, approve_arming

PREVIEW = ROOT / "scripts/wslpe-p1c-north-cutover-preview.py"
WORKER = ROOT / "scripts/wslpe-p1c-rollback-worker.py"

def source():
    spec = importlib.util.spec_from_file_location("wslpe_rollback_plan_preview", PREVIEW)
    if spec is None or spec.loader is None:
        raise ValueError("WSLPE source preview not available")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def main() -> int:
    print("KINGDOMS WSLPE | INDEPENDENT RECOVERY TIMER SOURCE GATE (READ ONLY)")
    print("[NO CHANGES] No systemd, nftables, VMware, NAT or NORTH writes")
    try:
        p = source()
        p.north_source_contract()
        details = p.collect()
        vmx = details["vmx"]
        uid = vmx.stat().st_uid
        if uid <= 0:
            raise ValueError("Registered VMware owner must not be root")
        username = pwd.getpwuid(uid).pw_name
        plan = prepare_plan(vmx, vmx, details["vmnet"], uid)
        digest = sha256(encode_bundle(plan)).hexdigest()
        parent = Path(pwd.getpwuid(uid).pw_dir) / ".local/state/kingdoms-wslpe-recovery"
        bundle = parent / "recovery.json"
        timer = make_timer_preview(
            owner=username, vmx=vmx, bundle=bundle,
            pin=digest, python=Path(sys.executable), worker=WORKER,
            unit="kingdoms-wslpe-restore-0000000000000000"
        )
        print(f"[PASS] Current registered WSLPE VMX={vmx.name}")
        print(f"[PASS] In-memory original recovery bundle digest={digest}")
        print(f"[PASS] Proposed owner-context systemd rollback delay={timer.delay_seconds}s")
        print(f"[INFO] Timer unit name is illustrative; unique ID required at approval")
        issues = approve_arming(
            boot_guard_reboot_verified=False,
            management_return_route_verified=False,
            exact_workstation_vm_owner_verified=True,
            recovery_live_test_verified=False,
            host_l2_isolation_verified=False,
        )
        for reason in issues:
            print(f"[RELEASE BLOCKED] {reason}")
        print("[RESULT] WSLPE_ROLLBACK_TIMER_PLAN=PASS; TIMER_ARMED=FALSE")
        print("[RESULT] WSLPE_NAT_CUTOVER_AUTHORIZED=FALSE")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"[BLOCKED] WSLPE recovery plan failed: {type(exc).__name__}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
