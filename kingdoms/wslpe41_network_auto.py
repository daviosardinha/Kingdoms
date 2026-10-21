"""Read-only, deterministic WSLPE41 /24 allocation from authoritative host inputs.

A candidate is NOT permission to reconfigure VMware. Native guest creation
must rerun the collision audit and verify the actual assigned vmnet/guest IP.
"""
from __future__ import annotations

import ipaddress
import re


class NetworkSelectionBlocked(ValueError):
    pass


NORTH = ipaddress.IPv4Network("10.4.0.0/16")
SUBNET = re.compile(r"^answer\s+VNET_(\d+)_(HOSTONLY_SUBNET|HOSTONLY_NETMASK)\s+(\S+)\s*$")
CANDIDATES = tuple(
    f"172.{second}.{third}"
    for second in (28, 29, 30)
    for third in range(220, 255)
)


def _prefix_network(value: str) -> ipaddress.IPv4Network:
    if not isinstance(value, str):
        raise NetworkSelectionBlocked("Invalid native instance network")
    if re.fullmatch(r"(?:[0-9]{1,3}\.){2}[0-9]{1,3}", value):
        value += ".0/24"
    try:
        network = ipaddress.IPv4Network(value, strict=True)
    except (ValueError, TypeError) as exc:
        raise NetworkSelectionBlocked("Invalid native instance network") from exc
    if not network.is_private or network.is_loopback or network.is_link_local:
        raise NetworkSelectionBlocked("Only independent private networks are allowed")
    return network


def occupied_networks(
    addresses: list[dict], routes: list[dict],
    vmware_networking: str, native_instance_prefixes: list[str],
) -> tuple[ipaddress.IPv4Network, ...]:
    """Inspect live interfaces, all nondefault routes, VMware and stopped VMs."""
    if not isinstance(addresses, list) or not isinstance(routes, list):
        raise NetworkSelectionBlocked("Linux host interface/route evidence missing")
    if not isinstance(vmware_networking, str) or not vmware_networking.strip():
        raise NetworkSelectionBlocked("VMware networking metadata missing")
    if not isinstance(native_instance_prefixes, list):
        raise NetworkSelectionBlocked("Native workspace instance inventory missing")
    occupied = [NORTH]
    for item in addresses:
        if not isinstance(item, dict) or not isinstance(item.get("addr_info", []), list):
            raise NetworkSelectionBlocked("Invalid host address inventory")
        for address in item.get("addr_info", []):
            if address.get("family") != "inet":
                continue
            try:
                occupied.append(ipaddress.IPv4Network(
                    f"{address['local']}/{address['prefixlen']}", strict=False))
            except (ValueError, TypeError, KeyError) as exc:
                raise NetworkSelectionBlocked("Unparseable live IPv4 interface") from exc
    for route in routes:
        if not isinstance(route, dict):
            raise NetworkSelectionBlocked("Invalid route inventory")
        destination = route.get("dst", "default")
        if destination in ("default", "0.0.0.0/0"):
            continue
        try:
            occupied.append(ipaddress.IPv4Network(destination, strict=False))
        except (ValueError, TypeError) as exc:
            raise NetworkSelectionBlocked("Unparseable live IPv4 route") from exc
    vmnets: dict[str, dict[str, str]] = {}
    for line in vmware_networking.splitlines():
        match = SUBNET.fullmatch(line.strip())
        if match:
            number, key, value = match.groups()
            vmnets.setdefault(number, {})[key] = value
        elif re.match(r"^answer\s+VNET_\d+_(?:HOSTONLY_SUBNET|HOSTONLY_NETMASK)\b", line.strip()):
            raise NetworkSelectionBlocked("Malformed VMware subnet metadata")
    if not vmnets:
        raise NetworkSelectionBlocked("No VMware subnet definitions were inspected")
    for vmnet, data in vmnets.items():
        if set(data) != {"HOSTONLY_SUBNET", "HOSTONLY_NETMASK"}:
            raise NetworkSelectionBlocked(f"Incomplete vmnet{vmnet} subnet definition")
        try:
            occupied.append(ipaddress.IPv4Network(
                (data["HOSTONLY_SUBNET"], data["HOSTONLY_NETMASK"]), strict=False))
        except (ValueError, TypeError) as exc:
            raise NetworkSelectionBlocked(f"Invalid vmnet{vmnet} subnet") from exc
    for prefix in native_instance_prefixes:
        occupied.append(_prefix_network(prefix))
    return tuple(occupied)


def select_available_prefix(
    addresses: list[dict], routes: list[dict],
    vmware_networking: str, native_instance_prefixes: list[str],
    *, candidates: tuple[str, ...] = CANDIDATES,
) -> str:
    """Choose first non-overlapping private /24; never modify the host."""
    occupied = occupied_networks(
        addresses, routes, vmware_networking, native_instance_prefixes)
    for candidate in candidates:
        try:
            network = _prefix_network(candidate)
        except NetworkSelectionBlocked:
            raise
        if network.prefixlen != 24:
            raise NetworkSelectionBlocked("WSLPE exercise network must be /24")
        if all(not network.overlaps(used) for used in occupied):
            return ".".join(str(network.network_address).split(".")[:3])
    raise NetworkSelectionBlocked("No free WSLPE /24 in approved allocation pool")
