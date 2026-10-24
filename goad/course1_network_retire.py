"""Owner-scoped retirement of a destroyed NORTH VMware instance.

Unlike the *installed* verifier, this does not require transient Vagrant NAT
management forwarding replacements to survive Vagrant destroy. A retirement
is permitted ONLY after the old five VMs have been destroyed, zero VMs are
running and no NAT forwarding declaration remains. Foreign vmnets and all
historical transaction journals remain untouched.

CLI: python3 -m goad.course1_network_retire plan|apply --provider-dir ABS_PATH
Both modes require explicit sudo. The plan is read-only.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

from goad.course1_host_network_apply import (
    NETWORKING, NETMAP, BACKUPS, OWNER, VMWARE_NETWORKS, asset_paths,
    _reconstruct_committed_vmnet, reviewed_nat_retirements, RETIRED_NAT,
)
from goad.course1_hostaddrs import SERVICE, TIMER, render_hostaddr_assets
from goad.course1_vmnet_config import verify_vmnet_config
from goad.course1_vmnet_journal import exclusive_vmnet_lock, inspect_vmnet_journals
from goad.course1_vmnet_transaction import _atomic_bytes, _plain_regular
from goad.kingdoms_topology import load_course1_topology


MACHINES = ("GOAD-ROUTER", "GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01")
MARKER = "# Kingdoms Course 1 managed networks (additive; source-only plan)"
DECLARATION = re.compile(r"^answer VNET_(10|20|99)_([A-Z0-9_]+) ")
COMMENT = re.compile(r"^# vmnet(10|20|99): (NORTH|SEVENKINGDOMS|MANAGEMENT)$")


class RetirementBlocked(RuntimeError):
    pass


def _host_command(*args, timeout=120, check=True):
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RetirementBlocked("Host command unavailable: " + args[0]) from exc
    if check and proc.returncode:
        raise RetirementBlocked(
            "Host command failed: " + " ".join(args) + ": " +
            (proc.stderr or proc.stdout).strip()[:400]
        )
    return proc


def _safe_regular(path, expected_uid, mode=None):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise RetirementBlocked(f"Missing or unsafe NORTH evidence: {path}")
    s = path.stat()
    if (not stat.S_ISREG(s.st_mode) or s.st_nlink != 1
            or s.st_uid != expected_uid or (s.st_mode & 0o022)
            or (mode is not None and stat.S_IMODE(s.st_mode) != mode)):
        raise RetirementBlocked(f"Unsafe ownership or permissions: {path}")
    return s


def _read_plan(provider, *, networking=NETWORKING, owner=OWNER,
               backups=BACKUPS, files=None, owner_uid=0):
    provider = Path(provider)
    if (not provider.is_absolute() or provider.is_symlink()
            or not provider.is_dir() or provider.resolve(strict=True) != provider
            or provider.name != "provider" or
            not re.fullmatch(r"[a-f0-9]{6}-north-vmware", provider.parent.name)):
        raise RetirementBlocked("Expected the exact original NORTH instance provider")
    _safe_regular(owner, owner_uid, 0o600)
    try:
        record = json.loads(Path(owner).read_text())
    except (OSError, ValueError) as exc:
        raise RetirementBlocked("Invalid NORTH ownership JSON") from exc
    layout = load_course1_topology()
    if (not isinstance(record, dict) or record.get("profile") != "NORTH"
            or record.get("provider") != str(provider)
            or record.get("network_base") != layout["network_base"]
            or record.get("vmnets") !=
               {name: seg["vmnet"] for name, seg in layout["segments"].items()}):
        raise RetirementBlocked("Immutable NORTH owner does not match this provider")

    backups = Path(backups)
    if backups.is_symlink() or not backups.is_dir():
        raise RetirementBlocked("Historical NORTH backup directory invalid")
    backup = Path(record.get("backup", ""))
    if (not backup.is_absolute() or backup.is_symlink()
            or backup.parent.is_symlink() or backup.parent.parent != backups):
        raise RetirementBlocked("NORTH original backup path is not owned")
    _safe_regular(backup, owner_uid, 0o600)
    original = backup.read_bytes()
    if hashlib.sha256(original).hexdigest() != record.get("baseline_sha256"):
        raise RetirementBlocked("NORTH original backup SHA mismatch")
    journals = inspect_vmnet_journals(backups)
    if any(entry["state"] not in ("COMMITTED", "ROLLED_BACK") for entry in journals):
        raise RetirementBlocked("Unresolved VMware transaction journal")
    commits = [
        x for x in journals if x["state"] == "COMMITTED"
        and x["provider"] == str(provider) and x["backup"] == str(backup)
        and x["baseline_sha256"] == record["baseline_sha256"]
    ]
    if len(commits) != 1:
        raise RetirementBlocked("No unique committed journal for this NORTH owner")
    _reconstruct_committed_vmnet(record, original, layout)
    receipt = Path(owner).parent / RETIRED_NAT.name
    if receipt.exists() or receipt.is_symlink():
        retired = reviewed_nat_retirements(
            str(provider), original, source=receipt, owner_uid=owner_uid
        )
        if not retired:
            raise RetirementBlocked("Retired NAT receipt is not valid")
        for declaration in retired:
            if original.decode("utf-8").splitlines().count(declaration) != 1:
                raise RetirementBlocked("Retired NAT receipt lacks an exact original rule")
    else:
        retired = frozenset()

    netpath = Path(networking)
    meta = _safe_regular(netpath, owner_uid)
    current = netpath.read_bytes()
    try:
        text = current.decode("utf-8")
        verify_vmnet_config(text, layout)
    except (UnicodeError, ValueError) as exc:
        raise RetirementBlocked("NORTH vmnet topology is inconsistent") from exc

    # A destroyed and fully retired Vagrant generation should not have ANY
    # vmnet8 port forwards, not merely a formerly approved number of ports.
    if any(line.strip().startswith("add_nat_portfwd ") for line in text.splitlines()):
        raise RetirementBlocked("NAT forwards still exist; inspect foreign ownership first")

    owned_keys = {}
    expected = {}
    for zone in layout["segments"].values():
        index = int(zone["vmnet"][5:])
        expected[index] = {
            "DHCP", "HOSTONLY_NETMASK", "HOSTONLY_SUBNET",
            "VIRTUAL_ADAPTER", "NAT"
        }
        if zone["host_address"]:
            expected[index].add("HOSTONLY_HOSTADDR")
    keep = []
    removed = []
    for line in text.splitlines(keepends=True):
        clean = line.rstrip("\r\n")
        m = re.match(r"^answer VNET_(10|20|99)_([A-Z0-9_]+) (\S+)$", clean)
        if m:
            index, key = int(m.group(1)), m.group(2)
            if key not in expected[index]:
                raise RetirementBlocked("Unknown NORTH vmnet declaration: " + clean)
            if key in owned_keys.setdefault(index, set()):
                raise RetirementBlocked("Duplicate NORTH vmnet declaration: " + clean)
            owned_keys[index].add(key)
            removed.append(clean)
        elif clean == MARKER or COMMENT.fullmatch(clean):
            removed.append(clean)
        else:
            if re.match(r"^\s*(?:answer\s+)?VNET_(10|20|99)_", clean):
                raise RetirementBlocked("Unrecognized NORTH vmnet syntax: " + clean)
            keep.append(line)
    for number in expected:
        keys = owned_keys.get(number, set())
        # VMware may remove either optional .254 HOSTONLY_HOSTADDR line.
        mandatory = expected[number] - {"HOSTONLY_HOSTADDR"}
        if not mandatory <= keys or keys - expected[number]:
            raise RetirementBlocked(f"Missing or extra NORTH vmnet{number} settings")
    if len(removed) < 15:
        raise RetirementBlocked("Incomplete NORTH vmnet declaration removal")
    clean_config = "".join(keep).encode("utf-8")
    if not clean_config.strip():
        raise RetirementBlocked("Refusing to erase VMware's foreign configuration")
    if any(re.match(rb"\s*answer VNET_(10|20|99)_", line)
           for line in clean_config.splitlines()):
        raise RetirementBlocked("NORTH network declaration survived retirement plan")

    files = asset_paths() if files is None else files
    expected_assets = render_hostaddr_assets(layout)
    if set(files) != set(expected_assets):
        raise RetirementBlocked("NORTH host-address asset set differs from source")
    for name, path in files.items():
        _safe_regular(path, owner_uid)
        if Path(path).read_bytes() != expected_assets[name].encode():
            raise RetirementBlocked("NORTH host asset content drift: " + name)

    for machine in MACHINES:
        registry = (provider / ".vagrant" / "machines" / machine /
                    "vmware_desktop" / "id")
        if registry.exists() or registry.is_symlink():
            raise RetirementBlocked("NORTH Vagrant guest still registered: " + machine)

    return {
        "owner": Path(owner), "provider": provider, "networking": netpath,
        "backup_root": backups, "old_config": current, "new_config": clean_config,
        "network_meta": meta, "files": {name: Path(p) for name, p in files.items()},
        "removed": removed, "layout": layout, "retired_nat_receipt": receipt if retired else None
    }


def _ensure_host_offline():
    running = _host_command("vmrun", "-T", "ws", "list").stdout.strip()
    if running != "Total running VMs: 0":
        raise RetirementBlocked("VMware has running guests or ambiguous inventory")
    for process in ("vmware-vmx", "vmware"):
        proc = _host_command("pgrep", "-x", process, check=False)
        if proc.returncode != 1:
            raise RetirementBlocked(f"VMware process active or cannot be inspected: {process}")


def _foreign_network_manifest(raw):
    """VMware may rotate DHCP hashes and order, but not foreign vmnet settings."""
    items = Counter()
    for line in raw.decode("utf-8").splitlines():
        words = line.split()
        if len(words) != 3 or words[0] != "answer":
            continue
        m = re.fullmatch(r"VNET_(\\d+)_([A-Z0-9_]+)", words[1])
        if m and int(m.group(1)) not in (10, 20, 99):
            if m.group(2) == "DHCP_CFG_HASH":
                continue
            items[" ".join(words)] += 1
    return items


def _verify_interfaces_removed():
    for vmnet in ("vmnet10", "vmnet20", "vmnet99"):
        proc = _host_command("ip", "link", "show", "dev", vmnet, check=False)
        if proc.returncode == 0:
            raise RetirementBlocked(f"VMware retained retired interface {vmnet}")
    current = Path(NETWORKING).read_text()
    if any(re.match(r"^answer VNET_(10|20|99)_", line)
           for line in current.splitlines()):
        raise RetirementBlocked("Retired NORTH vmnet settings regenerated")
    if any(line.startswith("add_nat_portfwd ") for line in current.splitlines()):
        raise RetirementBlocked("VMware regenerated retired NAT management ports")


def plan(provider):
    if os.geteuid() != 0:
        raise RetirementBlocked("Explicit sudo required")
    with exclusive_vmnet_lock(BACKUPS):
        _ensure_host_offline()
        inspection = _read_plan(provider)
        timer = _host_command("systemctl", "is-enabled", TIMER, check=False)
        if timer.returncode or timer.stdout.strip() != "enabled":
            raise RetirementBlocked("Original NORTH timer is not enabled")
        print("[PASS] NORTH_RETIREMENT_OWNER_BACKUP_JOURNAL")
        print("[PASS] ZERO_GUESTS_AND_ZERO_NAT_FORWARDING")
        print(f"[PASS] NORTH_HOST_ASSETS_AND_{len(inspection['removed'])}_REMOVABLE_LINES")
        print("REMOVED_VMNets=vmnet10,vmnet20,vmnet99")
        print("[PASS] NORTH_RETIREMENT_PLAN_READY")


def apply(provider):
    if os.geteuid() != 0:
        raise RetirementBlocked("Explicit sudo required")
    with exclusive_vmnet_lock(BACKUPS):
        _ensure_host_offline()
        data = _read_plan(provider)
        if _host_command("systemctl", "is-enabled", TIMER, check=False).stdout.strip() != "enabled":
            raise RetirementBlocked("NORTH timer must be enabled before cleanup")
        if not Path(VMWARE_NETWORKS).is_file():
            raise RetirementBlocked("VMware networks executable unavailable")
        folder = Path(tempfile.mkdtemp(prefix="retire-north-", dir=BACKUPS))
        os.chmod(folder, 0o700)
        for name, source in (("networking.before", data["networking"]),
                             ("owner.original.json", data["owner"])):
            dest = folder / name
            with dest.open("xb") as f:
                os.fchmod(f.fileno(), 0o600)
                f.write(source.read_bytes())
                f.flush()
                os.fsync(f.fileno())
        old = data["old_config"]
        expected_foreign = _foreign_network_manifest(old)
        netmap = Path(NETMAP)
        if netmap.is_symlink():
            raise RetirementBlocked("Unsafe VMware netmap symlink")
        old_netmap = netmap.read_bytes() if netmap.exists() else None
        if old_netmap is not None:
            _safe_regular(netmap, 0)
            dest = folder / "netmap.before"
            with dest.open("xb") as f:
                os.fchmod(f.fileno(), 0o600)
                f.write(old_netmap)
                f.flush()
                os.fsync(f.fileno())
        had_vmnet2 = _host_command(
            "ip", "link", "show", "dev", "vmnet2", check=False
        ).returncode == 0
        archived = []
        owner_retired = False
        changed = False
        timer_disabled = False
        try:
            _host_command("systemctl", "disable", "--now", TIMER)
            timer_disabled = True
            _host_command("systemctl", "stop", SERVICE, check=False)
            for unit in (TIMER, SERVICE):
                if _host_command("systemctl", "is-active", unit, check=False).stdout.strip() == "active":
                    raise RetirementBlocked("NORTH address service remained active: " + unit)
            _host_command(str(VMWARE_NETWORKS), "--stop")
            if data["networking"].read_bytes() != old:
                raise RetirementBlocked("VMware rewrote network settings during stop")
            _atomic_bytes(data["networking"], data["new_config"], data["network_meta"])
            changed = True
            _host_command(str(VMWARE_NETWORKS), "--start")
            _verify_interfaces_removed()
            if _foreign_network_manifest(data["networking"].read_bytes()) != expected_foreign:
                raise RetirementBlocked("VMware altered foreign vmnet declarations")
            if had_vmnet2 and _host_command(
                    "ip", "link", "show", "dev", "vmnet2", check=False
            ).returncode != 0:
                raise RetirementBlocked("Foreign vmnet2 disappeared during retirement")

            # Preserve original assets in the protected historical evidence
            # folder rather than unlinking them irreversibly.
            for name, source in data["files"].items():
                if source.read_bytes() != render_hostaddr_assets(data["layout"])[name].encode():
                    raise RetirementBlocked("NORTH asset changed during retirement")
                destination = folder / ("asset." + name)
                source.rename(destination)
                archived.append((source, destination))
            _host_command("systemctl", "daemon-reload")
            if data["retired_nat_receipt"] is not None:
                receipt = data["retired_nat_receipt"]
                reviewed_nat_retirements(
                    str(data["provider"]), Path(json.loads(data["owner"].read_text())["backup"]).read_bytes(),
                    source=receipt, owner_uid=0,
                )
                retired_archive = folder / "retired-nat-receipt.json"
                receipt.rename(retired_archive)
                archived.append((receipt, retired_archive))
            if data["owner"].read_bytes() != (folder / "owner.original.json").read_bytes():
                raise RetirementBlocked("NORTH owner changed during retirement")
            data["owner"].rename(folder / "owner.retired.json")
            owner_retired = True
            print("[PASS] NORTH_OWNED_NETWORKS_RETIRED")
            print("[PASS] NORTH_HOST_ASSETS_ARCHIVED")
            print("[PASS] NORTH_OWNER_ARCHIVED")
            print("[EVIDENCE]", folder)
            return
        except Exception as exc:
            errors = []
            if owner_retired:
                try:
                    (folder / "owner.retired.json").rename(data["owner"])
                except OSError as e:
                    errors.append(f"owner rollback: {e}")
            for dest, archived_path in reversed(archived):
                try:
                    archived_path.rename(dest)
                except OSError as e:
                    errors.append(f"asset rollback: {e}")
            if changed:
                try:
                    _atomic_bytes(data["networking"], old, data["network_meta"])
                    _host_command(str(VMWARE_NETWORKS), "--start")
                except Exception as e:
                    errors.append(f"VMware rollback: {e}")
            else:
                try:
                    _host_command(str(VMWARE_NETWORKS), "--start")
                except Exception as e:
                    errors.append(f"VMware restart: {e}")
            if timer_disabled:
                try:
                    _host_command("systemctl", "daemon-reload")
                    _host_command("systemctl", "enable", "--now", TIMER)
                except Exception as e:
                    errors.append(f"timer rollback: {e}")
            if errors:
                raise RetirementBlocked(
                    "MANUAL RECOVERY REQUIRED; saved evidence at " + str(folder) +
                    "; rollback errors: " + "; ".join(errors)
                ) from exc
            raise RetirementBlocked(
                "NORTH retirement aborted and prior assets restored: " + str(exc)
            ) from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "apply"))
    parser.add_argument("--provider-dir", required=True)
    args = parser.parse_args()
    try:
        (plan if args.action == "plan" else apply)(args.provider_dir)
    except (RetirementBlocked, OSError, ValueError) as exc:
        parser.exit(1, "[BLOCKED] NORTH retirement: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
