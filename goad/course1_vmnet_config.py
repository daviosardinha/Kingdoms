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
    declared: dict[int, dict[str, str]] = {}
    for line in original.splitlines():
        found = KEY.match(line)
        if not found:
            continue
        vmnet, property_name = int(found.group(1)), found.group(2)
        occupied.add(vmnet)
        fields = line.split()
        if len(fields) != 3:
            raise NetworkPlanError("Malformed VMware network setting")
        if property_name in ("HOSTONLY_SUBNET", "HOSTONLY_NETMASK"):
            setting = declared.setdefault(vmnet, {})
            if property_name in setting:
                raise NetworkPlanError("Duplicate existing VMware subnet or netmask")
            setting[property_name] = fields[2]
    for setting in declared.values():
        subnet = setting.get("HOSTONLY_SUBNET")
        if subnet is None:
            continue
        mask = setting.get("HOSTONLY_NETMASK", "255.255.255.0")
        try:
            network = ipaddress.ip_network(f"{subnet}/{mask}", strict=True)
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


def verify_vmnet_config(config: str, layout: dict) -> tuple[str, ...]:
    """Verify exact config-level DHCP, NAT, subnet and host-adapter policy.

    This does not assert the host interfaces actually have the .254 addresses.
    The existing Linux address helper/runtime network checks remain separate.
    """
    if not isinstance(config, str) or not config.strip():
        raise NetworkPlanError("VMware networking configuration is absent")
    per_net: dict[int, dict[str, list[str]]] = {}
    for raw in config.splitlines():
        m = KEY.match(raw)
        if m is None:
            continue
        words = raw.split()
        if len(words) != 3:
            raise NetworkPlanError("Malformed existing VMware network setting")
        per_net.setdefault(int(m.group(1)), {}).setdefault(m.group(2), []).append(words[2])

    checked = []
    for name in NETWORK_LABELS:
        zone = layout["segments"][name]
        number = int(zone["vmnet"][5:])
        values = per_net.get(number, {})
        network = ipaddress.ip_network(zone["cidr"], strict=True)
        expected = {
            "DHCP": "no",
            "NAT": "no",
            "HOSTONLY_NETMASK": "255.255.255.0",
            "HOSTONLY_SUBNET": str(network.network_address),
            "VIRTUAL_ADAPTER": "yes" if zone["host_address"] is not None else "no",
        }
        # VMware may remove the optional host-address metadata when it
        # recreates an adapter; host addresses require separate live checks.
        if zone["host_address"] is not None:
            if "HOSTONLY_HOSTADDR" in values:
                expected["HOSTONLY_HOSTADDR"] = zone["host_address"]
        elif "HOSTONLY_HOSTADDR" in values:
            raise NetworkPlanError(f"Protected {name} zone has an unwanted host address")
        for key, value in expected.items():
            actual = values.get(key, [])
            if actual != [value]:
                raise NetworkPlanError(
                    f"{zone['vmnet']} {key} mismatch or duplicate: "
                    f"expected {value}, observed {actual}"
                )
        checked.append(f"{zone['vmnet']} {name.upper()} configuration matches Kingdoms topology")
    return tuple(checked)


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
    parser.add_argument("action", choices=("plan", "check"))
    parser.add_argument("--network-base", default=None)
    parser.add_argument("--vmnet", action="append", default=[])
    args = parser.parse_args()
    try:
        allocations = parse_vmnet_args(args.vmnet)
        if args.action == "check":
            layout = load_course1_topology(args.network_base, allocations)
            if not NETWORKING_FILE.is_file() or NETWORKING_FILE.is_symlink():
                raise NetworkPlanError("VMware networking baseline is missing or unsafe")
            findings = verify_vmnet_config(
                NETWORKING_FILE.read_text(encoding="utf-8"), layout
            )
        else:
            planned = network_plan(args.network_base, allocations)
    except (NetworkPlanError, ValueError, OSError, KeyError) as exc:
        parser.exit(1, "[BLOCKED] NORTH VMware networking: " + str(exc) + "\n")
    if args.action == "check":
        for finding in findings:
            print("[PASS] " + finding)
        print("[CONFIG ONLY] Host interface addresses and owner identity not proven")
    else:
        print(json.dumps({k: v for k, v in planned.items() if k != "proposed_text"},
                         indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
