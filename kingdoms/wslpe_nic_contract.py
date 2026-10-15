"""Provider-neutral WSLPE two-stage Windows networking contract.

Adapted from NORTH's proven semantics, without invoking NORTH's router/DC,
segmented vmnet setup, or its lifecycle scripts. Read-only evidence gates here;
the exercise transition must never disconnect NAT without a verified independent
host-only interface and direct authenticated management channel.
"""
from __future__ import annotations

import ipaddress
import re

NORTH_VNETS = {"vmnet10", "vmnet20", "vmnet30", "vmnet99"}
MANAGEMENT_VNETS = {"vmnet8"}  # conventional NAT, NOT a hardcoded requirement
FORBIDDEN = NORTH_VNETS | MANAGEMENT_VNETS


def parse_vmx_networks(vmx: str) -> dict[int, dict[str, str]]:
    """Map exact VMware ethernet slot properties without writing the VMX."""
    result = {}
    pattern = re.compile(
        r'^\s*ethernet(\d+)\.([a-zA-Z0-9]+)\s*=\s*"([^"]*)"\s*$',
        flags=re.IGNORECASE,
    )
    for line in vmx.splitlines():
        match = pattern.match(line)
        if match:
            slot, key, value = match.groups()
            result.setdefault(int(slot), {})[key.lower()] = value
    return result


def check_provisioning_layout(vmx: str) -> list[str]:
    """Fail closed if the initial NAT/independent NIC arrangement is unproven."""
    reasons = []
    slots = parse_vmx_networks(vmx)
    nat = slots.get(0, {})
    if nat.get("present", "TRUE").upper() == "FALSE":
        reasons.append("VMX Ethernet0 provisioning NIC missing")
    if nat.get("connectiontype", "").lower() != "nat":
        reasons.append("VMX Ethernet0 must be provider-managed provisioning NAT")
    if nat.get("startconnected", "TRUE").upper() == "FALSE":
        reasons.append("VMX Ethernet0 NAT is currently disconnected")
    exercise = slots.get(1, {})
    if exercise.get("present", "").upper() != "TRUE":
        reasons.append("VMX Ethernet1 exercise interface not explicitly present")
    if exercise.get("connectiontype", "").lower() not in ("custom", "hostonly"):
        reasons.append("VMX Ethernet1 is not a custom/host-only exercise NIC")
    return reasons


def check_exercise_mapping(vmx: str, vmnet_subnets: dict[str, str], prefix: str) -> list[str]:
    """Require the *actual* dedicated vmnet to own the chosen guest /24."""
    reasons = check_provisioning_layout(vmx)
    slots = parse_vmx_networks(vmx)
    exercise = slots.get(1, {})
    assigned = exercise.get("vnet", "")
    if not re.fullmatch(r"vmnet\d+", assigned):
        reasons.append(
            "VMware exercise adapter lacks an explicit vnet assignment. "
            "Do not infer a VMware vmnet from Vagrant private_network alone."
        )
        return reasons
    if assigned in FORBIDDEN:
        reasons.append(f"{assigned} is NORTH or shared management; WSLPE must be separate")
        return reasons
    try:
        target = ipaddress.ip_network(prefix + ".0/24", strict=True)
        actual = ipaddress.ip_network(vmnet_subnets[assigned], strict=False)
    except (KeyError, ValueError, TypeError):
        reasons.append(f"Exercise vmnet {assigned} has no validated subnet metadata")
        return reasons
    if target != actual:
        reasons.append(
            f"Exercise vmnet {assigned} is {actual}, not native WSLPE {target}"
        )
    return reasons


def check_exercise_persistent_state(vmx: str) -> list[str]:
    """NORTH-style post-transition proof, without changing VM/host state."""
    slots = parse_vmx_networks(vmx)
    reasons = []
    if slots.get(0, {}).get("startconnected", "").upper() != "FALSE":
        reasons.append("Provisioning Ethernet0 NAT is not persistently disconnected")
    exercise = slots.get(1, {})
    if exercise.get("present", "").upper() != "TRUE":
        reasons.append("Exercise Ethernet1 is missing")
    if exercise.get("startconnected", "TRUE").upper() == "FALSE":
        reasons.append("Exercise Ethernet1 is disconnected")
    return reasons
