#!/usr/bin/env python3
"""WSLPE P1-C: read-only local operator/exercise topology evidence.

This checks ONLY the native WSLPE VMX and local host metadata. It does not
probe NORTH, change VMware networking, manipulate firewall, run exploits,
or infer that a host-only vmnet protects the hypervisor from a SYSTEM guest.
"""
from __future__ import annotations

import importlib.util
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kingdoms.wslpe_nic_contract import (
    FORBIDDEN, check_exercise_mapping, parse_vmx_networks,
)

STAGE2_PATH = ROOT / "scripts/wslpe-stage2-inspect.py"
VMWARE_NETWORKING = Path("/etc/vmware/networking")


def imported(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("Required WSLPE source inspector unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validated_exercise_vnet(vmx_source: str) -> str:
    slots = parse_vmx_networks(vmx_source)
    nat = slots.get(0, {})
    exercise = slots.get(1, {})
    if nat.get("connectiontype", "").lower() != "nat":
        raise ValueError("WSLPE provisioning Ethernet0 is not NAT")
    if nat.get("startconnected", "TRUE").upper() != "TRUE":
        raise ValueError("WSLPE NAT already disconnected; do not modify it")
    if exercise.get("connectiontype", "").lower() != "custom":
        raise ValueError("WSLPE exercise adapter is not a custom host-only vmnet")
    if exercise.get("present", "").upper() != "TRUE":
        raise ValueError("WSLPE exercise adapter is not explicitly present")
    if exercise.get("startconnected", "TRUE").upper() == "FALSE":
        raise ValueError("WSLPE exercise NIC is disconnected")
    vnet = exercise.get("vnet", "")
    if not re.fullmatch(r"vmnet[0-9]{1,3}", vnet) or vnet in FORBIDDEN:
        raise ValueError("WSLPE exercise NIC has an untrusted/shared vmnet assignment")
    return vnet


def host_interface_ipv4(records: list, name: str, prefix: str) -> str:
    expected = ipaddress.ip_network(f"{prefix}.0/24", strict=True)
    if not isinstance(records, list) or len(records) != 1:
        raise ValueError("WSLPE host-only vmnet interface inventory is ambiguous")
    iface = records[0]
    if iface.get("ifname") != name:
        raise ValueError("Host-only interface name differs from WSLPE VMX")
    matches = []
    for address in iface.get("addr_info", []):
        if address.get("family") != "inet":
            continue
        ip = ipaddress.ip_address(address.get("local"))
        if ip in expected and address.get("prefixlen") == 24:
            matches.append(str(ip))
    if len(matches) != 1:
        raise ValueError("Host lacks one unique IPv4 address on WSLPE exercise subnet")
    return matches[0]


def guest_route_device(routes: list, name: str) -> None:
    if not isinstance(routes, list) or len(routes) != 1:
        raise ValueError("Route toward WSLPE guest is ambiguous")
    if routes[0].get("dev") != name:
        raise ValueError("Host route toward WSLPE guest does not use its dedicated vmnet")


def command_json(*args: str) -> list:
    completed = subprocess.run(
        list(args), text=True, capture_output=True,
        check=False, timeout=15,
    )
    if completed.returncode:
        raise ValueError("Host read-only network query failed")
    document = json.loads(completed.stdout)
    if not isinstance(document, list):
        raise ValueError("Host interface/route inventory was not JSON array")
    return document


def main() -> int:
    print("KINGDOMS WSLPE | P1-C OPERATOR BOUNDARY PREFLIGHT (READ ONLY)", flush=True)
    print("[NO CHANGES] WSLPE, NORTH, VMware, NAT, nftables, Linux and Windows unchanged")
    try:
        stage2 = imported(STAGE2_PATH, "wslpe_p1c_stage2")
        vmnet_reader = imported(
            ROOT / "scripts/wslpe-check-host-network.py", "wslpe_p1c_vmnet"
        )
        instance, manifest = stage2.find_instance(stage2.WORKSPACE)
        vmx = stage2.locate_registered_vm(instance)
        source = vmx.read_text(encoding="utf-8", errors="replace")
        vnet = validated_exercise_vnet(source)
        prefix = manifest["ip_range"]
        definitions = dict(vmnet_reader.configured_vmnets(
            VMWARE_NETWORKING.read_text(encoding="utf-8")
        ))
        reasons = check_exercise_mapping(
            source, {key: str(value) for key, value in definitions.items()}, prefix
        )
        if reasons:
            raise ValueError("; ".join(reasons))
        host_ip = host_interface_ipv4(
            command_json("ip", "-j", "-4", "address", "show", "dev", vnet),
            vnet, prefix,
        )
        guest_ip = f"{prefix}.31"
        guest_route_device(
            command_json("ip", "-j", "-4", "route", "get", guest_ip), vnet
        )
    except (OSError, ValueError, TypeError, KeyError,
            subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"[BLOCKED] {type(exc).__name__}: {exc}")
        return 1

    print(f"[PASS] Exact registered WSLPE VM: {vmx.name}")
    print(f"[PASS] WSLPE exercise network: {vnet} ({prefix}.0/24)")
    print(f"[INFO] Host vmnet-side IPv4: {host_ip}; guest exercise IPv4: {guest_ip}")
    print("[INFO] WSLPE Ethernet0 provisioning NAT remains connected")
    print("[PASS] Host routing toward guest exercise IP uses the expected vmnet")
    print("[RELEASE BLOCKED] This host-only vmnet also connects the guest to the HOST.")
    print("[RELEASE BLOCKED] NAT remains attached; egress and hypervisor access are not isolated.")
    print("[NOT VERIFIED] Host INPUT/FORWARD filtering FROM compromised WSLPE,")
    print("               out-of-band console recovery, nft persistence, guest egress,")
    print("               operator-only management and learner RDP source restrictions.")
    print("[NEXT] Design and approve WSLPE-only external host firewall and rollback")
    print("       before any NAT disconnect or learner provisioning.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
