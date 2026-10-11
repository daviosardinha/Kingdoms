"""NORTH-only provisioning route controller for the existing Kingdoms lifecycle.

Requires explicit provider directory for mutating actions. Every route added
is tracked in a private /run ownership record; never delete or replace
an unowned route. Original full-Kingdoms route behavior is unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import subprocess
import sys
from pathlib import Path

from goad.kingdoms_topology import load_course1_topology, parse_vmnet_args

STATE_DIR = Path("/run/kingdoms-course1-routes")
PROTO = "186"


class RouteConflict(ValueError):
    pass


def route_plan(network_base=None, vmnets=None) -> dict:
    topology = load_course1_topology(network_base, vmnets)
    north = topology["segments"]["north"]
    parent = topology["segments"]["sevenkingdoms"]
    return {
        "destination": parent["cidr"],
        "gateway": north["gateway"],
        "interface": north["vmnet"],
        "host_address": north["host_address"] + "/24",
        "protocol": PROTO,
    }


def run(*command: str, check=True) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RouteConflict(f"Cannot run {command[0]} for route inspection") from exc
    if check and result.returncode != 0:
        raise RouteConflict(f"Network command failed: {command[0]} {command[1]}")
    return result


def route_table() -> list[dict]:
    try:
        data = json.loads(run("ip", "-j", "-4", "route", "show", "table", "all").stdout)
    except (ValueError, TypeError) as exc:
        raise RouteConflict("Invalid structured Linux route table") from exc
    if not isinstance(data, list):
        raise RouteConflict("Linux route table is not a list")
    return data


def route_matches(entry: dict, desired: dict) -> bool:
    return (
        entry.get("dst") == desired["destination"]
        and entry.get("gateway") == desired["gateway"]
        and entry.get("dev") == desired["interface"]
        and str(entry.get("protocol")) == desired["protocol"]
        and str(entry.get("table", "main")) in ("main", "254")
    )


def overlaps(entry: dict, desired: dict) -> bool:
    if entry.get("dst") in (None, "default"):
        return False
    try:
        destination = ipaddress.ip_network(entry["dst"], strict=False)
    except (ValueError, KeyError) as exc:
        raise RouteConflict("Cannot classify existing route destination") from exc
    return destination.version == 4 and destination.overlaps(
        ipaddress.ip_network(desired["destination"])
    )


def check_routes(entries: list[dict], desired: dict, owner: bool) -> bool:
    matching = [entry for entry in entries if overlaps(entry, desired)]
    if len(matching) > 1 or (matching and not route_matches(matching[0], desired)):
        raise RouteConflict("Foreign/overlapping host route: cannot modify protected subnet")
    if matching and not owner:
        raise RouteConflict("Matching host route exists but has no Course 1 ownership record")
    if owner and not matching:
        raise RouteConflict("Route ownership record exists but kernel route is missing")
    return bool(matching)


def provider_state(provider_dir: str) -> tuple[Path, str]:
    path = Path(provider_dir)
    if not path.is_absolute() or not path.is_dir() or path.is_symlink():
        raise RouteConflict("Provider directory must be an existing absolute non-symlink directory")
    real = str(path.resolve(strict=True))
    marker = hashlib.sha256(real.encode("utf-8")).hexdigest()[:24]
    return STATE_DIR / (marker + ".json"), real


def read_owned(state_path: Path, provider: str, desired: dict) -> bool:
    if not state_path.exists() and not state_path.is_symlink():
        return False
    if not state_path.is_file() or state_path.is_symlink():
        raise RouteConflict("Unsafe provisioning-route ownership record")
    data = json.loads(state_path.read_text(encoding="utf-8"))
    if data != {"provider": provider, "route": desired}:
        raise RouteConflict("Route ownership record does not match selected instance/topology")
    return True


def check_host_adapter(desired: dict) -> None:
    result = run("ip", "-j", "-4", "addr", "show", "dev", desired["interface"])
    try:
        interfaces = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise RouteConflict("Cannot parse host vmnet interface address") from exc
    expected = desired["host_address"]
    if len(interfaces) != 1 or expected not in {
        f'{a.get("local")}/{a.get("prefixlen")}'
        for a in interfaces[0].get("addr_info", [])
        if a.get("family") == "inet"
    }:
        raise RouteConflict(f"Missing managed host adapter {desired['interface']} address {expected}")
    if run("ping", "-c", "1", "-W", "1", desired["gateway"], check=False).returncode:
        raise RouteConflict("Kingdoms router gateway is not responding; route unchanged")


def save_state(state_path: Path, provider: str, desired: dict) -> None:
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    if STATE_DIR.is_symlink() or STATE_DIR.stat().st_uid != 0:
        raise RouteConflict("Route ownership directory has unsafe permissions/owner")
    tmp = state_path.with_suffix(".tmp")
    if tmp.exists() or tmp.is_symlink():
        raise RouteConflict("Stale or unsafe route-state staging path")
    try:
        with tmp.open("x", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump({"provider": provider, "route": desired}, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, state_path)
    finally:
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink()


def execute(action: str, provider_dir: str | None = None,
            network_base=None, vmnets=None) -> str:
    desired = route_plan(network_base, vmnets)
    if action == "plan":
        return json.dumps(desired, sort_keys=True)
    if action in ("enable", "disable") and os.geteuid() != 0:
        raise RouteConflict("Route mutations require root")
    if not provider_dir:
        raise RouteConflict("NORTH route status/mutation requires --provider-dir")
    state_path, provider = provider_state(provider_dir)
    owned = read_owned(state_path, provider, desired)
    entries = route_table()
    found = check_routes(entries, desired, owner=owned)
    if action == "status":
        return "OWNED" if found else "ABSENT"
    if action == "enable":
        if found:
            return "ALREADY OWNED"
        check_host_adapter(desired)
        run("ip", "-4", "route", "add", desired["destination"],
            "via", desired["gateway"], "dev", desired["interface"],
            "proto", desired["protocol"])
        try:
            save_state(state_path, provider, desired)
        except (OSError, RouteConflict):
            run("ip", "-4", "route", "del", desired["destination"],
                "via", desired["gateway"], "dev", desired["interface"],
                "proto", desired["protocol"])
            raise
        return "ADDED OWNED ROUTE"
    if action == "disable":
        if not found:
            return "ALREADY ABSENT"
        run("ip", "-4", "route", "del", desired["destination"],
            "via", desired["gateway"], "dev", desired["interface"],
            "proto", desired["protocol"])
        state_path.unlink()
        return "REMOVED OWNED ROUTE"
    raise RouteConflict("Unsupported route action")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "status", "enable", "disable"))
    parser.add_argument("--provider-dir", default=None)
    parser.add_argument("--network-base", default=None)
    parser.add_argument("--vmnet", action="append", default=[])
    args = parser.parse_args()
    try:
        result = execute(args.action, args.provider_dir, args.network_base,
                         parse_vmnet_args(args.vmnet))
    except (RouteConflict, ValueError, OSError) as exc:
        parser.exit(1, f"[BLOCKED] Course 1 provisioning route: {exc}\n")
    print("[PASS] " + result)


if __name__ == "__main__":
    main()
