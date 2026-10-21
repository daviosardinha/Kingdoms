"""Read-only host evidence for the one-shot WSLPE41 native VMware install.

Never provisions, stops, reconfigures or snapshots VMware guests. A successful
plan is a *candidate*, not a deployment authorization or network isolation proof.
All host commands are read-only and fail closed on missing/ambiguous evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess

from kingdoms.wslpe41_network_auto import (
    NetworkSelectionBlocked, select_available_prefix,
)


VMWARE_NETWORKING = Path("/etc/vmware/networking")
MAX_INSTANCES = 500
MAX_OUTPUT = 2_000_000


class HostEvidenceBlocked(ValueError):
    pass


@dataclass(frozen=True)
class HostInstallPlan:
    prefix: str
    subnet: str
    guest_address: str
    running_vm_count: int
    registered_instance_count: int
    workspace_count: int


def read_only_command(*command: str, timeout: int = 20) -> str:
    try:
        result = subprocess.run(
            list(command), capture_output=True, text=True, check=False,
            timeout=timeout, stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HostEvidenceBlocked(f"Read-only command unavailable: {command[0]}") from exc
    if result.returncode != 0 or len(result.stdout) > MAX_OUTPUT:
        raise HostEvidenceBlocked(f"Read-only command failed: {command[0]}")
    return result.stdout


def ipv4_json(*command: str) -> list:
    raw = read_only_command("ip", "-j", "-4", *command)
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HostEvidenceBlocked("Malformed Linux IPv4 inventory") from exc
    if not isinstance(decoded, list):
        raise HostEvidenceBlocked("Unexpected Linux IPv4 inventory shape")
    return decoded


def running_vm_count(output: str) -> int:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        raise HostEvidenceBlocked("VMware running guest inventory missing")
    match = re.fullmatch(r"Total running VMs: (\d+)", lines[0])
    if not match or int(match.group(1)) != len(lines) - 1:
        raise HostEvidenceBlocked("VMware running guest inventory is inconsistent")
    if len(set(lines[1:])) != len(lines[1:]):
        raise HostEvidenceBlocked("VMware running guest inventory has duplicates")
    return int(match.group(1))


def native_instance_prefixes(workspaces: tuple[Path, ...]) -> tuple[list[str], int]:
    if not workspaces:
        raise HostEvidenceBlocked("At least one native workspace must be inspected")
    seen: set[Path] = set()
    prefixes: list[str] = []
    total = 0
    for root in workspaces:
        if root.is_symlink():
            raise HostEvidenceBlocked("Refusing symlinked native workspace")
        canonical = root.resolve()
        if canonical in seen:
            raise HostEvidenceBlocked("Duplicate native workspace")
        seen.add(canonical)
        if not root.exists():
            # A clean checkout has no workspace yet. Explicit additional
            # workspace roots must be present; checked by the CLI.
            continue
        if not root.is_dir():
            raise HostEvidenceBlocked("Native workspace is not a directory")
        children = list(root.iterdir())
        if len(children) > MAX_INSTANCES:
            raise HostEvidenceBlocked("Too many native workspace entries")
        for instance in children:
            if instance.is_symlink():
                raise HostEvidenceBlocked("Symlinked native instance")
            if not instance.is_dir():
                continue
            manifest = instance / "instance.json"
            if manifest.is_symlink():
                raise HostEvidenceBlocked("Symlinked native instance manifest")
            if not manifest.exists():
                continue
            if not manifest.is_file() or manifest.stat().st_size > 200_000:
                raise HostEvidenceBlocked("Unsafe native instance manifest")
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise HostEvidenceBlocked("Unreadable native instance manifest") from exc
            if not isinstance(data, dict):
                raise HostEvidenceBlocked("Invalid native instance manifest")
            prefix = data.get("ip_range")
            if not isinstance(prefix, str):
                raise HostEvidenceBlocked("Native instance subnet is unknown")
            prefixes.append(prefix)
            total += 1
    return prefixes, total


def host_plan(
    *, workspaces: tuple[Path, ...],
    vmware_networking: Path = VMWARE_NETWORKING,
) -> HostInstallPlan:
    """One read-only evidence snapshot. Re-run immediately before any install."""
    if vmware_networking.is_symlink() or not vmware_networking.is_file():
        raise HostEvidenceBlocked("VMware networking file is missing or symlinked")
    if vmware_networking.stat().st_size > 200_000:
        raise HostEvidenceBlocked("Unexpected VMware networking file size")
    try:
        vmnet_text = vmware_networking.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise HostEvidenceBlocked("VMware networking metadata unreadable") from exc
    addresses = ipv4_json("addr", "show")
    routes = ipv4_json("route", "show", "table", "all")
    running = running_vm_count(read_only_command("vmrun", "-T", "ws", "list"))
    prefixes, registered = native_instance_prefixes(workspaces)
    try:
        selected = select_available_prefix(addresses, routes, vmnet_text, prefixes)
    except NetworkSelectionBlocked as exc:
        raise HostEvidenceBlocked(str(exc)) from exc
    return HostInstallPlan(
        prefix=selected,
        subnet=selected + ".0/24",
        guest_address=selected + ".31",
        running_vm_count=running,
        registered_instance_count=registered,
        workspace_count=len(workspaces),
    )
