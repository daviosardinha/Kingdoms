"""Read-only VMware Workstation library inventory, including powered-off guests.

Workstation's ~/.vmware/inventory.vmls lists VMX files known to the GUI.
vmrun list alone does NOT include powered-off guests. This module does not
enumerate all unregistered or inaccessible VMX files on the host.
"""
from __future__ import annotations

import re
from pathlib import Path

# Primary Workstation library entries and VMware's alternate index identifiers.
_REG_ENTRY = re.compile(
    r'^\s*(?:vmlist\d+\.config|index\d+\.id)\s*=\s*"([^"\r\n]*)"\s*$',
    re.I | re.M,
)
MAX_INVENTORY_BYTES = 2_000_000
MAX_REGISTERED = 512


def parse_library_vmx_paths(contents: str) -> tuple[list[Path], int]:
    """Parse registry VMX pointers; malformed/non-absolute entries are flagged.

    Empty slots are normal. The caller can reject suspicious path formats.
    Identifiers are returned as paths only inside the local process; full
    paths are intentionally absent from the published survey.
    """
    discovered: set[str] = set()
    invalid = 0
    for matched in _REG_ENTRY.finditer(contents):
        candidate = matched.group(1).strip()
        if not candidate:
            continue
        path = Path(candidate)
        if not path.is_absolute() or path.suffix.lower() != ".vmx":
            invalid += 1
            continue
        discovered.add(str(path))
    if len(discovered) > MAX_REGISTERED:
        raise ValueError("VMware Workstation registered VM count exceeds survey limit")
    return [Path(s) for s in sorted(discovered)], invalid


def inspect_workstation_library(summarize, reference_macs,
                                library_path: Path | None = None) -> dict:
    """Inspect registered VMX network settings only, never guest power state."""
    path = library_path if library_path is not None else (
        Path.home() / ".vmware" / "inventory.vmls"
    )
    output = {
        "library_status": "NOT_FOUND",
        "library_present": False,
        "complete": False,
        "invalid_entries": 0,
        "registered_vm_count": 0,
        "registered_vms": [],
    }
    try:
        if path.is_symlink():
            output["library_status"] = "UNREADABLE"
            return output
        if not path.exists():
            return output
        output["library_present"] = True
        if not path.is_file() or path.stat().st_size > MAX_INVENTORY_BYTES:
            output["library_status"] = "UNREADABLE"
            return output
        paths, invalid = parse_library_vmx_paths(
            path.read_text(encoding="utf-8", errors="replace")
        )
    except (ValueError, OSError):
        output["library_status"] = "UNREADABLE"
        return output
    rows = [summarize(item, reference_macs) for item in paths]
    output.update({
        "invalid_entries": invalid,
        "registered_vm_count": len(paths),
        "registered_vms": rows,
        "complete": invalid == 0 and all(row["readable"] for row in rows),
    })
    output["library_status"] = "INSPECTED" if output["complete"] else "INCOMPLETE"
    return output
