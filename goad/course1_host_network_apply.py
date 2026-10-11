"""Native NORTH host-network adapter used by Kingdoms setup-vmware-networks.sh.

The original six-machine GOAD setup is untouched. Applying this reduced
three-vmnet plan requires explicit root execution, a reviewed baseline digest,
an existing provider directory, and a clean VMware Workstation host.
No VM is launched and the NORTH install guard stays active.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import pwd
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from goad.course1_hostaddrs import (
    HELPER, SERVICE, TIMER, inspect_live_hostaddrs, inspect_live_hostaddr_assets,
)
from goad.course1_hostaddr_install import install_owned_address_assets
from goad.course1_network_preflight import inspect_live
from goad.course1_vmnet_config import verify_vmnet_config
from goad.course1_vmnet_transaction import (
    _atomic_bytes, _plain_regular, _safe_directory, execute_testable_network_transaction,
)
from goad.kingdoms_topology import load_course1_topology

NETWORKING = Path("/etc/vmware/networking")
NETMAP = Path("/etc/vmware/netmap.conf")
BACKUPS = Path("/etc/vmware/kingdoms-course1-backups")
OWNER = Path("/etc/vmware/kingdoms-course1-owner.json")
VMWARE_NETWORKS = Path("/usr/bin/vmware-networks")
SYSTEMD = Path("/etc/systemd/system")


class NorthSetupError(RuntimeError):
    pass


def run_command(*args, timeout=80):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NorthSetupError("Host command unavailable or timed out: " + args[0]) from exc
    if result.returncode:
        raise NorthSetupError(
            "Host command failed: " + " ".join(map(str, args))
            + ": " + (result.stderr.strip() or result.stdout.strip())[:400]
        )


def operator_inventory():
    """sudo must inspect the original desktop user's registered VMX entries."""
    name = os.environ.get("SUDO_USER")
    if not name or name == "root":
        raise NorthSetupError("Use sudo from the Kali desktop user, not a root login")
    home = Path(pwd.getpwnam(name).pw_dir)
    if not home.is_dir() or home.is_symlink():
        raise NorthSetupError("Cannot establish the VMware desktop inventory owner")
    return home / ".vmware/inventory.vmls"


def snapshot_netmap(path):
    if not path.is_file() or path.is_symlink():
        raise NorthSetupError("Missing or unsafe VMware netmap.conf; manual review required")
    meta = _plain_regular(path)
    return path.read_bytes(), meta


def durable_netmap_backup(folder, original):
    fd, path = tempfile.mkstemp(prefix="netmap-before-north-", suffix=".backup", dir=folder)
    with os.fdopen(fd, "wb") as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(original)
        output.flush()
        os.fsync(output.fileno())
    return path


class VMwareNetworkRestart:
    """Restore this attempt's netmap bytes on transaction rollback."""

    def __init__(self, path, original, metadata, executable=VMWARE_NETWORKS):
        self.path, self.original, self.metadata = path, original, metadata
        self.executable = str(executable)
        self.calls = 0
        self.observed = original

    def __call__(self):
        rolling_back = self.calls != 0
        self.calls += 1
        if rolling_back and self.path.read_bytes() != self.observed:
            raise NorthSetupError("VMware netmap changed outside this transaction; manual reconciliation")
        run_command(self.executable, "--stop")
        if rolling_back:
            _atomic_bytes(self.path, self.original, self.metadata)
        try:
            run_command(self.executable, "--start")
        finally:
            self.observed = self.path.read_bytes()
        if rolling_back and self.observed != self.original:
            raise NorthSetupError("VMware did not restore the original netmap; manual reconciliation")


def asset_paths():
    return {
        "helper": Path(HELPER),
        "service": SYSTEMD / SERVICE,
        "timer": SYSTEMD / TIMER,
    }


def systemd_activate():
    run_command("systemctl", "daemon-reload")
    run_command("systemctl", "start", SERVICE)
    run_command("systemctl", "enable", "--now", TIMER)


def systemd_disable():
    run_command("systemctl", "disable", "--now", TIMER)


def systemd_reload():
    run_command("systemctl", "daemon-reload")


def apply(provider_dir, reviewed_sha256, networking=NETWORKING, netmap=NETMAP,
          backups=BACKUPS, owner=OWNER, library=None, vmware_networks=VMWARE_NETWORKS):
    """One guarded VMware transaction; all callbacks run inside its lock."""
    if os.geteuid() != 0:
        raise NorthSetupError("Explicit sudo/root permission is required")
    if not re.fullmatch(r"[0-9a-f]{64}", reviewed_sha256 or ""):
        raise NorthSetupError("Supply the reviewed 64-digit lowercase baseline SHA-256")
    if not Path(provider_dir).is_absolute():
        raise NorthSetupError("Provider must be an existing absolute instance path")
    if not vmware_networks.is_file() or not os.access(vmware_networks, os.X_OK):
        raise NorthSetupError("VMware network service executable is missing")
    user_library = library if library is not None else operator_inventory()
    layout = load_course1_topology()

    # This is the initial read-only inspection. It is repeated INSIDE the lock.
    inspect_live(networking=networking, library=user_library)
    if Path(owner).exists() or Path(owner).is_symlink():
        raise NorthSetupError("A NORTH vmnet owner already exists")
    paths = asset_paths()
    for path in paths.values():
        if path.exists() or path.is_symlink():
            raise NorthSetupError("Existing NORTH systemd asset requires reconciliation")
    original, metadata = snapshot_netmap(netmap)
    _safe_directory(Path(networking).parent)
    if not Path(backups).exists():
        Path(backups).mkdir(mode=0o700)
    _safe_directory(Path(backups))
    # A durable netmap backup is necessary even if this process is killed.
    netmap_backup = durable_netmap_backup(backups, original)
    print("[BACKUP] VMware netmap original:", netmap_backup, flush=True)
    restart = VMwareNetworkRestart(Path(netmap), original, metadata, vmware_networks)
    lease = None

    def locked_preflight():
        inspect_live(networking=networking, library=user_library)
        current, _ = snapshot_netmap(netmap)
        if current != original:
            raise NorthSetupError("VMware netmap changed since initial plan; refusing host writes")
        for path in paths.values():
            if path.exists() or path.is_symlink():
                raise NorthSetupError("NORTH address asset was created by another process")

    def verify_runtime():
        nonlocal lease
        verify_vmnet_config(Path(networking).read_text(encoding="utf-8"), layout)
        def verify_addr():
            inspect_live_hostaddrs(layout)
            inspect_live_hostaddr_assets(layout)
        lease = install_owned_address_assets(
            layout, paths, systemd_activate, systemd_disable,
            systemd_reload, verify_addr, owner_uid=0,
        )

    try:
        installed = execute_testable_network_transaction(
            Path(networking), Path(backups), Path(owner), Path(provider_dir),
            layout, reviewed_sha256, restart, verify_runtime,
            preflight=locked_preflight,
        )
        print("[PASS] NORTH VMware networking and persistent host addresses installed", flush=True)
        return installed
    except Exception:
        if lease is not None:
            # An error after asset verification/creation must not strand the timer.
            lease.rollback()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-dir", required=True)
    parser.add_argument("--reviewed-sha256", required=True)
    args = parser.parse_args()
    try:
        apply(args.provider_dir, args.reviewed_sha256)
    except (NorthSetupError, ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, "[BLOCKED] Course 1 host setup: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
