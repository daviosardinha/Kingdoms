"""Pure WSLPE-only nftables candidate renderer. Never applies host rules.

Blocking the guest at the host's INPUT/FORWARD hooks does not address ARP,
VMware Layer 2, other guests on vmnet, or the provisioning NAT adapter.
"""
from __future__ import annotations

import ipaddress
import re
from kingdoms.wslpe_nic_contract import FORBIDDEN

TABLE = "kingdoms_wslpe_exercise"
INPUT_CHAIN = "wslpe_host_ingress"
FORWARD_CHAIN = "wslpe_forward"
PRIORITY = -75


def validate_boundary(vmnet: str, subnet: str, host: str, guest: str) -> None:
    if (not isinstance(vmnet, str) or not re.fullmatch(r"vmnet[0-9]{1,3}", vmnet)
            or vmnet in FORBIDDEN):
        raise ValueError("WSLPE vmnet must be dedicated, non-NORTH, explicit")
    try:
        network = ipaddress.IPv4Network(subnet, strict=True)
        host_ip = ipaddress.IPv4Address(host)
        guest_ip = ipaddress.IPv4Address(guest)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid WSLPE exercise addressing") from exc
    if (network.prefixlen != 24 or not network.is_private
            or network.overlaps(ipaddress.IPv4Network("10.4.0.0/16"))
            or host_ip not in network or guest_ip not in network
            or guest_ip == host_ip
            or guest_ip in (network.network_address, network.broadcast_address)
            or host_ip in (network.network_address, network.broadcast_address)):
        raise ValueError("WSLPE subnet or host/guest IPs violate isolation")
    if guest_ip != ipaddress.IPv4Address(int(network.network_address) + 31):
        raise ValueError("Expected WSLPE native instance guest .31")


def render_host_filter(vmnet: str, subnet: str, host: str, guest: str) -> str:
    """A candidate only: INPUT allows established replies, denies new guest
    ingress; FORWARD blocks both directions; never touches OUTPUT, other
    vmnets, other firewall tables or the host's NAT provider.
    """
    validate_boundary(vmnet, subnet, host, guest)
    return (
        f"add table inet {TABLE}\n"
        f"add chain inet {TABLE} {INPUT_CHAIN} "
        f"{{ type filter hook input priority {PRIORITY}; policy accept; }}\n"
        f'add rule inet {TABLE} {INPUT_CHAIN} iifname "{vmnet}" '
        'ct state established,related accept comment "WSLPE operator reply only"\n'
        f'add rule inet {TABLE} {INPUT_CHAIN} iifname "{vmnet}" '
        'drop comment "WSLPE guest to Kali blocked"\n'
        f"add chain inet {TABLE} {FORWARD_CHAIN} "
        f"{{ type filter hook forward priority {PRIORITY}; policy accept; }}\n"
        f'add rule inet {TABLE} {FORWARD_CHAIN} iifname "{vmnet}" '
        'drop comment "WSLPE guest forwarding blocked"\n'
        f'add rule inet {TABLE} {FORWARD_CHAIN} oifname "{vmnet}" '
        'drop comment "WSLPE cross-network ingress blocked"\n'
    )


def exact_rollback() -> str:
    """Never flush the global host firewall."""
    return f"delete table inet {TABLE}\n"
