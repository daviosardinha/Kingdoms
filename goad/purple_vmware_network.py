"""Guarded additive vmnet40 bootstrap for the independent PURPLE VMware lab.

Only root may apply. Never modify NORTH's immutable owner/backup. The North
verifier accepts the added segment ONLY with a matching root-owned attestation.
No running VMware guests, network/VPN collisions, or preexisting vmnet40.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import pwd
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from goad.course1_vmnet_config import (
    _existing_network_metadata, verify_owned_vmnet_runtime,
)
from goad.course1_vmnet_journal import (
    exclusive_vmnet_lock, require_reconciled, record_journal,
)
from goad.course1_vmnet_transaction import _atomic_bytes, _plain_regular, _safe_directory

NETWORKING = Path("/etc/vmware/networking")
OWNER = Path("/etc/vmware/kingdoms-purple-owner.json")
NORTH_OWNER = Path("/etc/vmware/kingdoms-course1-owner.json")
BACKUPS = Path("/etc/vmware/kingdoms-course1-backups")
NETWORKS = Path("/usr/bin/vmware-networks")
VMNET = "vmnet40"
SUBNET = ipaddress.ip_network("192.168.240.0/24")
HOST_ADDRESS = "192.168.240.1"
FIELDS = {
    "DHCP": "no",
    "HOSTONLY_NETMASK": "255.255.255.0",
    "HOSTONLY_SUBNET": "192.168.240.0",
    "VIRTUAL_ADAPTER": "yes",
    "NAT": "no",
}
PREFIX = "answer VNET_40_"
MACS = frozenset((
    "00:50:56:10:40:30", "00:50:56:10:40:31",
    "00:50:56:10:40:32", "00:50:56:10:40:51",
))


class PurpleNetworkError(RuntimeError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _command(*args: str, timeout: int = 30) -> str:
    try:
        result = subprocess.run(args, text=True, capture_output=True,
                                check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PurpleNetworkError(f"Host command unavailable: {args[0]}") from exc
    if result.returncode != 0:
        raise PurpleNetworkError(
            f"{args[0]} exited {result.returncode}: "
            + (result.stderr.strip() or result.stdout.strip())[:220]
        )
    return result.stdout


def append_vmnet(original: str) -> str:
    """Add one dedicated host-only vmnet to an otherwise unmodified config."""
    occupied, ranges = _existing_network_metadata(original)
    if 40 in occupied or any(SUBNET.overlaps(x) for x in ranges):
        raise PurpleNetworkError("vmnet40/subnet already in VMware networking")
    if re.search(r"(?m)^\s*(?:answer\s+)?VNET_40_", original):
        raise PurpleNetworkError("Ambiguous vmnet40 declaration")
    lines = ["# PURPLE vmnet40: root-owned additive lab overlay"]
    lines += [f"{PREFIX}{key} {value}" for key, value in FIELDS.items()]
    lines.append(f"{PREFIX}HOSTONLY_HOSTADDR {HOST_ADDRESS}")
    return original.rstrip("\n") + "\n\n" + "\n".join(lines) + "\n"


def strip_checked_overlay(observed: bytes) -> bytes:
    """Return bytes without only known vmnet40 directives.

    Any unknown/duplicate/wrong vmnet40 setting fails; callers must run the
    original NORTH verifier on the stripped bytes, so other drift is rejected.
    """
    try:
        decoded = observed.decode("utf-8")
    except UnicodeError as exc:
        raise PurpleNetworkError("Invalid VMware networking encoding") from exc
    entries: dict[str, str] = {}
    remaining = []
    for line in decoded.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith(PREFIX):
            words = stripped.split()
            if len(words) != 3:
                raise PurpleNetworkError("Malformed vmnet40 declaration")
            key = words[1][len("VNET_40_"):]
            if key in entries:
                raise PurpleNetworkError("Duplicate vmnet40 field")
            entries[key] = words[2]
        elif re.match(r"(?i)^(?:answer\s+)?VNET_40_", stripped):
            raise PurpleNetworkError("Unknown vmnet40 declaration")
        else:
            remaining.append(line)
    for key, expected in FIELDS.items():
        if entries.get(key) != expected:
            raise PurpleNetworkError(f"vmnet40 {key} absent or changed")
    extra = set(entries) - set(FIELDS) - {"HOSTONLY_HOSTADDR"}
    if extra or (entries.get("HOSTONLY_HOSTADDR", HOST_ADDRESS) != HOST_ADDRESS):
        raise PurpleNetworkError("Unapproved vmnet40 configuration")
    return "".join(remaining).encode("utf-8")


def _owner_record(path: Path, uid: int = 0) -> tuple[dict, bytes]:
    meta = _plain_regular(path)
    if meta.st_uid != uid or stat.S_IMODE(meta.st_mode) != 0o600:
        raise PurpleNetworkError(f"Unsafe owner record: {path}")
    content = path.read_bytes()
    try:
        parsed = json.loads(content)
    except (ValueError, UnicodeError) as exc:
        raise PurpleNetworkError("Malformed owner record") from exc
    if not isinstance(parsed, dict):
        raise PurpleNetworkError("Owner record must be an object")
    return parsed, content


def authorized_strip(
    observed: bytes, north_owner_bytes: bytes, *, receipt: Path = OWNER,
    north_provider: str | None = None, uid: int = 0,
) -> bytes:
    """Allow only attested additive Purple VMnet, never generic foreign drift."""
    record, _ = _owner_record(Path(receipt), uid)
    if (set(record) != {"schema", "provider", "north_owner_sha256",
                        "network_before_sha256", "network_after_sha256",
                        "vmnet", "subnet", "backup"}
            or record["schema"] != "kingdoms.purple.vmnet.v1"
            or record["north_owner_sha256"] != _sha(north_owner_bytes)
            or record["vmnet"] != VMNET
            or record["subnet"] != str(SUBNET)
            or (north_provider is not None and record["provider"] != north_provider)
            or not isinstance(record["network_before_sha256"], str)
            or not isinstance(record["network_after_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", record["network_before_sha256"])
            or not re.fullmatch(r"[0-9a-f]{64}", record["network_after_sha256"])):
        raise PurpleNetworkError("Purple overlay attestation does not match NORTH")
    backup = Path(record["backup"])
    if (not backup.is_absolute() or backup.is_symlink()
            or not backup.is_file()
            or BACKUPS not in backup.parents
            or _sha(backup.read_bytes()) != record["network_before_sha256"]):
        raise PurpleNetworkError("Purple backup missing or checksum mismatch")
    return strip_checked_overlay(observed)


def _guard_host():
    if _command("vmrun", "-T", "ws", "list").strip() != "Total running VMs: 0":
        raise PurpleNetworkError("VMware guests still running")
    pgrep = subprocess.run(["pgrep", "-x", "vmware-vmx"], capture_output=True,
                           text=True, check=False, timeout=10)
    if pgrep.returncode != 1:
        raise PurpleNetworkError("VMware guest process active or cannot be inspected")
    if Path("/dev/vmnet40").exists():
        raise PurpleNetworkError("vmnet40 device already exists without ownership")
    if subprocess.run(["ip", "link", "show", "vmnet40"], capture_output=True,
                      check=False, timeout=10).returncode == 0:
        raise PurpleNetworkError("vmnet40 host interface already exists")
    # Prevent overlaps with *any* address or route, including connected VPNs.
    for arg in (("-j", "-4", "address", "show"), ("-j", "-4", "route", "show", "table", "all")):
        objects = json.loads(_command("ip", *arg))
        if not isinstance(objects, list):
            raise PurpleNetworkError("Cannot enumerate host network state")
        for obj in objects:
            nets = []
            if "addr_info" in obj:
                nets = [f"{a['local']}/{a['prefixlen']}"
                        for a in obj["addr_info"] if a.get("family") == "inet"]
            elif obj.get("dst") not in (None, "default"):
                nets = [obj["dst"]]
            for cidr in nets:
                if SUBNET.overlaps(ipaddress.ip_network(cidr, strict=False)):
                    raise PurpleNetworkError("Purple subnet overlaps host route/address")
    # Scan VMware-registered VMX files to fail closed on vnet or MAC reuse.
    user = os.environ.get("SUDO_USER")
    if not user or user == "root":
        raise PurpleNetworkError("Run via sudo from the desktop user")
    inventory = Path(pwd.getpwnam(user).pw_dir) / ".vmware" / "inventory.vmls"
    if inventory.is_symlink():
        raise PurpleNetworkError("Unsafe VMware inventory symlink")
    if inventory.exists():
        import re as regex
        for raw_path in regex.findall(r'(?m)^vmlist\d+\.config\s*=\s*"([^"]+)"', inventory.read_text()):
            vmx = Path(raw_path)
            if not vmx.is_file() or vmx.is_symlink():
                raise PurpleNetworkError("Cannot verify registered VMX")
            content = vmx.read_text(errors="replace").lower()
            if re.search(r'(?im)^\s*ethernet\d+\.vnet\s*=\s*"vmnet40"', content):
                raise PurpleNetworkError("Registered VM already uses vmnet40")
            if any(re.search(r'(?im)^\s*ethernet\d+\.(?:address|generatedaddress)\s*=\s*"' + mac + '"', content)
                   for mac in MACS):
                raise PurpleNetworkError("Registered VM already uses Purple MAC")


def _verify_live_overlay(after: bytes, previous: bytes):
    # The original config must remain valid under NORTH's existing narrow
    # Vagrant normalization allowances; no broad declaration changes allowed.
    from goad.kingdoms_topology import load_course1_topology
    verify_owned_vmnet_runtime(previous, strip_checked_overlay(after),
                               previous, load_course1_topology())
    address = _command("ip", "-o", "-4", "address", "show", "dev", VMNET)
    host = [part for part in address.split() if part.startswith("192.168.240.")]
    if not host or not any(ipaddress.ip_interface(a).ip in SUBNET for a in host):
        raise PurpleNetworkError("VMware did not assign a vmnet40 host address")
    _command("ip", "link", "show", VMNET)


def install(provider_dir: str):
    """Install additive vmnet40 under NORTH's existing global VMware lock."""
    if os.geteuid() != 0:
        raise PurpleNetworkError("Root privileges required")
    provider = Path(provider_dir)
    if not provider.is_absolute() or provider.is_symlink() or not provider.is_dir():
        raise PurpleNetworkError("Purple instance provider path missing")
    if not BACKUPS.is_dir():
        raise PurpleNetworkError("NORTH backup/lock directory unavailable")
    from goad.course1_host_network_apply import (
        inspect_installed_north, VMwareNetworkRestart, snapshot_netmap, NETMAP,
    )
    with exclusive_vmnet_lock(BACKUPS):
        require_reconciled(BACKUPS)
        if OWNER.exists() or OWNER.is_symlink():
            raise PurpleNetworkError("Purple network owner already exists")
        north, north_bytes = _owner_record(NORTH_OWNER)
        north_provider = north.get("provider")
        inspect_installed_north(north_provider)
        _guard_host()
        _safe_directory(NETWORKING.parent)
        meta = _plain_regular(NETWORKING)
        before = NETWORKING.read_bytes()
        proposal = append_vmnet(before.decode("utf-8")).encode("utf-8")
        prior_netmap, netmap_metadata = snapshot_netmap(NETMAP)
        backup_folder = Path(tempfile.mkdtemp(prefix="purple-", dir=BACKUPS))
        backup_folder.chmod(0o700)
        backup = backup_folder / "networking.original"
        with backup.open("xb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(before)
            handle.flush()
            os.fsync(handle.fileno())
        journal = {
            "state": "PREPARED", "provider": str(provider.resolve()),
            "baseline_sha256": _sha(before),
            "proposed_sha256": _sha(proposal), "backup": str(backup),
        }
        record_journal(backup_folder, journal)
        changed = False
        restart = VMwareNetworkRestart(NETMAP, prior_netmap, netmap_metadata)
        try:
            if before != NETWORKING.read_bytes():
                raise PurpleNetworkError("Networking changed after preflight")
            _atomic_bytes(NETWORKING, proposal, meta)
            changed = True
            journal["state"] = "WRITTEN"
            record_journal(backup_folder, journal)
            restart()
            journal["state"] = "VERIFYING"
            record_journal(backup_folder, journal)
            after = NETWORKING.read_bytes()
            _verify_live_overlay(after, before)
            if NORTH_OWNER.read_bytes() != north_bytes:
                raise PurpleNetworkError("NORTH owner changed during Purple bootstrap")
            receipt = {
                "schema": "kingdoms.purple.vmnet.v1",
                "provider": north_provider,
                "north_owner_sha256": _sha(north_bytes),
                "network_before_sha256": _sha(before),
                "network_after_sha256": _sha(after),
                "vmnet": VMNET, "subnet": str(SUBNET), "backup": str(backup),
            }
            with OWNER.open("x", encoding="utf-8") as handle:
                os.fchmod(handle.fileno(), 0o600)
                json.dump(receipt, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            journal["state"] = "COMMITTED"
            record_journal(backup_folder, journal)
            print("[PASS] vmnet40 created and NORTH immutable owner preserved")
        except Exception as error:
            if changed:
                # Never overwrite an unknown third-party modification.
                now = NETWORKING.read_bytes()
                try:
                    _verify_live_overlay(now, before)
                except Exception as drift:
                    journal["state"] = "MANUAL_RECONCILIATION"
                    record_journal(backup_folder, journal)
                    raise PurpleNetworkError(
                        f"Unsafe rollback due to observed network drift: {backup}"
                    ) from drift
                if OWNER.exists():
                    raise PurpleNetworkError("Purple owner created; manual reconciliation required") from error
                _atomic_bytes(NETWORKING, before, meta)
                try:
                    restart()
                except Exception as restart_error:
                    journal["state"] = "MANUAL_RECONCILIATION"
                    record_journal(backup_folder, journal)
                    raise PurpleNetworkError(
                        f"Rollback restart failed; backup: {backup}"
                    ) from restart_error
            journal["state"] = "ROLLED_BACK"
            record_journal(backup_folder, journal)
            raise PurpleNetworkError(f"Purple bootstrap failed; original restored: {backup}") from error


def check():
    north, raw = _owner_record(NORTH_OWNER)
    from goad.course1_host_network_apply import inspect_installed_north
    inspect_installed_north(north.get("provider"))
    authorized_strip(NETWORKING.read_bytes(), raw,
                     north_provider=north["provider"])
    print("[PASS] Purple vmnet40 ownership verified through NORTH")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("apply", "verify"))
    parser.add_argument("--provider-dir", default=None)
    args = parser.parse_args()
    try:
        if args.action == "apply":
            if not args.provider_dir:
                parser.error("apply requires --provider-dir")
            install(args.provider_dir)
        else:
            check()
    except (OSError, ValueError, PurpleNetworkError) as exc:
        parser.exit(1, f"[BLOCKED] Purple VMware networking: {exc}\n")


if __name__ == "__main__":
    main()
