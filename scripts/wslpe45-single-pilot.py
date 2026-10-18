#!/usr/bin/env python3
"""Isolated #28 WSLPE qualification pilot; NOT the 25-scenario release gate.

Guest inspection requires --preflight; only --execute permits fixture writes.
Intentionally allows one source-reviewed candidate and preserves failure state.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
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


def runtime_workspace(override: str | None) -> Path:
    """Use actual native registration, not the fresh Git worktree's empty workspace.

    Only a verified, owner-controlled native WSLPE workspace may be selected.
    Multiple valid registrations are deliberately ambiguous.
    """
    helper = ROOT / "scripts/wslpe-stage2-inspect.py"
    if helper.is_symlink() or not helper.is_file():
        raise batch.BatchBlocked("Native WSLPE registration helper unavailable")
    spec = importlib.util.spec_from_file_location("wslpe_pilot_instance", helper)
    if not spec or not spec.loader:
        raise batch.BatchBlocked("Cannot load native WSLPE registration helper")
    stage = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stage)
    candidates = ([Path(override).expanduser()] if override else [
        ROOT / "workspace",
        Path.home() / "kingdoms-lpe-standalone/workspace",
        Path.home() / "kingdoms-rebuild/workspace",
    ])
    verified = []
    for candidate in candidates:
        if (not candidate.is_dir() or candidate.is_symlink()
                or candidate.stat().st_uid != os.geteuid()):
            continue
        try:
            stage.find_instance(candidate)
        except (OSError, ValueError):
            continue
        verified.append(candidate.resolve(strict=True))
    verified = list(dict.fromkeys(verified))
    if len(verified) != 1:
        raise batch.BatchBlocked(
            "Native WSLPE registration not uniquely found (matches="
            + str(len(verified))
            + "); supply --workspace with the original Kingdoms workspace directory"
        )
    return verified[0]


def snapshot_gate(workspace: Path) -> None:
    """Reuse pinned native WSLPE VMware snapshot check on verified workspace."""
    path = ROOT / "scripts/wslpe40-stage.py"
    if path.is_symlink() or not path.is_file():
        raise batch.BatchBlocked("Pinned WSLPE VM snapshot guard missing")
    spec = importlib.util.spec_from_file_location("wslpe_pilot_snapshot", path)
    if not spec or not spec.loader:
        raise batch.BatchBlocked("Cannot import WSLPE snapshot guard")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.verify_vm_snapshot(module.load_preflight(), workspace=workspace)


def execute_stage(ansible: Path, inv: Path, varsfile: Path, row: dict,
                  expected: str, action: str, state: str | None, label: str,
                  env: dict, timeout: int, preserve_shared: bool) -> tuple[bool, int, str]:
    cmd = batch.command(ansible, inv, varsfile, row, expected, action, state, label)
    vars_requested = json.loads(cmd[-1])
    vars_requested["wslpe_pilot_preserve_shared"] = preserve_shared
    cmd[-1] = json.dumps(vars_requested, separators=(",", ":"))
    try:
        completed = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True,
                                   text=True, timeout=timeout, check=False)
        diagnostics = completed.stdout + "\n" + completed.stderr
        rc = completed.returncode
    except subprocess.TimeoutExpired:
        diagnostics, rc = "Exact standalone WSLPE step timed out", 124
    marker = f"WSLPE45_BATCH_STAGE={row['id']}:{label}:PASS"
    return (rc == 0 and diagnostics.count(marker) == 1), rc, diagnostics


def diagnostic_summary(complete_log: str) -> str:
    """Extract a bounded Windows/Ansible failure message; never dump secrets."""
    import re
    for line in complete_log.splitlines():
        if "fatal: [ws01]" not in line or "=>" not in line:
            continue
        try:
            response = json.loads(line.split("=>", 1)[1].strip())
        except (ValueError, TypeError):
            continue
        if not isinstance(response, dict):
            continue
        errors = response.get("error", [])
        for item in errors if isinstance(errors, list) else []:
            if not isinstance(item, dict):
                continue
            exception = item.get("exception", {})
            category = item.get("category_info", {})
            candidate = (
                exception.get("message") if isinstance(exception, dict) else None
            ) or (
                category.get("reason") if isinstance(category, dict) else None
            )
            if isinstance(candidate, str) and candidate.strip():
                candidate = candidate.strip().splitlines()[0][:280]
                if re.search(r"(?i)(password|credential|bearer|secret|token|cookie)\s*[:=]", candidate):
                    return "Windows error details contain sensitive content; see private log"
                return candidate
        message = response.get("msg")
        if isinstance(message, str) and message.strip():
            message = message.strip().splitlines()[0][:200]
            if not re.search(r"(?i)(password|credential|bearer|secret|token|cookie)\s*[:=]", message):
                return message
    return "Windows failure details unavailable; review private log"


def run(args: argparse.Namespace) -> int:
    row = source_gate(args.technique)
    print(f"[PILOT] #{row['number']} {row['id']} (only); NORTH untouched", flush=True)
    print("[NOT RELEASE] Lifecycle checks do not establish learner exploitation", flush=True)
    if not args.execute and not args.preflight:
        print("[PLAN ONLY] No VMware, WinRM, Ansible or guest access", flush=True)
        print("[SEQUENCE] read-only clean preflight, then apply/validate/reset/clean/reapply/validate", flush=True)
        print("[EXECUTE] Requires a clean reviewed checkout and a native WSLPE snapshot", flush=True)
        return 0
    if not 60 <= args.timeout_seconds <= 3600:
        raise batch.BatchBlocked("Pilot timeout must be between 60 and 3600 seconds")

    head = clean_head()
    workspace = runtime_workspace(args.workspace)
    print("[WORKSPACE] Unique original native WSLPE registration verified", flush=True)
    base = batch.trusted_safety()
    inv, varsfile, expected = base.exact_standalone(workspace)
    if ipaddress.ip_address(expected) in ipaddress.ip_network("10.4.0.0/16"):
        raise batch.BatchBlocked("NORTH network is never a pilot target")
    snapshot_gate(workspace)
    print("[VMWARE] Unique registered standalone VM and recovery snapshot verified", flush=True)

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
        common = ROOT / "ansible/files/wslpe45/WslpeFixture.psm1"
        if common.is_symlink() or not common.is_file():
            raise batch.BatchBlocked("Approved shared ownership library unavailable")
        digest = hashlib.sha256(common.read_bytes()).hexdigest().upper()
        cmd = [str(ansible), "-i", str(inv), "-i", str(varsfile),
               "--limit", "ws01,localhost", str(PREFLIGHT), "-e",
               json.dumps({"wslpe_expected_address": expected,
                           "wslpe_pilot_shared_sha256": digest}, separators=(",", ":"))]
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
            print(f"[BLOCKED] #28 Windows preflight exit={rc}", flush=True)
            print("[REASON] " + diagnostic_summary(diagnostics), flush=True)
            print(f"[PRIVATE] {failure} (redact before sharing)", flush=True)
            return 2
        present = diagnostics.count("WSLPE45_PILOT28_25_MODE=OWNED_MARKER_ONLY") == 1
        absent = diagnostics.count("WSLPE45_PILOT28_25_MODE=ABSENT") == 1
        if present == absent:
            raise batch.BatchBlocked("Cannot establish an unambiguous #25 overlap state")
        if present:
            print("[PRESERVE] #25 marker-only owned fixture verified; shared library writes disabled", flush=True)
        if args.preflight:
            print("[PASS] #28 read-only guest preflight; no scenario writes", flush=True)
            return 0

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
                                                args.timeout_seconds, present)
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
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--preflight", action="store_true")
    parser.add_argument("--workspace", default=None,
                        help="original Kingdoms native workspace, not the fresh Git worktree")
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
