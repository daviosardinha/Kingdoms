"""WSLPE-only owner-context rollback rehearsal. No VMware or nft writes.

Proves an independent *system* systemd timer can launch an unprivileged
process as the owner of the uniquely registered WSLPE VMX, independently
of an SSH login shell. This does NOT yet prove vmrun shutdown/restore.
"""
from __future__ import annotations

import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import tempfile
import time
import uuid


def owner_identity(vmx: Path, current_uid: int | None = None) -> tuple[int, str]:
    """Only the existing non-root VMX owner may rehearse rollback."""
    uid = os.getuid() if current_uid is None else current_uid
    if not isinstance(vmx, Path) or vmx.is_symlink() or not vmx.is_file():
        raise ValueError("WSLPE registered VMX unavailable or symlinked")
    if uid <= 0 or vmx.stat().st_uid != uid:
        raise ValueError("WSLPE recovery must execute as the exact non-root VM owner")
    entry = pwd.getpwuid(uid)
    username = entry.pw_name
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username):
        raise ValueError("Untrusted VMware owner account name")
    return uid, username


def command(args: list[str], timeout: int = 20):
    return subprocess.run(args, capture_output=True, text=True,
                          check=False, timeout=timeout)


def rehearse_owner_timer(uid: int, username: str,
                         runner=command, sleep=time.sleep) -> str:
    """Independent systemd timer touches ONE disposable owner-owned marker."""
    if uid <= 0 or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username):
        raise ValueError("Untrusted timer owner")
    stem = uuid.uuid4().hex[:16]
    unit = f"kingdoms-wslpe-owner-check-{stem}"
    folder = Path(tempfile.mkdtemp(prefix=f"{unit}-", dir="/tmp"))
    marker = folder / "fired"
    try:
        if folder.stat().st_uid != uid or folder.stat().st_mode & 0o077:
            raise ValueError("Temporary WSLPE owner proof directory unsafe")
        arm = runner([
            "sudo", "-n", "systemd-run", "--quiet",
            "--unit", unit, "--on-active=3s", "--collect",
            f"--property=User={username}",
            "/usr/bin/touch", str(marker),
        ])
        if arm.returncode:
            raise ValueError("Independent owner-context systemd timer unavailable")
        state = runner(["sudo", "-n", "systemctl", "is-active", f"{unit}.timer"])
        if state.returncode or state.stdout.strip() != "active":
            raise ValueError("Owner-context timer not confirmed active")
        for _ in range(15):
            if marker.is_file():
                if marker.is_symlink() or marker.stat().st_uid != uid:
                    raise ValueError("Timed WSLPE owner proof has wrong identity")
                return unit
            sleep(1)
        raise ValueError("Owner-context recovery timer did not execute")
    finally:
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError("Owner recovery proof directory changed unexpectedly")
        if folder.stat().st_uid != uid:
            raise ValueError("Owner recovery proof directory ownership changed")
        if marker.is_symlink():
            raise ValueError("Owner recovery sentinel changed unexpectedly")
        shutil.rmtree(folder)
