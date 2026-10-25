"""Fail-closed checks for NORTH's offline full backup and fifth fresh install.

No VMware mutations. Backup content includes the entire original instance
(VMX, VMDK, VMSD, snapshots, metadata) and ~/.vagrant.d box bases/metadata.
Root-owned host VMware configuration is archived separately by the runner.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

OLD = "8aafc9-north-vmware"
GUESTS = ("GOAD-ROUTER", "GOAD-DC01", "GOAD-DC02",
          "GOAD-SRV02", "GOAD-WS01")


class BackupBlocked(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise BackupBlocked(reason)


def valid_instance(root):
    root = Path(root).resolve(strict=True)
    inst = root / "workspace" / OLD
    provider = inst / "provider"
    require(inst.is_dir() and not inst.is_symlink() and
            provider.is_dir() and not provider.is_symlink() and
            inst.resolve(strict=True) == inst and provider.resolve(strict=True) == provider,
            "Original NORTH instance missing or redirected")
    meta = inst / "instance.json"
    mode = provider / ".goad-nomad-mode"
    require(meta.is_file() and not meta.is_symlink() and
            mode.is_file() and not mode.is_symlink(),
            "Original metadata or mode missing")
    data = json.loads(meta.read_text(encoding="utf-8"))
    require((data.get("id"), data.get("lab"), data.get("provider"),
             data.get("status")) == (OLD, "NORTH", "vmware", "installed")
            and mode.read_text().strip() == "exercise",
            "Original installed/exercise NORTH status not proven")
    paths = {}
    for name in GUESTS:
        reg = provider / ".vagrant" / "machines" / name / "vmware_desktop" / "id"
        require(reg.is_file() and not reg.is_symlink(), "VMX ID missing: " + name)
        vmx = Path(reg.read_text().strip())
        require(vmx.is_absolute() and vmx.is_file() and not vmx.is_symlink()
                and vmx.resolve().is_relative_to(reg.parent.resolve())
                and vmx.resolve().is_relative_to(inst.resolve()),
                "Foreign or missing VMX: " + name)
        paths[name] = str(vmx)
    return inst, paths


def running_vms():
    p = subprocess.run(["vmrun", "-T", "ws", "list"],
                       capture_output=True, text=True, check=False, timeout=45)
    require(p.returncode == 0, "Cannot inspect running VMware guests")
    lines = [x.strip() for x in p.stdout.splitlines() if x.strip()]
    require(lines and re.fullmatch(r"Total running VMs: \d+", lines[0]),
            "Malformed VMware running list")
    require(len(lines) - 1 == int(lines[0].rsplit(":", 1)[1]),
            "VMware reported VM count mismatch")
    return set(lines[1:])


def preflight(root):
    inst, paths = valid_instance(root)
    require(running_vms() == set(paths.values()),
            "Exactly the five original NORTH VMs must be running; foreign VM present or VM missing")
    # Reuse the existing VMware inventory evidence to guard powered-off
    # unrelated VMs before any host network retirement.
    inventory = Path.home() / ".vmware" / "inventory.vmls"
    if inventory.exists():
        require(inventory.is_file() and not inventory.is_symlink(),
                "Unsafe VMware user inventory")
        for line in inventory.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.fullmatch(r'\\s*vmlist\\d+\\.config\\s*=\\s*"([^"]+)"\\s*', line)
            if not m:
                continue
            vmx = Path(m.group(1))
            require(not vmx.is_symlink(), "Foreign VMware inventory has a symlink")
            if not vmx.is_file() or str(vmx.resolve()) in set(paths.values()):
                continue
            contents = vmx.read_text(encoding="utf-8", errors="replace")
            for nic in ("vmnet10", "vmnet20", "vmnet99"):
                require(not re.search(r'^\\s*ethernet\\d+\\.vnet\\s*=\\s*"' + nic + r'"',
                                      contents, re.I | re.M),
                        "An unrelated registered VM uses a NORTH network")
    require(not (Path(root) / "workspace" / OLD).is_symlink(), "Instance symlink")
    print("[PASS] NORTH_ORIGINAL_FIVE_RUNNING_VMS_AND_INSTALLED_MODE")
    return inst, paths


def offline(root):
    inst, paths = valid_instance(root)
    require(not running_vms(),
            "VMware Workstation must have zero running VMs before offline backup/destruction")
    print("[PASS] NORTH_ALL_VMWARE_VMS_STOPPED")
    return inst, paths


def allocation(path):
    total = 0
    for directory, subdirs, filenames in os.walk(path, followlinks=False):
        for name in subdirs + filenames:
            p = Path(directory) / name
            st = p.lstat()
            require(not (stat.S_ISCHR(st.st_mode) or stat.S_ISBLK(st.st_mode)
                         or stat.S_ISFIFO(st.st_mode) or stat.S_ISSOCK(st.st_mode)),
                    "Special source file cannot be included in portable backup: " + str(p))
            if stat.S_ISREG(st.st_mode):
                total += st.st_blocks * 512
    return total


def space(root, destination):
    inst, _ = valid_instance(root)
    home = Path.home() / ".vagrant.d"
    require(home.is_dir() and not home.is_symlink(), "Vagrant home absent or unsafe")
    dest = Path(destination)
    require(dest.is_dir() and not dest.is_symlink(), "Backup directory missing or symlink")
    instance_usage = allocation(inst)
    vagrant_usage = allocation(home)
    source_free = shutil.disk_usage(inst).free
    backup_free = shutil.disk_usage(dest).free
    # Allow for filesystem overhead and another full NORTH installation.
    capacity = instance_usage + vagrant_usage
    reserve = 25 * 1024**3
    if os.stat(dest).st_dev == os.stat(inst).st_dev:
        require(backup_free >= capacity + instance_usage + reserve,
                "Insufficient free space for backups + new NORTH + 25 GiB reserve")
    else:
        require(backup_free >= capacity + 5 * 1024**3,
                "Insufficient free space for offline backup destination")
        require(source_free >= instance_usage + reserve,
                "Insufficient source disk space for new NORTH + reserve")
    print("[PASS] NORTH_BACKUP_AND_FRESH_INSTALL_DISK_SPACE")


def file_inventory(root):
    """Map paths to SHA-256 or symlink text, refusing special files."""
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "Backup source directory unsafe")
    result = {}
    for directory, subdirs, files in os.walk(root, followlinks=False):
        for name in sorted(subdirs + files):
            path = Path(directory) / name
            key = path.relative_to(root).as_posix()
            st = path.lstat()
            if stat.S_ISLNK(st.st_mode):
                result[key] = ["symlink", os.readlink(path)]
            elif stat.S_ISREG(st.st_mode):
                digest = hashlib.sha256()
                with path.open("rb") as fh:
                    for buf in iter(lambda: fh.read(8 * 1024 * 1024), b""):
                        digest.update(buf)
                result[key] = ["file", st.st_size, digest.hexdigest()]
            elif stat.S_ISDIR(st.st_mode):
                result[key] = ["directory"]
            else:
                raise BackupBlocked("Special file in backup: " + str(path))
    return result


def verify_copy(root, backup):
    root = Path(root)
    backup = Path(backup)
    inst, vmxs = offline(root)
    require(backup.is_dir() and not backup.is_symlink(),
            "Backup destination unsafe")
    entries = (("instance", inst),
               ("vagrant-home", Path.home() / ".vagrant.d"))
    for label, source in entries:
        target = backup / label
        actual = file_inventory(target)
        expected = file_inventory(source)
        require(actual == expected,
                "Backup is not a byte-for-byte match for: " + label)
        destination = backup / (label + "-sha256-manifest.json")
        require(not destination.exists() and not destination.is_symlink(),
                "Backup integrity manifest already present")
        with destination.open("x", encoding="utf-8") as out:
            json.dump(actual, out, sort_keys=True, indent=1)
            out.write("\n")
        os.chmod(destination, 0o600)
        print("[PASS] NORTH_BACKUP_BYTE_VERIFIED=" + label)
    require(all((backup / "instance" /
                 Path(vmx).relative_to(inst)).is_file() for vmx in vmxs.values()),
            "One or more original VMX files absent from backup")
    print("[PASS] NORTH_FIVE_VM_OFFLINE_BACKUP_VERIFIED")


def post_destroy(root):
    # Vagrant destroy intentionally removes guest registrations and VMX files.
    # Validate exact installed owner and provider path without requiring guests
    # that should no longer exist at this post-destruction checkpoint.
    inst = Path(root).resolve(strict=True) / "workspace" / OLD
    provider = inst / "provider"
    require(inst.is_dir() and not inst.is_symlink() and
            provider.is_dir() and not provider.is_symlink(),
            "Exact installed original NORTH workspace no longer exists")
    meta = json.loads((inst / "instance.json").read_text())
    require((meta.get("id"), meta.get("lab"), meta.get("provider")) ==
            (OLD, "NORTH", "vmware"), "Wrong post-destroy workspace metadata")
    require(not running_vms(), "VMware guests still running after destroy")
    provider = inst / "provider"
    for machine in GUESTS:
        id_file = provider / ".vagrant" / "machines" / machine / "vmware_desktop" / "id"
        require(not id_file.exists() and not id_file.is_symlink(),
                "Old Vagrant registration survived destroy: " + machine)
    for path in provider.rglob("*"):
        require(not (path.is_file() and path.suffix.lower() in
                (".vmx", ".vmdk", ".vmsd", ".vmsn", ".vmem", ".nvram")),
                "VM guest disk or metadata survived destroy: " + str(path))
    print("[PASS] NORTH_OLD_FIVE_VMS_DESTROYED")


def delete_old_workspace(root, backup):
    inst = Path(root).resolve(strict=True) / "workspace" / OLD
    post_destroy(root)
    path = Path(backup) / "instance" / "instance.json"
    require(path.is_file() and not path.is_symlink(),
            "Verified original backup no longer available")
    meta = json.loads(path.read_text())
    require(meta.get("id") == OLD and meta.get("status") == "installed",
            "Original installed backup receipt missing")
    require((Path(backup) / "backup-verified.marker").is_file(),
            "Offline backup was never certified")
    shutil.rmtree(inst)
    require(not inst.exists(), "Retired instance directory survived cleanup")
    print("[PASS] NORTH_ONLY_OLD_DESTROYED_WORKSPACE_REMOVED")


def discover_new(root):
    base = Path(root) / "workspace"
    matches = []
    for folder in base.iterdir():
        file = folder / "instance.json"
        if not file.is_file() or file.is_symlink():
            continue
        state = json.loads(file.read_text())
        if state.get("lab") == "NORTH" and state.get("provider") == "vmware":
            matches.append((folder, state))
    require(len(matches) == 1, "Expected exactly one NORTH VMware instance after reinstall")
    path, meta = matches[0]
    require(path.name != OLD and
            (meta.get("id"), meta.get("status")) == (path.name, "installed") and
            (path / "provider/.goad-nomad-mode").read_text().strip() == "exercise",
            "Fifth NORTH installation did not finish in installed/exercise mode")
    receipts = list((path / "install-timings").glob("*.json"))
    require(len(receipts) == 1, "Expected one original fifth installation receipt")
    record = json.loads(receipts[0].read_text())
    require(record.get("status") == "completed" and
            record.get("provider_success") is True and
            record.get("instance_id") == path.name,
            "Fifth install did not complete original uninterrupted provider/Ansible phases")
    print("[PASS] NORTH_UNINTERRUPTED_ONE_COMMAND_INSTALL", file=sys.stderr)
    print(path.name)


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("preflight","offline","space",
                                       "verify-copy","post-destroy","remove-old",
                                       "discover-new"))
    p.add_argument("--root", required=True)
    p.add_argument("--backup")
    args = p.parse_args()
    try:
        if args.action == "preflight":
            preflight(args.root)
        elif args.action == "offline":
            offline(args.root)
        elif args.action == "space":
            require(args.backup, "Missing backup directory")
            space(args.root, args.backup)
        elif args.action == "verify-copy":
            require(args.backup, "Missing backup directory")
            verify_copy(args.root, args.backup)
        elif args.action == "post-destroy":
            post_destroy(args.root)
        elif args.action == "remove-old":
            require(args.backup, "Missing backup directory")
            delete_old_workspace(args.root, args.backup)
        else:
            discover_new(args.root)
    except (BackupBlocked, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        p.exit(1, "[BLOCKED] NORTH full-backup workflow: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
