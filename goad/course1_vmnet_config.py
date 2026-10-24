"""Course 1 VMware host-network config planning for the existing Kingdoms script.

No filesystem/systemd/VMware/route mutations. Generate the three vmnets
declared by ad/NORTH/topology.json; preserve every original VMware setting,
and fail on occupied network IDs or inherited address overlap. This is the
source of truth for a future audited installation stage, NOT a new provider.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import ipaddress
import json
import re
import sys
from pathlib import Path

from goad.kingdoms_topology import load_course1_topology, parse_vmnet_args
from goad.course1_hostaddrs import hostaddr_plan, render_hostaddr_assets

NETWORKING_FILE = Path("/etc/vmware/networking")
KEY = re.compile(r"^\s*answer\s+VNET_(\d+)_([A-Z0-9_]+)(?:\s+|$)")
NETWORK_DECLARATION = re.compile(r"^\s*(?:answer\s+)?VNET_(\d+)_", re.I)
NETWORK_LABELS = ("north", "sevenkingdoms", "management")


class NetworkPlanError(ValueError):
    """Host networking must not be changed until the collision is resolved."""


def _existing_network_metadata(original: str) -> tuple[set[int], list[ipaddress.IPv4Network]]:
    occupied: set[int] = set()
    ranges: list[ipaddress.IPv4Network] = []
    declared: dict[int, dict[str, str]] = {}
    for line in original.splitlines():
        found = KEY.match(line)
        if not found:
            continue
        vmnet, property_name = int(found.group(1)), found.group(2)
        occupied.add(vmnet)
        fields = line.split()
        if len(fields) != 3:
            raise NetworkPlanError("Malformed VMware network setting")
        if property_name in ("HOSTONLY_SUBNET", "HOSTONLY_NETMASK"):
            setting = declared.setdefault(vmnet, {})
            if property_name in setting:
                raise NetworkPlanError("Duplicate existing VMware subnet or netmask")
            setting[property_name] = fields[2]
    for setting in declared.values():
        subnet = setting.get("HOSTONLY_SUBNET")
        if subnet is None:
            continue
        mask = setting.get("HOSTONLY_NETMASK", "255.255.255.0")
        try:
            network = ipaddress.ip_network(f"{subnet}/{mask}", strict=True)
        except ValueError as exc:
            raise NetworkPlanError("Invalid existing VMware host-only subnet") from exc
        ranges.append(network)
    return occupied, ranges


def render_vmnet_config(original: str, layout: dict) -> str:
    """Return desired /etc/vmware/networking with all foreign lines preserved."""
    if not isinstance(original, str) or not original.strip():
        raise NetworkPlanError("Missing VMware networking baseline")
    segments = layout.get("segments", {})
    if set(segments) != set(NETWORK_LABELS):
        raise NetworkPlanError("Unexpected Course 1 network segments")
    selected: set[int] = set()
    requested: list[ipaddress.IPv4Network] = []
    for name, zone in segments.items():
        vmnet = zone["vmnet"]
        if not re.fullmatch(r"vmnet\d+", vmnet):
            raise NetworkPlanError("Invalid VMware vmnet assignment")
        vmnet_id = int(vmnet[5:])
        if vmnet_id in selected:
            raise NetworkPlanError("Duplicate vmnet ID")
        selected.add(vmnet_id)
        requested.append(ipaddress.ip_network(zone["cidr"], strict=True))
        if name == "sevenkingdoms" and zone["host_address"] is not None:
            raise NetworkPlanError("Protected parent subnet must not get a host adapter")
    if len(requested) != len(set(requested)):
        raise NetworkPlanError("Duplicate requested subnet")

    occupied, existing_ranges = _existing_network_metadata(original)
    collisions = selected & occupied
    if collisions:
        raise NetworkPlanError("VMware vmnet IDs already allocated: " + repr(sorted(collisions)))
    for proposed in requested:
        for foreign in existing_ranges:
            if proposed.overlaps(foreign):
                raise NetworkPlanError("Requested subnet overlaps existing VMware network")
    # Malformed/unknown VNET declarations are not safe to treat as available.
    for line in original.splitlines():
        if line.lstrip().startswith("#"):
            continue
        candidate = NETWORK_DECLARATION.match(line)
        if candidate and int(candidate.group(1)) in selected:
            raise NetworkPlanError("Ambiguous existing requested VMware network definition")

    lines = []
    lines.append("# Kingdoms Course 1 managed networks (additive; source-only plan)")
    for name in NETWORK_LABELS:
        zone = segments[name]
        net = int(zone["vmnet"][5:])
        subnet = ipaddress.ip_network(zone["cidr"], strict=True)
        host = zone["host_address"]
        lines.extend((
            f"# {zone['vmnet']}: {name.upper()}",
            f"answer VNET_{net}_DHCP no",
            f"answer VNET_{net}_HOSTONLY_NETMASK 255.255.255.0",
            f"answer VNET_{net}_HOSTONLY_SUBNET {subnet.network_address}",
            f"answer VNET_{net}_VIRTUAL_ADAPTER {'yes' if host else 'no'}",
        ))
        if host:
            # The running host address is separately proven at install time.
            lines.append(f"answer VNET_{net}_HOSTONLY_HOSTADDR {host}")
        lines.append(f"answer VNET_{net}_NAT no")
    suffix = "\n".join(lines) + "\n"
    return original.rstrip("\n") + "\n\n" + suffix


def verify_vmnet_config(config: str, layout: dict) -> tuple[str, ...]:
    """Verify exact config-level DHCP, NAT, subnet and host-adapter policy.

    This does not assert the host interfaces actually have the .254 addresses.
    The existing Linux address helper/runtime network checks remain separate.
    """
    if not isinstance(config, str) or not config.strip():
        raise NetworkPlanError("VMware networking configuration is absent")
    per_net: dict[int, dict[str, list[str]]] = {}
    for raw in config.splitlines():
        m = KEY.match(raw)
        if m is None:
            continue
        words = raw.split()
        if len(words) != 3:
            raise NetworkPlanError("Malformed existing VMware network setting")
        per_net.setdefault(int(m.group(1)), {}).setdefault(m.group(2), []).append(words[2])

    checked = []
    for name in NETWORK_LABELS:
        zone = layout["segments"][name]
        number = int(zone["vmnet"][5:])
        values = per_net.get(number, {})
        network = ipaddress.ip_network(zone["cidr"], strict=True)
        expected = {
            "DHCP": "no",
            "NAT": "no",
            "HOSTONLY_NETMASK": "255.255.255.0",
            "HOSTONLY_SUBNET": str(network.network_address),
            "VIRTUAL_ADAPTER": "yes" if zone["host_address"] is not None else "no",
        }
        # VMware may remove the optional host-address metadata when it
        # recreates an adapter; host addresses require separate live checks.
        if zone["host_address"] is not None:
            if "HOSTONLY_HOSTADDR" in values:
                expected["HOSTONLY_HOSTADDR"] = zone["host_address"]
        elif "HOSTONLY_HOSTADDR" in values:
            raise NetworkPlanError(f"Protected {name} zone has an unwanted host address")
        for key, value in expected.items():
            actual = values.get(key, [])
            if actual != [value]:
                raise NetworkPlanError(
                    f"{zone['vmnet']} {key} mismatch or duplicate: "
                    f"expected {value}, observed {actual}"
                )
        checked.append(f"{zone['vmnet']} {name.upper()} configuration matches Kingdoms topology")
    return tuple(checked)



def known_vmware_hostaddr_normalization(proposed: bytes, observed: bytes, layout: dict) -> bool:
    """Accept ONLY optional NORTH .254 metadata lines removed by VMware.

    Workstation may drop HOSTONLY_HOSTADDR on network service restart. The
    Linux/systemd .254 checks remain authoritative. No other byte, whitespace,
    network, route or existing VMware setting may change unnoticed.
    """
    variants = {proposed}
    for name in ("north", "management"):
        segment = layout["segments"][name]
        number = segment["vmnet"][5:]
        address = segment["host_address"]
        if address is None:
            return False
        removable = f"answer VNET_{number}_HOSTONLY_HOSTADDR {address}\n".encode("ascii")
        variants |= {data.replace(removable, b"", 1)
                     for data in tuple(variants) if removable in data}
    return observed in variants



def verify_owned_vmnet_runtime(owned: bytes, observed: bytes, baseline: bytes,
                               layout: dict, reviewed_nat_retirements=None) -> tuple[str, ...]:
    """Accept only safe VMware/Vagrant runtime normalization of owned vmnets.

    The commit-time owner SHA remains immutable. Unlike the initial apply
    transaction, live Vagrant machine creation causes VMware to reorder its
    settings, rotate *foreign* DHCP config hashes and create vmnet8 NAT port
    forwards. Compare canonical declarations, never blindly trust a hash of
    the mutable runtime file. New forwards are limited to the *original*
    vmnet8 NAT subnet and Windows/SSH guest management ports.
    """
    try:
        base_text = baseline.decode("utf-8")
        owned_text = owned.decode("utf-8")
        observed_text = observed.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NetworkPlanError("VMware networking has invalid UTF-8") from exc
    verify_vmnet_config(observed_text, layout)
    owned_vmnet_ids = {int(z["vmnet"][5:]) for z in layout["segments"].values()}
    optional_hosts = {
        (int(z["vmnet"][5:]), "HOSTONLY_HOSTADDR"): z["host_address"]
        for z in layout["segments"].values() if z["host_address"] is not None
    }

    def entries(text):
        result = Counter()
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            words = line.split()
            if words[0] == "answer":
                if len(words) != 3:
                    raise NetworkPlanError("Malformed VMware answer declaration")
                match = re.fullmatch(r"VNET_(\d+)_([A-Z0-9_]+)", words[1])
                if match:
                    number, key = int(match.group(1)), match.group(2)
                    value = words[2]
                    if (number, key) in optional_hosts:
                        if value != optional_hosts[(number, key)]:
                            raise NetworkPlanError("Wrong NORTH optional host address")
                        continue  # Normal VMware removal/restoration is harmless.
                    if number not in owned_vmnet_ids and key == "DHCP_CFG_HASH":
                        if re.fullmatch(r"[a-fA-F0-9]{40}", value) is None:
                            raise NetworkPlanError("Malformed VMware DHCP config hash")
                        line = f"answer VNET_{number}_DHCP_CFG_HASH <rotating>"
                    else:
                        line = " ".join(words)
                else:
                    line = " ".join(words)
            elif words[0] == "add_nat_portfwd":
                # No unknown syntax or wrapped line may sneak through.
                if len(words) != 6:
                    raise NetworkPlanError("Malformed Vagrant NAT forwarding entry")
                line = " ".join(words)
            result[line] += 1
        return result

    recorded = entries(owned_text)
    active = entries(observed_text)
    removed = recorded - active
    additions = active - recorded
    # Never erase a foreign directive by calling it Vagrant normalization.
    # The optional retirement proof is a separate, root-owned host attestation:
    # absence of that proof preserves the original fail-closed behavior.
    reviewed = frozenset() if reviewed_nat_retirements is None else reviewed_nat_retirements
    if type(reviewed) is not frozenset or any(type(item) is not str for item in reviewed):
        raise NetworkPlanError("Reviewed NAT retirements must be exact immutable lines")
    if removed and (len(removed) != len(reviewed)
                    or set(removed) != reviewed
                    or any(removed[line] != 1 for line in removed)):
        raise NetworkPlanError(
            "VMware removed or modified owned/foreign network declarations: "
            + repr(sorted(removed.elements())[:4])
        )
    if reviewed and not removed:
        raise NetworkPlanError("Stale or unused NAT retirement authorization")

    # This subnet comes from the immutable original backup, not the live
    # config. Never accept new forwarding to NORTH's isolated 10.4 networks.
    settings = {}
    for raw in base_text.splitlines():
        words = raw.split()
        if len(words) == 3 and words[0] == "answer" and words[1].startswith("VNET_8_"):
            if words[1] in settings:
                raise NetworkPlanError("Duplicate original vmnet8 NAT metadata")
            settings[words[1]] = words[2]
    try:
        if settings.get("VNET_8_NAT") != "yes":
            raise ValueError("vmnet8 is not an owned foreign NAT network")
        nat_range = ipaddress.ip_network(
            f'{settings["VNET_8_HOSTONLY_SUBNET"]}/'
            f'{settings["VNET_8_HOSTONLY_NETMASK"]}', strict=True,
        )
        if not isinstance(nat_range, ipaddress.IPv4Network):
            raise ValueError("vmnet8 must use IPv4")
    except (KeyError, ValueError) as exc:
        raise NetworkPlanError(
            "Original vmnet8 NAT subnet cannot be authenticated"
        ) from exc

    port_keys = set()
    for declaration in active:
        if not declaration.startswith("add_nat_portfwd "):
            continue
        parts = declaration.split()
        if len(parts) != 6 or parts[2] not in ("tcp", "udp"):
            raise NetworkPlanError("Unexpected VMware NAT forwarding syntax")
        try:
            source_port, target_port = int(parts[3]), int(parts[5])
            if not (1 <= source_port <= 65535 and 1 <= target_port <= 65535):
                raise ValueError("Port out of range")
            target = ipaddress.IPv4Address(parts[4])
        except (ValueError, ipaddress.AddressValueError) as exc:
            raise NetworkPlanError("Invalid VMware NAT forwarding destination") from exc
        key = (parts[1], parts[2], source_port)
        if key in port_keys or active[declaration] != 1:
            raise NetworkPlanError("Duplicate VMware NAT forwarding host port")
        port_keys.add(key)

    # A reviewed baseline removal must be an *exact* old vmnet8 TCP
    # management forward that was replaced at the same host port. This is
    # not permission to delete unrelated NAT forwards, or to redirect an
    # approved host port into NORTH's isolated networks.
    for declaration in reviewed:
        words = declaration.split()
        if (len(words) != 6 or words[0:3] !=
                ["add_nat_portfwd", "8", "tcp"]):
            raise NetworkPlanError("Reviewed retirement is not vmnet8 TCP management")
        try:
            host_port, guest_port = int(words[3]), int(words[5])
            guest_ip = ipaddress.IPv4Address(words[4])
        except ValueError as exc:
            raise NetworkPlanError("Malformed reviewed NAT retirement") from exc
        if (host_port < 1025 or host_port > 65535
                or guest_port not in (22, 5985, 5986)
                or guest_ip not in nat_range
                or guest_ip in (nat_range.network_address,
                                nat_range.broadcast_address)
                or recorded[declaration] != 1
                or active[declaration] != 0):
            raise NetworkPlanError("Reviewed NAT retirement fails pinned baseline policy")
        replacements = [
            line for line in additions.elements()
            if line.startswith("add_nat_portfwd 8 tcp ")
            and len(line.split()) == 6
            and line.split()[3] == words[3]
        ]
        if len(replacements) != 1:
            raise NetworkPlanError(
                "Reviewed retired host port lacks unique replacement")
    if not additions and not removed:
        return ("VMware network declarations are semantically unchanged",)

    for declaration in additions.elements():
        parts = declaration.split()
        if (len(parts) != 6 or parts[0] != "add_nat_portfwd"
                or parts[1] != "8" or parts[2] != "tcp"):
            raise NetworkPlanError("Unexpected new VMware networking directive")
        target = ipaddress.IPv4Address(parts[4])
        target_port = int(parts[5])
        if (target not in nat_range
                or target in (nat_range.network_address, nat_range.broadcast_address)
                or target_port not in (22, 5985, 5986)):
            raise NetworkPlanError("New NAT forwarding is outside approved Vagrant management")
    return (
        "VMware declaration ordering and foreign DHCP hashes are normalized",
        "New Vagrant forwarding is restricted to baseline vmnet8 guest management",
    )


def network_plan(network_base=None, vmnets=None, baseline: str | None = None) -> dict:
    layout = load_course1_topology(network_base, vmnets)
    if baseline is None:
        if not NETWORKING_FILE.is_file() or NETWORKING_FILE.is_symlink():
            raise NetworkPlanError("VMware networking baseline is missing or unsafe")
        baseline = NETWORKING_FILE.read_text(encoding="utf-8")
    desired = render_vmnet_config(baseline, layout)
    before = hashlib.sha256(baseline.encode("utf-8")).hexdigest()
    after = hashlib.sha256(desired.encode("utf-8")).hexdigest()
    return {
        "profile": "NORTH",
        "network_base": layout["network_base"],
        "segment_settings": {
            name: {
                "vmnet": zone["vmnet"],
                "cidr": zone["cidr"],
                "host_address": zone["host_address"],
                "dhcp": False,
                "nat": False,
            }
            for name, zone in layout["segments"].items()
        },
        "baseline_sha256": before,
        "proposed_sha256": after,
        "proposed_text": desired,
        "mode": "READ-ONLY; no VMware, kernel, systemd, or files modified",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render-only VMware network plan for existing Kingdoms NORTH"
    )
    parser.add_argument("action", choices=("plan", "check", "hostaddr-plan"))
    parser.add_argument("--network-base", default=None)
    parser.add_argument("--vmnet", action="append", default=[])
    args = parser.parse_args()
    try:
        allocations = parse_vmnet_args(args.vmnet)
        if args.action == "hostaddr-plan":
            layout = load_course1_topology(args.network_base, allocations)
            hostaddr = hostaddr_plan(layout)
            hostaddr["assets"] = sorted(render_hostaddr_assets(layout))
            hostaddr["mode"] = "READ-ONLY; no systemd unit installed"
        elif args.action == "check":
            layout = load_course1_topology(args.network_base, allocations)
            if not NETWORKING_FILE.is_file() or NETWORKING_FILE.is_symlink():
                raise NetworkPlanError("VMware networking baseline is missing or unsafe")
            findings = verify_vmnet_config(
                NETWORKING_FILE.read_text(encoding="utf-8"), layout
            )
        else:
            planned = network_plan(args.network_base, allocations)
    except (NetworkPlanError, ValueError, OSError, KeyError) as exc:
        parser.exit(1, "[BLOCKED] NORTH VMware networking: " + str(exc) + "\n")
    if args.action == "hostaddr-plan":
        print(json.dumps(hostaddr, indent=2, sort_keys=True))
    elif args.action == "check":
        for finding in findings:
            print("[PASS] " + finding)
        print("[CONFIG ONLY] Host interface addresses and owner identity not proven")
    else:
        print(json.dumps({k: v for k, v in planned.items() if k != "proposed_text"},
                         indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
