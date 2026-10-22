"""Guarded correction of ONLY the new WSLPE vmnet4 host IPv4 interface.

VMware Workstation can create a host-only interface with .1 (or no IPv4)
even when /etc/vmware/networking requests HOSTONLY_HOSTADDR .254.
This helper is called only under the journaled transaction, after VMware
network start and before host adapter/isolation acceptance. Never touches
other interfaces, global forwarding, VMware configuration or guest NICs.

A wrong subnet, unexpected routes, a bridge/master, multiple addresses or a
non-VMware-looking interface fail CLOSED without IPv4 mutation.
"""
from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Callable

from kingdoms.wslpe_management_vmnet_plan import inventory
from kingdoms.wslpe_management_vmnet_transaction import NetworkTransactionBlocked
from kingdoms.wslpe_management_vmnet_workstation import IP, _host_run, _json_list, _trusted_binary

VMNET = "vmnet4"
SUBNET = "172.28.233.0/24"
HOST_ADDR = "172.28.233.254"
PREFIX = 24
NETWORK = ipaddress.IPv4Network(SUBNET)


class UnexpectedVmnet4Route(NetworkTransactionBlocked):
    """Fail closed with bounded structured evidence preserved by the journal."""

    def __init__(self, routes: list, addresses: list):
        super().__init__("Unexpected vmnet4 route; refusing host IP repair")
        self.network_evidence = {
            "interface": VMNET,
            "routes": [
                {key: str(row[key])[:64] for key in
                 ("dst", "dev", "type", "scope", "protocol", "table",
                  "gateway", "via", "prefsrc", "src")
                 if key in row and isinstance(row[key], (str, int))}
                for row in routes[:12] if isinstance(row, dict)
            ],
            "ipv4": [
                {"local": str(rec.get("local", ""))[:40],
                 "prefixlen": rec.get("prefixlen")}
                for rec in addresses[:4] if isinstance(rec, dict)
            ],
            "truncated": len(routes) > 12,
        }


def _allowed_host_only_routes(routes: list) -> bool:
    """Only a directly connected subnet plus local/broadcast kernel entries.

    Never normalize a vmnet4 with a default route, gateway, foreign subnet,
    cross-VMnet device, or unknown routing type.
    """
    if not isinstance(routes, list) or len(routes) > 16:
        return False
    connected = 0
    for row in routes:
        if not isinstance(row, dict) or row.get("dev") != VMNET:
            return False
        if row.get("gateway") or row.get("via"):
            return False
        kind = row.get("type", "unicast")
        dst = row.get("dst")
        if kind in ("local", "broadcast"):
            try:
                single = ipaddress.IPv4Network(dst)
            except (ValueError, TypeError):
                return False
            if single.prefixlen != 32 or single.network_address not in NETWORK:
                return False
            continue
        if kind != "unicast" or dst != SUBNET or row.get("scope", "link") != "link":
            return False
        src = row.get("prefsrc", row.get("src"))
        if src:
            try:
                if ipaddress.IPv4Address(src) not in NETWORK:
                    return False
            except (ValueError, TypeError):
                return False
        connected += 1
    return connected <= 1


def address_transition(*, vmnet: str, subnet: str, networking_text: str,
                       address_rows: list, link_rows: list,
                       route_rows: list) -> tuple[list[str], ...]:
    """Return exact safe iproute2 argv tails, no mutation at this stage."""
    if (vmnet, subnet) != (VMNET, SUBNET):
        raise NetworkTransactionBlocked("Wrong WSLPE management IP contract")
    meta = inventory(networking_text).get(4, {})
    expected = {
        "HOSTONLY_SUBNET": "172.28.233.0",
        "HOSTONLY_NETMASK": "255.255.255.0",
        "HOSTONLY_HOSTADDR": HOST_ADDR,
        "DHCP": "no", "NAT": "no", "VIRTUAL_ADAPTER": "yes",
    }
    if any(meta.get(k) != v for k, v in expected.items()):
        raise NetworkTransactionBlocked("vmnet4 metadata not configured for operator-only network")
    if (len(link_rows) != 1 or not isinstance(link_rows[0], dict)
            or link_rows[0].get("ifname") != VMNET
            or len(address_rows) != 1 or not isinstance(address_rows[0], dict)
            or address_rows[0].get("ifname") != VMNET):
        raise NetworkTransactionBlocked("vmnet4 adapter missing or ambiguous")
    link = link_rows[0]
    if ("UP" not in link.get("flags", []) or "master" in link
            or "link" in link or link.get("linkinfo", {}).get("info_kind") in
            {"bridge", "bond", "vlan", "veth"}):
        raise NetworkTransactionBlocked("vmnet4 is not a standalone UP host-only interface")
    inet = [x for x in address_rows[0].get("addr_info", [])
            if isinstance(x, dict) and x.get("family") == "inet"]
    if not _allowed_host_only_routes(route_rows):
        raise UnexpectedVmnet4Route(
            route_rows if isinstance(route_rows, list) else [],
            inet,
        )
    if len(inet) > 1:
        raise NetworkTransactionBlocked("Multiple vmnet4 IPv4 addresses; refusing repair")
    if inet:
        record = inet[0]
        ip_string = record.get("local")
        prefixlen = record.get("prefixlen")
        try:
            old = ipaddress.IPv4Address(ip_string)
        except (ipaddress.AddressValueError, TypeError) as exc:
            raise NetworkTransactionBlocked("Invalid vmnet4 host IPv4 address") from exc
        if prefixlen != PREFIX or old not in NETWORK or old in {
                NETWORK.network_address, NETWORK.broadcast_address}:
            raise NetworkTransactionBlocked("Foreign vmnet4 address/prefix; refusing repair")
        if str(old) == HOST_ADDR:
            return ()
        # Delete the .1-style primary BEFORE adding .254. Deleting an IPv4
        # primary after adding a secondary can remove BOTH addresses on Linux.
        return (["-4", "address", "del", f"{old}/{PREFIX}", "dev", VMNET],
                ["-4", "address", "add", f"{HOST_ADDR}/{PREFIX}", "dev", VMNET])
    if route_rows:
        raise NetworkTransactionBlocked("vmnet4 has a route with no address")
    return (["-4", "address", "add", f"{HOST_ADDR}/{PREFIX}", "dev", VMNET],)


class Vmnet4HostAddressReconciler:
    """Restricted post-start host-only IP reconciler; caller owns rollback."""

    def __init__(self, *, ip_binary: Path = IP,
                 run: Callable[..., str] = _host_run):
        self.ip_binary = ip_binary
        self.run = run

    def reconcile(self, vmnet: str, subnet: str, networking_text: str) -> str:
        _trusted_binary(self.ip_binary)
        binary = str(self.ip_binary)
        address = _json_list(self.run(
            [binary, "-j", "-4", "address", "show", "dev", vmnet],
            timeout=15), "vmnet4 address")
        link = _json_list(self.run(
            [binary, "-j", "link", "show", "dev", vmnet],
            timeout=15), "vmnet4 link")
        routes = _json_list(self.run(
            [binary, "-j", "-4", "route", "show", "dev", vmnet],
            timeout=15), "vmnet4 routes")
        operations = address_transition(
            vmnet=vmnet, subnet=subnet, networking_text=networking_text,
            address_rows=address, link_rows=link, route_rows=routes,
        )
        for tail in operations:
            self.run([binary, *tail], timeout=15)
        return ("VMNET4_IPV4_RECONCILED" if operations else "VMNET4_IPV4_ALREADY_CORRECT")
