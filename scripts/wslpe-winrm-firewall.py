#!/usr/bin/env python3
"""WSLPE-only protective nftables input guard for the VMware NAT WinRM port.

This is NOT a replacement for the proven NORTH network lifecycle. The nft
table affects only non-loopback INPUT packets addressed to the current WSLPE
WinRM forwarded TCP port. No vmnet/NAT service restarts, no VM state changes.
--apply requires the exact native port. --migrate-from-port requires the
independently verified original WSLPE-only rule, the current native port and
explicit confirmation. It replaces only that one rule by handle (atomic
nftables transaction). Never deletes a table or touches another lab.
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
from kingdoms.wslpe_winrm_guard import (
    TABLE, firewall_batch, migrated_firewall_batch,
    require_vmware_nat_owner, verify_firewall_json,
)

INSPECTOR_FILE = ROOT / "scripts/wslpe-stage2-inspect.py"
SPEC = importlib.util.spec_from_file_location("wslpe_guard_inspector", INSPECTOR_FILE)
if SPEC is None or SPEC.loader is None:
    raise SystemExit("[BLOCKED] WSLPE native instance inspector missing")
INSPECTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSPECTOR)


def run(command: list[str], *, data: str | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            command, input=data, capture_output=True, text=True,
            check=False, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"Cannot safely inspect {command[0]} state: {type(exc).__name__}") from exc


def installed_guard(port: int) -> bool:
    output = run(["nft", "-j", "list", "table", "inet", TABLE])
    if output.returncode != 0:
        if "No such file or directory" in output.stderr:
            return False
        raise ValueError("Cannot inspect nftables table as root")
    if not verify_firewall_json(output.stdout, port):
        raise ValueError(
            "Existing WSLPE nftables table does not exactly match this forwarded port. "
            "Refusing to overwrite or append rules."
        )
    return True


def native_port() -> tuple[int, str]:
    instance, info = INSPECTOR.find_instance(INSPECTOR.WORKSPACE)
    INSPECTOR.locate_registered_vm(instance)
    port = INSPECTOR.forwarded_winrm_port(instance)
    if info.get("lab") != "WSLPE":
        raise ValueError("Instance is not WSLPE")
    return port, info["id"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--apply", action="store_true",
        help="Add a scoped, in-memory host INPUT drop for non-loopback access",
    )
    action.add_argument(
        "--migrate-from-port", type=int, metavar="OLD_PORT",
        help="Explicitly replace the one verified WSLPE-only guard on OLD_PORT",
    )
    parser.add_argument(
        "--confirm-port", type=int,
        help="Explicit operator approval of the actual dynamically discovered TCP port",
    )
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.exit(1, "[BLOCKED] Run this diagnostic as root using sudo.\n")
    try:
        port, instance_name = native_port()
        output = run(["ss", "-H", "-lntp"])
        if output.returncode != 0:
            raise ValueError("Cannot inspect privileged TCP listener ownership")
        owner_verified = require_vmware_nat_owner(output.stdout, port)
        if args.migrate_from_port is not None:
            # Existing table can only be updated by explicit, exact old-port
            # provenance. Do not fall into normal --apply if it differs.
            if args.confirm_port != port or not owner_verified:
                raise ValueError("Native current port confirmation or VMware NAT owner missing")
            snapshot = run(["nft", "-j", "list", "table", "inet", TABLE])
            if snapshot.returncode != 0:
                raise ValueError("Existing WSLPE guard unavailable for migration")
            batch = migrated_firewall_batch(
                snapshot.stdout, args.migrate_from_port, port
            )
            checked = run(["nft", "-c", "-f", "-"], data=batch)
            if checked.returncode != 0:
                raise ValueError("nftables rejected checked WSLPE-only rule replacement")
            # Detect intervening changes before mutation. The nft rule-handle
            # transaction also fails if the original rule was removed.
            latest = run(["nft", "-j", "list", "table", "inet", TABLE])
            if latest.returncode != 0 or latest.stdout != snapshot.stdout:
                raise ValueError("WSLPE guard changed since migration preflight")
            applied = run(["nft", "-f", "-"], data=batch)
            if applied.returncode != 0:
                raise ValueError("WSLPE-only rule replacement failed")
            if not installed_guard(port):
                raise ValueError("Post-migration WSLPE guard verification failed")
            print(f"[PASS] Exact WSLPE input guard migrated from TCP/"
                  f"{args.migrate_from_port} to TCP/{port}")
            print("[IMPORTANT] In-memory rule only; external reachability and "
                  "reboot persistence remain unverified")
            print("[NO CHANGES] Other nftables tables, VMware NAT and NORTH untouched")
            return 0
        guarded = installed_guard(port)
        print(f"KINGDOMS WSLPE HOST WINRM GUARD | instance={instance_name}")
        print(f"[INFO] Guest WinRM TCP 5985 -> VMware NAT host TCP {port}")
        print(f"[INFO] vmnet-nat exact wildcard listener confirmed: {owner_verified}")
        print(f"[INFO] Dedicated WSLPE nftables rule verified: {guarded}")
        if not owner_verified:
            raise ValueError(
                "Expected a unique vmnet-nat IPv4 wildcard listener. "
                "Ownership changed or is unproven; refusing acceptance."
            )
        if guarded:
            print("[PASS] Non-loopback traffic to this specific host port is dropped")
            print("[NOT VERIFIED] External independent reachability; reboot persistence")
            print("[NO CHANGES] Existing firewall, VMware and NORTH unchanged")
            return 0
        if not args.apply:
            print("[BLOCKED] Live wildcard WinRM forward is not restricted")
            print(f"[NEXT] sudo python3 scripts/wslpe-winrm-firewall.py "
                  f"--apply --confirm-port {port}")
            return 1
        if args.confirm_port != port:
            raise ValueError("Exact port confirmation missing/mismatched")
        if args.confirm_port is None or not 1 <= args.confirm_port <= 65535:
            raise ValueError("Invalid approved port")
        apply = run(["nft", "-f", "-"], data=firewall_batch(port))
        if apply.returncode != 0:
            raise ValueError(
                "nftables rejected the WSLPE-only guard; inspect rules manually. "
                "No VMware/NORTH changes made."
            )
        if not installed_guard(port):
            raise ValueError("Post-apply nftables verification failed")
        print(f"[PASS] WSLPE-only non-loopback INPUT TCP/{port} DROP verified")
        print("[IMPORTANT] Rule is live but not reboot-persistent. Never expose learners.")
        print("[NO CHANGES] VMware vmnets, shared NAT daemon and NORTH untouched")
        return 0
    except (ValueError, OSError) as exc:
        print(f"[BLOCKED] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
