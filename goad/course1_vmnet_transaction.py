"""Transactional file layer for the existing Kingdoms Course 1 vmnet setup.

This module is deliberately NOT wired into a host-applying CLI yet.
It accepts injected VMware stop/start and live verification callbacks,
so source regressions can prove rollback and ownership safety without
running VMware or touching /etc/vmware.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Callable

from goad.course1_vmnet_config import render_vmnet_config


class VmnetTransactionError(RuntimeError):
    pass


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _plain_regular(path: Path) -> os.stat_result:
    if path.is_symlink() or not path.is_file():
        raise VmnetTransactionError("VMware networking must be a plain regular file")
    data = path.stat()
    if not stat.S_ISREG(data.st_mode) or data.st_nlink != 1:
        raise VmnetTransactionError("Unsafe or hard-linked VMware networking file")
    return data


def _safe_directory(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        raise VmnetTransactionError("Backup/ownership directory is missing or unsafe")
    if path.stat().st_mode & 0o022:
        raise VmnetTransactionError("Backup/ownership directory is group/world writable")


def _atomic_bytes(path: Path, content: bytes, metadata: os.stat_result) -> None:
    """Preserve file owner/mode and only replace within the same directory."""
    fd, tmp = tempfile.mkstemp(prefix=".kingdoms-course1-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), stat.S_IMODE(metadata.st_mode))
            os.fchown(output.fileno(), metadata.st_uid, metadata.st_gid)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(tmp, path)
        fd_dir = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd_dir)
        finally:
            os.close(fd_dir)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def execute_testable_network_transaction(
    networking: Path,
    backup_root: Path,
    owner_record: Path,
    layout: dict,
    expected_original_sha256: str,
    restart_networks: Callable[[], None],
    verify_live_networks: Callable[[], None],
) -> dict:
    """Execute a single, callback-driven atomic transaction on testable paths.

    Safety contract:
    - A caller has already proven VMware VM/process and vmnet ownership.
    - The baseline must match the previously reviewed plan hash.
    - No existing ownership record is overwritten.
    - A permanent backup is written before any config replacement.
    - Failure restores only if config still matches this transaction's bytes.
      Concurrent third-party edits are never overwritten.
    - The callbacks are supplied by a separately reviewed runtime controller,
      NOT by this module's CLI (there is no mutating CLI).
    """
    networking = Path(networking)
    backup_root = Path(backup_root)
    owner_record = Path(owner_record)
    metadata = _plain_regular(networking)
    _safe_directory(networking.parent)
    _safe_directory(backup_root)
    _safe_directory(owner_record.parent)
    if owner_record.exists() or owner_record.is_symlink():
        raise VmnetTransactionError("Existing vmnet ownership record needs reconciliation")
    original = networking.read_bytes()
    if _digest(original) != expected_original_sha256:
        raise VmnetTransactionError("VMware config changed after plan review")
    try:
        proposed = render_vmnet_config(original.decode("utf-8"), layout).encode("utf-8")
    except (UnicodeDecodeError, ValueError) as exc:
        raise VmnetTransactionError("Unable to safely render proposed VMware settings") from exc

    backup_name = "north-" + _digest(original)[:16] + "-"
    backup_folder = Path(tempfile.mkdtemp(prefix=backup_name, dir=backup_root))
    os.chmod(backup_folder, 0o700)
    backup = backup_folder / "networking.original"
    with backup.open("xb") as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(original)
        output.flush()
        os.fsync(output.fileno())

    changed = False
    try:
        if networking.read_bytes() != original:
            raise VmnetTransactionError("VMware config changed during backup")
        _atomic_bytes(networking, proposed, metadata)
        changed = True
        restart_networks()
        verify_live_networks()
        if networking.read_bytes() != proposed:
            raise VmnetTransactionError("VMware modified networking after verification")
        record = {
            "profile": "NORTH",
            "network_base": layout["network_base"],
            "vmnets": {name: zone["vmnet"] for name, zone in layout["segments"].items()},
            "baseline_sha256": _digest(original),
            "installed_sha256": _digest(proposed),
            "backup": str(backup),
        }
        # Exclusive create; never replace someone else's ownership record.
        with owner_record.open("x", encoding="utf-8") as output:
            os.fchmod(output.fileno(), 0o600)
            json.dump(record, output, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
        return record
    except Exception as original_error:
        if changed:
            # Do not destroy changes made by VMware or another administrator.
            # Save the backup for manual diagnosis if exact restoration is unsafe.
            if networking.read_bytes() != proposed:
                raise VmnetTransactionError(
                    f"Concurrent/VMware mutation detected; original preserved at {backup}; "
                    "refusing unsafe automatic rollback"
                ) from original_error
            _atomic_bytes(networking, original, metadata)
            try:
                restart_networks()
            except Exception as restore_error:
                raise VmnetTransactionError(
                    f"Configuration restored but network restart failed; backup: {backup}"
                ) from restore_error
        raise VmnetTransactionError(
            f"VMware setup transaction failed safely; backup preserved at {backup}"
        ) from original_error
