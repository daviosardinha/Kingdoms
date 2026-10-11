#!/usr/bin/env python3
"""Remove only verified stale GOAD and SQL-clone VMware Workstation library entries.

Plan by default; destructive registry edit requires 'apply --confirm'.
Never deletes VMX files, virtual disks, snapshots or unrelated VMs.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

GOAD_MACHINES = frozenset({
    "GOAD-DC01", "GOAD-DC02", "GOAD-DC03",
    "GOAD-SRV02", "GOAD-SRV03", "GOAD-WS01", "GOAD-ROUTER",
})
CONFIG = re.compile(r'^\s*vmlist(\d+)\.config\s*=\s*"([^"]*)"\s*$')
PROPERTY = re.compile(r'^\s*vmlist(\d+)\.')
VMX_SUFFIX = re.compile(r'^[a-f0-9-]{36}/[A-Za-z0-9_.-]+\.vmx$')
EXPECTED_SLOTS = frozenset(range(4, 12))


def target_slots(text: str, home: Path) -> frozenset[int]:
    root = home / "Documents/GOAD_NOMAD/workspace/6fdd5a-goad-vmware/provider/.vagrant/machines"
    clone = home / "vmware/KINGDOMS-SQL-CLONE/KINGDOMS-SQL-CLONE.vmx"
    configs = {}
    for line in text.splitlines():
        found = CONFIG.match(line)
        if not found:
            continue
        slot, path = int(found.group(1)), found.group(2)
        if slot in configs:
            raise ValueError(f"Duplicate VMware library slot {slot}")
        configs[slot] = path

    selected = set()
    machines = set()
    clone_seen = False
    for slot, path in configs.items():
        target = Path(path)
        is_clone = target == clone
        machine = None
        try:
            tail = target.relative_to(root).parts
            if len(tail) == 4 and tail[0] in GOAD_MACHINES and tail[1] == "vmware_desktop":
                if VMX_SUFFIX.fullmatch("/".join(tail[2:])):
                    machine = tail[0]
        except ValueError:
            pass
        if not (is_clone or machine):
            continue
        if target.exists() or target.is_symlink():
            raise ValueError(f"VMX still exists; cannot remove registration: {target}")
        if machine:
            if machine in machines:
                raise ValueError(f"Duplicate registration for {machine}")
            machines.add(machine)
        if is_clone:
            if clone_seen:
                raise ValueError("Duplicate SQL clone registration")
            clone_seen = True
        selected.add(slot)

    if machines != GOAD_MACHINES or not clone_seen or selected != EXPECTED_SLOTS:
        raise ValueError(
            "Registration set differs from the proven seven GOAD machines "
            "plus SQL clone in slots 4-11; refuse editing"
        )
    return frozenset(selected)


def strip_slots(text: str, slots: frozenset[int]) -> str:
    return "".join(
        line for line in text.splitlines(keepends=True)
        if not ((match := PROPERTY.match(line)) and int(match.group(1)) in slots)
    )


def confirm_no_vmware() -> None:
    check = subprocess.run(["vmrun", "-T", "ws", "list"],
                           capture_output=True, text=True, timeout=20)
    if check.returncode != 0 or check.stdout.strip() != "Total running VMs: 0":
        raise ValueError("VMware running-guest state is not exactly zero")
    for name in ("vmware", "vmware-vmx"):
        process = subprocess.run(["pgrep", "-x", name],
                                 capture_output=True, text=True, timeout=10)
        if process.returncode != 1:
            raise ValueError(f"VMware application/guest process detected or unchecked: {name}")


def apply(registry: Path, original: str, cleaned: str) -> Path:
    confirm_no_vmware()
    # Refuse registry changed between planning and update.
    if registry.read_text(encoding="utf-8") != original:
        raise ValueError("VMware library changed during cleanup")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = registry.with_name("inventory.vmls.backup-" + stamp)
    with backup.open("x", encoding="utf-8") as handle:
        handle.write(original)
    backup.chmod(0o600)

    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=registry.parent, delete=False
        ) as handle:
            tmp = Path(handle.name)
            os.fchmod(handle.fileno(), stat.S_IMODE(registry.stat().st_mode))
            handle.write(cleaned)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, registry)
        tmp = None
        if registry.read_text(encoding="utf-8") != cleaned:
            raise ValueError("Registry verification mismatch")
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink()
    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "apply"))
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    home = Path.home()
    registry = home / ".vmware/inventory.vmls"
    try:
        if not registry.is_file() or registry.is_symlink():
            raise ValueError("VMware library absent or symlinked")
        original = registry.read_text(encoding="utf-8")
        slots = target_slots(original, home)
        cleaned = strip_slots(original, slots)
        print("[VERIFIED] 7 deleted original GOAD guests + 1 deleted SQL clone")
        print("[TARGETS] " + ", ".join("vmlist" + str(n) for n in sorted(slots)))
        if args.action == "plan":
            print("[PLAN ONLY] No files changed")
            return 0
        if not args.confirm:
            raise ValueError("Apply requires --confirm")
        backup = apply(registry, original, cleaned)
        print("[PASS] Eight stale VMware library registrations removed")
        print("[BACKUP] " + str(backup))
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print("[BLOCKED] " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
