"""Pure source-derived topology planning for the reduced Kingdoms Course 1 lab.

No Vagrant, host vmnet, firewall, AD, or instance mutations take place here.
All resolved addresses originate from a single Course 1 manifest. Runtime
deployment must still perform exact host vmnet/MAC/routing ownership checks.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "ad" / "NORTH" / "topology.json"
SEGMENTS = frozenset(("north", "sevenkingdoms", "management"))
EXPECTED_WINDOWS = frozenset(("GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01"))
RESERVED_VMNETS = frozenset((0, 1, 8))


def load_course1_topology(network_base=None, vmnets=None, manifest_path=MANIFEST_PATH):
    """Compute immutable-in-practice preview data; do not change the host.

    Nondefault network bases require explicit, unique vmnet assignments.
    Allocation alone is NOT an assertion that host vmnets are unused;
    deployment preflight must establish actual ownership separately.
    """
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if manifest.get("profile") != "NORTH" or manifest.get("router") != "GOAD-ROUTER":
        raise ValueError("Invalid Kingdoms Course 1 profile/router identity")

    raw_segments = manifest.get("segments", {})
    raw_windows = manifest.get("windows", {})
    if set(raw_segments) != SEGMENTS or set(raw_windows) != EXPECTED_WINDOWS:
        raise ValueError("Unexpected Course 1 segments or Windows roster")

    default = ipaddress.IPv4Network(manifest["network_base"], strict=True)
    subnet = ipaddress.IPv4Network(network_base or str(default), strict=True)
    if default != ipaddress.IPv4Network("10.4.0.0/16"):
        raise ValueError("Unexpected default Course 1 network base")
    if subnet.prefixlen != 16 or subnet.network_address.packed[0] != 10:
        raise ValueError("Expected a 10.X.0.0/16 network, such as 10.5.0.0/16")

    defaults = {key: spec["vmnet"] for key, spec in raw_segments.items()}
    allocations = dict(defaults if vmnets is None else vmnets)
    if set(allocations) != SEGMENTS:
        raise ValueError("VMware vmnet allocation must name all three segments")
    if subnet != default and vmnets is None:
        raise ValueError("A nondefault /16 requires explicit independent vmnet allocation")

    ids = list(allocations.values())
    if any(type(value) is not int or value <= 0 or value >= 255 or value in RESERVED_VMNETS
           for value in ids):
        raise ValueError("Invalid vmnet ID (default VMware vmnet1/vmnet8 are reserved)")
    if len(ids) != len(set(ids)):
        raise ValueError("Multiple Course 1 segments cannot share a VMware vmnet")
    if subnet != default and set(ids) & set(defaults.values()):
        raise ValueError("Alternate /16 may not reuse default Kingdoms vmnet10/20/99 IDs")

    second_octet = subnet.network_address.packed[1]
    segments = {}
    for key, spec in raw_segments.items():
        octet = spec["third_octet"]
        router_host = spec["router_host"]
        host_interface = spec["host_interface"]
        if type(octet) is not int or octet < 1 or octet > 254:
            raise ValueError("Segment third octet must be a valid unique /24")
        if type(router_host) is not int or not 1 <= router_host <= 254:
            raise ValueError("Invalid router address")
        if host_interface is not None and (
            type(host_interface) is not int or not 1 <= host_interface <= 254
            or host_interface == router_host
        ):
            raise ValueError("Invalid host-adapter address")
        if key == "sevenkingdoms" and host_interface is not None:
            raise ValueError("Protected Seven Kingdoms zone may not expose host adapter")
        prefix = f"10.{second_octet}.{octet}"
        segments[key] = {
            "cidr": prefix + ".0/24",
            "gateway": prefix + f".{router_host}",
            "host_address": None if host_interface is None else prefix + f".{host_interface}",
            "vmnet": f"vmnet{allocations[key]}",
        }
    if len({s["cidr"] for s in segments.values()}) != 3:
        raise ValueError("Duplicate third octet across segments")

    windows = {}
    hostnames = set()
    for machine, spec in raw_windows.items():
        segment = spec["segment"]
        octet = spec["host_octet"]
        inventory = spec["inventory"]
        if segment not in ("north", "sevenkingdoms"):
            raise ValueError(f"Windows machine {machine} must be on a domain segment")
        if not isinstance(inventory, str) or inventory in hostnames:
            raise ValueError("Duplicate or invalid Ansible inventory host")
        hostnames.add(inventory)
        if type(octet) is not int or octet <= 1 or octet >= 254:
            raise ValueError(f"Invalid host octet for {machine}")
        prefix = segments[segment]["gateway"].rsplit(".", 1)[0]
        windows[machine] = {
            "inventory": inventory,
            "segment": segment,
            "address": prefix + f".{octet}",
            "gateway": segments[segment]["gateway"],
            "vmnet": segments[segment]["vmnet"],
        }
    if len({w["address"] for w in windows.values()}) != len(windows):
        raise ValueError("Duplicate Windows IP addresses")

    return {
        "profile": "NORTH",
        "network_base": str(subnet),
        "windows": windows,
        "router": "GOAD-ROUTER",
        "segments": segments,
        "validated": "source-shape-only",
        "requires": "host collision, vmnet/MAC ownership and AD DNS authority preflight",
    }


def parse_vmnet_args(raw):
    result = {}
    for entry in raw:
        key, sep, value = entry.partition("=")
        if not sep or not value.isdecimal() or key in result:
            raise ValueError("Use unique SEGMENT=VMNET_NUMBER pairs")
        result[key] = int(value)
    return result or None


def main():
    parser = argparse.ArgumentParser(description="Read-only Kingdoms Course 1 topology planner")
    parser.add_argument("--network-base", default=None, help="10.X.0.0/16, default 10.4.0.0/16")
    parser.add_argument("--vmnet", action="append", default=[],
                        help="Explicit segment allocation, e.g. north=11 (repeat for 3)")
    args = parser.parse_args()
    try:
        resolved = load_course1_topology(args.network_base, parse_vmnet_args(args.vmnet))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(resolved, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
