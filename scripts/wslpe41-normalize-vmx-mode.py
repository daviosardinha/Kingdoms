#!/usr/bin/env python3
"""One-time exact-fresh-WSLPE VMX permission correction, NEVER recursive.

The already registered VMX was observed owner=current user, single link,
regular, 4473 bytes, mode 0771. Only this exact legacy mode can be
changed to 0600, with explicit operator approval and a private durable
receipt. Nothing in this file changes NICs, VM power, guest Windows or
shared networking. Host vmnet4 keeper check requires recent sudo -v.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kingdoms.wslpe41_management_nic import (
    INSTANCE, NicBlocked, _read_vmx, _write_atomic, host_operator_network_ready,
    identify, zero_vmware_guests,
)

OLD_MODE = 0o771
NEW_MODE = 0o600
APPROVAL = "NORMALIZE-ONLY-FRESH-WSLPE-VMX-MODE"
STATE = Path.home() / ".local/state/kingdoms-wslpe41-vmx-permissions" / INSTANCE
NIC_JOURNAL = Path.home() / ".local/state/kingdoms-wslpe41-mgmt-nic" / INSTANCE / "journal.json"


def preflight():
    if os.geteuid() == 0:
        raise NicBlocked("Run as non-root VMware Workstation owner")
    zero_vmware_guests()
    host_operator_network_ready()
    if NIC_JOURNAL.exists() or NIC_JOURNAL.is_symlink():
        raise NicBlocked("A prior NIC transaction journal exists; do not normalize permissions")
    target = identify(Path.home(), exact_legacy_0771_probe=True)
    metadata = target.vmx.lstat()
    if stat.S_IMODE(metadata.st_mode) not in (OLD_MODE, NEW_MODE):
        raise NicBlocked(f"Unexpected exact VMX mode {stat.S_IMODE(metadata.st_mode):04o}")
    return target, metadata


def normalize(expected_sha256: str, approval: str) -> None:
    if approval != APPROVAL:
        raise NicBlocked("Explicit exact-instance VMX mode authorization required")
    target, metadata = preflight()
    if expected_sha256 != target.digest:
        raise NicBlocked("Original VMX SHA256 no longer matches read-only plan")
    if stat.S_IMODE(metadata.st_mode) != OLD_MODE:
        raise NicBlocked("One-time mode normalization accepts ONLY original 0771")
    if STATE.exists() or STATE.is_symlink():
        raise NicBlocked("Permission-maintenance receipt already exists")
    STATE.mkdir(mode=0o700, parents=True)
    if (STATE.is_symlink() or STATE.stat().st_uid != os.getuid()
            or stat.S_IMODE(STATE.stat().st_mode) != 0o700):
        raise NicBlocked("Private receipt directory not trusted")

    record = {
        "schema": "kingdoms.wslpe41.vmx.mode.v1",
        "status": "prepared", "vmx": str(target.vmx),
        "original_sha256": target.digest, "old_mode": "0771", "new_mode": "0600",
    }
    receipt = STATE / "receipt.json"
    _write_atomic(receipt, json.dumps(record, sort_keys=True).encode("utf-8"), 0o600)

    # Open the exact VMX inode with O_NOFOLLOW; prove it still matches the plan,
    # then change mode on the same file descriptor (not a pathname that could
    # have been swapped after validation).
    zero_vmware_guests()
    fd = os.open(target.vmx, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        current = os.fstat(fd)
        if ((current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino)
                or stat.S_IMODE(current.st_mode) != OLD_MODE
                or current.st_uid != os.getuid() or current.st_nlink != 1):
            raise NicBlocked("VMX inode or original mode changed during guarded maintenance")
        snapshot = os.read(fd, len(target.original) + 1)
        if snapshot != target.original or hashlib.sha256(snapshot).hexdigest() != target.digest:
            raise NicBlocked("VMX contents changed after private receipt preparation")
        os.fchmod(fd, NEW_MODE)
        os.fsync(fd)
    finally:
        os.close(fd)

    verified = _read_vmx(target.vmx)
    if verified != target.original or stat.S_IMODE(target.vmx.lstat().st_mode) != NEW_MODE:
        raise NicBlocked("VMX normalized mode/contents not verified; preserve receipt")
    record["status"] = "committed"
    _write_atomic(receipt, json.dumps(record, sort_keys=True).encode("utf-8"), 0o600)
    print("[COMMITTED] Only fresh WSLPE VMX permissions normalized 0771 -> 0600")
    print("[VMX SHA256 UNCHANGED] " + target.digest)
    print("[RECEIPT] " + str(receipt))
    print("[NO VMX CONTENT CHANGE] Existing NAT and vmnet3 NICs preserved")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--approve", default="")
    args = parser.parse_args(argv)
    try:
        if args.plan:
            if args.expected_sha256 or args.approve:
                raise NicBlocked("Read-only plan takes no authorization parameters")
            target, metadata = preflight()
            print("[SCOPE] Fresh native bf5369-wslpe-vmware ONLY")
            print("[VMX] " + str(target.vmx))
            print(f"[OWNER UID] {metadata.st_uid}")
            print(f"[MODE] {stat.S_IMODE(metadata.st_mode):04o}")
            print("[SHA256] " + target.digest)
            print("[PLAN PASS] Exact original VMX registered; mode-normalization candidate verified")
            print("[NO CHANGES] No file, guest or VMware host configuration writes")
            return 0
        if not args.expected_sha256:
            raise NicBlocked("Pinned original VMX hash required")
        normalize(args.expected_sha256, args.approve)
        return 0
    except (NicBlocked, OSError, ValueError, KeyError) as exc:
        print("[BLOCKED] Exact WSLPE VMX permission maintenance: " + str(exc))
        print("[NO AUTOMATIC RETRY] Check private receipt and VMX state")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
