"""Explicit root-owned exception for PURPLE Vagrant port mappings in NORTH.

Only registered PURPLE-WS01 / 172.28.233.31 is eligible; no broad subnet
allowlist, VMware networking edits, or automatic adoption of unknown ports.
Operator performs a one-time read/prove-and-record action while PURPLE exists.
NORTH verification thereafter reads a root-owned, identity-pinned receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

OWNER = Path("/etc/vmware/kingdoms-course1-owner.json")
NETWORKING = Path("/etc/vmware/networking")
RECEIPT = Path("/etc/vmware/kingdoms-course1-foreign-vagrant.json")
MACHINE = "PURPLE-WS01"
LAB_IP = "172.28.233.31"
PORTS = (22, 5985, 5986)
SCHEMA = "kingdoms.north.foreign-vagrant.v1"


class ForeignNatError(ValueError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _safe_file(path: Path, uid=0, mode=0o600) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ForeignNatError(f"Missing/unsafe attestation file: {path}")
    st = path.stat()
    if (not stat.S_ISREG(st.st_mode) or st.st_uid != uid
            or stat.S_IMODE(st.st_mode) != mode or st.st_size > 8192):
        raise ForeignNatError(f"Unsafe owner, mode or size for: {path}")
    return path.read_bytes()


def _provider_identity(directory: str) -> tuple[Path, Path]:
    p = Path(directory)
    if (not p.is_absolute() or p.is_symlink() or not p.is_dir()
            or p.name != "provider" or
            not re.fullmatch(r"[0-9a-f]{6}-purple-vmware", p.parent.name)
            or p.parent.parent.name != "workspace"):
        raise ForeignNatError("Provider is not an installed PURPLE VMware instance")
    return p, p.resolve(strict=True)


def _vmx_identity(provider: Path) -> tuple[str, str]:
    state = provider / ".vagrant" / "machines" / MACHINE / "vmware_desktop"
    pointer = state / "id"
    if pointer.is_symlink() or not pointer.is_file() or pointer.stat().st_size > 4096:
        raise ForeignNatError("PURPLE-WS01 Vagrant VMX pointer missing or unsafe")
    raw = pointer.read_bytes()
    vmx = Path(raw.decode("utf-8").strip())
    if not vmx.is_absolute() or vmx.is_symlink() or not vmx.is_file():
        raise ForeignNatError("PURPLE-WS01 VMX missing or unsafe")
    if os.path.commonpath((str(state.resolve()), str(vmx.resolve()))) != str(state.resolve()):
        raise ForeignNatError("PURPLE-WS01 VMX points outside its own Vagrant state")
    return str(vmx.resolve()), _sha(raw)


def _check_guest_address(provider: Path):
    file = provider / "Vagrantfile"
    if file.is_symlink() or not file.is_file() or file.stat().st_size > 200000:
        raise ForeignNatError("Generated PURPLE Vagrantfile missing or unsafe")
    contents = file.read_text(encoding="utf-8")
    if not re.search(r':name\s*=>\s*["\']PURPLE-WS01["\']\s*,\s*:ip\s*=>\s*["\']172\.28\.233\.31["\']', contents):
        raise ForeignNatError("PURPLE-WS01 guest IP is not the expected host-only address")


def _parse_ports(stdout: str) -> dict[int, int]:
    found = re.findall(r"(?m)^\s*(\d+)\s+\(guest\)\s*=>\s*(\d+)\s+\(host\)\s*$", stdout)
    ports = {}
    for guest, host in found:
        guest, host = int(guest), int(host)
        if guest in ports or guest not in PORTS or host < 1025 or host > 65535:
            raise ForeignNatError("Vagrant port output has an unexpected or duplicate port")
        ports[guest] = host
    if set(ports) != set(PORTS) or len(set(ports.values())) != 3:
        raise ForeignNatError("Expected three distinct PURPLE-WS01 Vagrant management ports")
    return ports


def _rules(ports: dict[int, int]) -> frozenset[str]:
    if set(ports) != set(PORTS) or len(set(ports.values())) != 3:
        raise ForeignNatError("Invalid verified host ports")
    return frozenset(
        f"add_nat_portfwd 8 tcp {ports[guest]} {LAB_IP} {guest}"
        for guest in PORTS
    )


def approved_foreign_forwardings(
    north_provider: str, owner_bytes: bytes, *, source: Path = RECEIPT,
    owner_uid: int = 0
) -> frozenset[str]:
    """Read-only exact attestation; absent record authorizes NOTHING."""
    source = Path(source)
    if not source.exists() and not source.is_symlink():
        return frozenset()
    try:
        record = json.loads(_safe_file(source, owner_uid))
    except (UnicodeError, ValueError, OSError) as exc:
        raise ForeignNatError("Unreadable PURPLE forwarding receipt") from exc
    required = {
        "schema", "north_provider", "north_owner_sha256",
        "purple_provider", "vmx_path", "vmx_pointer_sha256",
        "machine", "guest_ip", "ports", "rules",
    }
    if not isinstance(record, dict) or set(record) != required:
        raise ForeignNatError("Unexpected PURPLE forwarding receipt fields")
    if (record["schema"] != SCHEMA
            or record["north_provider"] != str(Path(north_provider).resolve())
            or record["north_owner_sha256"] != _sha(owner_bytes)
            or record["machine"] != MACHINE
            or record["guest_ip"] != LAB_IP):
        raise ForeignNatError("PURPLE forwarding receipt is not bound to this NORTH owner")
    p, resolved = _provider_identity(record["purple_provider"])
    vmx, pointer_sha = _vmx_identity(p)
    _check_guest_address(p)
    if (str(resolved) != record["purple_provider"]
            or record["vmx_path"] != vmx
            or record["vmx_pointer_sha256"] != pointer_sha):
        raise ForeignNatError("PURPLE instance VMX identity changed")
    ports = record["ports"]
    if (not isinstance(ports, dict) or set(ports) != {"22", "5985", "5986"}
            or any(type(v) is not int or not 1025 <= v <= 65535
                   for v in ports.values())):
        raise ForeignNatError("Malformed PURPLE forwarding port evidence")
    checked = _rules({int(k): v for k, v in ports.items()})
    if (type(record["rules"]) is not list or len(record["rules"]) != 3
            or len(set(record["rules"])) != 3
            or checked != frozenset(record["rules"])):
        raise ForeignNatError("PURPLE forwarding receipt rules were modified")
    return checked


def register(north_provider: str, foreign_provider: str, *,
             owner: Path = OWNER, networking: Path = NETWORKING,
             receipt: Path = RECEIPT, owner_uid: int = 0,
             vagrant_output: str | None = None):
    """Record only proven guest-specific ports; never mutate VMware networking."""
    if os.geteuid() != 0:
        raise ForeignNatError("Run via sudo from the Kali desktop user")
    if receipt.exists() or receipt.is_symlink():
        raise ForeignNatError("An attestation already exists; refuse silent replacement")
    record = json.loads(_safe_file(owner, owner_uid))
    if record.get("profile") != "NORTH" or record.get("provider") != str(Path(north_provider).resolve()):
        raise ForeignNatError("NORTH owner is not the selected installed instance")
    p, resolved = _provider_identity(foreign_provider)
    vmx, pointer_sha = _vmx_identity(p)
    _check_guest_address(p)
    if vagrant_output is None:
        user = os.environ.get("SUDO_USER", "")
        if not user or user == "root":
            raise ForeignNatError("SUDO_USER must identify the VMware desktop owner")
        pwd.getpwnam(user)
        executable = shutil.which("vagrant")
        runner = shutil.which("runuser")
        if not executable or not runner:
            raise ForeignNatError("Cannot run Vagrant as the desktop user")
        try:
            proc = subprocess.run(
                [runner, "-u", user, "--", executable, "port", MACHINE],
                cwd=str(p), capture_output=True, text=True, timeout=25, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ForeignNatError("Vagrant port query failed or timed out") from exc
        if proc.returncode:
            raise ForeignNatError("Cannot verify PURPLE Vagrant ports")
        vagrant_output = proc.stdout
    ports = _parse_ports(vagrant_output)
    rules = _rules(ports)
    if networking.is_symlink() or not networking.is_file():
        raise ForeignNatError("VMware networking file missing or unsafe")
    net_meta = networking.stat()
    if (net_meta.st_uid != owner_uid or not stat.S_ISREG(net_meta.st_mode)
            or net_meta.st_size > 1048576):
        raise ForeignNatError("VMware networking ownership or size is unsafe")
    observed = networking.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in observed.splitlines() if ln.strip().startswith("add_nat_portfwd ")]
    if any(lines.count(line) != 1 for line in rules):
        raise ForeignNatError("Observed VMware NAT forwards do not exactly match registered PURPLE ports")
    data = {
        "schema": SCHEMA,
        "north_provider": str(Path(north_provider).resolve()),
        "north_owner_sha256": _sha(owner.read_bytes()),
        "purple_provider": str(resolved),
        "vmx_path": vmx,
        "vmx_pointer_sha256": pointer_sha,
        "machine": MACHINE,
        "guest_ip": LAB_IP,
        "ports": {str(k): v for k, v in ports.items()},
        "rules": sorted(rules),
    }
    # Receipt is a limited, explicit one-time operator authorization, not
    # network write/restart. If the normal NORTH guard still fails, undo it.
    fd = os.open(str(receipt), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(data, output, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
        approved_foreign_forwardings(
            north_provider, owner.read_bytes(), source=receipt, owner_uid=owner_uid)
        from goad.course1_host_network_apply import inspect_installed_north
        inspect_installed_north(north_provider)
    except BaseException:
        receipt.unlink(missing_ok=True)
        raise
    print("[PASS] Verified PURPLE-WS01 VMX and Vagrant host ports")
    print("[PASS] NORTH immutable owner and VMware networking unchanged")
    print("[PASS] Root-only exact three-forward receipt recorded; NORTH guard passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("register",))
    parser.add_argument("--north-provider", required=True)
    parser.add_argument("--purple-provider", required=True)
    args = parser.parse_args()
    try:
        register(args.north_provider, args.purple_provider)
    except (ForeignNatError, OSError, ValueError, UnicodeError, KeyError) as exc:
        parser.exit(1, f"[BLOCKED] NORTH-PURPLE NAT forwarding attestation: {exc}\n")


if __name__ == "__main__":
    main()
