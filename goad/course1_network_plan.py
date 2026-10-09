"""Kingdoms Course 1 same-host network collision contracts (READ ONLY).

Reference identities are read from the canonical Kingdoms Vagrant/router source.
A valid *proposal* is not host availability, a deployable instance, nor an
authorization to modify vmnets or start guests. No OS/hypervisor calls here.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
from dataclasses import dataclass
from pathlib import Path

from goad.course1_runtime_contract import COURSE1, ROUTER, ProfileNotReady
from goad.course1_source_gate import inspect_source_preview

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_VAGRANT = ROOT / "ad/GOAD/providers/vmware/Vagrantfile"
REFERENCE_ROUTER = ROOT / "ad/GOAD/providers/vmware/router/provision.sh"

ZONES = ("NORTH", "SEVENKINGDOMS", "ESSOS_TRANSITION", "MANAGEMENT")
MACHINE_ZONE = {
    "GOAD-DC01": "SEVENKINGDOMS",
    "GOAD-DC02": "NORTH",
    "GOAD-SRV02": "NORTH",
    "GOAD-WS01": "NORTH",
}
VMNET_PATTERN = re.compile(r"vmnet(?:[1-9][0-9]*)\Z")
MAC_PATTERN = re.compile(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\Z")


def require(predicate: bool, message: str) -> None:
    if not predicate:
        raise ProfileNotReady(message)


@dataclass(frozen=True)
class Surface:
    vmnets: frozenset[str]
    macs: frozenset[str]
    ips: frozenset[ipaddress.IPv4Address]


def surface_from_vagrant(content: str) -> Surface:
    """Extract network identities from actual Ruby adapter declarations."""
    vmnets = frozenset(re.findall(r':vnet\s*=>\s*"(vmnet[0-9]+)"', content))
    macs = frozenset(s.lower() for s in re.findall(
        r':(?:lab_mac|mac)\s*=>\s*"((?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})"',
        content,
    ))
    ips = frozenset(ipaddress.IPv4Address(s) for s in re.findall(
        r':ip\s*=>\s*"([0-9.]+)"', content
    ))
    require(bool(vmnets) and bool(macs) and bool(ips),
            "VMware source does not expose expected network identifiers")
    return Surface(vmnets, macs, ips)


def reference_contract() -> tuple[Surface, tuple[ipaddress.IPv4Network, ...]]:
    """Include router-only MANAGEMENT subnet as well as Windows IP networks."""
    vagrant = REFERENCE_VAGRANT.read_text(encoding="utf-8")
    router = REFERENCE_ROUTER.read_text(encoding="utf-8")
    surface = surface_from_vagrant(vagrant)
    gateways = re.findall(
        r'configure_lab_interface\s+"[^"]+"\s+"\$\{[^}]+\}"\s+"([0-9.]+)"',
        router,
    )
    require(len(gateways) == 4, "reference router must declare all four gateways")
    require(len(surface.vmnets) == 4 and len(surface.ips) == 6
            and len(surface.macs) >= 10,
            "reference VMware network fixture changed; re-review isolation contract")
    cidrs = tuple(sorted(
        {ipaddress.ip_network(f"{ip}/24", strict=False)
         for ip in (set(surface.ips) | {ipaddress.IPv4Address(g) for g in gateways})},
        key=lambda n: int(n.network_address),
    ))
    require(len(cidrs) == 4, "reference route subnets changed; fail closed")
    return surface, cidrs


def preview_shared_identifiers(preview_vagrant: str) -> dict[str, int]:
    """Count shared reference identifiers without printing MACs or credentials."""
    baseline, _ = reference_contract()
    candidate = surface_from_vagrant(preview_vagrant)
    return {
        "shared_vmnets": len(candidate.vmnets & baseline.vmnets),
        "shared_macs": len(candidate.macs & baseline.macs),
        "shared_ips": len(candidate.ips & baseline.ips),
    }


def _network(value: object) -> ipaddress.IPv4Network:
    require(isinstance(value, str), "zone subnet must be text")
    try:
        n = ipaddress.ip_network(value, strict=True)
    except ValueError as exc:
        raise ProfileNotReady("invalid proposed IPv4 network") from exc
    require(isinstance(n, ipaddress.IPv4Network) and n.prefixlen == 24,
            "proposal must retain explicit IPv4 /24 subnet contract")
    return n


def _address(value: object) -> ipaddress.IPv4Address:
    require(isinstance(value, str), "proposed address must be text")
    try:
        a = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ProfileNotReady("invalid proposed IPv4 address") from exc
    require(isinstance(a, ipaddress.IPv4Address),
            "proposed addresses must be IPv4")
    return a


def _mac(value: object) -> str:
    require(isinstance(value, str), "proposed MAC must be text")
    result = value.lower()
    require(MAC_PATTERN.fullmatch(result) is not None,
            "invalid proposed MAC address")
    require(int(result[:2], 16) & 1 == 0 and result != "00:00:00:00:00:00",
            "proposed MAC must be nonzero unicast")
    return result


def validate_proposal(proposal: object) -> dict:
    """Validate isolated topology *intent*, NOT VMware vmnet allocation.

    Reject reused reference layer-2 networks, overlapping layer-3 addresses,
    duplicate identities, wrong domain placement and unapproved source state.
    Never treat this result as proof of on-host vmnet/subnet availability.
    """
    require(isinstance(proposal, dict), "proposal must be a JSON object")
    require(proposal.get("profile") == COURSE1.name
            and proposal.get("state") == "PROPOSED_NOT_DEPLOYABLE",
            "only nondeployable Kingdoms Course 1 network proposals are accepted")
    zones = proposal.get("zones")
    machines = proposal.get("machines")
    router_macs = proposal.get("router_macs")
    require(isinstance(zones, dict) and set(zones) == set(ZONES),
            "exactly four distinct router/network zones are required")
    require(isinstance(machines, dict) and set(machines) == set(COURSE1.windows),
            "proposal must name exactly the four Course 1 Windows guests")
    require(isinstance(router_macs, dict) and set(router_macs) == set(ZONES),
            "router requires a MAC for every zone, including transitional ESSOS")
    require(set(MACHINE_ZONE) == set(COURSE1.windows),
            "machine/zone mapping not synchronized with Kingdoms roster")

    reference, ref_networks = reference_contract()
    guest_ips: set[ipaddress.IPv4Address] = set()
    all_macs: set[str] = set()
    vmnets: set[str] = set()
    cidrs: dict[str, ipaddress.IPv4Network] = {}
    gateways: dict[str, ipaddress.IPv4Address] = {}

    for zone in ZONES:
        data = zones[zone]
        require(isinstance(data, dict) and set(data) == {"vmnet", "subnet", "gateway"},
                "unexpected or missing proposed zone attributes")
        vmnet = data["vmnet"]
        require(isinstance(vmnet, str) and VMNET_PATTERN.fullmatch(vmnet) is not None
                and vmnet not in {"vmnet1", "vmnet8"},
                "invalid VMware host-only network name")
        require(vmnet not in reference.vmnets and vmnet not in vmnets,
                "VMware vmnet reused by reference or another proposed zone")
        vmnets.add(vmnet)
        cidr = _network(data["subnet"])
        require(not any(cidr.overlaps(other) for other in (*ref_networks, *cidrs.values())),
                "proposed subnet overlaps reference or another proposed zone")
        cidrs[zone] = cidr
        gateway = _address(data["gateway"])
        require(gateway in cidr and gateway not in (cidr.network_address, cidr.broadcast_address),
                "proposed gateway is not usable in its zone")
        gateways[zone] = gateway

    for machine in COURSE1.windows:
        data = machines[machine]
        require(isinstance(data, dict) and set(data) == {"zone", "ip", "mac"},
                "invalid proposed Windows guest identity")
        zone = MACHINE_ZONE[machine]
        require(data["zone"] == zone, "guest placed in wrong Kingdoms security zone")
        ip = _address(data["ip"])
        cidr = cidrs[zone]
        require(ip in cidr and ip not in (cidr.network_address, cidr.broadcast_address)
                and ip != gateways[zone] and ip not in guest_ips,
                "guest has duplicate, unusable or out-of-zone address")
        guest_ips.add(ip)
        mac = _mac(data["mac"])
        require(mac not in reference.macs and mac not in all_macs,
                "proposed guest MAC collides with another or reference guest")
        all_macs.add(mac)

    for zone in ZONES:
        mac = _mac(router_macs[zone])
        require(mac not in reference.macs and mac not in all_macs,
                "proposed router MAC collides with another or reference guest")
        all_macs.add(mac)

    return {
        "profile": COURSE1.name,
        "state": "PROPOSED_NOT_DEPLOYABLE",
        "windows_guests": len(machines),
        "router": ROUTER,
        "zones": list(ZONES),
        "unique_vmnets": len(vmnets),
        "unique_macs": len(all_macs),
        "reference_conflicts": 0,
        "host_networks_surveyed": False,
        "deployment_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--assert-preview-unsafe",
                       help="private preview directory; pass iff shared-host identity collisions exist")
    group.add_argument("--check-proposal",
                       help="JSON proposed network layout; never permits deployment")
    args = parser.parse_args()
    try:
        if args.assert_preview_unsafe:
            preview = Path(args.assert_preview_unsafe).expanduser()
            inspect_source_preview(preview)
            text = (preview / "instance-preview/Vagrantfile").read_text(encoding="utf-8")
            report = preview_shared_identifiers(text)
            require(all(n > 0 for n in report.values()),
                    "reference collision test no longer matches actual preview; review source")
            print("[PASS] Current Course 1 preview correctly rejected for same-host coexistence")
            print(json.dumps(report, indent=2))
            print("[BLOCKED] Shared vmnets/MACs/IPs: current preview cannot cohost reference")
        else:
            proposal = json.loads(Path(args.check_proposal).read_text(encoding="utf-8"))
            print(json.dumps(validate_proposal(proposal), indent=2))
            print("[BLOCKED] Static proposal is not host-surveyed or deployable")
    except (ProfileNotReady, OSError, UnicodeError, ValueError) as exc:
        parser.exit(1, "[FAIL] " + str(exc) + "\n")


if __name__ == "__main__":
    main()
