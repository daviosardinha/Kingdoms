"""Shared, read-only VMware Workstation resource planner for KINGDOMS labs.

An allocation is NOT a host mutation, trust grant, or installation approval.
The installation controller must hold the existing global vmnet lock, repeat
host discovery, commit an instance owner record, and prohibit networking
restarts while unrelated or peer guests are running.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import stat
from pathlib import Path

RESERVED = frozenset((0, 1, 8))
NET_KEY = re.compile(r"^answer VNET_(\d+)_([A-Z0-9_]+) (\S+)$")
VNET_PREFIX = re.compile(r"^(?:answer )?VNET_\d+_", re.I)
VMX_NET = re.compile(r'^\s*ethernet\d+\.vnet\s*=\s*"(vmnet\d+)"\s*$', re.I | re.M)
PROFILES = {
    "KINGDOMS": ("north", "sevenkingdoms", "essos", "management"),
    "NORTH": ("north", "sevenkingdoms", "management"),
    "WSLPE": ("exercise", "management"),
}
DEFAULT_IDS = {
    "KINGDOMS": (10, 20, 30, 99),
    "NORTH": (10, 20, 99),
    "WSLPE": (2, 3),
}


class CoexistenceError(ValueError):
    """A resource is in use or its provenance is insufficient."""


def _subnet(value):
    try:
        net = ipaddress.ip_network(value, strict=True)
        if not isinstance(net, ipaddress.IPv4Network):
            raise ValueError("IPv6 is not a VMware course subnet")
        return net
    except (ValueError, TypeError) as exc:
        raise CoexistenceError(f"Invalid exact IPv4 network: {value}") from exc


def network_inventory(text):
    """Parse VMware configuration without ignoring malformed or duplicate keys."""
    if not isinstance(text, str) or not text.strip():
        raise CoexistenceError("Missing VMware networking configuration")
    nets = {}
    ports = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = NET_KEY.fullmatch(line)
        if match:
            number, key, value = match.groups()
            number = int(number)
            fields = nets.setdefault(number, {})
            if key in fields:
                raise CoexistenceError(f"Duplicate vmnet{number} {key}")
            fields[key] = value
        elif VNET_PREFIX.match(line):
            raise CoexistenceError(f"Malformed VMware declaration: {line[:100]}")
        elif line.startswith("add_nat_portfwd"):
            parts = line.split()
            if len(parts) != 6 or parts[2] not in ("tcp", "udp"):
                raise CoexistenceError("Malformed NAT forwarding")
            try:
                ident, host, guest = int(parts[1]), int(parts[3]), int(parts[5])
                ipaddress.IPv4Address(parts[4])
            except ValueError as exc:
                raise CoexistenceError("Invalid NAT forwarding") from exc
            if not (1 <= host <= 65535 and 1 <= guest <= 65535):
                raise CoexistenceError("Invalid NAT forwarding port")
            port_key = (parts[2], host)
            if port_key in ports:
                raise CoexistenceError("Duplicate VMware NAT host listener")
            ports.add(port_key)
            nets.setdefault(ident, {})
    ranges = {}
    for number, fields in nets.items():
        subnet = fields.get("HOSTONLY_SUBNET")
        mask = fields.get("HOSTONLY_NETMASK")
        if (subnet is None) != (mask is None):
            raise CoexistenceError(f"Incomplete vmnet{number} subnet metadata")
        if subnet is not None:
            try:
                ranges[number] = _subnet(str(ipaddress.IPv4Network(
                    (subnet, mask), strict=False
                )))
            except (ValueError, TypeError) as exc:
                raise CoexistenceError(f"Bad vmnet{number} subnet metadata") from exc
    return nets, ranges


def owner_record(profile, provider, segments):
    """Canonical schema for a *future* locked/atomic registry writer."""
    if profile not in PROFILES or not isinstance(provider, str) or not Path(provider).is_absolute():
        raise CoexistenceError("Invalid lab profile or absolute provider path")
    if set(segments) != set(PROFILES[profile]):
        raise CoexistenceError("Missing or unexpected owned network roles")
    normalized = {}
    ids = set()
    for role in PROFILES[profile]:
        item = segments[role]
        if not isinstance(item, dict):
            raise CoexistenceError("Malformed owner segment")
        vmnet = item.get("vmnet")
        if not isinstance(vmnet, str) or not re.fullmatch(r"vmnet(?:[1-9]\d{0,2})", vmnet):
            raise CoexistenceError("Malformed owned vmnet")
        number = int(vmnet[5:])
        if number in RESERVED or number > 254 or number in ids:
            raise CoexistenceError("Duplicate or reserved owned vmnet")
        ids.add(number)
        normalized[role] = {"vmnet": vmnet, "cidr": str(_subnet(item.get("cidr")))}
    return {"schema": 1, "profile": profile, "provider": provider, "segments": normalized}


def load_owner_records(folder, owner_uid=0):
    """Trust only protected, single-link files in a protected registry directory.

    This does not migrate or overwrite legacy NORTH/WSLPE ownership records.
    Existing installations must be independently attested before enrollment.
    """
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise CoexistenceError("Missing or unsafe VMware owner registry")
    root = folder.stat()
    if root.st_uid != owner_uid or root.st_mode & 0o022:
        raise CoexistenceError("VMware owner registry permissions are unsafe")
    result = []
    for path in sorted(folder.iterdir()):
        if path.name.startswith("."):
            continue
        if path.suffix != ".json" or path.is_symlink() or not path.is_file():
            raise CoexistenceError("Unexpected VMware ownership registry entry")
        meta = path.stat()
        if (meta.st_uid != owner_uid or meta.st_nlink != 1
                or stat.S_IMODE(meta.st_mode) != 0o600):
            raise CoexistenceError("Unsafe VMware owner file permissions")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("not an object")
            if set(raw) != {"schema", "profile", "provider", "segments"} or raw["schema"] != 1:
                raise ValueError("unsupported owner version")
            canonical = owner_record(raw["profile"], raw["provider"], raw["segments"])
            if canonical != raw:
                raise ValueError("owner record is not canonical")
        except (KeyError, ValueError, TypeError, OSError) as exc:
            raise CoexistenceError("Invalid VMware owner registry entry") from exc
        result.append(raw)
    return result


def _validate_owners(owners, nets, configured):
    providers = set()
    assigned = {}
    owned_cidrs = []
    for raw in owners:
        try:
            if set(raw) != {"schema", "profile", "provider", "segments"} or raw["schema"] != 1:
                raise CoexistenceError("Unsupported peer owner schema")
            entry = owner_record(raw["profile"], raw["provider"], raw["segments"])
            if entry != raw:
                raise CoexistenceError("Noncanonical peer owner record")
        except (KeyError, TypeError) as exc:
            raise CoexistenceError("Malformed peer owner record") from exc
        if entry["provider"] in providers:
            raise CoexistenceError("Duplicate owner provider identity")
        providers.add(entry["provider"])
        for role, spec in entry["segments"].items():
            number = int(spec["vmnet"][5:])
            subnet = _subnet(spec["cidr"])
            if number in assigned:
                raise CoexistenceError("Two owners claim one vmnet")
            if number not in configured or configured[number] != subnet:
                raise CoexistenceError("Owned vmnet does not match live VMware subnet")
            attrs = nets[number]
            if attrs.get("NAT") != "no" or attrs.get("DHCP") != "no":
                raise CoexistenceError("Owned exercise/management vmnet lost isolation")
            if any(subnet.overlaps(existing) for existing in owned_cidrs):
                raise CoexistenceError("Overlapping owned laboratory networks")
            assigned[number] = (entry["provider"], role)
            owned_cidrs.append(subnet)
    return assigned




def plan_instance(profile, provider, segments, networking, *,
                  owners=(), link_names=(), routes=(), host_addresses=(),
                  registered_vmx=()):
    """Return an additive, deterministic plan; refuse unsupported IP overlap.

    Inputs must come from fresh VMware/OS/registered-VM discovery. For existing
    installs, only separately verified registry owners may pin an assignment.
    A vmnet-ID change never renumbers a course subnet.
    """
    if profile not in PROFILES or set(segments) != set(PROFILES[profile]):
        raise CoexistenceError("Unsupported profile or logical network roles")
    if not isinstance(provider, str) or not Path(provider).is_absolute():
        raise CoexistenceError("Expected absolute instance provider identity")
    wants = {role: _subnet(segments[role]) for role in PROFILES[profile]}
    for index, item in enumerate(wants.values()):
        if any(item.overlaps(other) for other in list(wants.values())[:index]):
            raise CoexistenceError("Profile segments overlap")
    nets, configured = network_inventory(networking)
    assignments = _validate_owners(owners, nets, configured)
    own = [r for r in owners if r["provider"] == provider]
    if len(own) > 1 or (own and own[0]["profile"] != profile):
        raise CoexistenceError("Provider has ambiguous lab ownership")
    linked = set()
    for name in link_names:
        if re.fullmatch(r"vmnet\d+", name):
            linked.add(int(name[5:]))
    for vmx in registered_vmx:
        linked.update(int(v[5:]) for v in VMX_NET.findall(vmx))
    other_routes = []
    for route in routes:
        if route in ("default", "0.0.0.0/0"):
            continue
        try:
            other_routes.append(_subnet(str(ipaddress.ip_network(route, strict=False))))
        except (ValueError, TypeError) as exc:
            raise CoexistenceError("Invalid host routing evidence") from exc
    addresses = []
    for value in host_addresses:
        try:
            addresses.append(ipaddress.IPv4Address(value))
        except ValueError as exc:
            raise CoexistenceError("Malformed host IPv4 address") from exc
    pinned = own[0]["segments"] if own else {}
    if pinned and set(pinned) != set(wants):
        raise CoexistenceError("Incomplete existing instance assignment")
    result = {}
    occupied = set(nets) | linked | set(assignments) | set(RESERVED)
    for i, role in enumerate(PROFILES[profile]):
        subnet = wants[role]
        own_number = int(pinned[role]["vmnet"][5:]) if pinned else None
        if any(subnet.overlaps(other) for num, other in configured.items()
               if num != own_number):
            raise CoexistenceError(f"{profile}/{role} overlaps existing VMware subnet")
        if any(subnet.overlaps(_subnet(s["cidr"]))
               for record in owners if record["provider"] != provider
               for s in record["segments"].values()):
            raise CoexistenceError("Lab CIDRs overlap verified peer; routing isolation unavailable")
        if any(subnet.overlaps(route) for route in other_routes) and own_number is None:
            raise CoexistenceError("Course subnet overlaps host routing table")
        if any(ip in subnet for ip in addresses) and own_number is None:
            raise CoexistenceError("Course subnet overlaps host interface address")
        if own_number is not None:
            if pinned[role]["cidr"] != str(subnet):
                raise CoexistenceError("Installed course CIDR drift")
            if assignments.get(own_number) != (provider, role):
                raise CoexistenceError("Installed vmnet ownership drift")
            number = own_number
        else:
            preference = DEFAULT_IDS[profile][i]
            options = [preference] + [n for n in range(2, 255) if n != preference]
            number = next((n for n in options if n not in occupied), None)
            if number is None:
                raise CoexistenceError("No unallocated VMware vmnet identifiers")
            occupied.add(number)
        result[role] = {"cidr": str(subnet), "vmnet": f"vmnet{number}"}
    return {"profile": profile, "provider": provider, "segments": result,
            "status": "EXISTING_VERIFIED" if own else "PROPOSED_NOT_INSTALLED",
            "host_mutation": False}
