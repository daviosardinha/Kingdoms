"""Explicit, privileged VMware network APPLY/ROLLBACK for Kingdoms Course 1.

No automatic guest shutdown, boot or Course 1 installation. A separate
read-only host survey must pass first. Nothing runs unless the operator selects
--apply/--rollback AND the explicit maintenance confirmation flag.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from goad.course1_host_survey import parse_vmware_networking
from goad.course1_vmnet_maintenance import inspect_maintenance
from goad.course1_network_plan import ZONES, require
from goad.course1_runtime_contract import ProfileNotReady

CONFIG = Path("/etc/vmware/networking")
NETMAP = Path("/etc/vmware/netmap.conf")
BACKUPS = Path("/etc/vmware/kingdoms-course1-backups")
NETWORK_EXEC = Path("/usr/bin/vmware-networks")
LOCKFILE = Path("/run/lock/kingdoms-course1-vmnet.lock")
VMNET_DEVICE_ROOT = Path("/dev")
BACKUP_ID = re.compile(r"c1-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}\Z")
CONFIRM = "I_APPROVE_KINGDOMS_COURSE1_VMWARE_NETWORK_MAINTENANCE"
MUTATION_STATES = ("BACKED_UP", "APPLIED", "ROLLED_BACK", "RECOVERY_NEEDED")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verify_no_vmware_guests() -> None:
    """Never stop networking under ANY running vmware-vmx process."""
    result = subprocess.run(["pgrep", "-x", "vmware-vmx"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, check=False)
    require(result.returncode == 1,
            "VMware guests are running or process check failed; shut down guests first")


def _run_networks(option: str) -> None:
    require(option in ("--stop", "--start"), "unexpected VMware networking command")
    require(NETWORK_EXEC.is_file() and os.access(NETWORK_EXEC, os.X_OK),
            "vmware-networks executable unavailable")
    status = subprocess.run([str(NETWORK_EXEC), option],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, check=False, timeout=90)
    require(status.returncode == 0,
            "VMware network service " + option + " failed; output withheld")


def _existing_config() -> bytes:
    require(CONFIG.is_file() and not CONFIG.is_symlink(),
            "VMware networking config unavailable or symlinked")
    require(CONFIG.stat().st_size <= 1_000_000,
            "VMware networking configuration too large")
    return CONFIG.read_bytes()


def _write_atomic(target: Path, value: bytes, preserve: os.stat_result) -> None:
    """Replace only the owned explicit target, retaining uid/gid/mode."""
    require(target.is_file() and not target.is_symlink(),
            "refuse replacement of missing or symlinked VMware file")
    handle, temp_path = tempfile.mkstemp(prefix=".kingdoms-c1-", dir=target.parent)
    try:
        with os.fdopen(handle, "wb") as f:
            f.write(value)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp_path, stat.S_IMODE(preserve.st_mode))
        os.chown(temp_path, preserve.st_uid, preserve.st_gid)
        os.replace(temp_path, target)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _save_manifest(folder: Path, payload: dict) -> None:
    file = folder / "manifest.json"
    require(not file.is_symlink(), "backup manifest symlink refused")
    file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    file.chmod(0o600)


def _backup(original: bytes, added: bytes) -> tuple[Path, dict]:
    require(BACKUPS.exists() is False or
            (BACKUPS.is_dir() and not BACKUPS.is_symlink()),
            "VMware backup root must be an ordinary directory")
    BACKUPS.mkdir(mode=0o700, parents=True, exist_ok=True) if not BACKUPS.exists() else None
    require(stat.S_IMODE(BACKUPS.stat().st_mode) == 0o700,
            "VMware maintenance backup root must be private (0700)")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ident = f"c1-{stamp}-{uuid.uuid4().hex[:8]}"
    folder = BACKUPS / ident
    folder.mkdir(mode=0o700)
    (folder / "networking.original").write_bytes(original)
    (folder / "networking.original").chmod(0o600)
    if NETMAP.is_file() and not NETMAP.is_symlink():
        shutil.copy2(NETMAP, folder / "netmap.original")
        (folder / "netmap.original").chmod(0o600)
    manifest = {
        "kind": "KINGDOMS_COURSE1_VMNET_TRANSACTION",
        "backup_id": ident,
        "state": "BACKED_UP",
        "original_sha256": sha(original),
        "proposed_sha256": sha(added),
        "applied_sha256": None,
        "had_netmap": (folder / "netmap.original").exists(),
    }
    _save_manifest(folder, manifest)
    return folder, manifest


def _read_backup(ident: str) -> tuple[Path, dict, bytes]:
    require(BACKUP_ID.fullmatch(ident) is not None, "invalid backup identity")
    folder = BACKUPS / ident
    require(folder.is_dir() and not folder.is_symlink(),
            "VMware maintenance backup directory missing or symlinked")
    manifest_file = folder / "manifest.json"
    original_file = folder / "networking.original"
    for file in (manifest_file, original_file):
        require(file.is_file() and not file.is_symlink(),
                "VMware maintenance backup incomplete")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    original = original_file.read_bytes()
    require(manifest.get("backup_id") == ident
            and manifest.get("kind") == "KINGDOMS_COURSE1_VMNET_TRANSACTION"
            and manifest.get("state") in MUTATION_STATES
            and manifest.get("original_sha256") == sha(original),
            "VMware maintenance backup failed integrity checks")
    return folder, manifest, original


def _required_new_keys(proposal: dict) -> dict:
    keys = {}
    for zone in ZONES:
        segment = proposal["zones"][zone]
        num = int(segment["vmnet"][5:])
        keys[(num, "HOSTONLY_SUBNET")] = segment["subnet"].split("/")[0]
        keys[(num, "DHCP")] = "no"
        keys[(num, "VIRTUAL_ADAPTER")] = (
            "no" if zone == "SEVENKINGDOMS" else "yes"
        )
    return keys


def _keys(config: bytes) -> dict:
    data = config.decode("utf-8")
    keys = {}
    for line in data.splitlines():
        line = line.strip()
        match = re.fullmatch(r"answer VNET_(\d+)_([A-Z0-9_]+)\s+(\S+)", line)
        if match:
            key = (int(match.group(1)), match.group(2))
            require(key not in keys, "duplicate VNET keys in VMware networking")
            keys[key] = match.group(3)
    return keys


def verify_applied(original: bytes, current: bytes, proposal: dict) -> None:
    """VMware may normalize formatting, but must preserve original VNET keys."""
    before, after = _keys(original), _keys(current)
    for key, value in before.items():
        # Workstation may discard HOSTONLY_HOSTADDR on restart; reference
        # persistent-address systemd logic already compensates for this.
        if key[1] == "HOSTONLY_HOSTADDR":
            continue
        require(after.get(key) == value,
                "reference VMware network key changed during Course 1 maintenance")
    for key, value in _required_new_keys(proposal).items():
        require(after.get(key) == value,
                "new Course 1 VMware vmnet missing after VMware restart")
    for zone in ZONES:
        dev = VMNET_DEVICE_ROOT / proposal["zones"][zone]["vmnet"]
        require(dev.exists() and not dev.is_symlink(),
                "Course 1 vmnet device missing after VMware restart")


def _restore_files(folder: Path, manifest: dict, original: bytes) -> None:
    _write_atomic(CONFIG, original, CONFIG.stat())
    if manifest["had_netmap"]:
        saved = folder / "netmap.original"
        require(saved.is_file() and not saved.is_symlink(),
                "netmap.conf backup is missing")
        if NETMAP.is_file() and not NETMAP.is_symlink():
            _write_atomic(NETMAP, saved.read_bytes(), NETMAP.stat())
        else:
            shutil.copy2(saved, NETMAP)


def _restore_and_restart(folder: Path, manifest: dict, original: bytes) -> None:
    _verify_no_vmware_guests()
    _run_networks("--stop")
    _restore_files(folder, manifest, original)
    _run_networks("--start")
    after = _existing_config()
    recovered = _keys(after)
    for key, value in _keys(original).items():
        if key[1] == "HOSTONLY_HOSTADDR":
            continue
        require(recovered.get(key) == value,
                "reference VMware network key failed recovery after restart")


def apply(proposal: dict, snapshot: dict) -> dict:
    """Explicit maintenance-only operation; caller must already be root."""
    require(os.geteuid() == 0, "VMware configuration changes require sudo")
    require(not NETMAP.is_symlink(),
            "VMware netmap.conf may not be a symlink during maintenance")
    _verify_no_vmware_guests()
    require(snapshot.get("running_vm_count") == 0,
            "snapshot is stale: running VMware guests were reported")
    original = _existing_config()
    report = inspect_maintenance(proposal, snapshot, original.decode("utf-8"))
    require(report["status"] == "HOST_CHANGE_REQUIRES_EXPLICIT_APPROVAL",
            "host is not in a stopped-guest maintenance state")
    planned = report["additive_lines_only"]
    new_content = original + ("\n" + "\n".join(planned) + "\n").encode("utf-8")
    require(report["vmware_networking_proposed_sha256"] == sha(new_content),
            "network maintenance proposal changed since preflight")
    folder, manifest = _backup(original, new_content)
    stop_attempted = False
    try:
        _verify_no_vmware_guests()
        stop_attempted = True
        _run_networks("--stop")
        _write_atomic(CONFIG, new_content, CONFIG.stat())
        _run_networks("--start")
        verify_applied(original, _existing_config(), proposal)
    except Exception as failure:
        if stop_attempted:
            try:
                _restore_and_restart(folder, manifest, original)
                manifest["state"] = "ROLLED_BACK"
                _save_manifest(folder, manifest)
            except Exception as recovery_error:
                manifest["state"] = "RECOVERY_NEEDED"
                _save_manifest(folder, manifest)
                raise ProfileNotReady(
                    "Course 1 network apply failed AND rollback needs manual recovery; "
                    f"backup_id={manifest['backup_id']}") from recovery_error
        raise ProfileNotReady(
            f"Course 1 network apply failed; original networking restored; "
            f"backup_id={manifest['backup_id']}") from failure

    manifest["applied_sha256"] = sha(_existing_config())
    manifest["state"] = "APPLIED"
    _save_manifest(folder, manifest)
    return {
        "status": "COURSE1_NETWORK_CONFIG_APPLIED",
        "backup_id": manifest["backup_id"],
        "original_reference_vmnets_preserved": True,
        "course1_networks_added": [proposal["zones"][z]["vmnet"] for z in ZONES],
        "new_host_addresses_and_persistence_pending": True,
        "guest_lifecycle_authorized": False,
        "deployment_authorized": False,
    }


def rollback(ident: str) -> dict:
    """A deliberate revert, never permitted while any VMware guest is running."""
    require(os.geteuid() == 0, "rollback requires sudo")
    _verify_no_vmware_guests()
    folder, manifest, original = _read_backup(ident)
    require(manifest["state"] in ("APPLIED", "RECOVERY_NEEDED", "BACKED_UP"),
            "backup is not eligible for manual rollback")
    now = _existing_config()
    current_sha = sha(now)
    require(current_sha == manifest.get("applied_sha256")
            or (manifest["state"] == "BACKED_UP" and current_sha in (
                manifest["proposed_sha256"], manifest["original_sha256"]
            ))
            or manifest["state"] == "RECOVERY_NEEDED",
            "current VMware network config has changed: manual review required")
    _restore_and_restart(folder, manifest, original)
    manifest["state"] = "ROLLED_BACK"
    _save_manifest(folder, manifest)
    return {
        "status": "REFERENCE_VMWARE_NETWORK_CONFIG_RESTORED",
        "backup_id": ident,
        "deployment_authorized": False,
    }


def _locked(operation):
    """Mutations serialize on a root-owned advisory lock."""
    require(os.geteuid() == 0, "Course 1 VMware maintenance requires root")
    require(not LOCKFILE.is_symlink(),
            "VMware maintenance lockfile must not be symlinked")
    fd = os.open(LOCKFILE, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ProfileNotReady(
                "another Course 1 VMware maintenance process is running"
            ) from exc
        return operation()
    finally:
        os.close(fd)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--apply", action="store_true")
    commands.add_argument("--rollback", metavar="BACKUP_ID")
    parser.add_argument("--proposal", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != CONFIRM:
        parser.error("explicit Course 1 VMware maintenance confirmation required")
    try:
        if args.apply:
            require(args.proposal is not None and args.snapshot is not None,
                    "apply requires --proposal and --snapshot")
            proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
            require(args.snapshot.is_file() and not args.snapshot.is_symlink(),
                    "VMware host snapshot unavailable or symlinked")
            age = datetime.now(timezone.utc).timestamp() - args.snapshot.stat().st_mtime
            require(0 <= age <= 120,
                    "host snapshot too old; rerun maintenance to recheck running guests")
            snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
            result = _locked(lambda: apply(proposal, snapshot))
        else:
            result = _locked(lambda: rollback(args.rollback))
        print(json.dumps(result, indent=2))
    except (ProfileNotReady, OSError, ValueError, TypeError,
            subprocess.TimeoutExpired) as exc:
        parser.exit(1, "[FAIL] " + str(exc) + "\n")


if __name__ == "__main__":
    main()
