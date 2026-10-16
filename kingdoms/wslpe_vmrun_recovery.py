"""NORTH-derived WSLPE recovery prerequisites: read-only VMware owner proof.

Never stops/starts guests, writes a registered VMX, mutates nftables/NAT,
or contacts NORTH. The only writes are disposable owner-owned /tmp files.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

from kingdoms.wslpe_nat_cutover_contract import (
    render_nat_offline, manifest, guarded_original_restore,
)

RESULT_NAME = "vmrun-result.json"


def verify_vmrun_output(output: str, expected_vmx: Path) -> int:
    """Strict vmrun inventory; exact VMX must occur once, never basename match."""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines or not re.fullmatch(r"Total running VMs:\s*\d+", lines[0]):
        raise ValueError("Invalid VMware Workstation inventory format")
    count = int(lines[0].split(":")[1].strip())
    if count != len(lines) - 1 or len(set(lines[1:])) != count:
        raise ValueError("Inconsistent VMware Workstation inventory")
    paths = [Path(line).resolve(strict=True) for line in lines[1:]]
    if paths.count(expected_vmx.resolve(strict=True)) != 1:
        raise ValueError("Exact registered WSLPE VMX not present exactly once")
    return count


def worker_vmrun_read_only(vmx: Path, vmrun_binary: Path, destination: Path) -> None:
    """Run only vmrun -T ws list as current unprivileged VMware owner."""
    if os.geteuid() == 0 or not vmx.is_file() or vmx.is_symlink():
        raise ValueError("Unprivileged owner and exact VMX required")
    if vmx.stat().st_uid != os.geteuid():
        raise ValueError("VMX owner mismatch")
    if (vmrun_binary.name != "vmrun" or not vmrun_binary.is_file()
            or not os.access(vmrun_binary, os.X_OK)):
        raise ValueError("Verified VMware vmrun binary required")
    if destination.name != RESULT_NAME or destination.is_symlink():
        raise ValueError("Untrusted probe output")
    if destination.parent.stat().st_uid != os.geteuid():
        raise ValueError("Probe directory does not belong to VMX owner")
    outcome = subprocess.run(
        [str(vmrun_binary), "-T", "ws", "list"],
        text=True, capture_output=True, check=False, timeout=25,
    )
    if outcome.returncode:
        raise ValueError("VMware list failed inside systemd owner context")
    count = verify_vmrun_output(outcome.stdout, vmx)
    # No other VM identities or user credentials are ever stored in output.
    destination.write_text(json.dumps({
        "status": "PASS", "vmx_sha256": sha256(str(vmx.resolve()).encode()).hexdigest(),
        "running_vm_count": count, "owner_uid": os.geteuid(),
    }), encoding="utf-8")
    os.chmod(destination, 0o600)


def rehearse_vmrun_systemd(vmx: Path, uid: int, username: str, *,
                           runner=None, sleep=None, python_bin: Path | None = None,
                           worker_script: Path | None = None,
                           vmrun_bin: Path | None = None) -> dict:
    """Host-side timer invokes reviewed worker as VMX owner, no VMware mutation."""
    if vmx.is_symlink() or not vmx.is_file() or vmx.stat().st_uid != uid:
        raise ValueError("Exact VMX owner must match operator")
    if uid <= 0 or pwd.getpwuid(uid).pw_name != username:
        raise ValueError("Owner identity mismatch")
    if runner is None:
        def runner(argv, timeout=20):
            return subprocess.run(argv, capture_output=True, text=True,
                                  check=False, timeout=timeout)
    if sleep is None:
        sleep = time.sleep
    python_bin = python_bin or Path(sys.executable)
    worker_script = worker_script or (
        Path(__file__).resolve().parents[1] / "scripts/wslpe-p1c-owner-vmrun-worker.py"
    )
    vmrun_bin = vmrun_bin or Path(shutil.which("vmrun") or "")
    if (not python_bin.is_file() or not worker_script.is_file()
            or vmrun_bin.name != "vmrun" or not vmrun_bin.is_file()):
        raise ValueError("Verified worker/Python/vmrun executable missing")
    identifier = uuid.uuid4().hex[:16]
    unit = f"kingdoms-wslpe-vmrun-check-{identifier}"
    folder = Path(tempfile.mkdtemp(prefix=f"{unit}-", dir="/tmp"))
    result = folder / RESULT_NAME
    try:
        if folder.stat().st_uid != uid or folder.stat().st_mode & 0o077:
            raise ValueError("VMware owner probe directory permissions unsafe")
        args = [
            "sudo", "-n", "systemd-run", "--quiet", "--collect",
            "--unit", unit, "--on-active=3s",
            f"--property=User={username}",
            str(python_bin), str(worker_script),
            "--worker", "--vmx", str(vmx), "--vmrun", str(vmrun_bin),
            "--result", str(result),
        ]
        if runner(args).returncode:
            raise ValueError("Owner-context VMware timer could not be armed")
        state = runner(["sudo", "-n", "systemctl", "is-active", f"{unit}.timer"])
        if state.returncode or state.stdout.strip() != "active":
            raise ValueError("Owner-context VMware timer was not active")
        for _ in range(45):
            if result.is_file():
                if result.is_symlink() or result.stat().st_uid != uid:
                    raise ValueError("VMware proof result is not owned by VMX operator")
                data = json.loads(result.read_text(encoding="utf-8"))
                if (not isinstance(data, dict) or data.get("status") != "PASS"
                    or data.get("owner_uid") != uid
                    or data.get("vmx_sha256") != sha256(str(vmx.resolve()).encode()).hexdigest()
                    or type(data.get("running_vm_count")) is not int
                    or not 1 <= data["running_vm_count"] <= 100):
                    raise ValueError("VMware owner-context result is untrusted")
                return data
            sleep(1)
        raise ValueError("Timed owner-context VMware inventory did not complete")
    finally:
        if folder.is_symlink() or folder.stat().st_uid != uid:
            raise ValueError("VMware proof cleanup directory untrusted")
        if result.is_symlink():
            raise ValueError("VMware proof cleanup file untrusted")
        shutil.rmtree(folder)


def rehearse_offline_copy(original: bytes, vmnet: str, uid: int) -> tuple[str, str]:
    """Exercise real file write/restore on private scratch copy, never real VMX."""
    text = original.decode("utf-8", errors="strict")
    if text.encode("utf-8") != original or len(original) > 1024 * 1024:
        raise ValueError("VMX does not have canonical UTF-8 representation")
    modified = render_nat_offline(text, vmnet)
    proof = manifest(text, modified, vmnet)
    with tempfile.TemporaryDirectory(prefix="wslpe-vmx-rehearsal-") as folder:
        dest = Path(folder) / "windows_10.vmx"
        if Path(folder).stat().st_uid != uid:
            raise ValueError("Scratch VMX must be owned by same VMware user")
        dest.write_bytes(original)
        if sha256(dest.read_bytes()).hexdigest() != proof.before_sha256:
            raise ValueError("Scratch VMX original failed hash verification")
        dest.write_bytes(modified.encode("utf-8"))
        current = dest.read_bytes().decode("utf-8")
        recovered = guarded_original_restore(current, text, proof, vmnet)
        dest.write_bytes(recovered.encode("utf-8"))
        if dest.read_bytes() != original:
            raise ValueError("Scratch VMX recovery did not match original byte-for-byte")
    return proof.before_sha256, proof.after_sha256
