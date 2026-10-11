#!/usr/bin/env python3
"""Read-only audit of obsolete NORTH and original Kingdoms host resources.

The script DOES NOT stop, unregister, delete, or alter anything. Its JSON
report is deliberately broad: some matches may be unrelated and must be
verified by the operator before deletion. No hidden destructive mode.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

NETWORK_IDS = (10, 11, 12, 13, 20, 30, 99)
SERVICE_NAMES = (
    "goad-nomad-vmnet-hostaddrs.service",
    "goad-nomad-vmnet-hostaddrs.timer",
    "kingdoms-north-vmnet-hostaddrs.service",
    "kingdoms-north-vmnet-hostaddrs.timer",
    "kingdoms-phase03-rickon.service",
    "kingdoms-rdp-bot.service",
)
OWNED_NAMES = {"GOAD", "NORTH"}


def run(*command: str, timeout: int = 15) -> dict:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=timeout
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout.strip()[:25000],
            "stderr": result.stderr.strip()[:1000],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"exit_code": None, "stdout": "", "stderr": str(exc)}


def file_info(path: Path) -> dict:
    result = {"path": str(path), "is_symlink": path.is_symlink(),
              "exists": path.exists() or path.is_symlink()}
    if path.is_symlink():
        try:
            result["symlink_target"] = os.readlink(path)
        except OSError:
            pass
    if path.exists():
        try:
            stat = path.stat()
            result["bytes"] = stat.st_size
            result["is_dir"] = path.is_dir()
        except OSError:
            pass
    return result


def vmx_ids(provider: Path) -> list[dict]:
    root = provider / ".vagrant" / "machines"
    if not root.is_dir() or root.is_symlink():
        return []
    result = []
    for candidate in sorted(root.glob("*/vmware_desktop/id")):
        if candidate.is_symlink() or not candidate.is_file():
            continue
        try:
            vmx = candidate.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            vmx = ""
        if not vmx or not os.path.isabs(vmx):
            result.append({"machine": candidate.parts[-3], "id_file": str(candidate),
                           "vmx": vmx, "warning": "missing or non-absolute identity"})
            continue
        ref = Path(vmx)
        result.append({
            "machine": candidate.parts[-3], "id_file": str(candidate),
            "vmx": vmx, "vmx_exists": ref.is_file(),
            "vmx_parent": str(ref.parent),
            "warning": "symlinked VMX" if ref.is_symlink() else "",
        })
    return result


def instance_candidates(checkout: Path) -> list[dict]:
    workspace = checkout / "workspace"
    if not workspace.is_dir() or workspace.is_symlink():
        return []
    instances = []
    for folder in sorted(workspace.iterdir()):
        if not folder.is_dir() or folder.is_symlink():
            continue
        marker = folder / "instance.json"
        info = {}
        if marker.is_file() and not marker.is_symlink():
            try:
                info = json.loads(marker.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError):
                info = {"warning": "unreadable instance.json"}
        provider = folder / "provider"
        ids = vmx_ids(provider)
        instances.append({
            "instance": folder.name,
            "workspace": str(folder),
            "provider": str(provider),
            "metadata": {k: info.get(k) for k in (
                "lab", "provider", "provisioner", "ip_range", "status"
            ) if k in info},
            "vagrant_identities": ids,
            "candidate_for_cleanup": (
                info.get("lab") in OWNED_NAMES or
                folder.name == "6ca91b-north-vmware"
            ),
        })
    return instances


def available_checkouts(explicit: list[str]) -> list[str]:
    home = Path.home()
    candidates = [
        home / "kingdoms-course1-src",
        home / "Documents" / "GOAD_NOMAD",
        home / "workspace" / "GOAD_NOMAD",
        home / "workspace" / "Kingdoms",
    ] + [Path(p).expanduser() for p in explicit]
    result = []
    seen = set()
    for item in candidates:
        try:
            rp = item.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if not rp.is_dir() or rp in seen:
            continue
        if (rp / ".git").exists() or (rp / "workspace").exists():
            result.append(str(rp))
            seen.add(rp)
    return result


def systemd_units() -> dict:
    names = list(SERVICE_NAMES)
    found = run("systemctl", "list-unit-files", "--all", "--no-legend",
                "--no-pager", timeout=12)
    for line in found["stdout"].splitlines():
        parts = line.split()
        if not parts:
            continue
        name = parts[0]
        if (name.startswith(("kingdoms-", "goad-", "friday-", "nomad-"))
                and name not in names):
            names.append(name)
    return {
        "discovered": sorted(names),
        "unit_file_listing": found,
        "unit_states": {unit: run(
            "systemctl", "show", unit, "--no-pager",
            "--property=LoadState,ActiveState,SubState,FragmentPath,UnitFileState"
        ) for unit in sorted(names)},
    }


def filesystem_matches() -> list[dict]:
    # This is an exact-location inventory. Do not scan or delete $HOME broadly.
    home = Path.home()
    candidates = [
        Path("/usr/local/sbin/goad-nomad-vmnet-hostaddrs"),
        Path("/usr/local/sbin/kingdoms-north-vmnet-hostaddrs"),
        Path("/etc/vmware/goad-nomad-backups"),
        Path("/etc/vmware/networking"),
        Path("/etc/vmware/netmap.conf"),
        Path("/etc/systemd/system/goad-nomad-vmnet-hostaddrs.service"),
        Path("/etc/systemd/system/goad-nomad-vmnet-hostaddrs.timer"),
        Path("/etc/systemd/system/kingdoms-north-vmnet-hostaddrs.service"),
        Path("/etc/systemd/system/kingdoms-north-vmnet-hostaddrs.timer"),
        Path("/etc/systemd/system/kingdoms-phase03-rickon.service"),
        Path("/etc/systemd/system/kingdoms-rdp-bot.service"),
        home / ".local/state/kingdoms",
        home / ".goad",
    ]
    return [file_info(item) for item in candidates if item.exists() or item.is_symlink()]


def vmware_network_config() -> dict:
    path = Path("/etc/vmware/networking")
    evidence = {"path": str(path), "available": path.is_file()}
    if not path.is_file():
        return evidence
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        evidence["error"] = str(exc)
        return evidence
    per_net = {}
    pattern = re.compile(r"^answer\s+VNET_(\d+)_([A-Z0-9_]+)\s+(.*)$")
    for line in lines:
        m = pattern.match(line.strip())
        if m and int(m.group(1)) in NETWORK_IDS:
            per_net.setdefault("vmnet" + m.group(1), []).append(
                {"key": m.group(2), "value": m.group(3)}
            )
    evidence["target_network_settings"] = per_net
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", action="append", default=[],
                        help="Additional repository checkout to inspect")
    parser.add_argument("--output", type=Path,
                        help="Optional JSON report file; writes ONLY this file")
    args = parser.parse_args()
    checkouts = available_checkouts(args.checkout)
    report = {
        "purpose": "READ_ONLY_PRE_DELETION_OWNERSHIP_AUDIT",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "checkouts": checkouts,
        "workspace_instances": {
            checkout: instance_candidates(Path(checkout)) for checkout in checkouts
        },
        "vmware_running_vmx": run("vmrun", "-T", "ws", "list", timeout=20),
        "vmware_registered_vmx": run("vmrun", "-T", "ws", "listRegisteredVM", timeout=20),
        "vmware_network_config": vmware_network_config(),
        "host_ipv4_routes": run("ip", "-j", "-4", "route", "show", "table", "all"),
        "host_ipv4_addresses": run("ip", "-j", "-4", "addr", "show"),
        "host_interface_links": run("ip", "-j", "link", "show"),
        "systemd": systemd_units(),
        "known_helper_paths": filesystem_matches(),
        "kingdoms_related_processes": run(
            "pgrep", "-af", r"kingdoms|goad|responder|ntlmrelayx|mitm6|xfreerdp"
        ),
        "scheduled_jobs": run("systemctl", "list-timers", "--all", "--no-pager"),
        "network_firewall_rules": {
            "nft_ruleset": run("nft", "-a", "list", "ruleset", timeout=15),
            "iptables_save": run("iptables-save", timeout=15),
        },
        "vmware_network_service": run("systemctl", "show", "vmware.service",
                                      "--property=LoadState,ActiveState,SubState"),
        "safety_notes": [
            "THIS IS ONLY AN INVENTORY, NOT A CLEANUP",
            "A matching name is not proof of instance ownership",
            "Do not delete vmnet1/vmnet8, VMware itself, or unrelated instances",
            "Review all VMX owners, backups and services before destruction",
            "Keep main branch and the fresh Course 1 rebuild branch",
        ],
    }
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        target = args.output.expanduser()
        if target.is_symlink() or target.exists():
            parser.error("--output must be a NEW file (never overwrite evidence)")
        if not target.parent.is_dir():
            parser.error("output parent directory must already exist")
        with target.open("x", encoding="utf-8") as handle:
            handle.write(payload + "\n")
        print(f"Saved read-only audit: {target}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
