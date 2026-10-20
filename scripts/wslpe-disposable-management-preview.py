#!/usr/bin/env python3
"""Render/read a disposable WSLPE NIC candidate. No Vagrant or VMware writes.

This does NOT provision the requested vmnet, configure Windows' third NIC,
move the WinRM communicator, or remove the current NAT forwarding ports.
The WSLPE source recipe is opt-in only; existing instances remain unchanged.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "ad/WSLPE/providers/vmware/Vagrantfile"
OPTIN = "KINGDOMS_WSLPE_DISPOSABLE_MGMT_NIC"
VNET = "KINGDOMS_WSLPE_DISPOSABLE_MGMT_VMNET"
PREFIX = "KINGDOMS_WSLPE_DISPOSABLE_MGMT_PREFIX"
NORTH = ipaddress.IPv4Network("10.4.0.0/16")
RESERVED_VNETS = {"vmnet0", "vmnet1", "vmnet8", "vmnet10", "vmnet20",
                  "vmnet30", "vmnet99"}


def validate_prefix(value: str) -> ipaddress.IPv4Network:
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9]{1,3}\.){2}[0-9]{1,3}", value):
        raise ValueError("Expected three IPv4 octets, not an arbitrary input")
    try:
        network = ipaddress.IPv4Network(f"{value}.0/24", strict=True)
    except ValueError as exc:
        raise ValueError("Invalid management /24") from exc
    if not network.is_private or network.overlaps(NORTH):
        raise ValueError("Management network must be private and outside NORTH")
    return network


def choose(exercise: str, management: str, vmnet: str):
    exercise_cidr = validate_prefix(exercise)
    management_cidr = validate_prefix(management)
    if exercise_cidr.overlaps(management_cidr):
        raise ValueError("Operator management network equals learner exercise network")
    if not isinstance(vmnet, str) or not re.fullmatch(r"vmnet[0-9]{1,3}", vmnet):
        raise ValueError("Malformed management vmnet name")
    if vmnet in RESERVED_VNETS:
        raise ValueError("Management vmnet conflicts with shared or NORTH networks")
    return exercise_cidr, management_cidr


def render_candidate(exercise: str, management: str, vmnet: str,
                     existing_registration=False) -> dict:
    """Load ONLY a temporary rendered Ruby recipe. Do not call Vagrant or VMware."""
    exercise_cidr, management_cidr = choose(exercise, management, vmnet)
    source = RECIPE.read_text(encoding="utf-8")
    if source.count("{{ip_range}}") != 2:
        raise ValueError("Source recipe template changed; cannot independently render")
    ruby = source.replace("{{ip_range}}", exercise)
    runner = 'eval(File.read(ARGV.fetch(0)) + "\\nputs JSON.generate(boxes)", binding, ARGV.fetch(0))'
    env = os.environ.copy()
    for key in (OPTIN, VNET, PREFIX):
        env.pop(key, None)
    env.update({OPTIN: "preview", VNET: vmnet, PREFIX: management})
    with tempfile.TemporaryDirectory(prefix="kingdoms-wslpe-disposable-preview-") as root:
        work = Path(root)
        path = work / "Vagrantfile"
        path.write_text(ruby, encoding="utf-8")
        if existing_registration:
            state = work / ".vagrant/machines/WSLPE-WS01/vmware_desktop"
            state.mkdir(parents=True)
            (state / "id").write_text("/not-a-vm", encoding="ascii")
        try:
            result = subprocess.run(
                ["ruby", "-rjson", "-e", runner, str(path)],
                cwd=work, env=env, text=True, capture_output=True,
                timeout=20, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("Ruby recipe source-only evaluation unavailable") from exc
    if result.returncode:
        raise ValueError("Opt-in WSLPE source candidate rejected by Ruby: " +
                         result.stderr.strip()[:350])
    try:
        boxes = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid generated Ruby candidate metadata") from exc
    if not isinstance(boxes, list) or len(boxes) != 1:
        raise ValueError("Candidate must contain exactly one WSLPE guest")
    one = boxes[0]
    expected = [{"slot": 2, "vnet": vmnet, "mac": None}]
    if (one.get("name") != "WSLPE-WS01"
            or one.get("ip") != f"{exercise}.31"
            or one.get("vmware_network_adapters") != expected
            or one.get("wslpe_disposable_management_prefix") != management
            or one.get("box") != "mayfly/windows10"):
        raise ValueError("WSLPE disposable candidate is inconsistent")
    # Return non-secret metadata, never a host write.
    return {"exercise_subnet": str(exercise_cidr),
            "management_subnet": str(management_cidr),
            "vmnet": vmnet, "guest": one["name"],
            "extra_adapter_slot": 2,
            "management_guest_address_planned": f"{management}.31",
            "network_status": "UNALLOCATED",
            "winrm_status": "NOT CONFIGURED"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exercise-prefix", required=True)
    parser.add_argument("--management-prefix", required=True)
    parser.add_argument("--management-vmnet", required=True)
    args = parser.parse_args(argv)
    try:
        report = render_candidate(args.exercise_prefix, args.management_prefix,
                                  args.management_vmnet)
    except (OSError, ValueError) as exc:
        print("[BLOCKED] Disposable management NIC preview: " + str(exc))
        return 2
    print("[PASS] WSLPE disposable VMware slot-2 source candidate")
    for key, value in report.items():
        print(f"  {key}: {value}")
    print("[NOT VERIFIED] Host vmnet allocation, Windows NIC address, Vagrant direct communicator, NAT forward removal")
    print("[NO CHANGES] No Kali, VMware, VM, Windows, Vagrant, NORTH or firewall changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
