#!/usr/bin/env python3
"""Inspect or install a dedicated WSLPE 3-port loopback-only INPUT guard.

Read-only by default. --apply requires root, the original native registered
WSLPE instance, exact current Vagrant port mappings and operator confirmation.
Does not touch NORTH, VMware networks, VMs, the existing 2210 guard or snapshots.
NOT boot-persistent. Do not use this alone as a WSLPE release approval.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kingdoms import wslpe_management_guard as guard

INSPECTOR_FILE = ROOT / "scripts/wslpe-stage2-inspect.py"
SPEC = importlib.util.spec_from_file_location("wslpe_3port_inspector", INSPECTOR_FILE)
if SPEC is None or SPEC.loader is None:
    raise SystemExit("[BLOCKED] Native WSLPE inspector missing")
INSPECTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSPECTOR)


def run(command: list[str], *, data: str | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, input=data, text=True, capture_output=True,
                              check=False, timeout=35)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Cannot inspect or operate " + command[0]) from exc


def native_ports(workspace: Path) -> dict[int, int]:
    instance, info = INSPECTOR.find_instance(workspace)
    if info.get("lab") != "WSLPE":
        raise ValueError("Selected instance is not native WSLPE")
    provider = instance / "provider"
    registry = provider / ".vagrant/machines/WSLPE-WS01/vmware_desktop/id"
    if not registry.is_file() or registry.is_symlink():
        raise ValueError("Native WSLPE VMX registration missing or unsafe")
    path = Path(registry.read_text(encoding="utf-8").strip())
    if not path.is_absolute() or path.is_symlink() or path.suffix.lower() != ".vmx":
        raise ValueError("Native WSLPE registered VMX path invalid")
    vmx = path.resolve(strict=True)
    if not vmx.is_file() or not vmx.is_relative_to(provider.resolve(strict=True)):
        raise ValueError("Native WSLPE VMX escaped registered provider")
    adapters = INSPECTOR.vmx_network_adapters(vmx.read_text(encoding="utf-8"))
    if (len(adapters) != 2 or adapters[0]["index"] != 0
            or adapters[0]["type"] != "nat" or adapters[1]["index"] != 1
            or adapters[1]["type"] != "custom" or adapters[1]["vnet"] != "vmnet2"):
        raise ValueError("WSLPE native VMX network identity changed")
    port_cmd = INSPECTOR.vagrant_port_command(instance)
    port_output = run(port_cmd)
    if port_output.returncode:
        raise ValueError("Existing native WSLPE Vagrant port inspection failed")
    return guard.parse_vagrant_ports(port_output.stdout)


def state(ports: dict[int, int]) -> bool:
    result = run(["nft", "-j", "list", "table", "inet", guard.TABLE])
    if result.returncode:
        if "No such file or directory" in result.stderr:
            return False
        raise ValueError("WSLPE management guard table unreadable")
    if not guard.verify_firewall_json(result.stdout, ports):
        raise ValueError(
            "Existing management guard differs from exact native port ownership; "
            "refusing alteration"
        )
    return True


def prove_listeners(ports: dict[int, int]) -> None:
    result = run(["ss", "-H", "-lntp"])
    if result.returncode or not guard.verify_nat_listeners(result.stdout, ports):
        raise ValueError("Three distinct vmnet-nat host listeners not uniquely proven")


def confirmation(ports: dict[int, int]) -> str:
    return ",".join(f"{guest}={ports[guest]}" for guest in guard.GUEST_PORTS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=str(
        Path.home() / "kingdoms-lpe-standalone/workspace"))
    parser.add_argument("--apply", action="store_true",
                        help="Atomic scoped nftables addition; NOT reboot-persistent")
    parser.add_argument("--confirm-ports", help="Exact current guest=host port mapping")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.exit(2, "[BLOCKED] Run as sudo/root for VM and firewall ownership checks\n")
    try:
        workspace = Path(args.workspace)
        if workspace.is_symlink() or not workspace.is_dir():
            raise ValueError("WSLPE native workspace missing/unsafe")
        ports = native_ports(workspace)
        prove_listeners(ports)
        current = state(ports)
        print("[WSLPE] Verified native management mappings: " + confirmation(ports))
        print("[NAT] All three unique wildcard listeners owned by vmnet-nat")
        if current:
            print("[PASS] Exact three-port loopback-only nftables guard installed")
            print("[NO CHANGES] Host, NORTH networks and VMs unchanged")
            print("[NOT VERIFIED] Boot-time exposure, firewall reboot persistence and off-host reachability")
            return 0
        if not args.apply:
            print("[BLOCKED] Management guard not installed for all three ports")
            print("[PLAN ONLY] No firewall changes performed")
            print("[NEXT] --apply --confirm-ports " + confirmation(ports))
            return 2
        if args.confirm_ports != confirmation(ports):
            raise ValueError("Explicit selected port confirmation missing or changed")
        # Pre-apply recheck; if VM/Vagrant/NAT changed, refuse any write.
        if native_ports(workspace) != ports:
            raise ValueError("WSLPE Vagrant ports changed before application")
        prove_listeners(ports)
        result = run(["nft", "-f", "-"], data=guard.firewall_batch(ports))
        if result.returncode:
            raise ValueError("Scoped nftables transaction rejected (no reset performed)")
        if not state(ports):
            raise ValueError("Post-apply three-port firewall check failed")
        if native_ports(workspace) != ports:
            raise ValueError("WSLPE ports changed during application; protection must be rechecked")
        prove_listeners(ports)
        print("[PASS] All three non-loopback management forwards blocked at INPUT")
        print("[NO CHANGES] Existing 2210 guard, VMware networking and NORTH untouched")
        print("[NOT RELEASE] Rule is in-memory, NOT reboot-persistent; verify fresh-start guard before VM boot")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print("[BLOCKED] WSLPE three-port firewall guard: " + str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
