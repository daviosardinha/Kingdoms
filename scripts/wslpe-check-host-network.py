#!/usr/bin/env python3
"""WSLPE operator-only, READ-ONLY Linux VMware network collision preflight.

Inspects all IPv4 interfaces/routes and /etc/vmware/networking, not merely
the default route. Does not configure vmnets, boot VMs or approve deployment.
Pass means no *visible* collision, NOT network-isolation proof.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import subprocess
from pathlib import Path


VMWARE_CONFIG = Path("/etc/vmware/networking")
NORTH_RESERVED = ipaddress.IPv4Network("10.4.0.0/16")
CONFIG_KEY = re.compile(
    r"^\s*answer\s+VNET_(\d+)_(HOSTONLY_SUBNET|HOSTONLY_NETMASK)\s+(\S+)\s*$"
)


def parse_prefix(value: str) -> ipaddress.IPv4Network:
    if not re.fullmatch(r"(?:\d{1,3}\.){2}\d{1,3}", value):
        raise ValueError("Expected three-octet IPv4 prefix such as 172.28.231")
    try:
        network = ipaddress.ip_network(f"{value}.0/24", strict=True)
    except ValueError as exc:
        raise ValueError("Invalid IPv4 /24 prefix") from exc
    if not network.is_private or network.is_loopback or network.is_link_local:
        raise ValueError("Only private, non-loopback /24 candidates are permitted")
    if network.overlaps(NORTH_RESERVED):
        raise ValueError("Candidate overlaps reserved NORTH 10.4.0.0/16")
    return network


def configured_vmnets(source: str) -> list[tuple[str, ipaddress.IPv4Network]]:
    values: dict[str, dict[str, str]] = {}
    for line in source.splitlines():
        match = CONFIG_KEY.fullmatch(line)
        if match:
            number, key, value = match.groups()
            values.setdefault(number, {})[key] = value
    if not values:
        raise ValueError("No VMware subnet metadata available")
    networks = []
    for number, values_for_net in sorted(values.items(), key=lambda item: int(item[0])):
        if "HOSTONLY_SUBNET" not in values_for_net:
            continue  # A VMware network without a configured IPv4 subnet.
        if "HOSTONLY_NETMASK" not in values_for_net:
            raise ValueError(f"vmnet{number} subnet has no netmask metadata")
        try:
            cidr = ipaddress.IPv4Network(
                (values_for_net["HOSTONLY_SUBNET"], values_for_net["HOSTONLY_NETMASK"]),
                strict=False,
            )
        except (ValueError, ipaddress.AddressValueError) as exc:
            raise ValueError(f"Invalid vmnet{number} subnet/netmask metadata") from exc
        networks.append((f"vmnet{number}", cidr))
    if not networks:
        raise ValueError("No usable VMware IPv4 subnet definitions")
    return networks


def host_ipv4_networks(addresses: list, routes: list) -> list[tuple[str, ipaddress.IPv4Network]]:
    found = []
    for interface in addresses:
        name = interface.get("ifname", "unknown-interface")
        for entry in interface.get("addr_info", []):
            if entry.get("family") != "inet":
                continue
            try:
                network = ipaddress.ip_network(
                    f"{entry['local']}/{entry['prefixlen']}", strict=False
                )
            except (KeyError, ValueError, TypeError) as exc:
                raise ValueError(f"Invalid IPv4 interface address on {name}") from exc
            found.append((f"interface {name}", network))
    for route in routes:
        destination = route.get("dst", "default")
        if destination in ("default", "0.0.0.0/0"):
            continue
        try:
            network = ipaddress.ip_network(destination, strict=False)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid IPv4 route destination: {destination!r}") from exc
        found.append((f"route table {route.get('table', 'main')} via {route.get('dev', 'unknown')}", network))
    return found


def assess(
    candidate: ipaddress.IPv4Network,
    addresses: list,
    routes: list,
    networking_text: str,
) -> tuple[list[str], list[str]]:
    """Return inspected evidence and collisions; do not change host state."""
    evidence = []
    conflicts = []
    targets = host_ipv4_networks(addresses, routes)
    targets += [(f"VMware {name}", cidr) for name, cidr in configured_vmnets(networking_text)]
    for label, cidr in targets:
        if candidate.overlaps(cidr):
            conflicts.append(f"{label} {cidr} overlaps {candidate}")
        elif label.startswith("VMware "):
            evidence.append(f"{label}: {cidr}")
    return evidence, sorted(set(conflicts))


def run_ip(*arguments: str) -> list:
    cmd = ["ip", "-j", "-4", *arguments]
    try:
        completed = subprocess.run(
            cmd, check=True, capture_output=True, text=True, timeout=15,
        )
        result = json.loads(completed.stdout)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
            json.JSONDecodeError) as exc:
        raise ValueError("Could not inspect " + " ".join(cmd)) from exc
    if not isinstance(result, list):
        raise ValueError("Unexpected iproute2 JSON output for " + " ".join(arguments))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ip-range", required=True,
        help="Three-octet private /24 candidate, e.g. 172.28.231",
    )
    args = parser.parse_args()
    try:
        candidate = parse_prefix(args.ip_range)
        addresses = run_ip("address", "show")
        routes = run_ip("route", "show", "table", "all")
        vmware_text = VMWARE_CONFIG.read_text(encoding="utf-8")
        evidence, conflicts = assess(candidate, addresses, routes, vmware_text)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"[BLOCKED] Unable to prove WSLPE VMware network clearance: {exc}\n")

    print(f"Kingdoms WSLPE READ-ONLY HOST NETWORK CHECK | candidate={candidate}")
    for line in evidence:
        print("  [INFO]", line)
    if conflicts:
        for conflict in conflicts:
            print("  [FAIL]", conflict)
        print("[BLOCKED] Candidate overlaps host routes, interfaces or VMware metadata")
        return 1
    print("[PASS] No candidate collision found in inspected Linux IPv4 and VMware configuration")
    print("[NOT VERIFIED] Actual Vagrant adapter mapping, other guests' static IPs, "
          "guest isolation, NAT policy and learner reachability")
    print("[NO CHANGES] Host, VMware, NORTH and WSLPE instance state untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
