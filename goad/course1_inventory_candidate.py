"""Course 1 nondeployable Ansible data/inventory address translation.

Preserves the validated parent/NORTH domain recipe and credentials while
translating only exact host endpoints and the one WS01 gateway. This does NOT
install AD, patch live Ansible hosts, or authorize provisioning.
"""
from __future__ import annotations

import json
import re

from goad.course1_network_plan import require, validate_proposal
from goad.course1_runtime_contract import COURSE1

HOST_BY_MACHINE = {
    "GOAD-DC01": ("dc01", "10.4.20.10"),
    "GOAD-DC02": ("dc02", "10.4.10.11"),
    "GOAD-SRV02": ("srv02", "10.4.10.22"),
    "GOAD-WS01": ("ws01", "10.4.10.31"),
}
FILES = (
    "data/config.json",
    "data/inventory",
    "data/inventory_disable_vagrant",
    "providers/vmware/inventory",
)


def render_candidate_inventories(source: dict[str, str], plan: dict) -> dict[str, str]:
    validate_proposal(plan)
    require(set(HOST_BY_MACHINE) == set(COURSE1.windows),
            "course inventory Windows roster diverges from profile")
    require(all(key in source for key in FILES),
            "reduced Course 1 source artifacts incomplete")

    config_text = source["data/config.json"]
    config = json.loads(config_text)
    lab = config["lab"]
    require(set(lab["hosts"]) == {"dc01", "dc02", "srv02", "ws01"},
            "unexpected Windows identities in Course 1 Ansible config")
    require(set(lab["domains"]) ==
            {"sevenkingdoms.local", "north.sevenkingdoms.local"},
            "unexpected AD domains in Course 1 config")
    require("essos.local" not in config_text.lower()
            and "braavos" not in config_text.lower(),
            "unpruned cross-forest fixture in Course 1 config")

    result = {
        "data/config.json": config_text,
        "data/inventory": source["data/inventory"],
    }
    inventory_map = {
        "data/inventory_disable_vagrant": source["data/inventory_disable_vagrant"],
        "providers/vmware/inventory": source["providers/vmware/inventory"],
    }
    for filename, inventory in inventory_map.items():
        for machine, (hostname, old_ip) in HOST_BY_MACHINE.items():
            new_ip = plan["machines"][machine]["ip"]
            pattern = rf"(?m)^(\s*{hostname}\s+ansible_host=){re.escape(old_ip)}(?=\s|$)"
            inventory, changed = re.subn(
                pattern, lambda m: m.group(1) + new_ip, inventory
            )
            require(changed == 1,
                    f"missing or duplicated {hostname} address in {filename}")

        # The existing WS01 provider inventory owns an explicit gateway.
        if filename == "providers/vmware/inventory":
            old = "lab_gateway=10.4.10.1"
            require(inventory.count(old) == 1,
                    "expected one canonical WS01 lab gateway in provider inventory")
            inventory = inventory.replace(
                old, "lab_gateway=" + plan["zones"]["NORTH"]["gateway"]
            )

        for zone, old_vmnet in (
            ("NORTH", "vmnet10"),
            ("SEVENKINGDOMS", "vmnet20"),
        ):
            inventory = inventory.replace(
                old_vmnet, plan["zones"][zone]["vmnet"]
            )
        require(not re.search(r"10\.4\.(?:10|20|30|99)\."
                              r"|vmnet(?:10|20|30|99)\b"
                              r"|\b(?:dc03|srv03)\b|essos\.local",
                              inventory, re.I),
                f"reference identities survived translated {filename}")
        result[filename] = inventory

    return result
