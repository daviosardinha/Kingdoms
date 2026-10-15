#!/usr/bin/env python3
"""Read-only diagnosis of an existing WSLPE VM's Vagrant/VMware state.

Do not start, reload, halt, destroy, repair or provision any VM. Resolve the
native WSLPE instance from Kingdoms and compare its registered VMX to the
actual VMware Workstation running inventory and Vagrant read-only status.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
STAGE2_SOURCE = ROOT / "scripts/wslpe-stage2-inspect.py"
MACHINE = "WSLPE-WS01"


def load_stage2():
    spec = importlib.util.spec_from_file_location("wslpe_state_base", STAGE2_SOURCE)
    if spec is None or spec.loader is None:
        raise ValueError("WSLPE source inspector unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_vmrun(stdout: str) -> list[Path]:
    """Normalize paths but preserve complete inventory for diagnosis."""
    lines = stdout.splitlines()
    if not lines or not lines[0].startswith("Total running VMs:"):
        raise ValueError("vmrun output was not a valid Workstation running-VM inventory")
    try:
        advertised = int(lines[0].split(":", 1)[1].strip())
    except (ValueError, IndexError) as exc:
        raise ValueError("Invalid running-VM inventory count") from exc
    paths = [Path(line.strip()).resolve(strict=False) for line in lines[1:]
             if line.strip()]
    if len(paths) != advertised:
        raise ValueError(
            "VMware running-VM inventory count and returned paths disagree"
        )
    return paths


def registered_vmx(instance: Path) -> Path:
    id_file = (
        instance / "provider/.vagrant/machines" / MACHINE
        / "vmware_desktop/id"
    )
    if not id_file.is_file() or id_file.is_symlink():
        raise ValueError("WSLPE Vagrant registration ID is missing or symlinked")
    raw = id_file.read_text(encoding="utf-8").strip()
    if not raw or not Path(raw).is_absolute():
        raise ValueError("WSLPE registered VMX path missing or not absolute")
    vmx = Path(raw).resolve(strict=False)
    if vmx.suffix.lower() != ".vmx" or "GOAD-" in str(vmx).upper():
        raise ValueError("Registered VMX is invalid or references a NORTH VM")
    return vmx


def run_read_only(args: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            args, cwd=str(cwd) if cwd is not None else None,
            capture_output=True, text=True, check=False, timeout=35,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 99, "", f"{type(exc).__name__}: read-only command unavailable"


def evaluate_registration(vmx: Path, running: list[Path]) -> tuple[str, int]:
    count = running.count(vmx)
    if count == 1:
        return "MATCHED", count
    if count > 1:
        return "AMBIGUOUS", count
    same_name = [p for p in running if p.name.casefold() == vmx.name.casefold()]
    return ("SAME_FILENAME_DIFFERENT_PATH" if same_name
            else "NOT_IN_RUNNING_INVENTORY"), 0


def main() -> int:
    print("KINGDOMS WSLPE | NATIVE VM REGISTRATION & POWER-STATE DIAGNOSTIC")
    print("[READ ONLY] No VM power, Vagrant lifecycle, NAT, firewall or NORTH changes")
    try:
        stage2 = load_stage2()
        instance, info = stage2.find_instance(stage2.WORKSPACE)
        vmx = registered_vmx(instance)
    except (OSError, ValueError) as exc:
        print(f"[BLOCKED] Native WSLPE instance registration: {exc}")
        return 1

    print(f"[INFO] WSLPE instance: {info['id']} | state={info['status']}")
    print(f"[INFO] Registered VMX: {vmx}")
    print(f"[INFO] Registered VMX file exists: {vmx.is_file()}")

    rc, output, stderr = run_read_only(["vmrun", "-T", "ws", "list"])
    if rc != 0:
        print(f"[BLOCKED] vmrun running inventory unavailable, exit={rc}")
        if stderr:
            print(f"[INFO] vmrun error: {stderr[:500]}")
        return 1
    try:
        running = parse_vmrun(output)
    except ValueError as exc:
        print(f"[BLOCKED] {exc}")
        return 1

    print(f"[INFO] VMware reports {len(running)} running VM(s)")
    for path in running:
        print(f"  [VMRUN] {path}")
    result, count = evaluate_registration(vmx, running)
    print(f"[RESULT] Exact native WSLPE VMX match: {result} (count={count})")
    if result == "NOT_IN_RUNNING_INVENTORY":
        print("[NOTE] Registered WSLPE guest is absent from vmrun's running inventory.")
        print("       This does not establish why it is missing or whether it is safely stopped.")
    elif result == "SAME_FILENAME_DIFFERENT_PATH":
        print("[NOTE] Another running VMX has the same filename, but a different path.")
        print("       Do not switch or rewrite Vagrant registration automatically.")

    # Vagrant status is read-only and runs in the existing operator context.
    rc, out, err = run_read_only(
        ["vagrant", "status", MACHINE], cwd=instance / "provider"
    )
    if rc == 0:
        lines = out.splitlines()
        print("[INFO] Vagrant status:")
        for line in lines[:18]:
            print(f"  {line}")
    else:
        print(f"[BLOCKED] Vagrant status unavailable, exit={rc}")
        if err:
            print(f"[INFO] Vagrant error: {err[:500]}")

    if result != "MATCHED" or not vmx.is_file() or rc != 0:
        print("[LOCKED] Do not retry install, power-on, destroy or reconfigure WSLPE.")
        print("[NEXT] Reconcile the exact Vagrant registration and VMware power state.")
        return 1
    print("[PASS] Native registered VMX is uniquely running and Vagrant status was readable")
    print("[NEXT] Re-run WSLPE network acceptance only; no boot needed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
