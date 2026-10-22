#!/usr/bin/env python3
"""Committed WSLPE vmnet4 host-address persistence, scoped to vmnet4 ONLY.

Root-owned, standalone installed copy for systemd. No imports from user
checkout. No VMware network restarts, guest operations, global forwarding,
vmnet3 or NORTH writes. Refuses uncommitted or changed management metadata.
The periodic service may repair only 172.28.233.1/24 -> .254/24 or an
unnumbered vmnet4 with no connected route. Never adopt foreign addresses.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

NETWORKING = Path("/etc/vmware/networking")
JOURNAL = Path("/var/lib/kingdoms/wslpe-vmnet4/journal.json")
IP = "/usr/bin/ip"
VMNET = "vmnet4"
SUBNET = "172.28.233.0/24"
EXPECTED_HOST = "172.28.233.254/24"
VMWARE_DEFAULT = "172.28.233.1/24"
EXPECTED_COMMIT = "9717eecc5c8f05f4d214018a7da280c4484dc3d2e9a26a33902a9efe3e89f990"
NET = ipaddress.IPv4Network(SUBNET)
READ_CAP = 600_000


class Denied(RuntimeError):
    """State is not safe for an isolated management host-address change."""


def _read_root(path: Path, *, secret: bool = False) -> bytes:
    try:
        details = path.lstat()
        if not stat.S_ISREG(details.st_mode) or details.st_uid != 0 or (
                details.st_mode & 0o022) or details.st_size > READ_CAP or details.st_nlink != 1:
            raise Denied(f"Untrusted root-owned state: {path}")
        if secret and stat.S_IMODE(details.st_mode) != 0o600:
            raise Denied("Untrusted transaction journal permissions")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            opened = os.fstat(fd)
            if opened.st_ino != details.st_ino or opened.st_dev != details.st_dev:
                raise Denied(f"State changed during read: {path}")
            content = os.read(fd, READ_CAP + 1)
            if len(content) > READ_CAP:
                raise Denied("State exceeds allowed size")
            return content
        finally:
            os.close(fd)
    except OSError as exc:
        raise Denied(f"Required root-owned state unavailable: {path}") from exc


def _answers(source: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in source.splitlines():
        fields = line.split()
        if not fields or fields[0] != "answer":
            continue
        if len(fields) != 3 or not fields[1].startswith("VNET_"):
            raise Denied("Malformed VMware network metadata")
        if fields[1] in data:
            raise Denied("Duplicate VMware network metadata")
        data[fields[1]] = fields[2]
    return data


def verify_committed_state(journal: dict, networking: bytes) -> str:
    """Reject changes to any original VMware directive except dropped HOSTADDR."""
    if (journal.get("version") != 1 or journal.get("status") != "committed"
            or journal.get("vmnet") != VMNET or journal.get("subnet") != SUBNET
            or journal.get("networking") != str(NETWORKING)
            or journal.get("proposed_sha256") != EXPECTED_COMMIT):
        raise Denied("Wrong or uncommitted vmnet4 transaction")
    try:
        original = base64.b64decode(journal["original_b64"], validate=True)
        if hashlib.sha256(original).hexdigest() != journal["original_sha256"]:
            raise Denied("Journal original source checksum mismatch")
        current_answers = _answers(networking.decode("utf-8"))
        old_answers = _answers(original.decode("utf-8"))
    except (KeyError, ValueError, UnicodeError, TypeError) as exc:
        raise Denied("Invalid VMware journal or networking metadata") from exc
    if not original or b"VNET_4_" in original:
        raise Denied("Original networking baseline already contained vmnet4")
    for key, value in old_answers.items():
        if key.endswith("_HOSTONLY_HOSTADDR") and key not in current_answers:
            # VMware Workstation 26 can drop this hint during network start.
            continue
        if current_answers.get(key) != value:
            raise Denied(f"Existing VMware network policy changed: {key}")
    for key in current_answers:
        if not key.startswith("VNET_4_") and key not in old_answers:
            raise Denied(f"Unexpected foreign network metadata: {key}")
    expected = {
        "VNET_4_DHCP": "no",
        "VNET_4_NAT": "no",
        "VNET_4_VIRTUAL_ADAPTER": "yes",
        "VNET_4_HOSTONLY_SUBNET": "172.28.233.0",
        "VNET_4_HOSTONLY_NETMASK": "255.255.255.0",
    }
    allowed = set(expected) | {"VNET_4_HOSTONLY_HOSTADDR"}
    if any(current_answers.get(k) != v for k, v in expected.items()):
        raise Denied("vmnet4 host-only network metadata drift")
    if any(key.startswith("VNET_4_") and key not in allowed
           for key in current_answers):
        raise Denied("Unexpected vmnet4 network directive")
    if current_answers.get("VNET_4_HOSTONLY_HOSTADDR", "172.28.233.254") != "172.28.233.254":
        raise Denied("Unexpected vmnet4 host-address metadata")
    actual_sha = hashlib.sha256(networking).hexdigest()
    if actual_sha != EXPECTED_COMMIT:
        print("[INFO] VMware normalized configuration text; verified all original answer directives")
    return actual_sha


def _ip(args: list[str]) -> list[dict]:
    try:
        result = subprocess.run([IP, *args], check=False,
                                capture_output=True, text=True, timeout=15,
                                stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Denied("Cannot query vmnet4 kernel state") from exc
    if result.returncode or len(result.stdout) > 200_000:
        raise Denied("vmnet4 kernel state unavailable")
    try:
        data = json.loads(result.stdout)
    except ValueError as exc:
        raise Denied("Malformed host routing state") from exc
    if not isinstance(data, list) or len(data) > 4096 or not all(isinstance(x, dict) for x in data):
        raise Denied("Unexpected host routing records")
    return data


def _write_ip(args: list[str]) -> None:
    try:
        result = subprocess.run([IP, "-4", "address", *args],
                                check=False, capture_output=True,
                                text=True, timeout=15,
                                stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Denied("Unable to reconcile management host address") from exc
    if result.returncode:
        raise Denied("vmnet4-only iproute2 mutation failed")


def _zero(path: str) -> bool:
    try:
        return Path(path).read_text(encoding="ascii").strip() == "0"
    except (OSError, UnicodeError):
        return False


def plan_snapshot(*, links: list[dict], addresses: list[dict],
                  routes: list[dict], forwarding: tuple[bool, bool, bool]) -> tuple[list[str], ...]:
    if not all(forwarding):
        raise Denied("Management or global IPv6 forwarding not disabled")
    if len(links) != 1 or links[0].get("ifname") != VMNET:
        raise Denied("vmnet4 link identity mismatch")
    link = links[0]
    if ("UP" not in link.get("flags", []) or "master" in link or
            "link" in link or link.get("linkinfo", {}).get("info_kind") in
            {"bridge", "bond", "veth", "vlan"}):
        raise Denied("vmnet4 interface is down or bridged")
    if len(addresses) != 1 or addresses[0].get("ifname") != VMNET:
        raise Denied("vmnet4 address record missing/ambiguous")
    values = addresses[0].get("addr_info", [])
    ipv4 = [x for x in values if isinstance(x, dict) and x.get("family") == "inet"]
    if len(ipv4) > 1:
        raise Denied("Multiple vmnet4 IPv4 addresses")
    for route in routes:
        if route.get("dst") == SUBNET and route.get("dev") != VMNET:
            raise Denied("Management subnet owned by another interface")
    vmnet_routes = [x for x in routes if x.get("dev") == VMNET]
    if len(vmnet_routes) > 1 or any(
            x.get("dst") != SUBNET or x.get("gateway") or x.get("via")
            or x.get("type", "unicast") != "unicast"
            or x.get("scope", "link") != "link"
            for x in vmnet_routes):
        raise Denied("Unexpected vmnet4 kernel route")
    if not ipv4:
        if vmnet_routes:
            raise Denied("Unnumbered management NIC still has a route")
        return (["add", EXPECTED_HOST, "dev", VMNET],)
    current = f'{ipv4[0].get("local")}/{ipv4[0].get("prefixlen")}'
    if current == EXPECTED_HOST:
        if len(vmnet_routes) != 1:
            raise Denied("Management connected route missing")
        if vmnet_routes[0].get("prefsrc", vmnet_routes[0].get("src", "172.28.233.254")) != "172.28.233.254":
            raise Denied("Management route source does not match committed host IP")
        return ()
    if current != VMWARE_DEFAULT:
        raise Denied("Foreign vmnet4 address, only VMware default .1 is repairable")
    if len(vmnet_routes) != 1:
        raise Denied("VMware default management address missing connected route")
    return (
        ["del", VMWARE_DEFAULT, "dev", VMNET],
        ["add", EXPECTED_HOST, "dev", VMNET],
    )


def snapshot() -> tuple[list[dict], list[dict], list[dict], tuple[bool, bool, bool]]:
    links = _ip(["-j", "link", "show", "dev", VMNET])
    addresses = _ip(["-j", "-4", "address", "show", "dev", VMNET])
    routes = _ip(["-j", "-4", "route", "show", "table", "main"])
    flags = tuple(_zero(p) for p in (
        "/proc/sys/net/ipv4/conf/vmnet4/forwarding",
        "/proc/sys/net/ipv6/conf/vmnet4/forwarding",
        "/proc/sys/net/ipv6/conf/all/forwarding"))
    return links, addresses, routes, flags


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--check", action="store_true", help="Read-only drift report")
    choice.add_argument("--repair", action="store_true", help="Correct ONLY vmnet4 IPv4")
    args = parser.parse_args(argv)
    try:
        if os.geteuid() != 0:
            raise Denied("Root required for committed journal verification")
        root_dir = JOURNAL.parent
        d = root_dir.lstat()
        if not stat.S_ISDIR(d.st_mode) or d.st_uid != 0 or stat.S_IMODE(d.st_mode) != 0o700:
            raise Denied("Unsafe committed-journal directory")
        journal = json.loads(_read_root(JOURNAL, secret=True))
        source_sha = verify_committed_state(journal, _read_root(NETWORKING))
        print(f"[COMMITTED] vmnet4 source journal valid; current SHA256={source_sha}")
        links, addresses, routes, forwarding = snapshot()
        steps = plan_snapshot(links=links, addresses=addresses, routes=routes,
                              forwarding=forwarding)
        if steps and args.check:
            print("[DRIFT] vmnet4 host IPv4 requires reconciliation")
            return 1
        for action in steps:
            if not args.repair:
                continue
            _write_ip(action)
        if args.repair:
            links, addresses, routes, forwarding = snapshot()
            if plan_snapshot(links=links, addresses=addresses, routes=routes,
                             forwarding=forwarding):
                raise Denied("vmnet4 host-address verification incomplete")
        print("[PASS] VMNET4_HOSTADDR_PERSISTENCE=PASS")
        return 0
    except (Denied, ValueError, TypeError, OSError) as exc:
        print(f"[BLOCKED] vmnet4 persistence: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
