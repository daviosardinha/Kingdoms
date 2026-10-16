"""WSLPE-only, dynamic-port boot firewall *candidate*, never installed.

It is unsafe to call an nftables reboot-persistent until all VMware
listener reassignments and boot order are proven. Use this to build the
scoped tables from exact registered WSLPE metadata, not hardcoded TCP/2210.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from kingdoms.wslpe_winrm_guard import firewall_batch, TABLE as GUARD
from kingdoms.wslpe_isolation_policy import (
    render_host_filter, TABLE as FILTER, validate_boundary,
)


@dataclass(frozen=True)
class BootPolicyCandidate:
    forwarded_winrm_port: int
    interface: str
    sha256: str
    nft_source: str
    boot_install_authorized: bool = False


def make_boot_candidate(port: int, vmnet: str, subnet: str,
                        host: str, guest: str) -> BootPolicyCandidate:
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("WSLPE forwarded WinRM port must be discovered")
    validate_boundary(vmnet, subnet, host, guest)
    source = firewall_batch(port) + render_host_filter(vmnet, subnet, host, guest)
    if (source.count(f"add table inet {GUARD}") != 1
            or source.count(f"add table inet {FILTER}") != 1
            or "flush ruleset" in source.lower()
            or "masquerade" in source.lower()
            or "delete table" in source.lower()):
        raise ValueError("Boot candidate would affect unrelated host state")
    if f"tcp dport {port} drop" not in source:
        raise ValueError("Management protection does not match live host port")
    return BootPolicyCandidate(
        port, vmnet, sha256(source.encode("utf-8")).hexdigest(), source
    )


def boot_protection_readiness(*, discovered_port: int, guarded_port: int,
                              guard_persists: bool, filter_persists: bool,
                              vmware_start_is_ordered: bool) -> list[str]:
    blockers = []
    if discovered_port != guarded_port:
        blockers.append("Forwarded WinRM port drift: current listener not guaranteed protected")
    if not guard_persists:
        blockers.append("Exact dynamic-port guard not proven across Kali restart")
    if not filter_persists:
        blockers.append("WSLPE INPUT/FORWARD nftables tables not proven persistent")
    if not vmware_start_is_ordered:
        blockers.append("VMware/Vagrant may start WSLPE before firewall guards")
    return blockers
