#!/usr/bin/env python3
"""Remove ONLY the seven retired Kingdoms VMware networks, with rollback.

No VM destruction, service deletion, registry rewriting, or disk deletion.
Use 'plan' first; 'apply --confirm' requires root and a zero-running-VM
check. VMware's default vmnet1/vmnet8 are never modified.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

OWNED = frozenset({10, 11, 12, 13, 20, 30, 99})
NETWORKING = Path("/etc/vmware/networking")
NETMAP = Path("/etc/vmware/netmap.conf")
VMWARE_NETWORKS = Path("/usr/bin/vmware-networks")
VNET_KEY = re.compile(r"^\s*answer\s+VNET_(\d+)_")
VNET_LABEL = re.compile(r"^\s*#\s*vmnet(\d+):", re.IGNORECASE)
REGISTERED_VMX = re.compile(r'^\s*vmlist\d+\.config\s*=\s*"([^"]+)"')
ATTACHED_NET = re.compile(
    r'^\s*ethernet\d+\.vnet\s*=\s*"(vmnet\d+)"',
    re.IGNORECASE | re.MULTILINE,
)


def render(clean_source: str) -> tuple[str, set[int]]:
    removed = set()
    output = []
    for line in clean_source.splitlines(keepends=True):
        key = VNET_KEY.match(line)
        label = VNET_LABEL.match(line)
        net = int(key.group(1)) if key else (int(label.group(1)) if label else None)
        if net in OWNED:
            removed.add(net)
            continue
        output.append(line)
    return "".join(output), removed


def shell(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True,
                          check=False, timeout=timeout)


def no_running_guests() -> None:
    v = shell("vmrun", "-T", "ws", "list")
    if v.returncode or not re.search(r"(?m)^Total running VMs:\s*0\s*$", v.stdout):
        raise RuntimeError("VMware running VM inventory is not exactly zero")
    p = shell("pgrep", "-x", "vmware-vmx")
    if p.returncode == 0:
        raise RuntimeError("vmware-vmx processes still exist; stop guests first")
    if p.returncode != 1:
        raise RuntimeError("could not reliably check vmware-vmx processes")


def powered_off_inventory_conflicts(home: Path) -> list[str]:
    inventory = home / ".vmware" / "inventory.vmls"
    if not inventory.is_file() or inventory.is_symlink():
        return []
    conflicts = []
    for line in inventory.read_text(encoding="utf-8", errors="replace").splitlines():
        match = REGISTERED_VMX.match(line)
        if not match:
            continue
        vmx = Path(match.group(1))
        if not vmx.is_file():
            continue
        if vmx.is_symlink():
            conflicts.append(f"Symlinked registered VMX requires manual review: {vmx}")
            continue
        config = vmx.read_text(encoding="utf-8", errors="replace")
        attached = {
            int(net[5:]) for net in ATTACHED_NET.findall(config)
            if net.lower().startswith("vmnet") and net[5:].isdigit()
        }
        if attached & OWNED:
            conflicts.append(f"Registered VM uses retired vmnet: {vmx}")
    return conflicts


def check_targets(source: str, desired: str, seen: set[int]) -> None:
    if not seen:
        raise RuntimeError("No retired vmnet keys or labels found: nothing to remove")
    for n in (1, 8):
        original = [l for l in source.splitlines() if VNET_KEY.match(l) and
                    int(VNET_KEY.match(l).group(1)) == n]
        final = [l for l in desired.splitlines() if VNET_KEY.match(l) and
                 int(VNET_KEY.match(l).group(1)) == n]
        if original != final:
            raise RuntimeError(f"Default vmnet{n} configuration would change")
    if any(VNET_KEY.match(l) and int(VNET_KEY.match(l).group(1)) in OWNED
           for l in desired.splitlines()):
        raise RuntimeError("Retired vmnet keys remain in proposed configuration")


def apply(source: str, new_source: str, backup_root: Path) -> None:
    if os.geteuid() != 0:
        raise RuntimeError("Apply requires root; use sudo after reviewing 'plan'")
    no_running_guests()
    operator_home = Path(os.environ.get("SUDO_USER_HOME", "")).expanduser()
    if not str(operator_home).startswith("/") or not operator_home.is_dir():
        raise RuntimeError("Set SUDO_USER_HOME to the real user's existing home")
    conflicts = powered_off_inventory_conflicts(operator_home)
    if conflicts:
        raise RuntimeError("; ".join(conflicts))
    if not VMWARE_NETWORKS.is_file():
        raise RuntimeError("VMware network control utility is missing")
    if not NETWORKING.is_file() or NETWORKING.is_symlink():
        raise RuntimeError("VMware networking config missing or symlinked")

    backup_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    shutil.copy2(NETWORKING, backup_root / "networking")
    if NETMAP.is_file():
        shutil.copy2(NETMAP, backup_root / "netmap.conf")
    print(f"[BACKUP] {backup_root}", flush=True)

    stopped = False
    try:
        result = shell(str(VMWARE_NETWORKS), "--stop", timeout=90)
        if result.returncode:
            raise RuntimeError(f"vmware-networks --stop failed: {result.stderr[-600:]}")
        stopped = True
        NETWORKING.write_text(new_source, encoding="utf-8")
        result = shell(str(VMWARE_NETWORKS), "--start", timeout=90)
        if result.returncode:
            raise RuntimeError(f"vmware-networks --start failed: {result.stderr[-600:]}")
        reloaded = NETWORKING.read_text(encoding="utf-8")
        if any(VNET_KEY.match(l) and int(VNET_KEY.match(l).group(1)) in OWNED
               for l in reloaded.splitlines()):
            raise RuntimeError("VMware recreated retired VNET entries")
        for n in (1, 8):
            old = [l for l in source.splitlines() if VNET_KEY.match(l) and
                   int(VNET_KEY.match(l).group(1)) == n]
            now = [l for l in reloaded.splitlines() if VNET_KEY.match(l) and
                   int(VNET_KEY.match(l).group(1)) == n]
            if old != now:
                raise RuntimeError(f"VMware changed default vmnet{n} configuration")
        print("[PASS] VMware network definitions removed; defaults preserved")
    except Exception:
        print("[ROLLBACK] Restoring saved VMware networking settings", file=sys.stderr)
        shutil.copy2(backup_root / "networking", NETWORKING)
        if stopped:
            try:
                shell(str(VMWARE_NETWORKS), "--stop", timeout=90)
                r = shell(str(VMWARE_NETWORKS), "--start", timeout=90)
                print(f"[ROLLBACK] VMware restart exit={r.returncode}", file=sys.stderr)
            except Exception as exc:
                print(f"[ROLLBACK ERROR] {exc}", file=sys.stderr)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "apply"))
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--backup-root", type=Path)
    args = parser.parse_args()
    try:
        if not NETWORKING.is_file():
            raise RuntimeError("Missing /etc/vmware/networking")
        source = NETWORKING.read_text(encoding="utf-8")
        desired, seen = render(source)
        check_targets(source, desired, seen)
        print(f"Retired vmnets: {', '.join('vmnet'+str(n) for n in sorted(seen))}")
        print(f"Remaining configuration lines: {len(desired.splitlines())}")
        if args.action == "plan":
            print("[PLAN ONLY] No host changes. Inspect VMware VMX ownership first.")
            return 0
        if not args.confirm or args.backup_root is None:
            raise RuntimeError("Apply requires --confirm and --backup-root")
        apply(source, desired, args.backup_root)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"[BLOCKED] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
