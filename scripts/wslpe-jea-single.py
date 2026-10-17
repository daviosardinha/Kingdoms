#!/usr/bin/env python3
"""Dedicated #30 JEA source plan or explicitly approved single-stage apply.

Does NOT restart WinRM, disable vagrant, restore snapshots or execute the
25-scenario batch. A source/registration success is NOT learner JEA proof.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kingdoms.wslpe45_batch_operator import (
    index_rows, controller_source_blockers, trusted_safety, command
)
from kingdoms.wslpe_vmrun_recovery import verify_vmrun_output

STAGE2 = ROOT / "scripts/wslpe-stage2-inspect.py"
JEA_AUDIT = ROOT / "scripts/wslpe-jea-readiness.py"
THUMB = "C773EC26D02940F559FE715B83628FEDAE2AA92D"
EXPECTED_SNAPSHOT = "KINGDOMS-WSLPE-PRE-JEA"
EXPECTED_ID = "jea_role_capability_misconfig"

def module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("Trusted module missing")
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

def local_candidate() -> dict:
    row = next((r for r in index_rows() if r["number"] == 30), None)
    if (not row or row["id"] != EXPECTED_ID or row["source_ci"] != "passed"
            or row["status"] != "candidate"):
        raise ValueError("JEA #30 is not source-qualified")
    path = ROOT / row["playbook"]
    if path.is_symlink() or not path.is_file():
        raise ValueError("Dedicated JEA source missing")
    import yaml
    plays = yaml.safe_load(path.read_text(encoding="utf-8"))
    if (not isinstance(plays, list) or len(plays) != 2
            or [p.get("hosts") for p in plays] != ["localhost", "wslpe"]
            or controller_source_blockers(path, plays)):
        raise ValueError("Dedicated JEA source dependencies or scope invalid")
    source = (ROOT / "ansible/files/wslpe45/WslpeJea.psm1").read_text(encoding="utf-8")
    if ("Register-PSSessionConfiguration" not in source
            or "-NoServiceRestart" not in source
            or "Restart-Service" in source
            or "Unregister-PSSessionConfiguration" not in source):
        raise ValueError("Unexpected JEA activation / rollback source")
    return row

def run_readonly_probe() -> None:
    response = subprocess.run(
        [sys.executable, str(JEA_AUDIT), "--expected-thumbprint", THUMB],
        cwd=ROOT, text=True, capture_output=True, timeout=75, check=False,
    )
    if (response.returncode != 0
            or "[PASS] WSLPE_JEA_CLEAN_PREEXISTING_STATE=TRUE" not in response.stdout):
        raise ValueError("JEA pre-existing state not clean or pinned HTTPS unavailable")
    print("[PASS] Exact clean JEA endpoint and pinned HTTPS transport")

def snapshot_and_running_owner() -> None:
    stage = module(STAGE2, "wslpe_jea_native_stage2")
    instance, meta = stage.find_instance(stage.WORKSPACE)
    if meta.get("lab") != "WSLPE":
        raise ValueError("Wrong standalone lab")
    vmx = stage.locate_registered_vm(instance)
    if (vmx.is_symlink() or not vmx.is_file()
            or not vmx.resolve().is_relative_to(stage.WORKSPACE.resolve())
            or vmx.stat().st_uid != os.geteuid()):
        raise ValueError("Registered VMX does not belong to exact VMware operator")
    running = subprocess.run(
        ["vmrun", "-T", "ws", "list"], text=True, capture_output=True,
        timeout=35, check=False,
    )
    if running.returncode:
        raise ValueError("VMware inventory unavailable")
    verify_vmrun_output(running.stdout, vmx)
    snapshots = subprocess.run(
        ["vmrun", "-T", "ws", "listSnapshots", str(vmx)],
        text=True, capture_output=True, timeout=70, check=False,
    )
    if (snapshots.returncode or
            snapshots.stdout.splitlines().count(EXPECTED_SNAPSHOT) != 1):
        raise ValueError("Expected recovery snapshot missing or ambiguous")
    print("[PASS] Exact running WSLPE VMX and pre-JEA recovery snapshot present")
    print("[NOT VERIFIED] Real snapshot restore and independent failure rollback")

def apply_jea(row: dict) -> None:
    safety = trusted_safety()
    inv, varsfile, expected = safety.exact_standalone()
    tools = Path.home() / ".goad/.venv/bin"
    ansible, ansible_inv = tools / "ansible-playbook", tools / "ansible-inventory"
    if not ansible.is_file() or not ansible_inv.is_file():
        raise ValueError("Pinned WSLPE Ansible runtime missing")
    env = os.environ.copy()
    env.update({
        "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg"),
        "ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles"),
        "ANSIBLE_NOCOLOR": "1",
    })
    resolved = subprocess.run(
        safety.resolved_inventory_command(ansible_inv, inv, varsfile),
        cwd=ROOT, env=env, text=True, capture_output=True, timeout=45, check=False)
    if resolved.returncode:
        raise ValueError("Inventory resolution failed")
    safety.check_inventory(json.loads(resolved.stdout), expected)
    request = command(ansible, inv, varsfile, row, expected, "apply", None, "apply")
    print("[APPLY] One JEA #30 registration only; no WinRM restart or batch execution", flush=True)
    try:
        result = subprocess.run(request, cwd=ROOT, env=env, timeout=300,
                                check=False)
    except subprocess.TimeoutExpired:
        raise ValueError("JEA apply timed out; inspect partial registration via console")
    if result.returncode:
        raise ValueError("JEA apply failed; inspect partial registration via console")
    print("[PASS] Ansible #30 JEA registration stage completed")
    print("[NOT VERIFIED] Learner JEA connectivity and endpoint execution context")
    print("[NEXT] Verify JEA endpoint locally; do not restart WinRM blindly")

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="explicit single-guest registration")
    p.add_argument("--recovery-rehearsed", action="store_true",
                   help="assert separately verified real-VM snapshot recovery")
    args = p.parse_args()
    print("KINGDOMS WSLPE | #30 JEA SINGLE-TECHNIQUE GATE", flush=True)
    try:
        row = local_candidate()
        print("[PASS] #30 only source candidate validated")
        if not args.apply:
            print("[PLAN ONLY] No Windows, VMware, WinRM or NORTH actions")
            print("[REQUIRED] Verified real-VM restore, independent console and explicit approval")
            return 0
        if not args.recovery_rehearsed:
            raise ValueError("Verified REAL WSLPE recovery rehearsal is required before apply")
        if not sys.stdin.isatty():
            raise ValueError("Interactive local operator approval required")
        snapshot_and_running_owner()
        run_readonly_probe()
        answer = input("Type APPLY WSLPE JEA 30 to register only #30: ").strip()
        if answer != "APPLY WSLPE JEA 30":
            raise ValueError("Operator cancelled JEA registration")
        apply_jea(row)
        return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError,
            subprocess.SubprocessError) as exc:
        print(f"[BLOCKED] {type(exc).__name__}; no automatic VM restore or retry", flush=True)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
