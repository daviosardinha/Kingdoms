"""NORTH-only, fail-closed VMware offline owner release.

The old five VMX files and Vagrant identities are NEVER modified. The reviewed
manifest is bound to the owner, immutable baseline, source-derived assets and
the EXACT thirteen Vagrant NAT rules, not to an arbitrary host-wide reset.

Only use the mutating entrypoint after a successful source gate and a deliberate
operator handoff (five guests stopped, removed from Workstation Library, never
deleted from disk). All modifying operations run under the existing vmnet lock.
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
import tempfile

from goad.course1_host_network_apply import (
    BACKUPS, NETMAP, NETWORKING, OWNER, VMWARE_NETWORKS, NorthSetupError,
    VMwareNetworkRestart, asset_paths, operator_inventory, require_explicit_root,
    run_command, snapshot_netmap, systemd_activate, systemd_reload,
)
from goad.course1_hostaddrs import SERVICE, TIMER, render_hostaddr_assets
from goad.course1_network_preflight import inactive_vmware, inspect_live as inspect_clean_host
from goad.course1_offline_handoff import (
    HandoffPlanError, expected_guest_vmx, inventory_state, plan, regular_file,
)
from goad.course1_vmnet_journal import exclusive_vmnet_lock, require_reconciled
from goad.course1_vmnet_transaction import (
    _atomic_bytes, _plain_regular, _safe_directory,
)
from goad.kingdoms_topology import load_course1_topology


class NorthReleaseError(RuntimeError):
    pass


# Reviewed exact Vagrant TCP forwards for THIS preserved NORTH instance only.
# Ports/IPs are not inferred from arbitrary VM guests.
NORTH_NAT = (
    "add_nat_portfwd 8 tcp 2200 192.168.213.133 22",
    "add_nat_portfwd 8 tcp 2201 192.168.213.134 5985",
    "add_nat_portfwd 8 tcp 2202 192.168.213.134 5986",
    "add_nat_portfwd 8 tcp 2203 192.168.213.134 22",
    "add_nat_portfwd 8 tcp 2204 192.168.213.135 5985",
    "add_nat_portfwd 8 tcp 2205 192.168.213.135 5986",
    "add_nat_portfwd 8 tcp 2206 192.168.213.135 22",
    "add_nat_portfwd 8 tcp 2207 192.168.213.136 5985",
    "add_nat_portfwd 8 tcp 2208 192.168.213.136 5986",
    "add_nat_portfwd 8 tcp 2209 192.168.213.136 22",
    "add_nat_portfwd 8 tcp 2222 192.168.213.132 22",
    "add_nat_portfwd 8 tcp 55985 192.168.213.133 5985",
    "add_nat_portfwd 8 tcp 55986 192.168.213.133 5986",
)

# Only the three NORTH vmnets; vmnet1/8/30 and all foreign lines are protected.
NORTH_DECLS = (
    "answer VNET_10_DHCP no",
    "answer VNET_10_HOSTONLY_NETMASK 255.255.255.0",
    "answer VNET_10_HOSTONLY_SUBNET 10.4.10.0",
    "answer VNET_10_VIRTUAL_ADAPTER yes",
    "answer VNET_10_NAT no",
    "answer VNET_20_DHCP no",
    "answer VNET_20_HOSTONLY_NETMASK 255.255.255.0",
    "answer VNET_20_HOSTONLY_SUBNET 10.4.20.0",
    "answer VNET_20_VIRTUAL_ADAPTER no",
    "answer VNET_20_NAT no",
    "answer VNET_99_DHCP no",
    "answer VNET_99_HOSTONLY_NETMASK 255.255.255.0",
    "answer VNET_99_HOSTONLY_SUBNET 10.4.99.0",
    "answer VNET_99_VIRTUAL_ADAPTER yes",
    "answer VNET_99_NAT no",
)
OWNED_LABELS = (
    "# Kingdoms Course 1 managed networks (additive; source-only plan)",
    "# vmnet10: NORTH",
    "# vmnet20: SEVENKINGDOMS",
    "# vmnet99: MANAGEMENT",
)
OWNED_ID = re.compile(rb"\bVNET_(10|20|99)_", re.I)


EXPECTED_PORTS = {
    "GOAD-DC01": {(22, 2200), (5985, 55985), (5986, 55986)},
    "GOAD-DC02": {(22, 2203), (5985, 2201), (5986, 2202)},
    "GOAD-SRV02": {(22, 2206), (5985, 2204), (5986, 2205)},
    "GOAD-WS01": {(22, 2209), (5985, 2207), (5986, 2208)},
    "GOAD-ROUTER": {(22, 2222)},
}
PORT_MAP = re.compile(r"(?m)^\s*(\d+)\s*\(guest\)\s*=>\s*(\d+)\s*\(host\)\s*$")


def verify_vagrant_ports(provider: Path) -> dict:
    """Read-only Vagrant port provenance BEFORE Workstation library removal."""
    import pwd
    import subprocess
    user = os.environ.get("SUDO_USER")
    if not user or user == "root":
        raise NorthReleaseError("Review Vagrant port mappings via sudo from Kali user")
    pwd.getpwnam(user)
    proof = {}
    for vm, expected in EXPECTED_PORTS.items():
        try:
            result = subprocess.run(
                ("runuser", "-u", user, "--", "vagrant", "port", vm),
                cwd=provider, capture_output=True, text=True, timeout=30, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise NorthReleaseError("Vagrant port proof is unavailable for " + vm) from exc
        if result.returncode:
            raise NorthReleaseError("Cannot verify Vagrant ports for " + vm)
        ports = [(int(guest), int(host))
                 for guest, host in PORT_MAP.findall(result.stdout)]
        if len(ports) != len(expected) or set(ports) != expected:
            raise NorthReleaseError("Unexpected/duplicate Vagrant forwarded ports for " + vm)
        proof[vm] = sorted(ports)
    if sum(map(len, proof.values())) != 13:
        raise NorthReleaseError("Expected exactly thirteen verified NORTH port mappings")
    return proof




def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def nat_lines(blob: bytes) -> Counter:
    return Counter(line.strip().decode("utf-8") for line in blob.splitlines()
                   if line.strip().startswith(b"add_nat_portfwd "))


def release_candidate(current: bytes, baseline: bytes) -> bytes:
    """Compare NAT delta with immutable baseline, then delete exact NORTH lines.

    Never remove NAT rules that were already present before NORTH, even when
    the current guest happens to use an overlapping port. Unknown changes fail.
    Preserve all foreign bytes, ordering and whitespace.
    """
    if not current or not baseline:
        raise NorthReleaseError("VMware config or immutable baseline is empty")
    old, now = nat_lines(baseline), nat_lines(current)
    if old - now:
        raise NorthReleaseError("A pre-NORTH NAT forward was removed; review ownership")
    if now - old != Counter(NORTH_NAT):
        raise NorthReleaseError("Live NAT delta does not match all 13 reviewed NORTH forwards")
    # Identical pre-existing forwards cannot be attributed safely to NORTH.
    if any(old[forward] for forward in NORTH_NAT):
        raise NorthReleaseError("Existing baseline forward overlaps NORTH; ownership ambiguous")
    # nat_lines() strips surrounding whitespace. Use the same canonicalization
    # when selecting lines for removal or we can leave a forward in place and
    # falsely report that a foreign NAT rule would be changed.
    expected_nat = Counter(NORTH_NAT)
    removed_nat = Counter()
    expected = Counter(s.encode("utf-8") for s in NORTH_DECLS)
    labels = set(s.encode("utf-8") for s in OWNED_LABELS)
    seen = Counter()
    retained = []
    for line in current.splitlines(keepends=True):
        stripped = line.rstrip(b"\r\n")
        if stripped in labels:
            continue
        if stripped in expected:
            seen[stripped] += 1
            continue
        if OWNED_ID.search(stripped):
            raise NorthReleaseError("Unknown or altered NORTH vmnet declaration")
        normalized = line.strip().decode("utf-8")
        if normalized in expected_nat and removed_nat[normalized] < expected_nat[normalized]:
            removed_nat[normalized] += 1
            continue
        retained.append(line)
    if removed_nat != expected_nat:
        raise NorthReleaseError("NORTH NAT forward removal count mismatch")
    if seen != expected:
        raise NorthReleaseError("NORTH vmnet declarations missing, duplicated or changed")
    result = b"".join(retained)
    if nat_lines(result) != old:
        raise NorthReleaseError("Candidate would alter a foreign NAT forward")
    if any(OWNED_ID.search(line) for line in result.splitlines()):
        raise NorthReleaseError("Candidate retains a NORTH vmnet declaration")
    if result == current:
        raise NorthReleaseError("Nothing selected for release")
    return result


def _read_assets(layout, paths, owner_uid):
    expected = render_hostaddr_assets(layout)
    if set(paths) != set(expected):
        raise NorthReleaseError("Incomplete NORTH-owned host-address assets")
    data = {}
    for kind, dest in paths.items():
        dest = Path(dest)
        metadata = _plain_regular(dest)
        expected_mode = 0o755 if kind == "helper" else 0o644
        if metadata.st_uid != owner_uid or stat.S_IMODE(metadata.st_mode) != expected_mode:
            raise NorthReleaseError("Unexpected NORTH asset owner or mode: " + kind)
        blob = dest.read_bytes()
        if blob != expected[kind].encode("utf-8"):
            raise NorthReleaseError("NORTH asset bytes differ from topology: " + kind)
        data[kind] = blob
    return data


def manifest(provider, inventory, networking=NETWORKING, owner=OWNER,
             expect="registered", owner_uid=0):
    """Read-only. Both registered and unregistered states yield the SAME hash."""
    provider, inventory = Path(provider), Path(inventory)
    state = plan(provider, inventory, expect)
    if expect == "registered":
        verify_vagrant_ports(provider)
    if state["vm_count"] != 5:
        raise NorthReleaseError("Expected five preserved NORTH VMs")
    config = Path(networking)
    _plain_regular(config)
    owner_file = Path(owner)
    _plain_regular(owner_file)
    original_owner = owner_file.read_bytes()
    record = json.loads(original_owner.decode("utf-8"))
    backup = Path(record["backup"])
    _plain_regular(backup)
    baseline = backup.read_bytes()
    current = config.read_bytes()
    proposed = release_candidate(current, baseline)
    layout = load_course1_topology()
    if sorted(int(z["vmnet"][5:]) for z in layout["segments"].values()) != [10, 20, 99]:
        raise NorthReleaseError("The NORTH topology no longer matches reviewed vmnets")
    assets = _read_assets(layout, asset_paths(), owner_uid)
    facts = {
        "schema": "kingdoms.north.offline-release.v1",
        "provider": state["provider"],
        "vm_count": 5,
        "vmx": state["vmx"],
        "baseline_sha256": digest(baseline),
        "owner_sha256": digest(original_owner),
        "networking_before_sha256": digest(current),
        "networking_candidate_sha256": digest(proposed),
        "nat_rules": list(NORTH_NAT),
        "vmnet_declarations": list(NORTH_DECLS),
        "hostaddr_asset_sha256": {key: digest(value) for key, value in assets.items()},
    }
    manifest_sha256 = digest(json.dumps(
        facts, sort_keys=True, separators=(",", ":")
    ).encode("utf-8"))
    return {**facts, "reviewed_sha256": manifest_sha256,
            "inventory_state": expect,
            "inventory_references": state["inventory_reference_count"],
            "release_authorized": False}


def _fsync_dir(path: Path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _durable_copy(directory: Path, name: str, data: bytes):
    target = directory / name
    with target.open("xb") as file:
        os.fchmod(file.fileno(), 0o600)
        file.write(data)
        file.flush()
        os.fsync(file.fileno())
    _fsync_dir(directory)
    return target


def _stage_journal(folder: Path, stage: dict):
    target = folder / "release.json"
    payload = (json.dumps(stage, sort_keys=True, indent=2) + "\n").encode()
    if not target.exists():
        _durable_copy(folder, "release.json", payload)
    else:
        _atomic_bytes(target, payload, _plain_regular(target))


def _verify_no_running_vmware():
    """Global restart must not disturb ANY active VMware Workstation VM."""
    inactive_vmware()


def _timer_stopped():
    import subprocess
    for cmd in (("systemctl", "is-active", TIMER),
                ("systemctl", "is-enabled", TIMER)):
        run = subprocess.run(cmd, capture_output=True, text=True, timeout=12, check=False)
        if run.returncode == 0:
            raise NorthReleaseError("NORTH host-address timer is still active/enabled")


def _disable_timer():
    run_command("systemctl", "disable", "--now", TIMER)
    run_command("systemctl", "stop", SERVICE)
    _timer_stopped()


def _remove_exact_assets(expected, paths):
    for kind, path in paths.items():
        path = Path(path)
        if path.is_symlink() or not path.is_file() or path.read_bytes() != expected[kind]:
            raise NorthReleaseError("NORTH asset changed during release: " + kind)
    for path in paths.values():
        Path(path).unlink()
    systemd_reload()


def _restore_exact_assets(expected, paths):
    for kind, path in paths.items():
        path = Path(path)
        if path.is_symlink():
            raise NorthReleaseError("Unsafe NORTH asset symlink during rollback")
        if path.exists():
            if path.read_bytes() != expected[kind]:
                raise NorthReleaseError("NORTH asset was replaced during rollback")
            continue
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as file:
            os.fchmod(file.fileno(), 0o755 if kind == "helper" else 0o644)
            file.write(expected[kind])
            file.flush()
            os.fsync(file.fileno())
    systemd_reload()


def _verify_network_after_release(networking: Path, candidate: bytes,
                                  original_nat: Counter):
    observed = networking.read_bytes()
    if observed != candidate:
        raise NorthReleaseError("VMware changed network bytes outside exact release candidate")
    if nat_lines(observed) != original_nat:
        raise NorthReleaseError("Foreign NAT forwards drifted during release")
    if any(OWNED_ID.search(line) for line in observed.splitlines()):
        raise NorthReleaseError("NORTH vmnet declaration survived release")


def _run_locked(provider, inventory, reviewed_sha256, networking, owner, backups,
                netmap, vmware_networks):
    """Caller holds the global vmnet lock."""
    require_reconciled(backups)
    _verify_no_running_vmware()
    verified = manifest(provider, inventory, networking, owner, expect="unregistered")
    if verified["reviewed_sha256"] != reviewed_sha256:
        raise NorthReleaseError("Review checksum or VMware configuration changed")
    _safe_directory(networking.parent)
    _safe_directory(owner.parent)
    _safe_directory(backups)
    original_meta = _plain_regular(networking)
    original = networking.read_bytes()
    owner_bytes = owner.read_bytes()
    record = json.loads(owner_bytes.decode("utf-8"))
    baseline = Path(record["backup"]).read_bytes()
    candidate = release_candidate(original, baseline)
    original_nat = nat_lines(baseline)
    paths = asset_paths()
    assets = _read_assets(load_course1_topology(), paths, 0)
    netmap_bytes, netmap_meta = snapshot_netmap(netmap)
    folder = Path(tempfile.mkdtemp(prefix="release-", dir=backups))
    os.chmod(folder, 0o700)
    backups_to_make = {"networking.original": original, "owner.original": owner_bytes}
    if netmap_bytes is not None:
        backups_to_make["netmap.original"] = netmap_bytes
    backups_to_make.update({"asset-" + kind: val for kind, val in assets.items()})
    for name, blob in backups_to_make.items():
        _durable_copy(folder, name, blob)
    journal = {
        "schema": "kingdoms.north.offline-release.v1",
        "state": "PREPARED",
        "provider": str(provider),
        "reviewed_sha256": reviewed_sha256,
        "networking_before_sha256": digest(original),
        "networking_candidate_sha256": digest(candidate),
        "backup_folder": str(folder),
    }
    _stage_journal(folder, journal)
    timer_disabled = False
    wrote_network = False
    owner_parked = False
    retired_owner = folder / "owner.retired"
    restart = VMwareNetworkRestart(netmap, netmap_bytes, netmap_meta, vmware_networks)
    try:
        if networking.read_bytes() != original or owner.read_bytes() != owner_bytes:
            raise NorthReleaseError("NORTH owner/networking changed during durable backup")
        _verify_no_running_vmware()
        _disable_timer()
        timer_disabled = True
        _atomic_bytes(networking, candidate, original_meta)
        wrote_network = True
        journal["state"] = "WRITTEN"
        _stage_journal(folder, journal)
        _verify_no_running_vmware()
        restart()
        journal["state"] = "VERIFYING"
        _stage_journal(folder, journal)
        _verify_network_after_release(networking, candidate, original_nat)
        # Prove the released NICs, routes, MACs and vmnet IDs are unused.
        inspect_clean_host(networking=networking, library=inventory)
        _remove_exact_assets(assets, paths)
        _verify_no_running_vmware()
        if owner.is_symlink() or owner.read_bytes() != owner_bytes:
            raise NorthReleaseError("NORTH owner changed before final release")
        # Ownership is relinquished LAST, after runtime and asset checks.
        os.replace(owner, retired_owner)
        _fsync_dir(owner.parent)
        _fsync_dir(folder)
        owner_parked = True
        journal["state"] = "COMMITTED_RELEASE"
        _stage_journal(folder, journal)
        return {"result": "COMMITTED_RELEASE", "release_backup": str(folder),
                "reviewed_sha256": reviewed_sha256, "preserved_vm_count": 5}
    except Exception as cause:
        try:
            if owner_parked:
                if owner.exists() or owner.is_symlink() or retired_owner.read_bytes() != owner_bytes:
                    raise NorthReleaseError("Owner changed after retirement; manual reconciliation")
                os.replace(retired_owner, owner)
                _fsync_dir(owner.parent)
                _fsync_dir(folder)
            if wrote_network:
                # Never restart VMware networking underneath a newly started guest.
                _verify_no_running_vmware()
                # A concurrent admin edit must NEVER be overwritten, even to rollback.
                if networking.read_bytes() != candidate:
                    raise NorthReleaseError("Concurrent VMware networking drift; manual reconciliation")
                _atomic_bytes(networking, original, original_meta)
                _verify_no_running_vmware()
                restart()
                if networking.read_bytes() != original:
                    raise NorthReleaseError("VMware networking rollback did not restore original bytes")
            if timer_disabled:
                _restore_exact_assets(assets, paths)
                systemd_activate()
            journal["state"] = "ROLLED_BACK"
            _stage_journal(folder, journal)
        except Exception as rollback_exc:
            journal["state"] = "MANUAL_RECONCILIATION"
            _stage_journal(folder, journal)
            raise NorthReleaseError(
                "NORTH release needs manual reconciliation; recovery copy at " + str(folder)
            ) from rollback_exc
        raise NorthReleaseError(
            "NORTH release failed and was rolled back; recovery at " + str(folder)
        ) from cause


def release(provider, inventory, reviewed_sha256, networking=NETWORKING,
            owner=OWNER, backups=BACKUPS, netmap=NETMAP,
            vmware_networks=VMWARE_NETWORKS):
    require_explicit_root()
    if not re.fullmatch(r"[a-f0-9]{64}", reviewed_sha256 or ""):
        raise NorthReleaseError("Supply the previously reviewed 64-character manifest SHA")
    provider, inventory, networking, owner = map(
        Path, (provider, inventory, networking, owner)
    )
    backups, netmap, vmware_networks = map(Path, (backups, netmap, vmware_networks))
    if not vmware_networks.is_file() or not os.access(vmware_networks, os.X_OK):
        raise NorthReleaseError("VMware networking service executable is unavailable")
    # Read-only first gate. The source of truth is the recheck INSIDE the lock.
    _verify_no_running_vmware()
    if manifest(provider, inventory, networking, owner, expect="unregistered")["reviewed_sha256"] != reviewed_sha256:
        raise NorthReleaseError("Manifest is stale or ownership has changed")
    with exclusive_vmnet_lock(backups):
        return _run_locked(provider, inventory, reviewed_sha256, networking,
                           owner, backups, netmap, vmware_networks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-dir", required=True)
    parser.add_argument("--reviewed-sha256",
                        help="Previously recorded release-plan reviewed_sha256")
    parser.add_argument("--apply", action="store_true",
                        help="OFFLINE HOST MUTATION. Five VMs must be unregistered")
    args = parser.parse_args()
    try:
        require_explicit_root()
        provider = Path(args.provider_dir)
        inventory = operator_inventory()
        if args.apply:
            if not args.reviewed_sha256:
                raise NorthReleaseError("No matching review hash provided")
            result = release(provider, inventory, args.reviewed_sha256)
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            result = manifest(provider, inventory, expect="registered")
            print(json.dumps(result, indent=2, sort_keys=True))
            print("[READ ONLY] Record reviewed_sha256 BEFORE shutdown; no files changed")
    except (NorthReleaseError, NorthSetupError, HandoffPlanError,
            ValueError, OSError, UnicodeError, RuntimeError) as exc:
        parser.exit(1, "[BLOCKED] NORTH offline release: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
