"""Owned NORTH address-repair assets for the existing Kingdoms network setup.

Purely callback-driven. This module never invokes systemctl or VMware itself;
the existing setup-vmware-networks.sh --north runtime adapter owns those actions.
The caller must hold the Course 1 global vmnet transaction lock.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

from goad.course1_hostaddrs import render_hostaddr_assets


class HostaddrInstallError(RuntimeError):
    pass


def _regular_directory(path: Path, owner_uid: int):
    if (path.is_symlink() or not path.is_dir()
            or path.stat().st_uid != owner_uid
            or path.stat().st_mode & 0o022):
        raise HostaddrInstallError("Unsafe NORTH host-address installation directory")


class OwnedAddressAssets:
    """A lease over newly created files, never over pre-existing systemd units."""

    def __init__(self, files, contents, disable, reload_units):
        self.files = files
        self.contents = contents
        self.disable = disable
        self.reload_units = reload_units
        self.started = False
        self.cleaned = False

    def rollback(self):
        if self.cleaned:
            return
        errors = []
        if self.started:
            try:
                self.disable()
            except Exception as exc:
                errors.append("unable to stop NORTH timer: " + str(exc))
                # Keep the helper/units if systemd might still execute them.
                raise HostaddrInstallError("; ".join(errors)) from exc
        for name, file in self.files.items():
            try:
                if (file.is_symlink() or not file.is_file()
                        or file.stat().st_nlink != 1
                        or file.read_bytes() != self.contents[name].encode("utf-8")):
                    raise HostaddrInstallError("NORTH asset was changed by another owner: " + name)
                file.unlink()
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            raise HostaddrInstallError("Manual reconciliation required: " + "; ".join(errors))
        self.reload_units()
        self.cleaned = True


def install_owned_address_assets(layout, paths, activate, disable, reload_units,
                                 verify, owner_uid=None):
    """Exclusively create and prove all three assets; undo on failure.

    No ownership is claimed over existing assets, even if their bytes match.
    Callers must invoke lease.rollback() if the enclosing vmnet commit fails.
    """
    owner = os.geteuid() if owner_uid is None else owner_uid
    expected = render_hostaddr_assets(layout)
    if set(paths) != set(expected):
        raise HostaddrInstallError("NORTH helper/service/timer locations are incomplete")
    files = {name: Path(path) for name, path in paths.items()}
    if len(set(files.values())) != 3:
        raise HostaddrInstallError("Duplicated NORTH host-address asset destination")
    for file in files.values():
        _regular_directory(file.parent, owner)
        if file.exists() or file.is_symlink():
            raise HostaddrInstallError("Existing NORTH host-address asset needs reconciliation")
    lease = OwnedAddressAssets(files, expected, disable, reload_units)
    try:
        for name, file in files.items():
            fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o755 if name == "helper" else 0o644)
            try:
                with os.fdopen(fd, "wb") as output:
                    os.fchmod(output.fileno(), 0o755 if name == "helper" else 0o644)
                    output.write(expected[name].encode("utf-8"))
                    output.flush()
                    os.fsync(output.fileno())
            except BaseException:
                # The just-created file is now owned by this lease.
                lease.files = {n: f for n, f in files.items() if f.exists()}
                raise
        lease.started = True
        activate()
        verify()
        return lease
    except Exception as exc:
        try:
            lease.files = {n: f for n, f in files.items() if f.exists() or f.is_symlink()}
            lease.rollback()
        except Exception as rollback_exc:
            raise HostaddrInstallError(
                "NORTH address setup failed and rollback needs manual reconciliation"
            ) from rollback_exc
        raise HostaddrInstallError("NORTH address setup was rolled back") from exc
