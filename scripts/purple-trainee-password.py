#!/usr/bin/env python3
"""Configure a fixed LX01 trainee password without putting secrets in Git.

init:    Prompt once, store only a salted SHA-512-crypt password hash in a
         user-owned, mode-0600 file outside the Kingdoms repository.
status:  Verify local hash file permissions and format without disclosing it.
apply:   Transfer the hash and LX01 account provisioner to one existing guest.
"""
from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ad/PURPLE/providers/vmware/provision-sliver-trainee.sh"
HASH_PATH = Path.home() / ".config/kingdoms/purple-lx01-trainee.sha512"
SHA512_CRYPT = re.compile(r"\$6\$(?:rounds=[0-9]+\$)?[A-Za-z0-9./]{8,16}\$[A-Za-z0-9./]{86}\Z")
VM = "PURPLE-LX01"
REMOTE_SCRIPT = "/tmp/purple-provision-sliver-trainee.sh"
REMOTE_HASH = "/home/vagrant/.purple-sliver-trainee.sha512"


class PasswordConfigurationError(RuntimeError):
    pass


def check_hash_file(path: Path = HASH_PATH) -> str:
    if path.is_symlink() or not path.is_file():
        raise PasswordConfigurationError("Password hash file is absent or a symlink; run init")
    metadata = path.stat()
    if metadata.st_uid != os.getuid() or (stat.S_IMODE(metadata.st_mode) & 0o077):
        raise PasswordConfigurationError("Password hash must belong to the current user with mode 0600")
    try:
        secret_hash = path.read_text(encoding="ascii").rstrip("\n")
    except (OSError, UnicodeError) as exc:
        raise PasswordConfigurationError("Unable to read private password hash") from exc
    if not SHA512_CRYPT.fullmatch(secret_hash):
        raise PasswordConfigurationError("Hash has an unexpected format (require SHA-512 crypt)")
    return secret_hash


def ensure_private_dir(path: Path) -> None:
    directory = path.parent
    if directory.is_symlink():
        raise PasswordConfigurationError("Secret directory must not be a symlink")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    m = directory.stat()
    if not directory.is_dir() or m.st_uid != os.getuid() or stat.S_IMODE(m.st_mode) & 0o077:
        raise PasswordConfigurationError("Secret directory must be owned by this user and private (0700)")


def init_password(rotate: bool = False) -> None:
    ensure_private_dir(HASH_PATH)
    if HASH_PATH.exists() or HASH_PATH.is_symlink():
        if not rotate:
            check_hash_file()
            print("[PASS] LX01 fixed password hash already configured; no changes")
            return
        check_hash_file()
    pw = getpass.getpass("Choose fixed PURPLE-LX01 trainee password: ")
    repeat = getpass.getpass("Confirm password: ")
    if pw != repeat:
        raise PasswordConfigurationError("Password confirmation did not match")
    if not (12 <= len(pw) <= 256) or any(ch in pw for ch in "\r\n\x00"):
        raise PasswordConfigurationError("Choose 12 to 256 characters, without newlines")
    result = subprocess.run(
        ["openssl", "passwd", "-6", "-stdin"],
        input=pw + "\n",
        text=True, capture_output=True, check=True,
    )
    secret_hash = result.stdout.strip()
    if not SHA512_CRYPT.fullmatch(secret_hash):
        raise PasswordConfigurationError("OpenSSL returned an unexpected password hash")
    if rotate:
        # Write new sensitive data into a private temporary file and atomically
        # replace the previous hash; never print either hash or plaintext.
        temp = HASH_PATH.with_suffix(".sha512.new")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "w", encoding="ascii") as handle:
                handle.write(secret_hash + "\n")
            os.replace(temp, HASH_PATH)
        finally:
            if temp.exists():
                temp.unlink()
    else:
        fd = os.open(HASH_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as handle:
            handle.write(secret_hash + "\n")
    check_hash_file()
    print("[PASS] Fixed password saved as a private hash outside Git; plaintext was not stored")
    print("[NOTE] Keep the same hash file for all future PURPLE installations")


def validate_provider(provider_dir: Path) -> Path:
    if provider_dir.is_symlink():
        raise PasswordConfigurationError("Provider directory must not be a symlink")
    provider = provider_dir.resolve(strict=True)
    if (provider.name != "provider" or
            not re.fullmatch(r"[0-9a-f]{6,}-purple-vmware", provider.parent.name) or
            not (provider / "Vagrantfile").is_file()):
        raise PasswordConfigurationError("Expected existing workspace/<id>-purple-vmware/provider")
    if ':name => "PURPLE-LX01"' not in (provider / "Vagrantfile").read_text(encoding="utf-8"):
        raise PasswordConfigurationError("Selected provider has no PURPLE-LX01 machine")
    identifier = provider / ".vagrant/machines/PURPLE-LX01/vmware_desktop/id"
    if identifier.is_symlink() or not identifier.is_file():
        raise PasswordConfigurationError("Existing PURPLE-LX01 VM identity is missing")
    return provider


def apply_existing(provider_dir: Path) -> None:
    check_hash_file()
    if not SOURCE.is_file():
        raise PasswordConfigurationError("Source-owned trainee provisioner missing in this checkout")
    provider = validate_provider(provider_dir)
    # Vagrant upload transfers the locally secured hash, not a plaintext password.
    commands = [
        ["vagrant", "upload", str(SOURCE), REMOTE_SCRIPT, VM],
        ["vagrant", "upload", str(HASH_PATH), REMOTE_HASH, VM],
        ["vagrant", "ssh", VM, "-c",
         "sudo chmod 600 " + REMOTE_HASH + " && "
         "sudo bash " + REMOTE_SCRIPT + " --ensure && "
         "sudo bash " + REMOTE_SCRIPT + " --verify; "
         "result=$?; sudo rm -f " + REMOTE_SCRIPT + " " + REMOTE_HASH + "; exit \"$result\""],
    ]
    for cmd in commands:
        subprocess.run(cmd, cwd=provider, check=True)
    print("[PASS] Existing PURPLE-LX01 trainee account and fixed password verified")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    initial = commands.add_parser("init", help="Prompt for the fixed password and store its hash")
    initial.add_argument("--rotate", action="store_true", help="Change the fixed password for subsequent installs")
    commands.add_parser("status", help="Validate the private hash file without displaying it")
    existing = commands.add_parser("apply", help="Apply password/account only to the current PURPLE-LX01 guest")
    existing.add_argument("--provider-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "init":
            init_password(rotate=args.rotate)
        elif args.command == "status":
            check_hash_file()
            print("[PASS] Private fixed password hash is configured for PURPLE-LX01")
        else:
            apply_existing(args.provider_dir)
        return 0
    except (PasswordConfigurationError, subprocess.CalledProcessError, OSError) as exc:
        print(f"[BLOCKED] PURPLE-LX01 password setup: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
