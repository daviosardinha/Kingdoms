"""Read-only verification of one NEW native WSLPE41 VMware exercise NIC.

The CIDR chosen before Stage 1 is merely a candidate. The actual VMX and
VMware host subnet table must independently agree after native provisioning.
No VMware network creation, NAT edits, or guest operations live here.
"""
from __future__ import annotations

import ipaddress
from pathlib import Path

from kingdoms.wslpe41_install_flow import FreshGuestIdentity, InstallBlocked
from kingdoms.wslpe41_network_auto import SUBNET
from kingdoms.wslpe_nic_contract import (
    check_exercise_mapping, parse_vmx_networks,
)


def verify_native_vmnet(
    identity: FreshGuestIdentity, *,
    vmware_networking: Path = Path("/etc/vmware/networking"),
) -> str:
    """Prove exactly two native VMware NICs and a dedicated exercise vmnet."""
    vmx = Path(identity.vmx)
    if (not vmx.is_absolute() or vmx.is_symlink() or not vmx.is_file()
            or vmx.stat().st_size > 1_000_000):
        raise InstallBlocked("New WSLPE41 VMX unavailable for network verification")
    if (vmware_networking.is_symlink() or not vmware_networking.is_file()
            or vmware_networking.stat().st_size > 200_000):
        raise InstallBlocked("Authoritative VMware networking metadata unavailable")
    try:
        source = vmx.read_text(encoding="utf-8")
        networking = vmware_networking.read_text(encoding="utf-8")
        expected = ipaddress.IPv4Network(identity.subnet, strict=True)
    except (OSError, UnicodeError, ValueError) as exc:
        raise InstallBlocked("New VMX/networking data cannot be interpreted") from exc
    if expected.prefixlen != 24:
        raise InstallBlocked("New WSLPE41 exercise network is not /24")
    slots = parse_vmx_networks(source)
    enabled = {index for index, data in slots.items()
               if data.get("present", "TRUE").upper() != "FALSE"}
    if enabled != {0, 1}:
        raise InstallBlocked("Fresh WSLPE41 has unexpected VMware adapters")
    definitions: dict[str, dict[str, str]] = {}
    for line in networking.splitlines():
        match = SUBNET.fullmatch(line.strip())
        if match:
            number, key, value = match.groups()
            name = f"vmnet{number}"
            entry = definitions.setdefault(name, {})
            if key in entry:
                raise InstallBlocked("Duplicate VMware subnet metadata")
            entry[key] = value
    vmnet_subnets: dict[str, str] = {}
    for name, values in definitions.items():
        if set(values) != {"HOSTONLY_SUBNET", "HOSTONLY_NETMASK"}:
            raise InstallBlocked("Incomplete VMware exercise subnet metadata")
        try:
            net = ipaddress.IPv4Network(
                (values["HOSTONLY_SUBNET"], values["HOSTONLY_NETMASK"]),
                strict=False,
            )
        except (ValueError, TypeError) as exc:
            raise InstallBlocked("Invalid VMware subnet metadata") from exc
        vmnet_subnets[name] = str(net)
    prefix = ".".join(str(expected.network_address).split(".")[:3])
    reasons = check_exercise_mapping(source, vmnet_subnets, prefix)
    if reasons:
        raise InstallBlocked("Fresh WSLPE41 NIC mapping is not isolated: " + "; ".join(reasons))
    selected = slots[1].get("vnet", "")
    owners = {name for name, cidr in vmnet_subnets.items() if cidr == str(expected)}
    if owners != {selected}:
        raise InstallBlocked("Fresh WSLPE41 exercise subnet has ambiguous VMware ownership")
    return selected
