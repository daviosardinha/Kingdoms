#!/usr/bin/env python3
"""Exact-WSLPE, read-only Task Scheduler COM feasibility probe for advanced #21.

Default: local plan with no network/guest/VM mutations. --execute
invokes ONLY ansible/wslpe-advanced21-probe.yml against the registered
native workgroup WSLPE-WS01, after the same strict instance/inventory
gates used by the 20/20-qualified original foundation.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "scripts/wslpe-fast-track-20.py"
PROBE = ROOT / "ansible/wslpe-advanced21-probe.yml"

def baseline():
    if not BASE.is_file():
        raise ValueError("Existing exact-WSLPE operator base is missing")
    spec = importlib.util.spec_from_file_location("wslpe_operator_advanced21", BASE)
    if not spec or not spec.loader:
        raise ValueError("Cannot load trusted WSLPE operator gate")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="run only the read-only native WSLPE Windows probe")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    return parser

def run(args):
    if not 60 <= args.timeout_seconds <= 900:
        raise ValueError("Advanced probe timeout must be 60–900 seconds")
    if PROBE.is_symlink() or not PROBE.is_file():
        raise ValueError("Standalone advanced #21 probe is missing or symlinked")
    base = baseline()
    inventory, varsfile, expected = base.exact_standalone()
    if not args.execute:
        print(f"[PLAN] Advanced #21 read-only Task Scheduler inspection for WSLPE-WS01 ({expected})")
        print("[PLAN] No task edits, no privilege assignment, no NORTH changes, no VM lifecycle")
        return 0

    tools = Path.home() / ".goad/.venv/bin"
    ansible = tools / "ansible-playbook"
    ansible_inventory = tools / "ansible-inventory"
    if not ansible.is_file() or not ansible_inventory.is_file():
        raise ValueError("Existing GOAD Ansible operator environment not installed")
    env = os.environ.copy()
    env["ANSIBLE_CONFIG"] = str(ROOT / "ansible/ansible.cfg")
    env["ANSIBLE_ROLES_PATH"] = str(ROOT / "ansible/roles")
    env["ANSIBLE_NOCOLOR"] = "1"

    checked = subprocess.run(
        base.resolved_inventory_command(ansible_inventory, inventory, varsfile),
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=40, check=False)
    if checked.returncode:
        raise ValueError("Native WSLPE inventory resolution failed")
    base.check_inventory(json.loads(checked.stdout), expected)

    print("[TARGET] Exact WSLPE-WS01 inventory and WinRM transport accepted", flush=True)
    print("[RUN] Advanced #21 read-only Task Scheduler security descriptor capability probe", flush=True)
    command = [str(ansible), "-i", str(inventory), "-i", str(varsfile),
               "--limit", "ws01,localhost", str(PROBE)]
    try:
        result = subprocess.run(command, cwd=ROOT, env=env,
                                capture_output=True, text=True,
                                timeout=args.timeout_seconds, check=False)
        status, diagnostic = result.returncode, result.stdout + "\n" + result.stderr
    except subprocess.TimeoutExpired:
        status, diagnostic = 124, "Advanced #21 read-only inspection timed out"
    if status:
        root = base.private_report_dir(str(
            Path.home() / ".local/state/kingdoms-wslpe-qualification"))
        private = base.private_failure_log(root, "adv21-probe", diagnostic)
        print(f"[BLOCKED] WSLPE advanced #21 read-only probe exit={status}")
        print(f"[DIAGNOSTIC] Private Ansible log: {private} (redact before sharing)")
        print("[STOP] No advanced scenario deployed")
        return 2
    expected_markers = (
        "WSLPE_ADV21_GUEST=EXACT",
        "WSLPE_ADV21_LOCAL_LEARNER=NONADMIN",
        "WSLPE_ADV21_TASK_COM_DACL_READ=PASS",
        "WSLPE_ADV21_PROBE_READ_ONLY=TRUE",
    )
    if any(marker not in diagnostic for marker in expected_markers):
        # Ansible can succeed with an omitted/skipped guest task. Never
        # accept exit=0 alone as a Windows feasibility result.
        root = base.private_report_dir(str(
            Path.home() / ".local/state/kingdoms-wslpe-qualification"))
        private = base.private_failure_log(root, "adv21-probe-marker", diagnostic)
        print("[BLOCKED] WSLPE guest did not return all expected probe markers")
        print(f"[DIAGNOSTIC] Private Ansible log: {private} (redact before sharing)")
        return 2
    print("[PASS] Advanced #21 native WSLPE task ACL read feasibility verified")
    print("[NEXT] Implement dedicated SYSTEM task definition fixture; no task was modified")
    return 0

def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        # Never display full command output, WinRM credentials or hostvars.
        msg = str(exc) if type(exc) is ValueError else type(exc).__name__
        print(f"[BLOCKED] Advanced #21 standalone probe: {msg}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
