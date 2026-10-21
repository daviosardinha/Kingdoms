#!/usr/bin/env python3
"""Read-only WSLPE owner / VMware source gate, optional harmless timer rehearsal.

--rehearse creates/deletes a temporary /tmp file via a 3-second host
systemd timer running as the exact VMware VMX owner. Does not stop VM,
change any VMX bytes, alter firewall or disconnect NAT.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kingdoms.wslpe_owner_recovery import owner_identity, rehearse_owner_timer
from kingdoms.wslpe_vmrun_recovery import rehearse_vmrun_systemd, rehearse_offline_copy

STAGE2 = ROOT / "scripts/wslpe-stage2-inspect.py"
NAT_PREVIEW = ROOT / "scripts/wslpe-p1c-north-cutover-preview.py"

# Never print arbitrary exception text from tools, subprocesses, or file paths.
# These codes map ONLY to our own fixed, source-reviewed ValueError strings.
OWNER_TIMER_REASONS = {
    "Temporary WSLPE owner proof directory unsafe": "OWNER_TEMP_DIR_UNSAFE",
    "Independent owner-context systemd timer unavailable": "SYSTEMD_RUN_FAILED",
    "Owner-context timer not confirmed active": "SYSTEMD_TIMER_NOT_ACTIVE",
    "Owner-context recovery timer did not execute": "SYSTEMD_MARKER_NOT_FIRED",
    "Timed WSLPE owner proof has wrong identity": "OWNER_MARKER_IDENTITY_INVALID",
    "Owner recovery proof directory changed unexpectedly": "OWNER_TEMP_DIR_CHANGED",
    "Owner recovery proof directory ownership changed": "OWNER_TEMP_OWNER_CHANGED",
    "Owner recovery sentinel changed unexpectedly": "OWNER_MARKER_CHANGED",
}


def mod(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("Missing exact WSLPE source code")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def exact_vmware_owner() -> tuple[Path, int, str]:
    stage = mod(STAGE2, "wslpe_owner_stage2")
    instance, info = stage.find_instance(stage.WORKSPACE)
    if info.get("lab") != "WSLPE":
        raise ValueError("Not the standalone WSLPE native instance")
    vmx = stage.locate_registered_vm(instance)
    if (vmx.is_symlink() or not vmx.resolve().is_relative_to(
            stage.WORKSPACE.resolve())):
        raise ValueError("Registered WSLPE VMX does not belong to workspace")
    uid, user = owner_identity(vmx)
    return vmx, uid, user


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rehearse", action="store_true",
                        help="execute harmless timed owner-context marker")
    parser.add_argument("--vmrun-readonly", action="store_true",
                        help="host timer runs vmrun LIST only, plus scratch VMX restore")
    args = parser.parse_args()
    print("KINGDOMS WSLPE | OWNER-SCOPED HOST RECOVERY REHEARSAL")
    print("[NO VM WRITES] No NAT cutover, VMware restart, VMX edits or NORTH operations")
    stage = "registered_guest"
    try:
        vmx, uid, user = exact_vmware_owner()
        stage = "north_source_preview"
        preview = mod(NAT_PREVIEW, "wslpe_owner_nat_preview")
        preview.north_source_contract()
        preview.running_exact(vmx)
        candidate = preview.collect()
        if candidate["vmx"].resolve() != vmx.resolve():
            raise ValueError("VMX registered identity changed during recovery preflight")
        print("[PASS] Exact WSLPE VMware owner and running VMX validated")
        if args.rehearse:
            stage = "owner_systemd_timer"
            unit = rehearse_owner_timer(uid, user)
            print(f"[PASS] WSLPE_OWNER_HOST_TIMER_FIRED=TRUE ({unit})")
            print("[PASS] Systemd host timer runs under exact WSLPE VMX owner")
        if args.vmrun_readonly:
            stage = "vmrun_owner_timer"
            if not args.rehearse:
                raise ValueError("VMware list proof requires prior owner timer rehearsal")
            data = rehearse_vmrun_systemd(vmx, uid, user)
            print("[PASS] WSLPE_SYSTEMD_VMRUN_LIST=TRUE")
            print(f"[INFO] VMware owner sees {data['running_vm_count']} running VM(s)")
            stage = "scratch_vmx_restore"
            before, after = rehearse_offline_copy(vmx.read_bytes(), candidate["vmnet"], uid)
            print("[PASS] WSLPE_SCRATCH_VMX_RESTORE_BYTE_EXACT=TRUE")
            print(f"[INFO] Scratch original SHA256={before}")
            print(f"[INFO] Scratch candidate SHA256={after}")
        elif not args.rehearse:
            print("[PREVIEW] Host owner rollback timer has NOT been exercised")
    except (OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired) as exc:
        reason = (
            OWNER_TIMER_REASONS.get(str(exc), type(exc).__name__)
            if stage == "owner_systemd_timer" else type(exc).__name__
        )
        print(f"[BLOCKED] WSLPE_RECOVERY_STAGE={stage} REASON={reason}; no VMware/NORTH changes")
        if stage == "owner_systemd_timer" and reason == "SYSTEMD_RUN_FAILED":
            print("[NEXT] Read-only host check: sudo -n -l; verify systemd-run authorization")
        elif stage == "owner_systemd_timer" and reason == "SYSTEMD_TIMER_NOT_ACTIVE":
            print("[NEXT] Inspect systemd system timer availability; do not bypass owner recovery")
        return 1
    print("[NOT VERIFIED] Actual vmrun stop/start, real VMX restore and independent failure rollback")
    print("[NOT VERIFIED] Host reboot/firewall persistence and ARP/L2 isolation")
    print("[RELEASE BLOCKED] WSLPE NAT cutover remains unauthorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
