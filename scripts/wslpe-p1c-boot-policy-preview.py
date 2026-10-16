#!/usr/bin/env python3
"""WSLPE-only dynamic WinRM + host-filter boot candidate (READ ONLY).

No systemd unit installation, nft apply, restart, VM/Vagrant/NORTH changes.
"""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kingdoms.wslpe_boot_policy import make_boot_candidate, boot_protection_readiness
from kingdoms.wslpe_winrm_guard import (
    TABLE as GUARD_TABLE, verify_firewall_json, require_vmware_nat_owner
)
PREVIEW = ROOT / "scripts/wslpe-p1c-north-cutover-preview.py"


def import_preview():
    spec = importlib.util.spec_from_file_location("wslpe_boot_preview_source", PREVIEW)
    if spec is None or spec.loader is None:
        raise ValueError("WSLPE-only preview missing")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def command(*argv):
    r = subprocess.run(argv, capture_output=True, text=True,
                       timeout=20, check=False)
    if r.returncode:
        raise ValueError("Privileged WSLPE boot guard inspection unavailable")
    return r.stdout


def verify_live_guard(port: int) -> bool:
    r = subprocess.run(["sudo", "-n", "nft", "-j", "list", "table", "inet", GUARD_TABLE],
                       capture_output=True, text=True, timeout=20, check=False)
    if r.returncode:
        # An absent guard is a BLOCKER, not an unauthorized automatic install.
        return False
    if not verify_firewall_json(r.stdout, port):
        raise ValueError("Existing WSLPE guard has changed or protects stale port")
    return True


def main() -> int:
    print("KINGDOMS WSLPE | LIVE-PORT BOOT FIREWALL PLAN (READ ONLY)")
    print("[NO CHANGES] No nft writes, systemd installs, NAT/VMX or NORTH operations")
    try:
        preview = import_preview()
        preview.north_source_contract()
        result = preview.collect()
        vmx = result["vmx"]
        if vmx.is_symlink() or not vmx.is_file():
            raise ValueError("Registered WSLPE VMX not trustworthy")
        port = result["port"]
        ss = command("sudo", "-n", "ss", "-H", "-lntp")
        if not require_vmware_nat_owner(ss, port):
            raise ValueError("Dynamic WinRM listener not verified as vmnet-nat")
        # The existing WSLPE metadata reader is the only source for subnet.
        stage = preview.module(preview.STAGE2, "wslpe_boot_native")
        instance, meta = stage.find_instance(stage.WORKSPACE)
        if stage.locate_registered_vm(instance).resolve() != vmx.resolve():
            raise ValueError("Registered WSLPE VMX changed")
        prefix = meta["ip_range"]
        candidate = make_boot_candidate(
            port, result["vmnet"], f"{prefix}.0/24",
            result["host"], result["guest"]
        )
        guard_ok = verify_live_guard(port)
        print(f"[PASS] Exact native WSLPE VMX={vmx.name}")
        print(f"[PASS] Current forwarded WinRM port TCP/{port} belongs to vmnet-nat")
        print(f"[PASS] Candidate has exact WSLPE guard+filter SHA256={candidate.sha256}")
        print(f"[INFO] Existing exact-port guard verified={guard_ok}")
        blocked = boot_protection_readiness(
            discovered_port=port, guarded_port=port,
            guard_persists=False, filter_persists=False,
            vmware_start_is_ordered=False,
        )
        for issue in blocked:
            print(f"[RELEASE BLOCKED] {issue}")
        print("[RESULT] BOOT_POLICY_PREVIEW=PASS; BOOT_INSTALL_AUTHORIZED=FALSE")
        return 0
    except (OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired) as exc:
        print(f"[BLOCKED] {type(exc).__name__}; no host or guest changes")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
