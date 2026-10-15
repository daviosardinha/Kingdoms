#!/usr/bin/env python3
"""Show scoped WSLPE nft candidate from exact live guest metadata (READ ONLY).

No nft apply, file writes, VMware changes, NAT changes or NORTH probes.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kingdoms.wslpe_nic_contract import check_exercise_mapping
from kingdoms.wslpe_isolation_policy import (
    TABLE, exact_rollback, render_host_filter,
)

STAGE2_PATH = ROOT / "scripts/wslpe-stage2-inspect.py"
VMSTATE_PATH = ROOT / "scripts/wslpe-vm-state-diagnose.py"
TOPOLOGY_PATH = ROOT / "scripts/wslpe-p1c-topology-audit.py"
HOSTNET_PATH = ROOT / "scripts/wslpe-check-host-network.py"
VMWARE_CONFIG = Path("/etc/vmware/networking")


def import_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("Missing WSLPE-only source module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def running_registered(vmx: Path, diagnostic) -> None:
    output = subprocess.run(
        ["vmrun", "-T", "ws", "list"], capture_output=True, text=True,
        check=False, timeout=20,
    )
    if output.returncode:
        raise ValueError("VMware running VM inventory unavailable")
    entries = diagnostic.parse_vmrun(output.stdout)
    status, count = diagnostic.evaluate_registration(vmx, entries)
    if status != "MATCHED" or count != 1:
        raise ValueError("WSLPE VMX not uniquely running")


def collect() -> tuple[str, str, str, str]:
    stage2 = import_script(STAGE2_PATH, "wslpe_policy_stage2")
    state = import_script(VMSTATE_PATH, "wslpe_policy_state")
    topology = import_script(TOPOLOGY_PATH, "wslpe_policy_topology")
    hostnet = import_script(HOSTNET_PATH, "wslpe_policy_hostnet")
    instance, manifest = stage2.find_instance(stage2.WORKSPACE)
    vmx = stage2.locate_registered_vm(instance)
    running_registered(vmx, state)
    vmx_source = vmx.read_text(encoding="utf-8", errors="replace")
    vmnet = topology.validated_exercise_vnet(vmx_source)
    prefix = manifest["ip_range"]
    definitions = dict(hostnet.configured_vmnets(
        VMWARE_CONFIG.read_text(encoding="utf-8")
    ))
    failures = check_exercise_mapping(
        vmx_source, {key: str(subnet) for key, subnet in definitions.items()}, prefix
    )
    if failures:
        raise ValueError("; ".join(failures))
    host = topology.host_interface_ipv4(
        topology.command_json("ip", "-j", "-4", "address", "show", "dev", vmnet),
        vmnet, prefix,
    )
    guest = f"{prefix}.31"
    topology.guest_route_device(
        topology.command_json("ip", "-j", "-4", "route", "get", guest),
        vmnet,
    )
    return vmnet, f"{prefix}.0/24", host, guest


def main() -> int:
    print("KINGDOMS WSLPE | HOST EXERCISE FILTER CANDIDATE (READ ONLY)")
    print("[NO CHANGES] No nft apply, no VMware/Windows/NAT writes, no NORTH probe")
    try:
        vmnet, subnet, host, guest = collect()
        candidate = render_host_filter(vmnet, subnet, host, guest)
    except (OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired) as exc:
        print(f"[BLOCKED] {type(exc).__name__}: {exc}")
        return 1
    print(f"[PASS] Unique WSLPE runtime: {vmnet} {subnet}")
    print(f"[INFO] Host={host} Guest={guest} NAT Ethernet0 still connected")
    print("\n===== CANDIDATE ONLY — DO NOT APPLY =====")
    print(candidate, end="")
    print("===== EXACT TABLE-ONLY ROLLBACK (NOT EXECUTED) =====")
    print(exact_rollback(), end="")
    print(f"[INFO] nft table: inet {TABLE}; other tables remain untouched")
    print("[NOT VERIFIED] nft syntax/live rule ordering, IPv6/ARP/L2, co-tenants,")
    print("               management recovery, NAT egress, persistence,")
    print("               isolation against a compromised SYSTEM guest")
    print("[RELEASE BLOCKED] Host firewall candidate cannot isolate attached NAT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
