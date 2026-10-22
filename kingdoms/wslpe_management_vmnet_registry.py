"""Read-only per-user VMware Workstation library inspection.

Workstation's inventory.vmls is a user library, NOT global proof of all
offline VMXs. This code never calls vmware-networks or mutates files.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from kingdoms.wslpe_management_vmnet_host_gate import (
    HostVmnetGateBlocked, RunningVmwareInventory,
)

INDEX = re.compile(r'^\s*vmlist(\d+)\.config\s*=\s*"([^"]+)"\s*$', re.I)
POSSIBLE = re.compile(r"^\s*vmlist\d+\.config\b", re.I)
VNET = re.compile(r'^\s*ethernet\d+\.vnet\s*=\s*"([^"]+)"\s*$', re.I)
POSSIBLE_VNET = re.compile(r"^\s*ethernet\d+\.vnet\s*=", re.I)
CUSTOM = re.compile(r'^\s*ethernet\d+\.connectionType\s*=\s*"custom"\s*$', re.I)
MAX_INVENTORY = 200_000
MAX_VMX = 2_000_000
MAX_ENTRIES = 500


@dataclass(frozen=True)
class LibraryAudit:
    count: int
    vmx_paths: tuple[str, ...]
    outside_roots: tuple[str, ...]
    running_not_in_library: tuple[str, ...]


def _regular(path: Path, max_bytes: int) -> str:
    if path.is_symlink() or not path.is_file():
        raise HostVmnetGateBlocked(f"VMware library/VMX missing or linked: {path}")
    if path.resolve(strict=True) != path:
        raise HostVmnetGateBlocked(f"VMware library/VMX uses path alias: {path}")
    if path.stat().st_size > max_bytes:
        raise HostVmnetGateBlocked(f"VMware library/VMX too large: {path}")
    try:
        return path.read_text(encoding="utf-8-sig")
    except (UnicodeError, OSError) as exc:
        raise HostVmnetGateBlocked("Cannot parse VMware inventory/VMX text safely") from exc


def parse_workstation_library(text: str) -> tuple[Path, ...]:
    """Extract all vmlistN.config VMX paths; reject ambiguous entries."""
    if not isinstance(text, str) or not text.strip():
        raise HostVmnetGateBlocked("Empty VMware Workstation library")
    indexed: dict[int, Path] = {}
    for line in text.splitlines():
        if not POSSIBLE.match(line):
            continue
        match = INDEX.fullmatch(line)
        if match is None:
            raise HostVmnetGateBlocked("Unparseable Workstation VMX library entry")
        number, value = match.groups()
        entry = Path(value)
        if (not entry.is_absolute() or entry.suffix.lower() != ".vmx"
                or any(c in value for c in ('\\', '\0'))):
            raise HostVmnetGateBlocked("Nonabsolute/unsupported VMX library path")
        if int(number) in indexed:
            raise HostVmnetGateBlocked("Duplicate VM library entry index")
        indexed[int(number)] = entry
        if len(indexed) > MAX_ENTRIES:
            raise HostVmnetGateBlocked("Workstation library exceeds size bound")
    if not indexed:
        raise HostVmnetGateBlocked("Workstation library contains no VMX entries")
    if len(set(indexed.values())) != len(indexed):
        raise HostVmnetGateBlocked("Duplicate VMX registered in Workstation library")
    return tuple(indexed[k] for k in sorted(indexed))


def referenced_vnets(text: str) -> set[str]:
    """Reject ambiguous custom VMX interface assignments."""
    refs: set[str] = set()
    custom = 0
    found = 0
    for line in text.splitlines():
        if POSSIBLE_VNET.match(line):
            found += 1
            match = VNET.fullmatch(line)
            if match is None:
                raise HostVmnetGateBlocked("Unparseable VMX vmnet assignment")
            name = match.group(1)
            if not re.fullmatch(r"vmnet\d+", name, re.I):
                raise HostVmnetGateBlocked("Unknown custom VMnet assignment")
            refs.add(name.lower())
        if CUSTOM.fullmatch(line):
            custom += 1
    if custom > found:
        raise HostVmnetGateBlocked("VMX has custom NIC without explicit vmnet")
    return refs


def audit_user_library(*, library: Path, roots: tuple[Path, ...],
                       running: RunningVmwareInventory,
                       candidate_vmnet: str) -> LibraryAudit:
    """Read only; partial offline-library evidence, never global registry proof."""
    if not re.fullmatch(r"vmnet[2-9]\d*", candidate_vmnet):
        raise HostVmnetGateBlocked("Invalid management VMnet")
    if not roots:
        raise HostVmnetGateBlocked("No supplied VMware workspace coverage")
    base_roots = []
    for root in roots:
        if root.is_symlink() or not root.is_dir() or root.resolve() != root.absolute():
            raise HostVmnetGateBlocked("Unsafe workspace root")
        base_roots.append(root.resolve(strict=True))
    vmxs = parse_workstation_library(_regular(library, MAX_INVENTORY))
    outside: list[str] = []
    for vmx in vmxs:
        if not any(vmx.is_relative_to(root) for root in base_roots):
            outside.append(str(vmx))
        references = referenced_vnets(_regular(vmx, MAX_VMX))
        if candidate_vmnet.lower() in references:
            raise HostVmnetGateBlocked(
                f"Registered Workstation VMX already references {candidate_vmnet}: {vmx}"
            )
    missing = sorted(set(running.vmx_paths) - {str(p) for p in vmxs})
    return LibraryAudit(len(vmxs), tuple(str(p) for p in vmxs),
                        tuple(sorted(outside)), tuple(missing))
