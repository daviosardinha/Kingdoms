"""Course 1 VMware host-network config planning for the existing Kingdoms script.

No filesystem/systemd/VMware/route mutations. Generate the three vmnets
declared by ad/NORTH/topology.json; preserve every original VMware setting,
and fail on occupied network IDs or inherited address overlap. This is the
source of truth for a future audited installation stage, NOT a new provider.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import sys
from pathlib import Path

from goad.kingdoms_topology import load_course1_topology, parse_vmnet_args

NETWORKING_FILE = Path("/etc/vmware/networking")
KEY = re.compile(r"^\s*answer\s+VNET_(\d+)_([A-Z0-9_]+)(?:\s+|$)")
NETWORK_DECLARATION = re.compile(r"^\s*(?:answer\s+)?VNET_(\d+)_", re.I)
NETWORK_LABELS = ("north", "sevenkingdoms", "management")


class NetworkPlanError(ValueError):
    """Host networking must not be changed until the collision is resolved."""


def _existing_network_metadata(original: str) -> tuple[set[int], list[ipaddress.IPv4Network]]:
    occupied: set[int] = set()
    ranges: list[ipaddress.IPv4Network] = []
    for line in original.splitlines():
        found = KEY.match(line)
        if not found:
            continue
        vmnet, property_name = int(found.group(1)), found.group(2)
        occupied.add(vmnet)
        if property_name == "HOSTONLY_SUBNET":
            fields = line.split()
            if len(fields) != 3:
                raise NetworkPlanError("Malformed VMware host-only subnet setting")
            try:
                network = ipaddress.ip_network(fields[2] + "/24", strict=True)
            except ValueError as exc:
                raise NetworkPlanError("Invalid existing VMware host-only subnet") from exc
            ranges.append(network)
    return occupied, ranges


def render_vmnet_config(original: str, layout: dict) -> str:
    """Return desired /etc/vmware/networking with all foreign lines preserved."""
    if not isinstance(original, str) or not original.strip():
        raise NetworkPlanError("Missing VMware networking baseline")
    segments = layout.get("segments", {})
    if set(segments) != set(NETWORK_LABELS):
        raise NetworkPlanError("Unexpected Course 1 network segments")
    selected: set[int] = set()
    requested: list[ipaddress.IPv4Network] = []
    for name, zone in segments.items():
        vmnet = zone["vmnet"]
        if not re.fullmatch(r"vmnet\d+", vmnet):
            raise NetworkPlanError("Invalid VMware vmnet assignment")
        vmnet_id = int(vmnet[5:])
        if vmnet_id in selected:
            raise NetworkPlanError("Duplicate vmnet ID")
        selected.add(vmnet_id)
        requested.append(ipaddress.ip_network(zone["cidr"], strict=True))
        if name == "sevenkingdoms" and zone["host_address"] is not None:
            raise NetworkPlanError("Protected parent subnet must not get a host adapter")
    if len(requested) != len(set(requested)):
        raise NetworkPlanError("Duplicate requested subnet")

    occupied, existing_ranges = _existing_network_metadata(original)
    collisions = selected & occupied
    if collisions:
        raise NetworkPlanError("VMware vmnet IDs already allocated: " + repr(sorted(collisions)))
    for proposed in requested:
        for foreign in existing_ranges:
            if proposed.overlaps(foreign):
                raise NetworkPlanError("Requested subnet overlaps existing VMware network")
    # Malformed/unknown VNET declarations are not safe to treat as available.
    for line in original.splitlines():
        if line.lstrip().startswith("#"):
            continue
        candidate = NETWORK_DECLARATION.match(line)
        if candidate and int(candidate.group(1)) in selected:
            raise NetworkPlanError("Ambiguous existing requested VMware network definition")

    lines = []
    lines.append("# Kingdoms Course 1 managed networks (additive; source-only plan)")
    for name in NETWORK_LABELS:
        zone = segments[name]
        net = int(zone["vmnet"][5:])
        subnet = ipaddress.ip_network(zone["cidr"], strict=True)
        host = zone["host_address"]
        lines.extend((
            f"# {zone['vmnet']}: {name.upper()}",
            f"answer VNET_{net}_DHCP no",
            f"answer VNET_{net}_HOSTONLY_NETMASK 255.255.255.0",
            f"answer VNET_{net}_HOSTONLY_SUBNET {subnet.network_address}",
            f"answer VNET_{net}_VIRTUAL_ADAPTER {'yes' if host else 'no'}",
        ))
        if host:
            # The running host address is separately proven at install time.
            lines.append(f"answer VNET_{net}_HOSTONLY_HOSTADDR {host}")
        lines.append(f"answer VNET_{net}_NAT no")
    suffix = "\n".join(lines) + "\n"
    return original.rstrip("\n") + "\n\n" + suffix


def network_plan(network_base=None, vmnets=None, baseline: str | None = None) -> dict:
    layout = load_course1_topology(network_base, vmnets)
    if baseline is None:
        if not NETWORKING_FILE.is_file() or NETWORKING_FILE.is_symlink():
            raise NetworkPlanError("VMware networking baseline is missing or unsafe")
        baseline = NETWORKING_FILE.read_text(encoding="utf-8")
    desired = render_vmnet_config(baseline, layout)
    before = hashlib.sha256(baseline.encode("utf-8")).hexdigest()
    after = hashlib.sha256(desired.encode("utf-8")).hexdigest()
    return {
        "profile": "NORTH",
        "network_base": layout["network_base"],
        "segment_settings": {
            name: {
                "vmnet": zone["vmnet"],
                "cidr": zone["cidr"],
                "host_address": zone["host_address"],
                "dhcp": False,
                "nat": False,
            }
            for name, zone in layout["segments"].items()
        },
        "baseline_sha256": before,
        "proposed_sha256": after,
        "proposed_text": desired,
        "mode": "READ-ONLY; no VMware, kernel, systemd, or files modified",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render-only VMware network plan for existing Kingdoms NORTH"
    )
    parser.add_argument("action", choices=("plan",))
    parser.add_argument("--network-base", default=None)
    parser.add_argument("--vmnet", action="append", default=[])
    args = parser.parse_args()
    try:
        planned = network_plan(args.network_base, parse_vmnet_args(args.vmnet))
    except (NetworkPlanError, ValueError, OSError, KeyError) as exc:
        parser.exit(1, "[BLOCKED] NORTH VMware networking: " + str(exc) + "\n")
    print(json.dumps({k: v for k, v in planned.items() if k != "proposed_text"},
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
