#!/usr/bin/env python3
"""Build/validate a *preview-only* four-Windows-VM Kingdoms Course 1 recipe.

NO GOAD installation or virtualization commands are issued. Generated data includes
existing lab credentials, so output must be outside Git and access-restricted.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ad" / "GOAD"
WINDOWS = ("GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01")
HOSTS = ("dc01", "dc02", "srv02", "ws01")
DOMAINS = ("sevenkingdoms.local", "north.sevenkingdoms.local")
UNWANTED = {"dc03", "srv03"}
MACHINE_RX = re.compile(r'^\s*:name\s*=>\s*"([^"]+)"', re.M)
# All top-level Ruby box declarations end at exactly two spaces of indentation.
BOX_RX = re.compile(r"^  \{\n.*?^  \},?\n", re.M | re.S)
FORBIDDEN = re.compile(r"essos|braavos|meereen|dc03|srv03|10\.4\.30", re.I)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_source() -> dict[str, str]:
    files = {
        "config": SOURCE / "data" / "config.json",
        "inventory": SOURCE / "data" / "inventory",
        "disabled": SOURCE / "data" / "inventory_disable_vagrant",
        "provider": SOURCE / "providers" / "vmware" / "inventory",
        "vagrant": SOURCE / "providers" / "vmware" / "Vagrantfile",
    }
    return {key: path.read_text(encoding="utf-8") for key, path in files.items()}


def prune_inventory(content: str) -> str:
    result = []
    group = ""
    for line in content.splitlines():
        stripped = line.strip()
        if (not stripped or stripped.startswith((";", "#"))):
            # Remove obsolete ESSOS comment blocks without altering active hosts.
            if FORBIDDEN.search(stripped):
                continue
            result.append(line)
            continue
        if stripped.startswith("["):
            group = stripped.strip("[]")
            result.append(line)
            continue
        # A parent-forest DC remains, but its ESSOS forest-trust play must not.
        if group == "trust":
            continue
        hostname = stripped.split(maxsplit=1)[0]
        if hostname in UNWANTED:
            continue
        result.append(line)
    return "\n".join(result).rstrip() + "\n"


def parsed_groups(inventory: str) -> dict[str, list[str]]:
    group = ""
    groups: dict[str, list[str]] = {}
    for original in inventory.splitlines():
        line = original.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("[") and line.endswith("]"):
            group = line[1:-1]
            groups.setdefault(group, [])
            continue
        groups.setdefault(group, []).append(line.split(maxsplit=1)[0])
    return groups


def build_config(content: str) -> str:
    original = json.loads(content)
    require("lab" in original, "Expected GOAD lab object")
    config = copy.deepcopy(original)
    lab = config["lab"]
    require(set(HOSTS).issubset(lab["hosts"]), "Missing required NORTH/root host")
    require(set(DOMAINS).issubset(lab["domains"]), "Missing required parent/child realm")
    require(set(UNWANTED).issubset(lab["hosts"]), "GOAD reference hosts changed; inspect the new inventory")
    require("essos.local" in lab["domains"], "GOAD reference ESSOS realm changed; inspect source")
    lab["hosts"] = {key: lab["hosts"][key] for key in HOSTS}
    lab["domains"] = {name: lab["domains"][name] for name in DOMAINS}
    parent = lab["domains"]["sevenkingdoms.local"]
    require(parent.get("trust") == "essos.local", "Parent trust is not the expected ESSOS fixture")
    parent["trust"] = ""
    cross = parent.get("multi_domain_groups_member", {})
    require(cross.get("AcrossTheNarrowSea") == ["essos.local\\daenerys.targaryen"],
            "Cross-forest group fixture changed; review before pruning")
    cross.pop("AcrossTheNarrowSea")
    # New local dual-instance SQL link is not provisioned by this preview.
    sql = lab["hosts"]["srv02"]["mssql"]
    require(set(sql["linked_servers"]) == {"BRAAVOS"}, "Unexpected MSSQL linked servers: refuse silent removal")
    sql["linked_servers"] = {}
    serialized = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    require(not FORBIDDEN.search(serialized),
            "Residual ESSOS reference in Course 1 recipe; refuse to generate")
    require(lab["hosts"]["dc02"]["domain"] == "north.sevenkingdoms.local",
            "NORTH membership changed")
    return serialized


def build_vagrant(content: str) -> str:
    blocks = list(BOX_RX.finditer(content))
    found = {}
    for match in blocks:
        block = match.group(0).rstrip()
        name = MACHINE_RX.search(block)
        require(name is not None, "Unidentified Ruby Vagrant machine block")
        require(name.group(1) not in found, "Duplicate Ruby Vagrant machine")
        found[name.group(1)] = block.rstrip(",")
    require(set(found) == set(WINDOWS) | {"GOAD-DC03", "GOAD-SRV03", "GOAD-ROUTER"},
            "Unexpected reference Vagrant machines; fail closed")
    # Keep the existing router *as is* for initial lifecycle compatibility:
    # its unused vmnet30 interface is NOT a dependency of ESSOS domain trust.
    ordered = [found[name] for name in WINDOWS + ("GOAD-ROUTER",)]
    return "# GENERATED PREVIEW ONLY; NOT WIRED INTO THE GOAD VMWARE PROVIDER.\n" + (
        "boxes = [\n" + ",\n\n".join(ordered) + "\n]\n"
    )


def render() -> dict[str, str]:
    src = load_source()
    config = build_config(src["config"])
    inventory = prune_inventory(src["inventory"])
    disabled = prune_inventory(src["disabled"])
    provider = prune_inventory(src["provider"])
    vagrant = build_vagrant(src["vagrant"])
    groups = parsed_groups(inventory)
    require(groups["domain"] == list(HOSTS), "Domain roster mismatch")
    for section, members in {
        "dc": ["dc01", "dc02"],
        "server": ["srv02"],
        "workstation": ["ws01"],
        "parent_dc": ["dc01"],
        "child_dc": ["dc02"],
        "trust": [],
        "adcs": ["dc01"],
        "mssql": ["srv02"],
    }.items():
        require(groups[section] == members,
                f"Unexpected [{section}] host list: {groups[section]}")
    require(groups["domain"] == parsed_groups(disabled)["domain"],
            "Post-Vagrant inventory doesn't match Course 1")
    provider_hosts = [x.split(maxsplit=1)[0] for x in provider.splitlines()
                      if x and not x.lstrip().startswith((";", "#", "["))]
    require(provider_hosts == list(HOSTS), "Provider inventory doesn't match Course 1")
    for name in ("inventory", "disabled", "provider"):
        require(not FORBIDDEN.search({"inventory": inventory, "disabled": disabled, "provider": provider}[name]),
                f"ESSOS reference in generated {name}")
    return {
        "data/config.json": config,
        "data/inventory": inventory,
        "data/inventory_disable_vagrant": disabled,
        "providers/vmware/inventory": provider,
        "providers/vmware/Vagrantfile": vagrant,
        "manifest.json": json.dumps({
            "profile": "course1-fall-of-the-north",
            "state": "PREVIEW_ONLY_NOT_INSTALLABLE",
            "windows_machines": list(WINDOWS),
            "router": "GOAD-ROUTER",
            "domain": "north.sevenkingdoms.local",
            "parent_domain": "sevenkingdoms.local",
            "removed": ["GOAD-DC03", "GOAD-SRV03", "essos.local"],
            "critical_blocks": [
                "GOAD runtime hardcodes the six-guest lifecycle",
                "router still has unused vmnet30 interface",
                "separate KINGDOMS2 SQL provisioning is not yet wired in",
                "NORTH/parent startup, DNS, trust and module 00-09 regression not validated",
                "do not run alongside the live reference lab: deterministic MACs/IPs",
            ],
        }, indent=2) + "\n",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="Validate source and staged topology in memory; do not write files (default)")
    parser.add_argument("--output", type=Path, help="Create private PREVIEW_ONLY directory outside Git checkout")
    parser.add_argument("--acknowledge-lab-credentials", action="store_true",
                        help="Required when writing the derived GOAD config with lab fixture passwords")
    args = parser.parse_args()
    if args.check and args.output:
        parser.error("Use --check or --output, not both")
    profile = render()
    print("[PASS] Course 1 source/topology contracts validated (4 Windows VMs + router)")
    print("[INFO] No installed VMware guest, Ansible config or GOAD source was modified")
    if not args.output:
        print("[INFO] Preview only. To write files, supply --output and --acknowledge-lab-credentials")
        return
    if not args.acknowledge_lab_credentials:
        parser.error("--output contains lab fixture passwords: add --acknowledge-lab-credentials")
    output = args.output.expanduser().resolve()
    require(not output.is_relative_to(ROOT.resolve()), "Output must be outside the Git repository")
    require(not output.exists(), "Output already exists; never overwrite generated credentials")
    old_umask = os.umask(0o077)
    try:
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
        for name, content in profile.items():
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            target.chmod(0o600)
    finally:
        os.umask(old_umask)
    print(f"[PASS] Private preview recipe written: {output}")
    print("[BLOCKED] Preview is intentionally not installable: lifecycle/provider contract pending")


if __name__ == "__main__":
    main()
