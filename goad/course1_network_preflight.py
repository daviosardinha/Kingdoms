"""Read-only, fail-closed VMware network ownership gate for Kingdoms Course 1.

This is NOT host-network setup, AD DNS validation, or authorization to boot.
It rejects reused VMware vmnet IDs, IP/route overlap, registered VMX MAC/
vmnet overlap, and active VMware application/guests before provisioning.
Unknown/unregistered VMX files cannot be proven absent by this scan; further
operator-owned Vagrant/VMware identity checks remain mandatory.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import subprocess
from pathlib import Path

from goad.kingdoms_topology import load_course1_topology, parse_vmnet_args
from goad.course1_artifact_render import MAC_PATTERN, render_course1_artifacts

NETWORKING = Path("/etc/vmware/networking")
VMWARE_LIBRARY = Path.home() / ".vmware/inventory.vmls"
REGISTERED = re.compile(r'(?m)^vmlist\d+\.config\s*=\s*"([^"]+)"\s*$')
VMX_NET = re.compile(r'(?im)^\s*ethernet\d+\.vnet\s*=\s*"(vmnet\d+)"')
VMX_MAC = re.compile(
    r'(?im)^\s*ethernet\d+\.(?:address|generatedAddress)\s*=\s*'
    r'"(00:50:56:(?:[0-9a-f]{2}:){2}[0-9a-f]{2})"'
)
VNET_LINE = re.compile(r"(?m)^answer\s+VNET_(\d+)_")


class NetworkConflict(ValueError):
    pass


def command(*argv: str) -> str:
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, check=False, timeout=20
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NetworkConflict(f"Cannot inspect host networking via {argv[0]}: {exc}") from exc
    if result.returncode:
        raise NetworkConflict(f"Host inspection command failed: {' '.join(argv)}")
    return result.stdout


def inactive_vmware() -> None:
    running = command("vmrun", "-T", "ws", "list")
    if running.strip() != "Total running VMs: 0":
        raise NetworkConflict("VMware has running guests or an unexpected VM inventory")
    for process in ("vmware-vmx", "vmware"):
        try:
            result = subprocess.run(
                ["pgrep", "-x", process], capture_output=True, text=True, timeout=10
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise NetworkConflict(f"Unable to inspect VMware process {process}") from exc
        if result.returncode != 1:
            raise NetworkConflict(f"VMware process {process} is active or cannot be checked")


def inspect_network_files(
    planned: dict, config: str, links: list, addresses: list, routes: list
) -> None:
    targets = {v["vmnet"] for v in planned["segments"].values()}
    ids = {int(vmnet[5:]) for vmnet in targets}
    occupied = {int(number) for number in VNET_LINE.findall(config)}
    collision = ids & occupied
    if collision:
        raise NetworkConflict(f"Requested VMware vmnet IDs already exist: {sorted(collision)}")

    link_names = {obj.get("ifname") for obj in links}
    reused = targets & link_names
    if reused:
        raise NetworkConflict(f"Requested VMware vmnet interfaces already exist: {sorted(reused)}")

    cidrs = [
        ipaddress.ip_network(zone["cidr"])
        for zone in planned["segments"].values()
    ]
    for link in addresses:
        for addr in link.get("addr_info", []):
            if addr.get("family") != "inet":
                continue
            try:
                ip = ipaddress.ip_address(addr["local"])
            except (ValueError, KeyError) as exc:
                raise NetworkConflict("Cannot interpret host IPv4 addresses") from exc
            if any(ip in desired for desired in cidrs):
                raise NetworkConflict(
                    f"Host address {ip} already occupies a requested Course 1 subnet"
                )

    for route in routes:
        dst = route.get("dst")
        if not dst or dst == "default":
            continue
        try:
            network = ipaddress.ip_network(dst, strict=False)
        except ValueError as exc:
            raise NetworkConflict(f"Unrecognized existing route destination: {dst}") from exc
        if network.version != 4:
            continue
        if any(network.overlaps(desired) for desired in cidrs):
            raise NetworkConflict(f"Existing host route overlaps Course 1 subnet: {dst}")


def inspect_vmware_library(
    planned: dict, artifacts: dict, library: str, vmx_data: dict[str, str]
) -> None:
    vmnets = {seg["vmnet"].lower() for seg in planned["segments"].values()}
    planned_macs = {
        mac.lower()
        for mac in MAC_PATTERN.findall(artifacts["providers/vmware/Vagrantfile"])
    }
    if len(planned_macs) != 7:
        raise NetworkConflict("Unable to establish seven planned VMware MAC identities")
    for path in REGISTERED.findall(library):
        contents = vmx_data.get(path)
        if contents is None:
            raise NetworkConflict(f"Registered VMware guest cannot be inspected: {path}")
        foreign_nets = {x.lower() for x in VMX_NET.findall(contents)}
        foreign_macs = {x.lower() for x in VMX_MAC.findall(contents)}
        if (foreign_nets & vmnets) or (foreign_macs & planned_macs):
            raise NetworkConflict(f"Registered VM has conflicting vmnet/MAC: {path}")


def inspect_live(
    network_base: str | None = None, vmnets: dict[str, int] | None = None,
    networking: Path = NETWORKING, library: Path = VMWARE_LIBRARY
) -> tuple[str, ...]:
    """Read host state only. Any inaccessible required evidence is a failure."""
    planned = load_course1_topology(network_base, vmnets)
    artifacts = render_course1_artifacts(network_base, vmnets)
    inactive_vmware()
    if not networking.is_file() or networking.is_symlink():
        raise NetworkConflict("VMware networking configuration is absent or symlinked")
    config = networking.read_text(encoding="utf-8")
    links = json.loads(command("ip", "-j", "link", "show"))
    addresses = json.loads(command("ip", "-j", "-4", "addr", "show"))
    routes = json.loads(command("ip", "-j", "-4", "route", "show", "table", "all"))
    if not all(isinstance(data, list) for data in (links, addresses, routes)):
        raise NetworkConflict("Host interface/route inspection is not a list")
    inspect_network_files(planned, config, links, addresses, routes)

    registered_text = ""
    vmx_data = {}
    if library.exists() or library.is_symlink():
        if not library.is_file() or library.is_symlink():
            raise NetworkConflict("VMware registration inventory is not a regular file")
        registered_text = library.read_text(encoding="utf-8")
        for vmx_path in REGISTERED.findall(registered_text):
            p = Path(vmx_path)
            if not p.is_file() or p.is_symlink():
                raise NetworkConflict(f"Registered VMware VMX is missing or uninspectable: {p}")
            vmx_data[vmx_path] = p.read_text(encoding="utf-8", errors="replace")
    inspect_vmware_library(planned, artifacts, registered_text, vmx_data)
    return (
        "No VMware guests or application processes running",
        "Requested vmnet IDs and host interface names are unused",
        "No occupied host IPs or overlapping IPv4 routes in the planned segments",
        "No conflicting registered VMware VMX vmnets or MAC addresses",
        "READ-ONLY PRECHECK PASS; NOT permission to install NORTH",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network-base", default=None)
    parser.add_argument("--vmnet", action="append", default=[])
    args = parser.parse_args()
    try:
        for result in inspect_live(args.network_base, parse_vmnet_args(args.vmnet)):
            print("[PASS] " + result)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, f"[BLOCKED] Kingdoms network ownership: {exc}\n")


if __name__ == "__main__":
    main()
