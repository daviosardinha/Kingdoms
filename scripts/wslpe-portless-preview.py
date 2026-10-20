#!/usr/bin/env python3
"""Read-only candidate audit. NEVER modifies or migrates a WSLPE VM.

The native current WSLPE VM is a two-NIC bootstrap; a blocked result is
expected until a separately reviewed management-network migration exists.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kingdoms.wslpe_portless_management import source_blockers

STAGE2 = ROOT / "scripts/wslpe-stage2-inspect.py"
spec = importlib.util.spec_from_file_location("wslpe_portless_inspection", STAGE2)
if spec is None or spec.loader is None:
    raise SystemExit("[BLOCKED] Native WSLPE registration inspector missing")
stage2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage2)


def checked_path(native_instance: Path) -> Path:
    provider = native_instance / "provider"
    manifest = provider / ".vagrant/machines/WSLPE-WS01/vmware_desktop/id"
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("Native VMware guest registration missing or unsafe")
    vmx = Path(manifest.read_text(encoding="utf-8").strip())
    if not vmx.is_absolute() or vmx.is_symlink() or vmx.suffix.lower() != ".vmx":
        raise ValueError("Unsafe native VMware VMX path")
    resolved = vmx.resolve(strict=True)
    if not resolved.is_file() or not resolved.is_relative_to(provider.resolve(strict=True)):
        raise ValueError("WSLPE registration does not own the selected VMX")
    return resolved


def configured_vmnets(text: str) -> dict[str, str]:
    pairs: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        match = re.fullmatch(
            r"\s*answer VNET_(\d+)_(HOSTONLY_SUBNET|HOSTONLY_NETMASK)\s+(\S+)\s*",
            line,
        )
        if match:
            index, name, value = match.groups()
            vmnet = "vmnet" + index
            target = pairs.setdefault(vmnet, {})
            if name in target:
                raise ValueError("Duplicate VMware network addressing declaration")
            target[name] = value
    from ipaddress import IPv4Network
    output = {}
    for name, value in pairs.items():
        if set(value) != {"HOSTONLY_SUBNET", "HOSTONLY_NETMASK"}:
            raise ValueError("Incomplete VMware network addressing")
        output[name] = str(IPv4Network(
            (value["HOSTONLY_SUBNET"], value["HOSTONLY_NETMASK"]), strict=False
        ))
    return output


def live_forwarding_summary(provider: Path) -> list[str]:
    command = stage2.vagrant_port_command(provider.parent)
    try:
        result = subprocess.run(
            command, cwd=provider, capture_output=True, text=True,
            timeout=35, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Vagrant forwarding inspection unavailable") from exc
    if result.returncode:
        raise ValueError("Vagrant forwarding inventory unavailable")
    rows = []
    for line in result.stdout.splitlines():
        entry = re.fullmatch(
            r"\s*(\d+)\s+\(guest\)\s+=>\s+(\d+)\s+\(host\)\s*", line,
        )
        if entry:
            rows.append(f"guest TCP/{entry[1]} -> host TCP/{entry[2]}")
        elif line.strip() and not line.strip().startswith((
            "The forwarded ports for the machine are listed below.",
            "these values may differ from values configured in the Vagrantfile",
            "provider supports automatic port collision detection and resolution.",
        )):
            raise ValueError("Unknown Vagrant forwarding evidence")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True,
                        help="Existing native WSLPE workspace, not fresh Git worktree")
    args = parser.parse_args()
    print("[WSLPE] Portless management TARGET ARCHITECTURE - READ ONLY")
    print("[NO CHANGES] No VMX, guest, VMware, firewall, Vagrant or NORTH operations")
    try:
        root = Path(args.workspace).expanduser()
        native, info = stage2.find_instance(root)
        if info.get("lab") != "WSLPE":
            raise ValueError("Native registration is not WSLPE")
        vmx = checked_path(native)
        networking = Path("/etc/vmware/networking").read_text(encoding="utf-8")
        topology = configured_vmnets(networking)
        blockers = source_blockers(vmx.read_text(encoding="utf-8"), topology)
        forwards = live_forwarding_summary(native / "provider")
        for item in forwards:
            print("[VAGRANT FORWARD] " + item)
        if forwards:
            blockers.append("Vagrant management still uses Kali host TCP ports")
        for reason in blockers:
            print("[BLOCKED] " + reason)
        print("[NOT VERIFIED] Direct operator-only WinRM, guest service binding, "
              "host/guest separation, port removal or power-off recovery")
        print("[NO CHANGES] Existing 41-scenario WSLPE master and NORTH untouched")
        if not blockers:
            print("[SOURCE PASS] Desired NIC/forwarding layout only, NOT release accepted")
        return 2 if blockers else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("[BLOCKED] Cannot prove portless candidate: " + str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
