"""Lock and durable journal for existing Kingdoms NORTH vmnet transactions.

No host apply entrypoint. Read-only reconciliation of interrupted runs.
All writers hold one permanent flock inode so two NORTH instances can never
apply competing /etc/vmware/networking changes at the same time.
"""
from __future__ import annotations

import fcntl
import json
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

ACTIVE = frozenset({"PREPARED", "WRITTEN", "VERIFYING", "MANUAL_RECONCILIATION"})
TERMINAL = frozenset({"COMMITTED", "ROLLED_BACK"})
ALL_STATES = ACTIVE | TERMINAL


class VmnetJournalError(RuntimeError):
    pass


@contextmanager
def exclusive_vmnet_lock(backup_root: Path):
    """Acquire one stable, fail-closed lock file; never unlink its inode."""
    root = Path(backup_root)
    if not root.is_dir() or root.is_symlink() or root.stat().st_mode & 0o022:
        raise VmnetJournalError("Unsafe global VMware transaction directory")
    path = root / ".north-network.lock"
    flags = os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise VmnetJournalError("Cannot open guarded VMware transaction lock") from exc
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise VmnetJournalError("VMware transaction lock ownership is invalid")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise VmnetJournalError("Another VMware network transaction owns the lock") from exc
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def record_journal(folder: Path, data: dict) -> None:
    """Atomically persist an auditable stage without replacing foreign files."""
    folder = Path(folder)
    if not folder.is_dir() or folder.is_symlink() or folder.stat().st_mode & 0o077:
        raise VmnetJournalError("Unsafe NORTH transaction backup directory")
    if data.get("state") not in ALL_STATES:
        raise VmnetJournalError("Invalid NORTH vmnet transaction journal state")
    dest = folder / "journal.json"
    if dest.is_symlink():
        raise VmnetJournalError("Journal path is a symlink")
    if dest.exists() and not dest.is_file():
        raise VmnetJournalError("Journal path is not a regular file")
    fd, temporary = tempfile.mkstemp(prefix=".north-journal-", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            os.fchmod(output.fileno(), 0o600)
            json.dump(data, output, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, dest)
        dir_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def inspect_vmnet_journals(backup_root: Path) -> tuple[dict, ...]:
    """Read-only recovery inventory; refuse malformed and incomplete evidence."""
    root = Path(backup_root)
    if not root.is_dir() or root.is_symlink():
        raise VmnetJournalError("VMware transaction backup directory is missing")
    results = []
    for folder in sorted(root.glob("north-*")):
        if not folder.is_dir() or folder.is_symlink():
            raise VmnetJournalError("Unsafe historical NORTH backup directory")
        path = folder / "journal.json"
        if not path.is_file() or path.is_symlink():
            raise VmnetJournalError("Historical NORTH backup lacks readable journal")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise VmnetJournalError("Unparseable historical NORTH journal") from exc
        if not isinstance(data, dict) or data.get("state") not in ALL_STATES:
            raise VmnetJournalError("Historical NORTH journal has invalid state")
        for required in ("provider", "baseline_sha256", "proposed_sha256", "backup"):
            if not isinstance(data.get(required), str) or not data[required]:
                raise VmnetJournalError("Incomplete historical NORTH journal")
        results.append({**data, "journal": str(path)})
    return tuple(results)


def inspect_north_release_journals(backup_root: Path) -> tuple[dict, ...]:
    """Fail closed on a stranded offline release without modifying old journals."""
    root = Path(backup_root)
    results = []
    for folder in sorted(root.glob("release-*")):
        if not folder.is_dir() or folder.is_symlink() or folder.stat().st_mode & 0o077:
            raise VmnetJournalError("Unsafe NORTH release backup folder")
        path = folder / "release.json"
        if path.is_symlink() or not path.is_file():
            raise VmnetJournalError("NORTH release recovery folder lacks a journal")
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            raise VmnetJournalError("Malformed NORTH release journal") from exc
        allowed = {"PREPARED", "WRITTEN", "VERIFYING", "MANUAL_RECONCILIATION",
                   "COMMITTED_RELEASE", "ROLLED_BACK"}
        if (not isinstance(state, dict)
                or state.get("schema") != "kingdoms.north.offline-release.v1"
                or state.get("state") not in allowed
                or state.get("backup_folder") != str(folder)
                or not isinstance(state.get("provider"), str)
                or not isinstance(state.get("reviewed_sha256"), str)):
            raise VmnetJournalError("Invalid NORTH release journal identity/state")
        results.append(state)
    return tuple(results)


def require_reconciled(backup_root: Path) -> None:
    unresolved = [item for item in inspect_vmnet_journals(backup_root)
                  if item["state"] in ACTIVE]
    if unresolved:
        raise VmnetJournalError(
            f"{len(unresolved)} interrupted/active vmnet transaction(s); "
            "manual ownership reconciliation required before another install"
        )
    releases = inspect_north_release_journals(backup_root)
    pending = [item for item in releases
               if item["state"] not in ("COMMITTED_RELEASE", "ROLLED_BACK")]
    if pending:
        raise VmnetJournalError(
            f"{len(pending)} unfinished NORTH release(s); "
            "manual reconciliation required before another install"
        )
