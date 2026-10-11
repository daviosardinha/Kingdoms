"""Render NORTH-specific .254 address repair from the Kingdoms topology.

Read-only source generation. No systemd or VMware installation here.
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess

from goad.kingdoms_topology import load_course1_topology, parse_vmnet_args

HELPER = "/usr/local/sbin/kingdoms-north-vmnet-hostaddrs"
SERVICE = "kingdoms-north-vmnet-hostaddrs.service"
TIMER = "kingdoms-north-vmnet-hostaddrs.timer"


def hostaddr_plan(layout):
    zones = layout["segments"]
    if set(zones) != {"north", "sevenkingdoms", "management"}:
        raise ValueError("Unexpected Course 1 network segments")
    if zones["sevenkingdoms"]["host_address"] is not None:
        raise ValueError("Protected parent network must have no host adapter")
    result = {}
    for name in ("north", "management"):
        zone = zones[name]
        iface, address, gateway = zone["vmnet"], zone["host_address"], zone["gateway"]
        prefix = zone["cidr"].split("/")[1]
        if not iface.startswith("vmnet") or not iface[5:].isdigit():
            raise ValueError("Invalid VMware interface")
        if not address or address == gateway:
            raise ValueError("Invalid host-visible address")
        result[iface] = {"desired": address + "/" + prefix,
                         "vmware_default": gateway + "/" + prefix}
    if len(result) != 2:
        raise ValueError("Expected exactly two host-visible adapters")
    return {"interfaces": result, "protected": zones["sevenkingdoms"]["vmnet"]}


def repair_decisions(layout, observed):
    """Decide exact commands, checking ALL interfaces before changing any."""
    plan = hostaddr_plan(layout)
    rules = plan["interfaces"]
    if plan["protected"] in observed or set(observed) != set(rules):
        raise ValueError("Missing or unexpected VMware host-visible interface")
    for iface, rule in rules.items():
        ips = observed[iface]
        if not isinstance(ips, list) or len(ips) != len(set(ips)):
            raise ValueError("Bad or duplicated VMware IPv4 inventory")
        if set(ips) - {rule["desired"], rule["vmware_default"]}:
            raise ValueError("Unowned IPv4 address on " + iface)
    actions = []
    for iface, rule in rules.items():
        if rule["vmware_default"] in observed[iface]:
            actions.append(("ip", "-4", "addr", "del", rule["vmware_default"], "dev", iface))
        if rule["desired"] not in observed[iface]:
            actions.append(("ip", "-4", "addr", "add", rule["desired"], "dev", iface))
    return tuple(actions)



def verify_hostaddr_runtime(layout, links, addresses):
    """Verify live Linux interfaces in parsed ip -j output, without writes."""
    if not isinstance(links, list) or not isinstance(addresses, list):
        raise ValueError("Malformed Linux network inspection output")
    planned = hostaddr_plan(layout)
    names = [link.get("ifname") for link in links]
    if planned["protected"] in names:
        raise ValueError("Protected Seven Kingdoms adapter exposed on Kali")
    if any(iface not in names for iface in planned["interfaces"]):
        raise ValueError("Missing host-visible VMware interface")
    observed = {}
    for iface in planned["interfaces"]:
        entries = [entry for entry in addresses if entry.get("ifname") == iface]
        if len(entries) != 1:
            raise ValueError("Missing or ambiguous host-address evidence")
        ips = []
        for addr in entries[0].get("addr_info", []):
            if addr.get("family") != "inet":
                continue
            if not isinstance(addr.get("local"), str) or type(addr.get("prefixlen")) is not int:
                raise ValueError("Incomplete IPv4 address evidence")
            ips.append(addr["local"] + "/" + str(addr["prefixlen"]))
        observed[iface] = ips
    needed = repair_decisions(layout, observed)
    if needed:
        raise ValueError("Host IPv4 repair is still required")
    return (
        "Both NORTH VMware host adapters have exactly the expected .254 addresses",
        "VMware .1 addresses are absent and Seven Kingdoms has no host adapter",
    )


def inspect_live_hostaddrs(layout):
    """Read-only iproute2 call; no systemd, VMware or kernel changes."""
    def read_ip(*args):
        try:
            result = subprocess.run(
                ("ip", "-j", *args), check=False, capture_output=True,
                text=True, timeout=12,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("Linux iproute2 inspection unavailable") from exc
        if result.returncode:
            raise ValueError("Failed to inspect Linux interfaces")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid iproute2 JSON") from exc
    return verify_hostaddr_runtime(
        layout, read_ip("link", "show"), read_ip("-4", "addr", "show")
    )


def render_hostaddr_assets(layout):
    plan = hostaddr_plan(layout)
    quote = shlex.quote
    script = r"""#!/usr/bin/env bash
set -euo pipefail

# Kingdoms NORTH: no ip addr flush; permit only VMware .1 and owned .254.
die() { echo "[BLOCKED] Course 1 hostaddr: $*" >&2; exit 1; }
wait_iface() {
  local iface="$1" i
  for i in $(seq 1 20); do
    ip link show dev "$iface" >/dev/null 2>&1 && return 0
    sleep 1
  done
  die "VMware interface absent: $iface"
}
validate_iface() {
  local iface="$1" desired="$2" original="$3" actual
  wait_iface "$iface"
  local -a ips=()
  mapfile -t ips < <(ip -4 -o addr show dev "$iface" | awk '{print $4}')
  for actual in "${ips[@]}"; do
    [[ "$actual" == "$desired" || "$actual" == "$original" ]] ||
      die "Unowned IPv4 address on $iface: $actual"
  done
}
repair_iface() {
  local iface="$1" desired="$2" original="$3"
  if ip -4 -o addr show dev "$iface" | awk '{print $4}' | grep -Fxq "$original"; then
    ip -4 addr del "$original" dev "$iface"
  fi
  if ! ip -4 -o addr show dev "$iface" | awk '{print $4}' | grep -Fxq "$desired"; then
    ip -4 addr add "$desired" dev "$iface"
  fi
  ip link set dev "$iface" up
  ip -4 -o addr show dev "$iface" | awk '{print $4}' | grep -Fxq "$desired" ||
    die "IPv4 repair failed for $iface"
}
"""
    # First validate every address and the protected zone, then modify.
    for iface, rule in plan["interfaces"].items():
        script += "validate_iface " + " ".join(map(quote, (
            iface, rule["desired"], rule["vmware_default"]
        ))) + "\n"
    script += "if ip link show dev " + quote(plan["protected"]) + (
        ' >/dev/null 2>&1; then die "Protected parent adapter exposed"; fi\n'
    )
    for iface, rule in plan["interfaces"].items():
        script += "repair_iface " + " ".join(map(quote, (
            iface, rule["desired"], rule["vmware_default"]
        ))) + "\n"
    service = f"""[Unit]
Description=Kingdoms Course 1 host-only IPv4 repair
After=network.target vmware.service

[Service]
Type=oneshot
ExecStart={HELPER}
"""
    timer = f"""[Unit]
Description=Maintain Kingdoms Course 1 VMware host-only IPv4
After=vmware.service

[Timer]
OnActiveSec=3s
OnUnitInactiveSec=15s
AccuracySec=1s
Unit={SERVICE}

[Install]
WantedBy=timers.target
"""
    return {"helper": script, "service": service, "timer": timer}


def main():
    parser = argparse.ArgumentParser(description="Read-only NORTH host-address preview")
    parser.add_argument("--live", action="store_true", help="Read-only host IPv4 verification")
    parser.add_argument("--network-base", default=None)
    parser.add_argument("--vmnet", action="append", default=[])
    args = parser.parse_args()
    try:
        layout = load_course1_topology(args.network_base, parse_vmnet_args(args.vmnet))
        planned = hostaddr_plan(layout)
        planned["assets"] = sorted(render_hostaddr_assets(layout))
        if args.live:
            for line in inspect_live_hostaddrs(layout):
                print("[PASS] " + line)
            planned["mode"] = "READ-ONLY host inspection; no systemd changes"
        else:
            planned["mode"] = "READ-ONLY; no systemd service installed"
    except (KeyError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(planned, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
