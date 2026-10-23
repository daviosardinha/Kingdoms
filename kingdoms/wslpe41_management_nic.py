"""Offline, exact-instance, journaled WSLPE41 management NIC attachment.

Separate from the generic disposable preview; cannot operate on other VMs.
Never touches VMware's shared network configuration, another VMX, NORTH,
Windows, Vagrant provisioning, WinRM, guest power or iproute2 configuration.
Only inserts a third VMware ethernet adapter into a powered-off existing VMX.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

from kingdoms.wslpe_nic_contract import parse_vmx_networks
from kingdoms.wslpe_management_vmnet_registry import (
    MAX_INVENTORY, MAX_VMX, _regular, parse_workstation_library,
)

INSTANCE = "bf5369-wslpe-vmware"
MACHINE = "WSLPE-WS01"
VMNET = "vmnet4"
SOURCE = "vmnet3"
TARGET_CIDR = "172.28.233.0/24"
TARGET_HOST = "172.28.233.254/24"
TARGET_GUEST = "172.28.233.31/24"  # planned only; NEVER applied by this module
APPROVAL = "ATTACH-ONLY-FRESH-WSLPE-VMNET4"
NETWORKING_SHA = "9717eecc5c8f05f4d214018a7da280c4484dc3d2e9a26a33902a9efe3e89f990"
NIC_LINES = (
    'ethernet2.present = "TRUE"',
    'ethernet2.connectionType = "custom"',
    'ethernet2.virtualDev = "e1000e"',
    'ethernet2.vnet = "vmnet4"',
    'ethernet2.startConnected = "TRUE"',
    'ethernet2.addressType = "generated"',
)
NIC_PATTERN = re.compile(r"^\s*ethernet(\d+)\.", flags=re.I)
SHA_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class NicBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class Target:
    instance: Path
    vmx: Path
    original: bytes
    digest: str


def _cmd(argv: list[str], *, timeout: int = 20) -> str:
    try:
        res = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NicBlocked("Required host read-only command unavailable") from exc
    if res.returncode or len(res.stdout) > 160_000:
        raise NicBlocked("Host maintenance guard failed: " + Path(argv[0]).name)
    return res.stdout.strip()


def zero_vmware_guests() -> None:
    output = _cmd(["/usr/bin/vmrun", "-T", "ws", "list"])
    if output != "Total running VMs: 0":
        raise NicBlocked("All VMware guests must be off before VMX mutation")
    try:
        res = subprocess.run(["/usr/bin/pgrep", "-x", "vmware-vmx"],
                             capture_output=True, timeout=12,
                             stdin=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NicBlocked("VMware VM process inventory unavailable") from exc
    if res.returncode != 1:
        raise NicBlocked("VMware guest processes still active or inventory uncertain")


def host_operator_network_ready() -> None:
    # Trust only the previously installed, root-owned WSLPE vmnet4 keeper.
    keeper = Path("/usr/local/libexec/kingdoms/wslpe-vmnet4-hostaddr-keeper.py")
    meta = keeper.lstat()
    if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != 0
            or meta.st_mode & 0o022 or not meta.st_mode & 0o111):
        raise NicBlocked("Committed vmnet4 root-installed keeper unavailable")
    checked = _cmd(["/usr/bin/sudo", "-n", "/usr/bin/python3",
                    str(keeper), "--check"], timeout=35)
    if "[PASS] VMNET4_HOSTADDR_PERSISTENCE=PASS" not in checked:
        raise NicBlocked("Host vmnet4 address/isolation keeper has not passed")
    for flag in ("is-active", "is-enabled"):
        if _cmd(["/usr/bin/systemctl", flag,
                 "kingdoms-wslpe-vmnet4-hostaddr.timer"]) not in ("active", "enabled"):
            raise NicBlocked("vmnet4 address persistence timer not healthy")


def _read_vmx(vmx: Path, *, exact_legacy_0771_probe: bool = False) -> bytes:
    """Read exact user-owned VMX, reporting the specific failed file gate.

    Do not broaden file ownership or access-mode policy. In particular,
    a VMware-created group-writable VMX requires an explicit separate
    owner-approved permission correction, not a silent trust bypass.
    """
    try:
        st = vmx.lstat()
    except OSError as exc:
        raise NicBlocked("Registered VMX metadata unavailable") from exc
    if stat.S_ISLNK(st.st_mode):
        raise NicBlocked("Registered VMX is a symlink; refusing attachment")
    if not stat.S_ISREG(st.st_mode):
        raise NicBlocked("Registered VMX is not a regular file")
    if st.st_uid != os.getuid():
        raise NicBlocked(
            f"Registered VMX owner mismatch: actual_uid={st.st_uid} "
            f"expected_uid={os.getuid()} (mode={stat.S_IMODE(st.st_mode):04o})"
        )
    if st.st_nlink != 1:
        raise NicBlocked(f"Registered VMX has unsafe link count: {st.st_nlink}")
    if st.st_size <= 0 or st.st_size > MAX_VMX:
        raise NicBlocked(
            f"Registered VMX size out of bounds: bytes={st.st_size} maximum={MAX_VMX}"
        )
    if st.st_mode & 0o022 and not (
            exact_legacy_0771_probe and stat.S_IMODE(st.st_mode) == 0o771):
        raise NicBlocked(
            f"Registered VMX is group/other-writable: "
            f"mode={stat.S_IMODE(st.st_mode):04o} gid={st.st_gid}; "
            "do not change permissions without an exact-instance maintenance gate"
        )
    raw = vmx.read_bytes()
    if len(raw) != st.st_size:
        raise NicBlocked("VMX changed during snapshot")
    return raw


def identify(home: Path, *, existing_ok: bool = False,
             exact_legacy_0771_probe: bool = False,
             allow_legacy_management_model: bool = False) -> Target:
    if os.geteuid() == 0:
        raise NicBlocked("VMX transaction must run as original non-root Workstation owner")
    instance = home / "kingdoms-wslpe41-fresh/workspace" / INSTANCE
    provider = instance / "provider"
    reg = provider / ".vagrant/machines" / MACHINE / "vmware_desktop/id"
    if any(p.is_symlink() for p in (instance, provider, reg)):
        raise NicBlocked("VMware native registration contains symlink")
    if not instance.is_dir() or not reg.is_file() or reg.stat().st_size > 10_000:
        raise NicBlocked("Fresh native WSLPE VM registration unavailable")
    info_path = instance / "instance.json"
    if info_path.is_symlink() or info_path.stat().st_size > 200_000:
        raise NicBlocked("Unsafe native instance metadata")
    info = json.loads(info_path.read_text(encoding="utf-8"))
    if (info.get("id") != INSTANCE or info.get("lab") != "WSLPE"
            or info.get("provider") != "vmware" or info.get("provisioner") != "local"
            or info.get("status") != "ready for provisioning"
            or info.get("ip_range") != "172.28.232" or info.get("extensions")):
        raise NicBlocked("Wrong native instance identity")
    vmx = Path(reg.read_text(encoding="utf-8").strip())
    if not vmx.is_absolute() or vmx.is_symlink():
        raise NicBlocked("VMX escapes dedicated native provider")
    try:
        resolved = vmx.resolve(strict=True)
        trusted_provider = provider.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise NicBlocked("Registered native VMX is missing or contains unsafe path aliases") from exc
    if resolved != vmx or not vmx.is_relative_to(trusted_provider):
        raise NicBlocked("VMX escapes dedicated native provider")
    inventory = parse_workstation_library(_regular(home / ".vmware/inventory.vmls",
                                                   MAX_INVENTORY))
    if inventory.count(vmx) != 1:
        raise NicBlocked("Fresh VMX not uniquely registered in user Workstation library")
    raw = _read_vmx(vmx, exact_legacy_0771_probe=exact_legacy_0771_probe)
    verify_layout(raw, allow_management=existing_ok,
                  allow_legacy_model=allow_legacy_management_model)
    return Target(instance, vmx, raw, hashlib.sha256(raw).hexdigest())


def verify_layout(raw: bytes, *, allow_management: bool = False,
                  allow_legacy_model: bool = False) -> None:
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise NicBlocked("VMX cannot be safely edited as UTF-8") from exc
    slots = parse_vmx_networks(text)
    indices = {int(m.group(1)) for line in text.splitlines()
               if (m := NIC_PATTERN.match(line))}
    needed = {0, 1, 2} if allow_management else {0, 1}
    if indices != needed:
        raise NicBlocked("Fresh guest VMX must have only original NIC slots 0/1")
    nat, exercise = slots.get(0, {}), slots.get(1, {})
    if (nat.get("present") != "TRUE" or nat.get("connectiontype", "").lower() != "nat"
            or nat.get("startconnected", "TRUE").upper() == "FALSE"
            or exercise.get("present") != "TRUE"
            or exercise.get("connectiontype", "").lower() != "custom"
            or exercise.get("vnet") != SOURCE
            or exercise.get("startconnected", "TRUE").upper() == "FALSE"):
        raise NicBlocked("Original provider NAT or learner vmnet3 NIC changed")
    if allow_management:
        mgmt = slots.get(2, {})
        if (mgmt.get("present") != "TRUE" or
                mgmt.get("connectiontype", "").lower() != "custom"
                or mgmt.get("vnet") != VMNET
                or mgmt.get("startconnected") != "TRUE"
                or mgmt.get("addresstype") != "generated"):
            raise NicBlocked("Management slot 2 has unexpected VMware configuration")
        model = mgmt.get("virtualdev")
        if model != "e1000e" and not (allow_legacy_model and model in (None, "e1000")):
            raise NicBlocked("Management NIC model must be pinned to e1000e")


def candidate_vmx(original: bytes) -> bytes:
    verify_layout(original)
    if not original.endswith(b"\n"):
        raise NicBlocked("VMX must end with newline to add exact adapter directives")
    candidate = original + ("\n".join(NIC_LINES) + "\n").encode("ascii")
    verify_layout(candidate, allow_management=True)
    return candidate


def _write_atomic(path: Path, content: bytes, original_mode: int) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".wslpe-vmx-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), original_mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def attach(*, home: Path, expected_sha256: str, approval: str) -> str:
    if approval != APPROVAL or not SHA_PATTERN.fullmatch(expected_sha256):
        raise NicBlocked("Exact NIC authorization and original VMX hash required")
    zero_vmware_guests()
    host_operator_network_ready()
    target = identify(home)
    if target.digest != expected_sha256:
        raise NicBlocked("VMX bytes changed after operator's read-only inspection")
    proposed = candidate_vmx(target.original)
    journal_dir = home / ".local/state/kingdoms-wslpe41-mgmt-nic" / INSTANCE
    if journal_dir.is_symlink() or journal_dir.exists():
        raise NicBlocked("Management VMX transaction journal already exists")
    journal_dir.mkdir(parents=True, mode=0o700)
    if stat.S_IMODE(journal_dir.stat().st_mode) != 0o700:
        raise NicBlocked("Private management VMX journal not 0700")
    journal = journal_dir / "journal.json"
    record = {
        "schema": "kingdoms.wslpe41.nic.v1",
        "status": "prepared", "instance": INSTANCE, "vmx": str(target.vmx),
        "original_sha256": target.digest,
        "proposed_sha256": hashlib.sha256(proposed).hexdigest(),
        "original_b64": base64.b64encode(target.original).decode("ascii"),
    }
    _write_atomic(journal, json.dumps(record, sort_keys=True).encode(), 0o600)
    try:
        zero_vmware_guests()
        if _read_vmx(target.vmx) != target.original:
            raise NicBlocked("VMX changed after journal creation")
        _write_atomic(target.vmx, proposed, stat.S_IMODE(target.vmx.stat().st_mode))
        verify_layout(_read_vmx(target.vmx), allow_management=True)
        if _read_vmx(target.vmx) != proposed:
            raise NicBlocked("VMX did not retain exact third NIC")
        record["status"] = "committed"
        _write_atomic(journal, json.dumps(record, sort_keys=True).encode(), 0o600)
    except Exception:
        current = _read_vmx(target.vmx)
        if current == proposed:
            zero_vmware_guests()
            _write_atomic(target.vmx, target.original, stat.S_IMODE(target.vmx.stat().st_mode))
            record["status"] = "rolled_back"
            _write_atomic(journal, json.dumps(record, sort_keys=True).encode(), 0o600)
        raise
    return str(journal)
