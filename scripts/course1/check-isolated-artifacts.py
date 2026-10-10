#!/usr/bin/env python3
"""Strict native Ansible parser gate for the isolated Course 1 inventories.

Credential-bearing native inventory output is captured in memory and never
printed, even on parser failures. No playbooks, guests or VMware commands.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from goad.course1_network_plan import validate_proposal
WINDOWS = {"dc01", "dc02", "srv02", "ws01"}


class OfflineGateError(RuntimeError):
    pass


def need(cond: bool, msg: str) -> None:
    if not cond:
        raise OfflineGateError(msg)


def check_inventory(candidate: Path, executable: str, name: str,
                    expected_ip: dict[str, str], kind: str, gateway: str) -> None:
    target = candidate / name
    need(target.is_file() and not target.is_symlink(),
         f"missing or symlinked isolated {kind} inventory")
    try:
        result = subprocess.run(
            [executable, "-i", str(target), "--list"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=ROOT, timeout=30, check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise OfflineGateError(f"native Ansible inventory parser failed for {kind}") from exc
    need(result.returncode == 0,
         f"native Ansible inventory parser rejected {kind}; output withheld")
    try:
        tree = json.loads(result.stdout)
    except ValueError as exc:
        raise OfflineGateError(f"Ansible {kind} parser did not return JSON") from exc

    data = tree.get("_meta", {}).get("hostvars", {})
    need(isinstance(data, dict), f"invalid {kind} hostvars")
    need(set(data) == WINDOWS, f"isolated {kind} inventory wrong host roster")
    if kind in ("post", "provider"):
        for key, ip in expected_ip.items():
            need(data[key].get("ansible_host") == ip,
                 f"{kind} address mismatch: {key}")
    if kind == "provider":
        need(data["ws01"].get("lab_gateway") == gateway,
             "WS01 gateway not translated to Course 1 NORTH")
    if kind == "post":
        need(data["ws01"].get("ansible_user") == data["srv02"].get("ansible_user")
             and data["ws01"].get("ansible_password")
             == data["srv02"].get("ansible_password"),
             "WS01 NORTH WinRM credentials inconsistent")

    needed = (
        {"domain": WINDOWS, "dc": {"dc01", "dc02"},
         "parent_dc": {"dc01"}, "child_dc": {"dc02"}, "trust": set()}
        if kind == "provision" else
        {"default": WINDOWS}
    )
    for group, expected in needed.items():
        actual = set(tree.get(group, {}).get("hosts", []))
        need(actual == expected, f"isolated {kind} Ansible group {group} mismatch")


def check(candidate: Path, proposal: dict) -> None:
    validate_proposal(proposal)
    binary = shutil.which("ansible-inventory") or str(
        Path.home() / ".goad/.venv/bin/ansible-inventory"
    )
    need(Path(binary).is_file() or shutil.which(binary) is not None,
         "native ansible-inventory executable unavailable")

    expected_ip = {
        {"GOAD-DC01": "dc01", "GOAD-DC02": "dc02",
         "GOAD-SRV02": "srv02", "GOAD-WS01": "ws01"}[m]: v["ip"]
        for m, v in proposal["machines"].items()
    }
    gateway = proposal["zones"]["NORTH"]["gateway"]
    for path, kind in (
        ("data/inventory", "provision"),
        ("data/inventory_disable_vagrant", "post"),
        ("providers/vmware/inventory", "provider"),
    ):
        check_inventory(candidate, binary, path, expected_ip, kind, gateway)
        print(f"[PASS] Isolated {kind} Ansible inventory: four hosts, intended addresses/groups")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    args = parser.parse_args()
    try:
        proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
        check(args.candidate, proposal)
    except (OfflineGateError, OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, "[FAIL] " + str(exc) + "\n")


if __name__ == "__main__":
    main()
