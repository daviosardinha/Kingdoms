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

STAGE2 = ROOT / "scripts/wslpe-stage2-inspect.py"
NAT_PREVIEW = ROOT / "scripts/wslpe-p1c-north-cutover-preview.py"


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
    args = parser.parse_args()
    print("KINGDOMS WSLPE | OWNER-SCOPED HOST RECOVERY REHEARSAL")
    print("[NO VM WRITES] No NAT cutover, VMware restart, VMX edits or NORTH operations")
    try:
        vmx, uid, user = exact_vmware_owner()
        preview = mod(NAT_PREVIEW, "wslpe_owner_nat_preview")
        preview.north_source_contract()
        preview.running_exact(vmx)
        print("[PASS] Exact WSLPE VMware owner and running VMX validated")
        if args.rehearse:
            unit = rehearse_owner_timer(uid, user)
            print(f"[PASS] WSLPE_OWNER_HOST_TIMER_FIRED=TRUE ({unit})")
            print("[PASS] Systemd host timer runs under exact WSLPE VMX owner")
        else:
            print("[PREVIEW] Host owner rollback timer has NOT been exercised")
    except (OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired) as exc:
        print(f"[BLOCKED] {type(exc).__name__}; no VMware/NORTH changes")
        return 1
    print("[NOT VERIFIED] Owner-context vmrun stop/start and exact VMX offline restore")
    print("[NOT VERIFIED] Host reboot/firewall persistence and ARP/L2 isolation")
    print("[RELEASE BLOCKED] WSLPE NAT cutover remains unauthorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
