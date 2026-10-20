"""Pure, fail-closed WSLPE portless-management architecture acceptance.

This is a target-state contract, NOT a VMware/Vagrant migration tool.
Provisioning NAT, learner exercise, and operator management must be separate.
Never infer that successful WinRM on the exercise NIC makes it trustworthy.
"""
from __future__ import annotations

import ipaddress
import re

from kingdoms.wslpe_nic_contract import FORBIDDEN, parse_vmx_networks

_IPV4_NORTH = ipaddress.IPv4Network("10.4.0.0/16")
_REQUIRED = ("connectiontype", "startconnected")


def _usable_subnet(text: str) -> ipaddress.IPv4Network:
    result = ipaddress.IPv4Network(text, strict=True)
    if (result.prefixlen != 24 or not result.is_private
            or result.overlaps(_IPV4_NORTH)):
        raise ValueError("Network is not an independently allocated private /24")
    return result


def source_blockers(vmx: str, configured: dict[str, str]) -> list[str]:
    """Evaluate a *future* disconnected-NAT/2-host-only-NIC profile.

    Slot 0: bootstrap NAT, persistently disconnected.
    Slot 1: learner exercise custom host-only vmnet.
    Slot 2: separate operator management custom host-only vmnet.
    """
    reasons: list[str] = []
    if not isinstance(vmx, str) or not isinstance(configured, dict):
        return ["Invalid VMware evidence"]
    slots = parse_vmx_networks(vmx)
    if set(slots) != {0, 1, 2}:
        return ["Portless management requires three exact adapter slots (0,1,2)"]
    keys = re.findall(
        r'(?im)^\s*ethernet([012])\.(connectiontype|startconnected|present|vnet)\s*=',
        vmx,
    )
    if len(keys) != len(set((int(slot), key.lower()) for slot, key in keys)):
        reasons.append("Duplicate VMware adapter configuration")
    nat = slots[0]
    if nat.get("connectiontype", "").lower() != "nat":
        reasons.append("Bootstrap adapter must remain identifiable as VMware NAT")
    if nat.get("startconnected", "").upper() != "FALSE":
        reasons.append("Bootstrap NAT must be persistently disconnected")
    names = []
    ranges = []
    for slot, purpose in ((1, "learner exercise"), (2, "operator management")):
        nic = slots[slot]
        if nic.get("present", "TRUE").upper() == "FALSE":
            reasons.append(f"{purpose} NIC is absent")
        if nic.get("startconnected", "TRUE").upper() == "FALSE":
            reasons.append(f"{purpose} NIC is disconnected")
        if nic.get("connectiontype", "").lower() != "custom":
            reasons.append(f"{purpose} NIC is not an explicitly assigned VMware custom adapter")
        name = nic.get("vnet", "")
        if not re.fullmatch(r"vmnet[0-9]+", name) or name in FORBIDDEN:
            reasons.append(f"{purpose} vmnet is missing, shared, or NORTH-owned")
        names.append(name)
        try:
            ranges.append(_usable_subnet(configured[name]))
        except (ValueError, KeyError, TypeError):
            reasons.append(f"{purpose} has no verified dedicated /24")
    if names[0] == names[1]:
        reasons.append("Management and exercise share the same vmnet")
    if len(ranges) == 2 and ranges[0].overlaps(ranges[1]):
        reasons.append("Management and exercise IPv4 subnets overlap")
    if len(ranges) == 2:
        for name, subnet in configured.items():
            if name in names:
                continue
            try:
                other = ipaddress.ip_network(subnet, strict=False)
            except (ValueError, TypeError):
                reasons.append(f"Cannot validate existing vmnet {name}")
                continue
            if any(x.overlaps(other) for x in ranges):
                reasons.append(f"Management/exercise network conflicts with {name}")
    return reasons


def lifecycle_blockers(*, native_vagrant_forwards: dict[int, int],
                       historical_nat_host_ports: set[int],
                       currently_listening_ports: set[int],
                       direct_operator_authentication_proven: bool,
                       management_service_separated: bool,
                       operator_host_isolated: bool,
                       no_peer_guest_sharing: bool,
                       vmware_boot_order_guard_proven: bool,
                       rollback_verified: bool) -> list[str]:
    """Fail closed until all runtime receipts exist. All flags need live proof."""
    reasons = []
    if native_vagrant_forwards:
        reasons.append("Native Vagrant still advertises management host-port forwarding")
    if historical_nat_host_ports & currently_listening_ports:
        reasons.append("Old VMware NAT management listeners remain on the Kali host")
    if not direct_operator_authentication_proven:
        reasons.append("No authenticated direct management proof on separate operator vmnet")
    if not management_service_separated:
        reasons.append("Privileged management service not proven isolated from exercise NIC")
    if not operator_host_isolated:
        reasons.append("Host and other vmnets not protected from learner exercise/management NIC")
    if not no_peer_guest_sharing:
        reasons.append("A co-tenant VM shares the learner exercise vmnet")
    if not vmware_boot_order_guard_proven:
        reasons.append("VMware/Vagrant boot and port-forward recreation guard unproven")
    if not rollback_verified:
        reasons.append("Independent power-off recovery and rollback unproven")
    return reasons
