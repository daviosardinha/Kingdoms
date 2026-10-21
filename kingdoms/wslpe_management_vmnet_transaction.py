"""Guarded, recoverable WSLPE management vmnet *source component*.

There is intentionally NO production CLI wiring. The eventual caller must
supply independent live ownership/collision, zero-guest, restart and interface
verification capabilities. Do not confuse unit tests with VMware validation.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Callable

from kingdoms.wslpe_management_vmnet_plan import candidate_plan


MAX_NETWORKING_BYTES = 200_000
MAX_JOURNAL_BYTES = 600_000


class NetworkTransactionBlocked(RuntimeError):
    """A fail-closed gate or unresolved recovery condition."""


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_regular(path: Path, max_bytes: int) -> tuple[bytes, os.stat_result]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes or info.st_nlink != 1:
        raise NetworkTransactionBlocked(f"Unsafe or oversized file: {path}")
    # O_NOFOLLOW protects against a last-second replacement with a symlink.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(fd)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_ino != info.st_ino
                or opened.st_dev != info.st_dev or opened.st_size > max_bytes):
            raise NetworkTransactionBlocked("File changed during open")
        content = b""
        while len(content) <= max_bytes:
            part = os.read(fd, max_bytes + 1 - len(content))
            if not part:
                break
            content += part
        if len(content) > max_bytes:
            raise NetworkTransactionBlocked("File exceeds size cap")
        return content, opened
    finally:
        os.close(fd)


def _atomic_replace(path: Path, payload: bytes, *, mode: int, uid: int, gid: int) -> None:
    """Preserve ownership, permission bits and durable rename on one filesystem."""
    temp_name = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix=".kingdoms-wslpe-", dir=path.parent)
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            os.fchown(stream.fileno(), uid, gid)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
        temp_name = None
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temp_name is not None:
            os.unlink(temp_name)


class WslpeVmnetTransaction:
    """One-owner additive change with private journal and explicit recovery.

    All callbacks are REQUIRED trusted integration boundaries, not stubs for a
    real host. The manager must remain private until those are implemented.
    """

    def __init__(self, *, networking: Path, journal: Path, lock: Path,
                 running_guests: Callable[[], int],
                 live_preflight: Callable[[str, str], None],
                 vmware_action: Callable[[str], None],
                 verify_created_network: Callable[[str, str], None]):
        self.networking = networking
        self.journal = journal
        self.lock = lock
        self.running_guests = running_guests
        self.live_preflight = live_preflight
        self.vmware_action = vmware_action
        self.verify_created_network = verify_created_network

    @contextmanager
    def _exclusive(self):
        if os.geteuid() != 0:
            raise NetworkTransactionBlocked("Root authorization required for VMware mutation")
        if self.lock.is_symlink() or self.lock.parent.is_symlink():
            raise NetworkTransactionBlocked("Unsafe lock path")
        if not self.lock.parent.is_dir():
            raise NetworkTransactionBlocked("Dedicated private lock directory missing")
        fd = os.open(self.lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1:
                raise NetworkTransactionBlocked("Unsafe lock ownership")
            os.fchmod(fd, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise NetworkTransactionBlocked("Another VMware allocation is active") from exc
            yield
        finally:
            os.close(fd)

    def _zero_guests(self) -> None:
        count = self.running_guests()
        if not isinstance(count, int) or isinstance(count, bool) or count != 0:
            raise NetworkTransactionBlocked(f"VMware guest activity unknown/nonzero: {count!r}")

    def _read_networking(self) -> tuple[bytes, os.stat_result]:
        content, info = _read_regular(self.networking, MAX_NETWORKING_BYTES)
        if info.st_uid != 0:
            raise NetworkTransactionBlocked("VMware networking file is not root-owned")
        return content, info

    def _save(self, data: dict) -> None:
        if self.journal.exists() or self.journal.is_symlink():
            _, prior = _read_regular(self.journal, MAX_JOURNAL_BYTES)
            if prior.st_uid != 0 or stat.S_IMODE(prior.st_mode) != 0o600:
                raise NetworkTransactionBlocked("Unsafe journal owner or permissions")
        if self.journal.parent.is_symlink() or not self.journal.parent.is_dir():
            raise NetworkTransactionBlocked("Dedicated private journal directory missing")
        encoded = (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()
        if len(encoded) > MAX_JOURNAL_BYTES:
            raise NetworkTransactionBlocked("Journal too large")
        _atomic_replace(self.journal, encoded, mode=0o600, uid=0, gid=0)

    def _load(self) -> dict:
        raw, info = _read_regular(self.journal, MAX_JOURNAL_BYTES)
        if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
            raise NetworkTransactionBlocked("Unsafe journal owner or permissions")
        try:
            data = json.loads(raw)
            original = base64.b64decode(data["original_b64"], validate=True)
            if (data["version"] != 1 or len(original) > MAX_NETWORKING_BYTES
                    or _digest(original) != data["original_sha256"]
                    or not isinstance(data["proposed_sha256"], str)
                    or data["networking"] != str(self.networking)):
                raise ValueError("Invalid journal payload")
        except (KeyError, ValueError, TypeError) as exc:
            raise NetworkTransactionBlocked("Journal integrity failure") from exc
        return data

    def _rollback(self, data: dict) -> None:
        """Never overwrite out-of-band changes or touch a live guest."""
        self._zero_guests()
        current, info = self._read_networking()
        if _digest(current) not in {data["original_sha256"], data["proposed_sha256"]}:
            raise NetworkTransactionBlocked("VMware networking drift; manual recovery required")
        self.vmware_action("stop")
        self._zero_guests()
        if _digest(current) != data["original_sha256"]:
            latest, _ = self._read_networking()
            if latest != current:
                raise NetworkTransactionBlocked("VMware networking changed during rollback")
            original = base64.b64decode(data["original_b64"], validate=True)
            _atomic_replace(self.networking, original, mode=data["mode"],
                            uid=data["uid"], gid=data["gid"])
        self.vmware_action("start")
        verified, _ = self._read_networking()
        if _digest(verified) != data["original_sha256"]:
            raise NetworkTransactionBlocked("Rollback verification mismatch")
        data["status"] = "rolled_back"
        self._save(data)

    def apply(self, *, vmnet: str, subnet: str, exercise_vmnet: str,
              exercise_subnet: str, expected_source_sha256: str,
              maintenance_approved: bool = False) -> str:
        """Internal only: fail closed unless all independent gates pass."""
        if maintenance_approved is not True:
            raise NetworkTransactionBlocked("Explicit maintenance authorization required")
        with self._exclusive():
            if self.journal.exists() or self.journal.is_symlink():
                raise NetworkTransactionBlocked("Prior transaction journal exists; inspect/recover first")
            self._zero_guests()
            original, info = self._read_networking()
            if _digest(original) != expected_source_sha256:
                raise NetworkTransactionBlocked("Stale VMware networking SHA256")
            try:
                source = original.decode("utf-8")
                proposed = candidate_plan(source, vmnet=vmnet, subnet=subnet,
                                          exercise_vmnet=exercise_vmnet,
                                          exercise_subnet=exercise_subnet).encode("utf-8")
            except (UnicodeError, ValueError) as exc:
                raise NetworkTransactionBlocked("Additive candidate contract failed") from exc
            if len(proposed) > MAX_NETWORKING_BYTES:
                raise NetworkTransactionBlocked("Proposed VMware configuration too large")
            if not proposed.startswith(original) or len(proposed) <= len(original):
                raise NetworkTransactionBlocked("Proposal would rewrite existing VMware bytes")
            self.live_preflight(vmnet, subnet)  # Collision + complete VMX registration evidence
            self._zero_guests()
            if self._read_networking()[0] != original:
                raise NetworkTransactionBlocked("VMware metadata changed before journal")
            data = {
                "version": 1, "status": "prepared", "networking": str(self.networking),
                "vmnet": vmnet, "subnet": subnet, "original_sha256": _digest(original),
                "proposed_sha256": _digest(proposed),
                "original_b64": base64.b64encode(original).decode("ascii"),
                "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid, "gid": info.st_gid,
            }
            self._save(data)  # Durable undo record BEFORE touching VMware
            try:
                self._zero_guests()
                self.vmware_action("stop")
                data["status"] = "stopped"
                self._save(data)
                self._zero_guests()
                if self._read_networking()[0] != original:
                    raise NetworkTransactionBlocked("VMware metadata drift during stop")
                _atomic_replace(self.networking, proposed, mode=data["mode"],
                                uid=data["uid"], gid=data["gid"])
                data["status"] = "installed"
                self._save(data)
                self._zero_guests()
                self.vmware_action("start")
                self.verify_created_network(vmnet, subnet)  # host adapter and isolation acceptance
                if _digest(self._read_networking()[0]) != data["proposed_sha256"]:
                    raise NetworkTransactionBlocked("VMware post-start metadata drift")
                data["status"] = "committed"
                self._save(data)
                return data["proposed_sha256"]
            except Exception as cause:
                try:
                    self._rollback(data)
                except Exception as recovery_error:
                    raise NetworkTransactionBlocked(
                        f"Allocation failed; RECOVERY REQUIRED: {recovery_error}"
                    ) from cause
                raise NetworkTransactionBlocked("Allocation failed; original configuration restored") from cause

    def recover(self) -> str:
        """Explicit crash recovery; never automatically roll back a committed vmnet."""
        with self._exclusive():
            data = self._load()
            if data["status"] not in {"prepared", "stopped", "installed"}:
                raise NetworkTransactionBlocked("Journal is not an unfinished transaction")
            self._rollback(data)
            return data["original_sha256"]
