#!/usr/bin/env python3
"""Read-only, powered-OFF WSLPE native registration and exercise NIC acceptance.

Intended for a guest-free VMware maintenance window; NOT a running guest
freshness attestation. Never invokes vmrun start, guest WinRM or VMware service.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kingdoms.wslpe_management_vmnet_plan import native_exercise_binding
from kingdoms.wslpe_management_vmnet_registry import (
    _regular, MAX_INVENTORY, MAX_VMX, parse_workstation_library,
)
from kingdoms.wslpe_management_vmnet_transaction import (
    _read_regular, MAX_NETWORKING_BYTES, NetworkTransactionBlocked,
)

def offline_native_contract(instance: Path, library: Path, networking: Path) -> tuple[str, str, str]:
    if instance.is_symlink() or not instance.is_dir() or not instance.is_absolute():
        raise NetworkTransactionBlocked("Native instance directory missing, linked or relative")
    if instance.name != "bf5369-wslpe-vmware":
        raise NetworkTransactionBlocked("Wrong fresh WSLPE instance")
    manifest = instance / "instance.json"
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 200_000:
        raise NetworkTransactionBlocked("Unsafe native instance metadata")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError) as exc:
        raise NetworkTransactionBlocked("Native instance manifest unreadable") from exc
    if (not isinstance(data, dict) or data.get("id") != instance.name
        or data.get("lab") != "WSLPE"
        or data.get("provider") != "vmware"
        or data.get("provisioner") != "local"
        or data.get("status") != "ready for provisioning"
        or data.get("extensions")
        or data.get("ip_range") != "172.28.232"):
        raise NetworkTransactionBlocked("Fresh instance identity/configuration mismatch")
    provider = instance / "provider"
    if provider.is_symlink() or not provider.is_dir():
        raise NetworkTransactionBlocked("Native VMware provider unavailable")
    registration = provider / ".vagrant/machines/WSLPE-WS01/vmware_desktop/id"
    if registration.is_symlink() or not registration.is_file() or registration.stat().st_size > 10_000:
        raise NetworkTransactionBlocked("Native Vagrant VMware VMX registration missing")
    try:
        path_raw = registration.read_text(encoding="utf-8").strip()
        vmx = Path(path_raw)
        if (not vmx.is_absolute() or vmx.is_symlink()
            or vmx.resolve(strict=True) != vmx or not vmx.is_relative_to(provider.resolve())
            or vmx.suffix.lower() != ".vmx"):
            raise NetworkTransactionBlocked("Native VMX is foreign or linked")
        vmx_text = _regular(vmx, MAX_VMX)
        registrations = parse_workstation_library(_regular(library, MAX_INVENTORY))
        if registrations.count(vmx) != 1:
            raise NetworkTransactionBlocked("Native VMX not uniquely registered in Workstation library")
        raw_network, _ = _read_regular(networking, MAX_NETWORKING_BYTES)
        exercise, subnet = native_exercise_binding(
            vmx_text, data["ip_range"], raw_network.decode("utf-8"))
    except (UnicodeError, OSError, ValueError) as exc:
        raise NetworkTransactionBlocked("Cannot establish native VMware offline contract") from exc
    if (exercise, subnet) != ("vmnet3", "172.28.232.0/24"):
        raise NetworkTransactionBlocked("Fresh exercise NIC is not the expected vmnet3")
    return str(vmx), exercise, subnet


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    print("[READ ONLY] Native WSLPE powered-off VMware registration contract")
    print("[NO CHANGES] No VM boot, shutdown or shared VMware network operations")
    try:
        vmx, exercise, subnet = offline_native_contract(
            args.instance_dir, Path.home() / ".vmware/inventory.vmls",
            Path("/etc/vmware/networking"))
    except (NetworkTransactionBlocked, ValueError, OSError) as exc:
        print(f"[BLOCKED] Native offline registration: {exc}")
        return 2
    print("[PASS] Unique fresh native Vagrant VMX matches Workstation user library")
    print(f"[NATIVE OFFLINE] Exact WSLPE exercise: {exercise} {subnet}")
    print("[NOT PROVEN] Windows guest freshness, authenticated operator access or 41/41")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
