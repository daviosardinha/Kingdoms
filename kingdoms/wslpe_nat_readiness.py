"""Pure WSLPE-only NAT handoff readiness contracts. Never mutates VM/network.

These checks are prerequisites, not proof that VMware has a reliable
hot-unplug API or that any NAT disconnect can be rolled back automatically.
"""
from __future__ import annotations
import ipaddress
import re
from kingdoms.wslpe_nic_contract import parse_vmx_networks


def mac_normal(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid VMware/Windows MAC type")
    normalized = re.sub(r"[:-]", "", value).lower()
    if not re.fullmatch(r"[0-9a-f]{12}", normalized):
        raise ValueError("VMware/Windows MAC must be exactly 48-bit")
    return normalized


def vmx_snapshot(source: str, exercise_vnet: str) -> dict:
    slots = parse_vmx_networks(source)
    if set(k for k, v in slots.items()
           if v.get("present", "TRUE").upper() != "FALSE") != {0, 1}:
        raise ValueError("WSLPE VM must have exactly two present VMware adapters")
    nat, exercise = slots[0], slots[1]
    if (nat.get("connectiontype", "").lower() != "nat"
            or nat.get("startconnected", "TRUE").upper() != "TRUE"):
        raise ValueError("WSLPE provisioning NAT is not connected in VMX")
    if (exercise.get("connectiontype", "").lower() != "custom"
            or exercise.get("vnet") != exercise_vnet
            or exercise.get("startconnected", "TRUE").upper() != "TRUE"):
        raise ValueError("WSLPE exercise NIC/vmnet mapping changed")
    nat_mac = mac_normal(nat.get("generatedaddress") or nat.get("address") or "")
    exercise_mac = mac_normal(exercise.get("generatedaddress") or exercise.get("address") or "")
    if nat_mac == exercise_mac:
        raise ValueError("VMware NAT and exercise adapter MAC addresses overlap")
    return {"nat_mac": nat_mac, "exercise_mac": exercise_mac,
            "nat_vmnet": nat.get("vnet") or "VMware default NAT",
            "exercise_vmnet": exercise_vnet}


def windows_snapshot(data: dict, vmx: dict, host: str, guest: str) -> dict:
    if (not isinstance(data, dict)
            or data.get("Machine") != "WSLPE-WS01"
            or data.get("DomainJoined") is not False):
        raise ValueError("Windows is not the unique domain-free WSLPE workstation")
    try:
        adapters = data["Adapters"]
        ipv4 = data["IPv4"]
        ipv6 = data["IPv6"]
        routes4 = data["DefaultRoutes4"]
        routes6 = data["DefaultRoutes6"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Windows networking snapshot is incomplete") from exc
    if not all(isinstance(x, list) for x in (adapters, ipv4, ipv6, routes4, routes6)):
        raise ValueError("Windows networking snapshot has ambiguous array types")
    by_mac = {}
    for adapter in adapters:
        mac = mac_normal(adapter.get("Mac", ""))
        if mac in by_mac:
            raise ValueError("Duplicate Windows MAC identity")
        by_mac[mac] = adapter
    nat = by_mac.get(vmx["nat_mac"])
    exercise = by_mac.get(vmx["exercise_mac"])
    if not nat or not exercise or nat.get("Status") != "Up" or exercise.get("Status") != "Up":
        raise ValueError("Both exact WSLPE Windows NICs are not UP")
    ni, ei = int(nat["Index"]), int(exercise["Index"])
    if ni == ei:
        raise ValueError("Windows NIC identity is ambiguous")
    if sum(1 for item in ipv4 if item.get("Address") == guest
           and int(item.get("Index", -1)) == ei and int(item.get("Prefix", -1)) == 24) != 1:
        raise ValueError("Expected exercise IPv4 is not on exact exercise NIC")
    if any(int(route.get("Index", -1)) == ei for route in routes4 + routes6):
        raise ValueError("WSLPE exercise NIC has a default IPv4 or IPv6 route")
    if any(ipaddress.ip_address(str(item.get("Address", ""))) ==
           ipaddress.ip_address(host) for item in ipv4):
        raise ValueError("Host-side WSLPE address appears on guest")
    exercise6 = [str(item.get("Address")) for item in ipv6
                 if int(item.get("Index", -1)) == ei]
    return {"nat_index": ni, "exercise_index": ei,
            "exercise_ipv6_count": len(exercise6),
            "vulnerable_exercise_ipv6": bool(exercise6),
            "nat_default_route_count": sum(1 for r in routes4 + routes6
                                           if int(r.get("Index", -1)) == ni)}


def cutover_blockers(nat_is_attached: bool, host_filter_persistent: bool,
                     independent_vm_rollback: bool, l2_isolation: bool) -> list[str]:
    blocked = []
    if nat_is_attached:
        blocked.append("NAT STILL ATTACHED — explicit VMX-only cutover required")
    if not host_filter_persistent:
        blocked.append("EXERCISE FILTER IS NOT PERSISTENT — host reboot exposes Kali")
    if not independent_vm_rollback:
        blocked.append("NO PROVEN INDEPENDENT VMX/VMWARE RESTORE MECHANISM")
    if not l2_isolation:
        blocked.append("ARP/L2 AND HYPERVISOR/NEIGHBOR DENIAL UNPROVEN")
    return blocked
