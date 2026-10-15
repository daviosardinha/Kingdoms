#!/usr/bin/env python3
"""Read-only WSLPE exercise-NIC readiness, modeled on NORTH's NIC lifecycle.

Never calls NORTH's lab-mode.sh. A PASS only means the independent VMware
exercise network has verified VMX/subnet/host interface metadata. It does
not disconnect management NAT, restart VMware, or change Windows settings.
"""
from __future__ import annotations

import importlib.util
import ipaddress
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kingdoms.wslpe_nic_contract import (
    check_exercise_mapping, check_provisioning_layout, parse_vmx_networks,
)

INSPECT_SOURCE = ROOT / "scripts/wslpe-stage2-inspect.py"
VMNET_SOURCE = ROOT / "scripts/wslpe-check-host-network.py"


def imported(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Required WSLPE checker unavailable: {path.name}")
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def host_interface_network(vnet: str) -> ipaddress.IPv4Network | None:
    try:
        result = subprocess.run(
            ["ip", "-j", "-4", "address", "show", "dev", vnet],
            capture_output=True, text=True, check=False, timeout=15,
        )
        if result.returncode != 0:
            return None
        interfaces = json.loads(result.stdout)
        networks = {
            ipaddress.ip_network(
                f"{a['local']}/{a['prefixlen']}", strict=False
            )
            for interface in interfaces
            for a in interface.get("addr_info", [])
            if a.get("family") == "inet"
        }
    except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired):
        return None
    return next(iter(networks)) if len(networks) == 1 else None


def main() -> int:
    print("KINGDOMS WSLPE | NORTH-DERIVED EXERCISE NIC PRE-FLIGHT (READ ONLY)")
    print("[NO CHANGES] No NAT disconnection, VM configuration or Windows writes")
    try:
        stage2 = imported(INSPECT_SOURCE, "wslpe_stage2_netread")
        network = imported(VMNET_SOURCE, "wslpe_vmnet_netread")
        instance, info = stage2.find_instance(stage2.WORKSPACE)
        vmx = stage2.locate_registered_vm(instance)
        vmx_text = vmx.read_text(encoding="utf-8", errors="replace")
        raw = network.VMWARE_CONFIG.read_text(encoding="utf-8")
        vmnets = dict(network.configured_vmnets(raw))
        known_subnets = {k: str(v) for k, v in vmnets.items()}
        prefix = info["ip_range"]
        reasons = check_exercise_mapping(vmx_text, known_subnets, prefix)
        slots = parse_vmx_networks(vmx_text)
        exercise_vmnet = slots.get(1, {}).get("vnet", "(unassigned)")
        print(f"[INFO] Native WSLPE prefix: {prefix}.0/24")
        print(f"[INFO] Registered guest: {vmx.name}")
        print(f"[INFO] Ethernet0: {slots.get(0, {}).get('connectiontype','unknown')} "
              f"startConnected={slots.get(0, {}).get('startconnected','(implicit)')}")
        print(f"[INFO] Ethernet1: {slots.get(1, {}).get('connectiontype','unknown')} "
              f"vnet={exercise_vmnet}")
        if exercise_vmnet in known_subnets:
            print(f"[INFO] VMware {exercise_vmnet} defined subnet: "
                  f"{known_subnets[exercise_vmnet]}")
            host_network = host_interface_network(exercise_vmnet)
            expected = ipaddress.ip_network(f"{prefix}.0/24")
            if host_network != expected:
                reasons.append(
                    f"Host interface {exercise_vmnet} does not expose the "
                    f"expected {expected} network (actual: {host_network})"
                )
        for reason in reasons:
            print(f"[BLOCKED] {reason}")
        if reasons:
            print("[NEXT] WSLPE requires its own host-only vmnet and verified "
                  "operator reachability before NAT can be disconnected")
            return 1
        print("[PASS] WSLPE dedicated exercise NIC network metadata matches instance")
        print("[NOT VERIFIED] Authenticated direct WinRM HTTPS, RDP access, "
              "guest-to-host restrictions, learner access")
        print("[LOCKED] Exercise-mode NAT handoff must not run until direct "
              "management and rollback are proved")
        return 0
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        print(f"[BLOCKED] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
