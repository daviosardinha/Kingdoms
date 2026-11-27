"""Read-only NORTH offline handoff inventory guard.

This intentionally cannot stop, unregister, delete or reassign a VM or VMware
network. It is the prerequisite to a separately reviewed, rollback-safe host
ownership release. Never remove the immutable owner/journal to bypass a gate.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

from goad.course1_host_network_apply import (
    NorthSetupError,
    inspect_installed_north,
    operator_inventory,
    require_explicit_root,
)

GUESTS = ("GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01", "GOAD-ROUTER")
REGISTERED = re.compile(r'(?m)^vmlist\d+\.config\s*=\s*"([^"\n]+)"\s*$')
INDEXED = re.compile(r'(?m)^index\d+\.id\s*=\s*"([^"\n]+)"\s*$')


class HandoffPlanError(ValueError):
    pass


def regular_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise HandoffPlanError("Required file is missing or symlinked: " + str(path))


def expected_guest_vmx(provider: Path) -> dict[str, str]:
    """Bind the plan to five actual, preserved Vagrant VMX files."""
    if not provider.is_absolute() or provider.is_symlink() or not provider.is_dir():
        raise HandoffPlanError("NORTH provider directory missing or unsafe")
    expected = {}
    for vm in GUESTS:
        root = provider / ".vagrant" / "machines" / vm / "vmware_desktop"
        marker = root / "id"
        regular_file(marker)
        name = marker.read_text(encoding="utf-8").strip()
        vmx = Path(name)
        if (not vmx.is_absolute() or vmx.suffix.lower() != ".vmx"
                or vmx.is_symlink() or not vmx.is_file()
                or vmx.parent.parent != root):
            raise HandoffPlanError("Vagrant VMX identity is unsafe: " + vm)
        expected[vm] = str(vmx)
    if len(set(expected.values())) != len(GUESTS):
        raise HandoffPlanError("Duplicate VMX identity across NORTH guests")
    return expected


def inventory_state(provider: Path, expected: dict[str, str], inventory: Path):
    """Match both VMware library lists without editing the user's inventory."""
    regular_file(inventory)
    contents = inventory.read_text(encoding="utf-8")
    prefix = str(provider) + "/"
    counts = (
        Counter(path for path in REGISTERED.findall(contents) if path.startswith(prefix)),
        Counter(path for path in INDEXED.findall(contents) if path.startswith(prefix)),
    )
    wanted = Counter(expected.values())
    if counts == (wanted, wanted):
        return "registered", len(wanted) * 2
    if counts == (Counter(), Counter()):
        return "unregistered", 0
    raise HandoffPlanError(
        "Incomplete/foreign VMware inventory references for the old NORTH "
        "provider. Stop: remove ONLY these five VMs from VMware Library "
        "without deleting their files, and re-check. No automatic edits."
    )


def plan(provider: Path, inventory: Path, expect: str) -> dict:
    provider = Path(provider)
    inventory = Path(inventory)
    proofs = inspect_installed_north(provider)
    expected = expected_guest_vmx(provider)
    state, count = inventory_state(provider, expected, inventory)
    if state != expect:
        raise HandoffPlanError(
            "Expected VMware library state " + expect + ", observed " + state
        )
    return {
        "mode": "READ_ONLY_NO_HOST_MODIFICATION",
        "provider": str(provider),
        "network_ownership": list(proofs),
        "vm_count": len(expected),
        "inventory_reference_count": count,
        "inventory_state": state,
        "vmx": expected,
        "disk_preservation": "No VM files were removed or modified",
        "network_release_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-dir", required=True)
    parser.add_argument("--expect", choices=("registered", "unregistered"),
                        default="registered")
    args = parser.parse_args()
    try:
        # Owner, backup and journal are protected by root-only access.
        require_explicit_root()
        record = plan(Path(args.provider_dir), operator_inventory(), args.expect)
    except (NorthSetupError, HandoffPlanError, OSError, UnicodeError) as exc:
        parser.exit(1, "[BLOCKED] NORTH offline handoff: " + str(exc) + "\n")
    print(json.dumps(record, sort_keys=True, indent=2))
    print("[PASS] Read-only NORTH VM inventory verified")
    print("[NOT AUTHORIZED] No shutdown, library unregister or vmnet release was performed")


if __name__ == "__main__":
    main()
