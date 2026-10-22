#!/usr/bin/env python3
"""WSLPE vmnet4 owner-approved shared-network maintenance entrypoint.

NO CHANGES without --apply and an exact approval token, pinned host SHA,
root privileges and independent zero-guest proof. Never shuts down VMs,
changes NORTH, configures global forwarding, or attaches a guest NIC.

This is for a separate explicit guest-free maintenance window, NOT for
readiness checks while the two Workstation guests remain running.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import pwd
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kingdoms.wslpe_management_vmnet_runtime import (
    STATE_ROOT, NETWORKING, VMNET, SUBNET, EXERCISE, EXERCISE_SUBNET,
    Vmnet4MaintenanceRuntime, running_zero,
)
from kingdoms.wslpe_management_vmnet_isolation import Vmnet4KernelIsolationVerifier
from kingdoms.wslpe_management_vmnet_transaction import (
    MAX_NETWORKING_BYTES, NetworkTransactionBlocked, _digest, _read_regular,
)

APPROVAL = "I_APPROVE_GUEST_FREE_VMNET4_MAINTENANCE"


def workspaces(owner: str) -> tuple[Path, ...]:
    try:
        account = pwd.getpwnam(owner)
    except KeyError as exc:
        raise NetworkTransactionBlocked("Invalid VMware Workstation owner") from exc
    if account.pw_uid == 0:
        raise NetworkTransactionBlocked("Root cannot own the original VMware library")
    home = Path(account.pw_dir)
    if not home.is_dir() or home.is_symlink():
        raise NetworkTransactionBlocked("Workstation user home is unavailable")
    return (
        home / "kingdoms-wslpe41-fresh/workspace",
        home / "kingdoms-lpe-standalone/workspace",
        home / "kingdoms-rebuild/workspace",
        home / "vmware/KINGDOMS-WSLPE41-LEARNER-TEST",
    )


def create_private_state_dir(root: Path) -> None:
    """Only after explicit authorization and guest-zero proof."""
    if root != STATE_ROOT:
        raise NetworkTransactionBlocked("Unexpected shared VMware state path")
    if root.is_symlink() or root.parent.is_symlink():
        raise NetworkTransactionBlocked("Untrusted state directory")
    for directory in (root.parent, root):
        if not directory.exists():
            if directory.is_symlink():
                raise NetworkTransactionBlocked("Unsafe state directory link")
            directory.mkdir(mode=0o700)
        meta = directory.lstat()
        if not stat.S_ISDIR(meta.st_mode) or meta.st_uid != 0:
            raise NetworkTransactionBlocked("State directory is not root owned")
        if directory == root and stat.S_IMODE(meta.st_mode) != 0o700:
            raise NetworkTransactionBlocked("Private journal directory requires 0700")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true",
                      help="Owner-authorized guest-free allocation (changes host networking)")
    mode.add_argument("--recover", action="store_true",
                      help="Recover only an incomplete journal; no general uninstall")
    mode.add_argument("--status", action="store_true",
                      help="Read-only current networking checksum (no guest mutation)")
    parser.add_argument("--owner", required=True, help="Original nonroot Workstation user")
    parser.add_argument("--expected-sha256",
                        help="Exact 64-digit current /etc/vmware/networking SHA256 for apply")
    parser.add_argument("--approve", default="", help="Explicit maintenance acknowledgement")
    args = parser.parse_args(argv)

    try:
        roots = workspaces(args.owner)
        if args.status:
            if args.approve or args.expected_sha256:
                raise NetworkTransactionBlocked("Status must remain read only")
            raw, _ = _read_regular(NETWORKING, MAX_NETWORKING_BYTES)
            print(f"[READ ONLY] VMware networking SHA256={_digest(raw)}")
            print(f"[NOT INSTALLED] This command does not allocate or approve {VMNET}")
            return 0

        if os.geteuid() != 0:
            raise NetworkTransactionBlocked("Root required for VMware maintenance")
        if args.approve != APPROVAL:
            raise NetworkTransactionBlocked("Exact guest-free maintenance approval required")
        if args.apply and not re.fullmatch(r"[0-9a-f]{64}", args.expected_sha256 or ""):
            raise NetworkTransactionBlocked("Pinned live host networking SHA256 required")
        if args.recover and args.expected_sha256:
            raise NetworkTransactionBlocked("Recovery never takes a new source hash")

        # This gate MUST execute before creating any state directory.
        running_zero(owner=args.owner)
        for root in roots:
            if root.is_symlink() or not root.is_dir():
                raise NetworkTransactionBlocked(f"Missing/linked VMware workspace: {root}")

        if args.recover and not (STATE_ROOT / "journal.json").is_file():
            raise NetworkTransactionBlocked("No incomplete vmnet4 journal to recover")

        create_private_state_dir(STATE_ROOT)
        verifier = Vmnet4KernelIsolationVerifier()
        runtime = Vmnet4MaintenanceRuntime(
            owner=args.owner, roots=roots,
            isolation_acceptance=verifier.verify,
        )
        transaction = runtime.assemble()
        if args.recover:
            restored = transaction.recover()
            print(f"[RECOVERED] Exact original VMware networking SHA256={restored}")
            print("[NO VMX CHANGES] No guest adapter or Windows operation performed")
            return 0

        actual, _ = _read_regular(NETWORKING, MAX_NETWORKING_BYTES)
        if _digest(actual) != args.expected_sha256:
            raise NetworkTransactionBlocked("Networking changed since source approval")
        committed = transaction.apply(
            vmnet=VMNET, subnet=SUBNET,
            exercise_vmnet=EXERCISE, exercise_subnet=EXERCISE_SUBNET,
            expected_source_sha256=args.expected_sha256,
            maintenance_approved=True,
        )
        print(f"[COMMITTED] vmnet4 source SHA256={committed}")
        print("[SCOPE] Host-only NIC and kernel nonrouting accepted at this instant")
        print("[NOT PROVEN] Windows NIC/WinRM, end-to-end isolation and reboot persistence")
        return 0
    except (NetworkTransactionBlocked, OSError, UnicodeError, ValueError) as exc:
        print(f"[BLOCKED] VMware management maintenance refused: {exc}")
        print("[NO AUTOMATIC GUEST SHUTDOWN] Investigate journal before retrying")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
