"""WSLPE read-only VMware guest inventory gate for management vmnet planning.

This gate does NOT authorize a vmware-networks restart: coverage of offline
registrations, ownership outside supplied workspaces, and guest network
isolation require separate proof before actual allocation.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess

from kingdoms.wslpe41_host_preflight import (
    HostEvidenceBlocked, read_only_command, running_vm_count,
)
from kingdoms.wslpe_management_vmnet_plan import inventory, vmx_conflicts


class HostVmnetGateBlocked(ValueError):
    """Insufficient or conflicting live host inventory evidence."""


@dataclass(frozen=True)
class RunningVmwareInventory:
    vmrun_count: int
    process_count: int
    vmx_paths: tuple[str, ...]


def parse_vmware_processes(returncode: int, stdout: str) -> int:
    """Interpret pgrep's no-match status exactly, not as an unknown success."""
    if returncode == 1 and stdout.strip() in ("", "0"):
        return 0
    if returncode != 0 or not re.fullmatch(r"[1-9][0-9]*", stdout.strip()):
        raise HostVmnetGateBlocked("Cannot establish exact vmware-vmx process count")
    count = int(stdout.strip())
    if count > 500:
        raise HostVmnetGateBlocked("Unbounded VMware process inventory")
    return count


def parse_running_vmware(output: str, roots: tuple[Path, ...],
                         process_count: int) -> RunningVmwareInventory:
    """Require that every running VMX is an existing, owned path in given roots."""
    if not roots:
        raise HostVmnetGateBlocked("No explicitly inspected workspaces")
    canonical_roots: list[Path] = []
    for root in roots:
        if root.is_symlink() or not root.is_dir():
            raise HostVmnetGateBlocked("Workspace is missing or symlinked")
        resolved = root.resolve(strict=True)
        if resolved != root.absolute():
            raise HostVmnetGateBlocked("Workspace path contains a symlink")
        if resolved in canonical_roots:
            raise HostVmnetGateBlocked("Duplicate VMware workspace")
        canonical_roots.append(resolved)

    try:
        count = running_vm_count(output)
    except HostEvidenceBlocked as exc:
        raise HostVmnetGateBlocked("Untrustworthy vmrun running inventory") from exc
    if count != process_count:
        raise HostVmnetGateBlocked(
            f"vmrun count {count} differs from vmware-vmx processes {process_count}"
        )

    lines = [line.strip() for line in output.splitlines() if line.strip()][1:]
    matched: list[str] = []
    for line in lines:
        path = Path(line)
        if not path.is_absolute() or path.suffix.lower() != ".vmx":
            raise HostVmnetGateBlocked("Running VMware entry is not an absolute VMX")
        if path.is_symlink() or not path.is_file():
            raise HostVmnetGateBlocked("Running VMware VMX is missing or linked")
        resolved = path.resolve(strict=True)
        if resolved != path:
            raise HostVmnetGateBlocked("Running VMware VMX contains path aliases")
        if not any(resolved.is_relative_to(root) for root in canonical_roots):
            raise HostVmnetGateBlocked(
                "Running VMX outside supplied workspace coverage"
            )
        matched.append(str(resolved))
    if len(set(matched)) != count:
        raise HostVmnetGateBlocked("Duplicate running VMware VMX registrations")
    return RunningVmwareInventory(count, process_count, tuple(sorted(matched)))


def probe_running_vmware(roots: tuple[Path, ...]) -> RunningVmwareInventory:
    """Read only: vmrun and kernel process count; recheck if topology changes."""
    try:
        vmrun = read_only_command("vmrun", "-T", "ws", "list")
        process = subprocess.run(
            ["pgrep", "-c", "-x", "vmware-vmx"], check=False,
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired, HostEvidenceBlocked) as exc:
        raise HostVmnetGateBlocked("Cannot inspect VMware running state") from exc
    count = parse_vmware_processes(process.returncode, process.stdout)
    return parse_running_vmware(vmrun, roots, count)


def scoped_candidate_free(networking_text: str, roots: tuple[Path, ...],
                          candidate_vmnet: str) -> None:
    """Reject reserved, allocated, and workspace-owned VMnets (read only)."""
    if not re.fullmatch(r"vmnet(?:[2-9]|[1-9][0-9]{1,2})", candidate_vmnet):
        raise HostVmnetGateBlocked("Invalid candidate VMnet")
    number = int(candidate_vmnet[5:])
    if number in {0, 1, 8, 10, 20, 30, 99}:
        raise HostVmnetGateBlocked("Candidate belongs to VMware/NORTH reserved range")
    try:
        vmnets = inventory(networking_text)
        conflicts = vmx_conflicts(list(roots), candidate_vmnet)
    except (ValueError, OSError) as exc:
        raise HostVmnetGateBlocked("Candidate workspace inventory incomplete") from exc
    if number in vmnets:
        raise HostVmnetGateBlocked("Candidate exists in VMware networking metadata")
    if conflicts:
        raise HostVmnetGateBlocked("Candidate referenced by an existing workspace VMX")
