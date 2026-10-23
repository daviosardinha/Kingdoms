"""Guarded WSLPE vmnet4 maintenance runtime assembly.

Source integration only. No CLI and no guest shutdown operation.
Only construct this runtime for the specific owner-approved maintenance action.
Root runs the hypervisor service; vmrun uses the original VMware owner UID,
not root's empty user library. Global process count must also be zero.

Host adapter verification alone is not proof of NORTH/WSLPE isolation.
An independent callable isolation_acceptance must be supplied by a reviewed
host-firewall/route isolation implementation; no permissive default exists.
"""
from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
from typing import Callable

from kingdoms.wslpe41_host_preflight import running_vm_count
from kingdoms.wslpe41_network_auto import occupied_networks
from kingdoms.wslpe_management_vmnet_host_gate import (
    HostVmnetGateBlocked, RunningVmwareInventory,
    parse_vmware_processes, scoped_candidate_free,
)
from kingdoms.wslpe_management_vmnet_registry import audit_user_library
from kingdoms.wslpe_management_vmnet_hostaddr import Vmnet4HostAddressReconciler
from kingdoms.wslpe_management_vmnet_transaction import (
    MAX_NETWORKING_BYTES, NetworkTransactionBlocked,
    WslpeVmnetTransaction, _read_regular,
)
from kingdoms.wslpe_management_vmnet_workstation import (
    BIN, IP, _host_run, _json_list, _trusted_binary,
    WorkstationHostAdapterVerifier, WorkstationNetworkService,
)

VMRUN = Path("/usr/bin/vmrun")
PGREP = Path("/usr/bin/pgrep")
NETWORKING = Path("/etc/vmware/networking")
STATE_ROOT = Path("/var/lib/kingdoms/wslpe-vmnet4")
VMNET = "vmnet4"
SUBNET = "172.28.233.0/24"
EXERCISE = "vmnet3"
EXERCISE_SUBNET = "172.28.232.0/24"


def owner_vmrun_list(owner: str) -> str:
    """Read the named real login user's Workstation inventory while root."""
    if os.geteuid() != 0:
        raise NetworkTransactionBlocked("Owner-scoped VMware inventory requires root")
    try:
        account = pwd.getpwnam(owner)
    except KeyError as exc:
        raise NetworkTransactionBlocked("Unknown Workstation owner") from exc
    if account.pw_uid == 0 or not Path(account.pw_dir).is_dir():
        raise NetworkTransactionBlocked("Invalid non-root VMware library owner")
    _trusted_binary(VMRUN, allow_trusted_symlink=True)

    def set_user():
        os.setgroups([])
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)

    env = {
        "HOME": account.pw_dir, "USER": account.pw_name,
        "LOGNAME": account.pw_name, "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
    }
    try:
        proc = subprocess.run(
            [str(VMRUN), "-T", "ws", "list"],
            capture_output=True, text=True, timeout=15, check=False,
            stdin=subprocess.DEVNULL, env=env, preexec_fn=set_user,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NetworkTransactionBlocked("Cannot read original-owner VMware inventory") from exc
    if proc.returncode != 0 or len(proc.stdout) > 200_000:
        raise NetworkTransactionBlocked("Owner VMware inventory failed")
    return proc.stdout


def assert_private_state_dir(root: Path) -> None:
    """Do not create privileged state implicitly; require a secure pre-made dir."""
    if (not root.is_absolute() or root.is_symlink() or
            root.resolve(strict=True) != root or
            root.parent.is_symlink()):
        raise NetworkTransactionBlocked("Unsafe private transaction state path")
    meta = root.stat()
    if (not stat.S_ISDIR(meta.st_mode) or meta.st_uid != 0
            or stat.S_IMODE(meta.st_mode) != 0o700):
        raise NetworkTransactionBlocked("Transaction state must be root-only 0700")
    if root.parent.stat().st_uid != 0:
        raise NetworkTransactionBlocked("Untrusted transaction parent owner")


def running_zero(*, owner: str, vmrun: Callable[[str], str] = owner_vmrun_list,
                 process_run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> int:
    """Both sources must independently agree that NO VMware VM process exists."""
    if os.geteuid() != 0:
        raise NetworkTransactionBlocked("Guest-zero proof requires root")
    _trusted_binary(PGREP, allow_trusted_symlink=True)
    try:
        result = process_run(
            [str(PGREP), "-c", "-x", "vmware-vmx"],
            capture_output=True, text=True, timeout=10, check=False,
            stdin=subprocess.DEVNULL,
        )
        proc_count = parse_vmware_processes(result.returncode, result.stdout)
        owner_count = running_vm_count(vmrun(owner))
    except (OSError, subprocess.TimeoutExpired, HostVmnetGateBlocked, ValueError) as exc:
        raise NetworkTransactionBlocked("Cannot establish zero VMware guests") from exc
    if proc_count != 0 or owner_count != 0:
        raise NetworkTransactionBlocked(
            f"Shared networking deferred; vmware-vmx={proc_count}, owner-vmrun={owner_count}"
        )
    return 0


def verify_candidate_collisions(networking_text: str, *,
                                vmnet: str, subnet: str, roots: tuple[Path, ...],
                                run: Callable[..., str] = _host_run) -> None:
    """Reject live host routing and VMX collisions just before maintenance."""
    if vmnet != VMNET or subnet != SUBNET:
        raise NetworkTransactionBlocked("Wrong current WSLPE management contract")
    scoped_candidate_free(networking_text, roots, vmnet)
    _trusted_binary(IP)
    addr = _json_list(run([str(IP), "-j", "-4", "addr", "show"], timeout=15), "address")
    routes = _json_list(run([str(IP), "-j", "-4", "route", "show",
                             "table", "all"], timeout=15), "routes")
    try:
        used = occupied_networks(addr, routes, networking_text, [])
    except (ValueError, TypeError) as exc:
        raise NetworkTransactionBlocked("Host route collision proof unavailable") from exc
    candidate = ipaddress.IPv4Network(subnet)
    if any(candidate.overlaps(other) for other in used):
        raise NetworkTransactionBlocked("Management subnet overlaps host/network routes")


class Vmnet4MaintenanceRuntime:
    """Source-only adapter for the journaled WSLPE vmnet4 transaction."""

    def __init__(self, *, owner: str, roots: tuple[Path, ...],
                 isolation_acceptance: Callable[[str, str], None],
                 networking: Path = NETWORKING, state_dir: Path = STATE_ROOT,
                 vmrun: Callable[[str], str] = owner_vmrun_list,
                 service: WorkstationNetworkService | None = None,
                 adapter: WorkstationHostAdapterVerifier | None = None,
                 reconciler: Vmnet4HostAddressReconciler | None = None,
                 route_run: Callable[..., str] = _host_run,
                 process_run: Callable[..., subprocess.CompletedProcess] = subprocess.run):
        if not callable(isolation_acceptance):
            raise NetworkTransactionBlocked("Independent firewall/isolation proof required")
        if not owner or owner == "root" or not roots:
            raise NetworkTransactionBlocked("Original non-root Workstation owner/workspaces required")
        self.owner = owner
        self.roots = roots
        self.isolation_acceptance = isolation_acceptance
        self.networking = networking
        self.state_dir = state_dir
        self.vmrun = vmrun
        self.process_run = process_run
        self.service = service if service is not None else WorkstationNetworkService()
        self.adapter = adapter if adapter is not None else WorkstationHostAdapterVerifier()
        self.reconciler = reconciler if reconciler is not None else Vmnet4HostAddressReconciler()
        self.route_run = route_run

    def _zero(self) -> int:
        return running_zero(owner=self.owner, vmrun=self.vmrun,
                            process_run=self.process_run)

    def _preflight(self, vmnet: str, subnet: str) -> None:
        self._zero()
        text, _ = _read_regular(self.networking, MAX_NETWORKING_BYTES)
        try:
            source = text.decode("utf-8")
        except UnicodeError as exc:
            raise NetworkTransactionBlocked("VMware networking metadata not UTF-8") from exc
        verify_candidate_collisions(source, vmnet=vmnet, subnet=subnet,
                                    roots=self.roots, run=self.route_run)
        running = RunningVmwareInventory(0, 0, ())
        try:
            user = pwd.getpwnam(self.owner)
            result = audit_user_library(
                library=Path(user.pw_dir) / ".vmware/inventory.vmls",
                roots=self.roots, running=running,
                candidate_vmnet=vmnet,
            )
        except (ValueError, OSError, KeyError) as exc:
            raise NetworkTransactionBlocked("Original-user VMware library audit incomplete") from exc
        if result.outside_roots or result.running_not_in_library:
            raise NetworkTransactionBlocked("VMware registration coverage is incomplete")
        self._zero()

    def _verify(self, vmnet: str, subnet: str) -> None:
        self._zero()  # Guests must still be off before changing host IPv4
        raw, _ = _read_regular(self.networking, MAX_NETWORKING_BYTES)
        text = raw.decode("utf-8")
        self.reconciler.reconcile(vmnet, subnet, text)
        self.adapter.verify_host_adapter(vmnet, subnet, text)
        # Must independently verify actual separation from NORTH and learner NIC.
        self.isolation_acceptance(vmnet, subnet)

    def assemble(self) -> WslpeVmnetTransaction:
        if os.geteuid() != 0:
            raise NetworkTransactionBlocked("Root-only maintenance transaction")
        assert_private_state_dir(self.state_dir)
        self._zero()
        return WslpeVmnetTransaction(
            networking=self.networking,
            journal=self.state_dir / "journal.json",
            lock=self.state_dir / "exclusive.lock",
            running_guests=self._zero,
            live_preflight=self._preflight,
            vmware_action=self.service.action,
            verify_created_network=self._verify,
        )
