"""Render consistent Course 1 runtime source text without host modifications.

This is an offline topology-to-artifact consistency proof, NOT a new installer.
Eventually the existing Kingdoms instance-generation path consumes these
texts. It must never silently install NORTH through generic Vagrant.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

from goad.kingdoms_topology import (
    MANIFEST_PATH, load_course1_topology, parse_vmnet_args,
)

SOURCE_FILES = (
    "providers/vmware/Vagrantfile",
    "providers/vmware/inventory",
    "data/inventory_disable_vagrant",
    "providers/vmware/router/provision.sh",
    "providers/vmware/router/nftables/exercise.nft",
)
MAC_PATTERN = re.compile(r"\b00:50:56:(?:[0-9a-f]{2}:){2}[0-9a-f]{2}\b", re.I)


def _mac_map(default_vagrant: str, seed: str) -> dict[str, str]:
    """Deterministic VMware-compatible MACs for an isolated alternate layout.

    Preserve every original MAC at 10.4 by not invoking this mapping.
    Static MACs use the VMware 00:50:56:00-3f OUI allocation. Cross-lab
    collisions must still be checked against all actual registered VMX files.
    """
    old = set(mac.lower() for mac in MAC_PATTERN.findall(default_vagrant))
    if len(old) != 7:
        raise ValueError("Expected four Windows and three router MAC identities")
    result = {}
    for mac in sorted(old):
        digest = hashlib.sha256((seed + "|" + mac).encode("ascii")).digest()
        candidate = "00:50:56:%02x:%02x:%02x" % (
            digest[0] & 0x3f, digest[1], digest[2]
        )
        if candidate in result.values() or candidate in old:
            raise ValueError("MAC collision in deterministic topology rendering")
        result[mac] = candidate
    return result


def render_course1_artifacts(
    network_base: str | None = None,
    vmnets: dict[str, int] | None = None,
    manifest_path: Path = MANIFEST_PATH,
) -> dict[str, str]:
    """Return source-bound Vagrant, inventories, router and policy text.

    The function reads canonical Kingdoms-owned Course 1 files and creates
    no directories or output files. It does not grant installation readiness.
    """
    root = Path(manifest_path).parent
    baseline = load_course1_topology(manifest_path=manifest_path)
    target = load_course1_topology(network_base, vmnets, manifest_path)
    files = {
        path: (root / path).read_text(encoding="utf-8")
        for path in SOURCE_FILES
    }
    substitutions: dict[str, str] = {}
    for machine, old in baseline["windows"].items():
        new = target["windows"][machine]
        substitutions[old["address"]] = new["address"]
    for key, old in baseline["segments"].items():
        new = target["segments"][key]
        for field in ("cidr", "gateway", "host_address", "vmnet"):
            if old[field] is not None:
                substitutions[old[field]] = new[field]

    is_original = (
        target["network_base"] == baseline["network_base"]
        and target["segments"] == baseline["segments"]
    )
    if is_original:
        # Exact byte equality with our existing Kingdoms-derived source files.
        result = files
    else:
        if target["network_base"] != baseline["network_base"]:
            assignments = [target["segments"][zone]["vmnet"] for zone in
                           sorted(target["segments"])]
            macs = _mac_map(
                files["providers/vmware/Vagrantfile"],
                target["network_base"] + "|" + "|".join(assignments),
            )
            substitutions.update(macs)
        # Regex token boundaries protect 10.4.10.1 from wrongly replacing
        # the initial characters of 10.4.10.11 or 10.4.10.100.
        tokens = sorted(substitutions, key=len, reverse=True)
        selector = re.compile(
            r"(?<![0-9A-Za-z_.])(?:"
            + "|".join(re.escape(token) for token in tokens)
            + r")(?![0-9A-Za-z_.])",
            re.I,
        )
        result = {
            path: selector.sub(lambda m: substitutions[m.group(0).lower()]
                               if m.group(0).lower() in substitutions
                               else substitutions[m.group(0)], src)
            for path, src in files.items()
        }

    vagrant = result["providers/vmware/Vagrantfile"]
    provider = result["providers/vmware/inventory"]
    post = result["data/inventory_disable_vagrant"]
    router = result["providers/vmware/router/provision.sh"]
    exercise = result["providers/vmware/router/nftables/exercise.nft"]

    for machine, host in target["windows"].items():
        if (f':name => "{machine}"' not in vagrant
                or f':ip => "{host["address"]}"' not in vagrant
                or f':vnet => "{host["vmnet"]}"' not in vagrant):
            raise ValueError("Vagrant host topology rendering mismatch: " + machine)
        for inventory in (provider, post):
            if (f'{host["inventory"]} ansible_host={host["address"]}'
                    not in inventory):
                raise ValueError("Ansible inventory topology mismatch: " + machine)
    for name, segment in target["segments"].items():
        if (f'"{segment["gateway"]}"' not in router
                or segment["vmnet"] not in vagrant):
            raise ValueError("Router/VMware segment mismatch: " + name)
    child = target["windows"]["GOAD-DC02"]["address"]
    parent = target["windows"]["GOAD-DC01"]["address"]
    if (f"ip saddr {child} ip daddr {parent}" not in exercise
            or f"ip saddr {parent} ip daddr {child}" not in exercise):
        raise ValueError("Parent/child AD firewall policy rendering mismatch")
    if any(re.search(r"essos|GOAD-DC03|GOAD-SRV03|vmnet30", doc, re.I)
           for doc in result.values()):
        raise ValueError("Deleted Essos artifacts remain in Course 1 output")
    if target["network_base"] != baseline["network_base"]:
        old_macs = set(MAC_PATTERN.findall(files["providers/vmware/Vagrantfile"]))
        new_macs = set(MAC_PATTERN.findall(vagrant))
        if len(new_macs) != 7 or old_macs & new_macs:
            raise ValueError("Nondefault topology did not isolate all VM MACs")
        router_macs = set(MAC_PATTERN.findall(router))
        if len(router_macs) != 3 or not router_macs.issubset(new_macs):
            raise ValueError("Router MAC identities mismatch VMware adapters")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only Kingdoms Course 1 coherent artifact renderer"
    )
    parser.add_argument("--network-base", default=None)
    parser.add_argument("--vmnet", action="append", default=[])
    args = parser.parse_args()
    try:
        artifacts = render_course1_artifacts(
            args.network_base, parse_vmnet_args(args.vmnet)
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    for path in artifacts:
        print("[PASS] topology rendered: " + path)
    print("[SAFE] In-memory proof only; no files, VMs, or VMware networks modified")


if __name__ == "__main__":
    main()
