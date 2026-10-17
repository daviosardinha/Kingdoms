"""Private WSLPE-only operator credential, separate from learner and fixtures.

Prepare once per native WSLPE instance; never reuse an image-wide password,
never rotate silently and never print credentials in automated output.
This module has no Windows, VMware or Ansible side effects.
"""
from __future__ import annotations
import os
from pathlib import Path
import re
import stat

from kingdoms.wslpe_learner_credentials import _strong_password

USERNAME = r"WSLPE-WS01\kingdom.operator"
ROOT = Path.home() / ".local/state/kingdoms-wslpe-operator"

def exact_instance_id(instance_id: str) -> str:
    if not isinstance(instance_id, str) or not re.fullmatch(
            r"[0-9a-f]{6}-wslpe-vmware", instance_id):
        raise ValueError("Not an exact WSLPE VMware instance identifier")
    return instance_id

def _private_dir(path: Path, *, create: bool = False) -> None:
    if path.is_symlink():
        raise ValueError("Operator credential directory is a symlink")
    if create and not path.exists():
        path.mkdir(mode=0o700)
    if (not path.is_dir() or path.stat().st_uid != os.geteuid()
            or stat.S_IMODE(path.stat().st_mode) != 0o700):
        raise ValueError("Operator credential directory must be owner-only 0700")

def _private_file(path: Path) -> None:
    if (path.is_symlink() or not path.is_file()
            or path.stat().st_uid != os.geteuid()
            or stat.S_IMODE(path.stat().st_mode) != 0o600):
        raise ValueError("Operator credential must be an owner-only 0600 regular file")

def operator_secret(instance_id: str, *, prepare: bool = False,
                    store: Path = ROOT) -> str:
    """Reuse existing secret or explicitly prepare it; NEVER replace implicitly."""
    ident = exact_instance_id(instance_id)
    if store.is_symlink():
        raise ValueError("Operator credential store cannot be a symlink")
    if not store.exists() and not prepare:
        raise ValueError("No prepared operator credential")
    if prepare:
        store.parent.mkdir(parents=True,exist_ok=True)
    _private_dir(store, create=prepare)
    folder = store / ident
    if not folder.exists() and not prepare:
        raise ValueError("No prepared instance operator credential")
    _private_dir(folder, create=prepare)
    path = folder / "credential"
    if path.is_symlink():
        raise ValueError("Operator credential path cannot be a symlink")
    if path.exists():
        _private_file(path)
        value = path.read_text(encoding="utf-8")
        if (not value.endswith("\n") or value.count("\n") != 1
                or len(value.strip()) < 24):
            raise ValueError("Invalid prepared operator credential")
        return value[:-1]
    if not prepare:
        raise ValueError("No prepared operator credential")
    generated = _strong_password()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(generated+"\n")
        handle.flush()
        os.fsync(handle.fileno())
    _private_file(path)
    return generated
