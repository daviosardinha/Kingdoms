"""Build a READ-ONLY additive VMware network maintenance plan for Course 1.

This produces an exact in-memory configuration delta without stopping VMware,
writing /etc/vmware/networking, changing interfaces or starting guests.
Application requires a separately approved maintenance workflow.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
from pathlib import Path

from goad.course1_host_fit import inspect_host_fit
from goad.course1_network_plan import ZONES, require, validate_proposal
from goad.course1_runtime_contract import ProfileNotReady

NETWORKING = Path("/etc/vmware/networking")
KEY = re.compile(r"^\s*answer\s+VNET_(\d+)_([A-Z0-9_]+)\s+(\S+)\s*$")
MAX_BYTES = 1_000_000


def desired_network_lines(proposal: dict) -> tuple[str, ...]:
    validate_proposal(proposal)
    result: list[str] = []
    host_addresses = proposal["host_addresses"]
    for zone in ZONES:
        cfg = proposal["zones"][zone]
        vmnet = cfg["vmnet"]
        number = int(vmnet[5:])
        require(2 <= number <= 19 and number != 8,
                "Course 1 VMware vmnet must be a supported custom-network candidate")
        network = ipaddress.IPv4Network(cfg["subnet"])
        host_visible = zone in ("NORTH", "MANAGEMENT")
        result.append(f"# KINGDOMS COURSE 1 {zone} {vmnet} (proposed, maintenance-only)")
        result.append(f"answer VNET_{number}_DHCP no")
        if host_visible:
            result.append(
                f"answer VNET_{number}_HOSTONLY_HOSTADDR {host_addresses[zone]}"
            )
        result.extend((
            f"answer VNET_{number}_HOSTONLY_NETMASK {network.netmask}",
            f"answer VNET_{number}_HOSTONLY_SUBNET {network.network_address}",
            f"answer VNET_{number}_VIRTUAL_ADAPTER {'yes' if host_visible else 'no'}",
        ))
    return tuple(result)


def compose_additive(original: str, proposal: dict) -> tuple[str, tuple[str, ...]]:
    """Fail closed on existing keys and keep every original byte intact."""
    require(original != "" and "\x00" not in original,
            "existing VMware networking configuration is invalid")
    require(original.endswith("\n"),
            "VMware networking file must end in newline before additive changes")
    lines = desired_network_lines(proposal)
    reserved = {int(proposal["zones"][zone]["vmnet"][5:]) for zone in ZONES}
    for line in original.splitlines():
        match = KEY.fullmatch(line)
        if match:
            number = int(match.group(1))
            require(number not in reserved,
                    f"existing VMware vmnet{number} entry; refuse overwrite")
        else:
            # Never remove or modify unknown VMware directives from the original.
            if re.match(r"^\s*answer\s+VNET_", line):
                raise ProfileNotReady(
                    "unknown VMware VNET directive; manual network editor review required"
                )
    new_config = original + "\n" + "\n".join(lines) + "\n"
    require(new_config.startswith(original),
            "proposed edit must preserve original VMware configuration exactly")
    return new_config, lines


def inspect_maintenance(proposal: dict, snapshot: dict, original: str) -> dict:
    """No install/network authorization: determine next real host action."""
    collision = inspect_host_fit(proposal, snapshot)
    registered = snapshot["registered_inventory"]
    require(registered.get("library_status") == "INSPECTED"
            and registered.get("complete") is True,
            "registered powered-off VMware inventory required before maintenance planning")
    config, additions = compose_additive(original, proposal)
    running = snapshot["running_vm_count"]
    require(isinstance(running, int) and running >= 0,
            "invalid number of running reference VMware guests")

    return {
        "kind": "KINGDOMS_COURSE1_VMWARE_MAINTENANCE_PLAN",
        "status": ("MAINTENANCE_WINDOW_REQUIRED" if running
                   else "HOST_CHANGE_REQUIRES_EXPLICIT_APPROVAL"),
        "profile": collision["profile"],
        "zones": {
            zone: {
                "vmnet": proposal["zones"][zone]["vmnet"],
                "subnet": proposal["zones"][zone]["subnet"],
                "host_adapter": zone in ("NORTH", "MANAGEMENT"),
                "dhcp": False,
                "nat": False,
            } for zone in ZONES
        },
        "vmware_networking_existing_sha256": hashlib.sha256(
            original.encode("utf-8")).hexdigest(),
        "vmware_networking_proposed_sha256": hashlib.sha256(
            config.encode("utf-8")).hexdigest(),
        "additive_lines_only": list(additions),
        "original_configuration_preserved": config.startswith(original),
        "registered_vmx_examined": registered["registered_vm_count"],
        "running_vm_count": running,
        "running_guest_shutdown_required": running > 0,
        "host_side_address_persistence_pending": True,
        "unregistered_vm_inventory_not_exhaustive": True,
        "vmware_networks_modified": False,
        "vmware_networks_allocated": False,
        "deployment_authorized": False,
        "allocation_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path,
                        help="private JSON snapshot from one read-only host survey")
    args = parser.parse_args()
    try:
        proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        require(NETWORKING.is_file() and not NETWORKING.is_symlink(),
                "VMware /etc/vmware/networking must be readable and not a symlink")
        require(NETWORKING.stat().st_size <= MAX_BYTES,
                "VMware networking file unexpectedly large")
        original = NETWORKING.read_text(encoding="utf-8")
        report = inspect_maintenance(proposal, snapshot, original)
        print(json.dumps(report, indent=2))
        print("[BLOCKED] Network changes require a maintenance window and a separate explicitly approved installer")
    except (ProfileNotReady, OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, "[FAIL] " + str(exc) + "\n")


if __name__ == "__main__":
    main()
