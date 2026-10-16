"""WSLPE local *development* learner credential, reusable without prompts.

The Windows account is a standard non-admin user. One unique credential
is generated once per local WSLPE checkout and kept OUTSIDE Git in an
owner-only 0700 directory / 0600 file. Production student instances must
have their own per-instance credential vault, not share this credential.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import stat
import string

ENV = "KINGDOMS_WSLPE_LEARNER_PASSWORD"
USERNAME = r"WSLPE-WS01\lpe.trainee"
DEFAULT_PATH = Path.home() / ".local/state/kingdoms-wslpe-learner/credential"


def _check_directory(directory: Path) -> None:
    if (directory.is_symlink() or not directory.is_dir()
            or directory.stat().st_uid != os.geteuid()
            or stat.S_IMODE(directory.stat().st_mode) != 0o700):
        raise ValueError("WSLPE learner credential directory must be private (0700) and owned by the operator")


def _check_file(path: Path) -> None:
    if (path.is_symlink() or not path.is_file()
            or path.stat().st_uid != os.geteuid()
            or stat.S_IMODE(path.stat().st_mode) != 0o600):
        raise ValueError("WSLPE learner credential must be a private owner-only (0600) regular file")


def _strong_password() -> str:
    # Include every required Windows password-complexity character class.
    classes = (string.ascii_uppercase, string.ascii_lowercase,
               string.digits, "!#%_-")
    source = "".join(classes)
    chars = [secrets.choice(c) for c in classes]
    chars += [secrets.choice(source) for _ in range(28)]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def _read(path: Path) -> str:
    _check_directory(path.parent)
    _check_file(path)
    data = path.read_text(encoding="utf-8")
    if not data.endswith("\n") or data.count("\n") != 1:
        raise ValueError("Invalid local WSLPE learner credential format")
    password = data[:-1]
    if len(password) < 12 or any(x in password for x in "\r\n\x00"):
        raise ValueError("Invalid stored WSLPE learner password")
    return password


def learner_password(*, bootstrap: bool, path: Path = DEFAULT_PATH,
                     environ: dict | None = None) -> str:
    """No input prompts. Reuse existing secret; generate only with bootstrap.

    Explicit environment override is still supported, but a mismatch
    with an existing credential fails rather than rotating silently.
    """
    env = os.environ if environ is None else environ
    supplied = env.get(ENV) or ""
    if supplied and (len(supplied) < 12 or any(x in supplied for x in "\r\n\x00")):
        raise ValueError("Configured WSLPE learner password must have 12+ characters without line breaks")
    if path.is_symlink():
        raise ValueError("WSLPE credential path is a symlink")
    if path.exists():
        existing = _read(path)
        if supplied and supplied != existing:
            raise ValueError("Existing WSLPE learner credential differs from operator environment; no password rotation")
        return existing
    if not bootstrap:
        if supplied:
            return supplied
        raise ValueError("No learner credential exists; run --execute --bootstrap-learner once")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _check_directory(path.parent)
    chosen = supplied or _strong_password()
    # Atomic create; never overwrite a credential that appeared meanwhile.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(chosen + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    _check_file(path)
    return chosen


def read_local_access(*, path: Path = DEFAULT_PATH) -> tuple[str, str]:
    """Called only by an explicit operator request, never in routine logs."""
    if not path.exists() and not path.is_symlink():
        raise ValueError(
            "WSLPE learner credential has not been created; run "
            "--execute --bootstrap-learner after inventory validation"
        )
    return USERNAME, _read(path)
