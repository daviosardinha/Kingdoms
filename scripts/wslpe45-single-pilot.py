#!/usr/bin/env python3
"""Isolated #28 WSLPE qualification pilot; NOT the 25-scenario release gate.

No guest contacts without --execute. Intentionally allows only one source-
reviewed candidate. Failed guest writes keep a private recovery sentinel.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
from secrets import token_hex

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kingdoms import wslpe45_batch_operator as batch

PILOTS = {"app_paths_registry_hijack": 28}
PREFLIGHT = ROOT / "ansible/wslpe45/pilot28-preflight.yml"
BRANCHES = {"feature/windows-lpe-45-batch", "feature/wslpe45-single-candidate-pilot"}
FLOW = batch.FLOW


def source_gate(technique: str) -> dict:
    """Run the existing 25-row source checks, but gate only the chosen row."""
    if technique not in PILOTS:
        raise batch.BatchBlocked("Technique has not been individually authorized for a pilot")
    rows, blockers = batch.source_readiness()
    number = PILOTS[technique]
    row = next((r for r in rows if r["number"] == number and r["id"] == technique), None)
    if row is None or row["status"] != "candidate" or row["source_ci"] != "passed":
        raise batch.BatchBlocked("Pilot candidate is not source-qualified")
    relevant = [msg for msg in blockers if msg.startswith(f"#{number:02d} ")]
    if relevant:
        raise batch.BatchBlocked("Pilot candidate source blocked: " + "; ".join(relevant))
    return row


def clean_head() -> str:
    """Refuse testing a different checkout or unstaged source changes."""
    def git(*args: str) -> str:
        result = subprocess.run(["git", *args], cwd=ROOT, text=True,
                                capture_output=True, timeout=30, check=False)
        if result.returncode:
            raise batch.BatchBlocked("Git provenance verification failed")
        return result.stdout.strip()
    if git("branch", "--show-current") not in BRANCHES:
        raise batch.BatchBlocked("Pilot must run from its reviewed feature branch")
    if git("status", "--porcelain"):
        raise batch.BatchBlocked("Pilot source checkout must be clean")
    return git("rev-parse", "HEAD")


def snapshot_gate() -> None:
    """Reuse the already approved registered WSLPE native VMware snapshot gate."""
    path = ROOT / "scripts/wslpe40-stage.py"
    if path.is_symlink() or not path.is_file():
        raise batch.BatchBlocked("Pinned WSLPE VM snapshot guard missing")
    spec = importlib.util.spec_from_file_location("wslpe_pilot_snapshot", path)
    if not spec or not spec.loader:
        raise batch.BatchBlocked("Cannot import WSLPE snapshot guard")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.verify_vm_snapshot(None)


def execute_stage(ansible: Path, inv: Path, varsfile: Path, row: dict,
                  expected: str, action: str, state: str | None, label: str,
                  env: dict, timeout: int) -> tuple[bool, int, str]:
    cmd = batch.command(ansible, inv, varsfile, row, expected, action, state, label)
    try:
        completed = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True,
                                   text=True, timeout=timeout, check=False)
        diagnostics = completed.stdout + "\n" + completed.stderr
        rc = completed.returncode
    except subprocess.TimeoutExpired:
        diagnostics, rc = "Exact standalone WSLPE step timed out", 124
    marker = f"WSLPE45_BATCH_STAGE={row['id']}:{label}:PASS"
    return (rc == 0 and diagnostics.count(marker) == 1), rc, diagnostics


def run(args: argparse.Namespace) -> int:
    row = source_gate(args.technique)
    print(f"[PILOT] #{row['number']} {row['id']} (only); NORTH untouched", flush=True)
    print("[NOT RELEASE] Lifecycle checks do not establish learner exploitation", flush=True)
    if not args.execute:
        print("[PLAN ONLY] No VMware, WinRM, Ansible or guest access", flush=True)
        print("[SEQUENCE] read-only clean preflight, then apply/validate/reset/clean/reapply/validate", flush=True)
        print("[EXECUTE] Requires a clean reviewed checkout and a native WSLPE snapshot", flush=True)
        return 0
    if not 60 <= args.timeout_seconds <= 3600:
        raise batch.BatchBlocked("Pilot timeout must be between 60 and 3600 seconds")

    head = clean_head()
    base = batch.trusted_safety()
    inv, varsfile, expected = base.exact_standalone()
    if ipaddress.ip_address(expected) in ipaddress.ip_network("10.4.0.0/16"):
        raise batch.BatchBlocked("NORTH network is never a pilot target")
    snapshot_gate()

    venv = Path.home() / ".goad/.venv/bin"
    ansible, ansible_inv = venv / "ansible-playbook", venv / "ansible-inventory"
    if not ansible.is_file() or not ansible_inv.is_file():
        raise batch.BatchBlocked("Trusted WSLPE Ansible tools missing")
    env = os.environ.copy()
    env.update({"ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg"),
                "ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles"),
                "ANSIBLE_NOCOLOR": "1"})
    inventory = subprocess.run(base.resolved_inventory_command(ansible_inv, inv, varsfile),
                               cwd=ROOT, env=env, capture_output=True,
                               text=True, timeout=40, check=False)
    if inventory.returncode:
        raise batch.BatchBlocked("WSLPE-only inventory cannot be resolved")
    base.check_inventory(json.loads(inventory.stdout), expected)

    root = batch.make_private_dir(args.report_dir)
    sentinel = root / ".wslpe45-recovery-required"
    lock = root / ".wslpe45-single-run.lock"
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if sentinel.exists() or sentinel.is_symlink():
            raise batch.BatchBlocked("Unresolved WSLPE45 recovery sentinel; no new deployment")
        # Independent read-only Windows inspection: the candidate module is
        # deliberately NOT imported before it exists. No fixture adoption.
        if PREFLIGHT.is_symlink() or not PREFLIGHT.is_file():
            raise batch.BatchBlocked("Missing reviewed #28 clean-state preflight")
        print("[PREFLIGHT] Check absent #28 task/key/fixture without writing", flush=True)
        cmd = [str(ansible), "-i", str(inv), "-i", str(varsfile),
               "--limit", "ws01,localhost", str(PREFLIGHT), "-e",
               json.dumps({"wslpe_expected_address": expected}, separators=(",", ":"))]
        try:
            result = subprocess.run(cmd, cwd=ROOT, env=env, text=True,
                                    capture_output=True, timeout=args.timeout_seconds,
                                    check=False)
            diagnostics = result.stdout + "\n" + result.stderr
            rc = result.returncode
        except subprocess.TimeoutExpired:
            diagnostics, rc = "Standalone clean-state preflight timed out", 124
        if rc or diagnostics.count("WSLPE45_PILOT28_CLEAN=PASS") != 1:
            failure = base.private_failure_log(root, "pilot-28-preflight", diagnostics)
            print(f"[BLOCKED] Existing/unknown #28 state; exit={rc}", flush=True)
            print(f"[PRIVATE] {failure} (redact before sharing)", flush=True)
            return 2

        report = {"schema": "kingdoms.wslpe45.single-pilot.v1", "target": "WSLPE-WS01",
                  "technique": row["id"], "number": row["number"], "commit": head,
                  "created_at": datetime.now(timezone.utc).isoformat(),
                  "completed": False, "learner_proof": "not_verified", "events": []}
        name = "wslpe45-pilot-28-" + token_hex(8) + ".json"
        report_path = batch.atomic_report(root, name, report)
        markerfd = os.open(sentinel, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(markerfd)
        for action, state, label in FLOW:
            ok, rc, diagnostics = execute_stage(ansible, inv, varsfile, row,
                                                expected, action, state, label, env,
                                                args.timeout_seconds)
            report["events"].append({"stage": label, "accepted": ok, "exit_code": rc})
            batch.atomic_report(root, name, report)
            if not ok:
                failure = base.private_failure_log(root, "pilot-28-" + label, diagnostics)
                print(f"[BLOCKED] #28 {label}; recovery sentinel retained", flush=True)
                print(f"[PRIVATE] {failure} (redact before sharing)", flush=True)
                print(f"[RECOVERY] {report_path}", flush=True)
                return 2
            print(f"[PASS] #28 {label}", flush=True)
        report["completed"] = True
        report["completed_at"] = datetime.now(timezone.utc).isoformat()
        batch.atomic_report(root, name, report)
        sentinel.unlink()
        print(f"[PASS] #28 six-stage fixture lifecycle; report: {report_path}", flush=True)
        print("[PENDING] Verify actual exploit from lpe.trainee before qualification", flush=True)
        return 0
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--technique", default="app_paths_registry_hijack")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--report-dir", default="~/.local/state/kingdoms-wslpe45-live")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        detail = str(exc) if isinstance(exc, batch.BatchBlocked) else type(exc).__name__
        print("[BLOCKED] WSLPE45 isolated pilot: " + detail, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
