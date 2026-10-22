"""WSLPE vmnet4 kernel L3/L2 isolation acceptance, read-only only.

Fail closed if Linux can route through the management interface or if the
interface is attached to any Linux bridge/master. This is a point-in-time
host invariant, not proof of end-to-end guest isolation or firewall policy.
No sysctl, nft, iptables or host route mutation happens here.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Callable

from kingdoms.wslpe_management_vmnet_transaction import NetworkTransactionBlocked
from kingdoms.wslpe_management_vmnet_workstation import (
    IP, _trusted_binary, _host_run, _json_list,
)

VMNET = "vmnet4"
SUBNET = "172.28.233.0/24"
SYSCTL = Path("/proc/sys/net")
ZERO_PATHS = (
    SYSCTL / "ipv4/conf/vmnet4/forwarding",
    SYSCTL / "ipv6/conf/vmnet4/forwarding",
    SYSCTL / "ipv6/conf/all/forwarding",
)
MAX_FILE_BYTES = 32


def validate_isolation_snapshot(*, vmnet: str, subnet: str,
                                sysctls: dict[str, str],
                                links: list[dict],
                                ipv4_routes: list[dict]) -> str:
    """Conservative no-forward/no-bridge invariant independent of VMware config."""
    if vmnet != VMNET or subnet != SUBNET:
        raise NetworkTransactionBlocked("Unexpected WSLPE management vmnet contract")
    for path in ZERO_PATHS:
        if sysctls.get(str(path)) != "0":
            raise NetworkTransactionBlocked(f"Host forwarding is enabled or unknown: {path}")
    if len(links) != 1 or links[0].get("ifname") != vmnet:
        raise NetworkTransactionBlocked("Management interface missing/ambiguous")
    link = links[0]
    if "master" in link or "link" in link or "linkinfo" in link and (
        link["linkinfo"].get("info_kind") in ("bridge", "bond", "vlan", "veth")
    ):
        raise NetworkTransactionBlocked("Management interface bridged/enslaved/stacked")
    if not isinstance(ipv4_routes, list):
        raise NetworkTransactionBlocked("Invalid host IPv4 route inventory")
    attached = [
        r for r in ipv4_routes
        if r.get("dev") == vmnet
        and r.get("type", "unicast") not in {"local", "broadcast"}
    ]
    if len(attached) != 1 or attached[0].get("dst") != subnet:
        raise NetworkTransactionBlocked("Unexpected vmnet4 routes in host routing tables")
    if any(r.get("gateway") or r.get("via") for r in attached):
        raise NetworkTransactionBlocked("vmnet4 is routed through a gateway")
    return "VMNET4_KERNEL_NONROUTING=PASS"


class Vmnet4KernelIsolationVerifier:
    """Read-only host kernel verifier; no global sysctl/firewall mutation."""

    def __init__(self, *, binary: Path = IP,
                 run: Callable[..., str] = _host_run,
                 read: Callable[[Path], str] | None = None):
        self.binary = binary
        self.run = run
        self.read = read if read is not None else self._bounded_read

    @staticmethod
    def _bounded_read(path: Path) -> str:
        try:
            with path.open("rb") as handle:
                contents = handle.read(MAX_FILE_BYTES + 1)
        except OSError as exc:
            raise NetworkTransactionBlocked(f"Cannot read kernel forwarding state: {path}") from exc
        if len(contents) > MAX_FILE_BYTES:
            raise NetworkTransactionBlocked("Unbounded kernel forwarding state")
        return contents.decode("ascii").strip()

    def verify(self, vmnet: str, subnet: str) -> str:
        if vmnet != VMNET or subnet != SUBNET:
            raise NetworkTransactionBlocked("Unexpected management network")
        _trusted_binary(self.binary)
        states = {str(path): self.read(path) for path in ZERO_PATHS}
        binary = str(self.binary)
        links = _json_list(self.run(
            [binary, "-j", "link", "show", "dev", vmnet], timeout=15
        ), "link")
        routes = _json_list(self.run(
            [binary, "-j", "-4", "route", "show", "table", "all"], timeout=15
        ), "routes")
        return validate_isolation_snapshot(
            vmnet=vmnet, subnet=subnet, sysctls=states,
            links=links, ipv4_routes=routes,
        )
