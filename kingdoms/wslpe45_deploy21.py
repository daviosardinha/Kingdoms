"""Installation coordinator using existing WSLPE source and native safety gates.

Existing #30 is retained and independently validated, never re-registered.
No reset, recovery bypass, implicit resume, account creation or network changes.
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
import re
import subprocess
from secrets import token_hex
import yaml
from kingdoms import wslpe45_batch_operator as batch
from kingdoms.wslpe_learner_credentials import learner_password

ROOT = batch.ROOT
BRANCH = "feature/wslpe45-single-candidate-pilot"
EXCLUDED = {25: "msi_repair_custom_action", 36: "wmi_privileged_provider_authorization",
            38: "dcom_server_launch_acl", 40: "custom_rpc_authorization"}
SELECTED = tuple(n for n in range(21, 46) if n not in EXCLUDED)
FLOW = (("apply", None, "apply"), ("validate", "vulnerable", "vulnerable"))
STATE = Path.home() / ".local/state/kingdoms-wslpe45-live"
PREFLIGHT = ROOT / "ansible/wslpe45/deploy21-preflight.yml"
JEA = ROOT / "ansible/wslpe45/deploy21-jea-status.yml"

def now():
    return datetime.now(timezone.utc).isoformat()

def helper(name):
    path = ROOT / "scripts" / name
    if path.is_symlink() or not path.is_file():
        raise batch.BatchBlocked("Native helper missing or linked")
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def selection():
    rows, blockers = batch.source_readiness()
    picked = [r for r in rows if r["number"] in SELECTED]
    if tuple(r["number"] for r in picked) != SELECTED or len(picked) != 21:
        raise batch.BatchBlocked("Exactly 21 ordered candidates required")
    if {r["number"]: r["id"] for r in rows if r["number"] in EXCLUDED} != EXCLUDED:
        raise batch.BatchBlocked("Explicit exclusion identity mismatch")
    failures = [b for b in blockers if any(b.startswith(f"#{n:02d} ") for n in SELECTED)]
    if failures:
        raise batch.BatchBlocked("; ".join(failures))
    return picked

def provenance():
    def git(*args):
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                           text=True, timeout=30, check=False)
        if r.returncode:
            raise batch.BatchBlocked("Git provenance query failed")
        return r.stdout.strip()
    if git("branch", "--show-current") != BRANCH or git("status", "--porcelain"):
        raise batch.BatchBlocked("Clean exact deployment branch required")
    origin = git("remote", "get-url", "origin").removesuffix(".git").rstrip("/")
    if origin not in ("https://github.com/daviosardinha/Kingdoms",
                      "git@github.com:daviosardinha/Kingdoms"):
        raise batch.BatchBlocked("Unexpected GitHub origin")
    head = git("rev-parse", "HEAD")
    if head != git("rev-parse", "refs/remotes/origin/" + BRANCH):
        raise batch.BatchBlocked("HEAD differs from fetched GitHub branch")
    return head

def durable(root, name, value):
    path = batch.atomic_report(root, name, value)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return path

def run_command(cmd, env, timeout):
    try:
        r = subprocess.run(cmd, cwd=ROOT, env=env, text=True,
                           capture_output=True, timeout=timeout, check=False)
        return r.returncode, r.stdout + "\n" + r.stderr
    except subprocess.TimeoutExpired as exc:
        def decode(x):
            return x.decode("utf-8", errors="replace") if isinstance(x, bytes) else x or ""
        return 124, decode(exc.stdout) + "\n" + decode(exc.stderr) + "\nTIMEOUT; guest state unknown"

def ansible_command(ansible, inv, varsfile, path, extra):
    return [str(ansible), "-i", str(inv), "-i", str(varsfile),
            "--limit", "ws01,localhost", str(path), "-e",
            json.dumps(extra, separators=(",", ":"))]

def stage_command(ansible, inv, varsfile, row, expected, action, state, label):
    if not any(r["number"] == row["number"] and r["id"] == row["id"]
               for r in batch.index_rows()):
        raise batch.BatchBlocked("Scenario number/name mismatch")
    if row["number"] not in SELECTED or (action, state, label) not in FLOW:
        raise batch.BatchBlocked("Non-deployment action or excluded scenario")
    # Preserve the known console-activated JEA installation. Never claim a
    # new registration or bypass the PS5.1 transport guard.
    if row["number"] == 30:
        action, state, label = "validate", "vulnerable", "vulnerable"
    cmd = batch.command(ansible, inv, varsfile, row, expected, action, state, label)
    extra = json.loads(cmd[-1])
    extra.update(wslpe_pilot_preserve_shared=True, wslpe_deploy21=True)
    cmd[-1] = json.dumps(extra, separators=(",", ":"))
    return cmd, f"WSLPE21_STAGE={row['id']}:{label}:PASS"

def deployment_loop(rows, report, checkpoint, invoke):
    """Persist intent BEFORE each step; failure leaves prior successes intact."""
    for row, record in zip(rows, report["scenarios"]):
        for action, state, label in FLOW:
            report["inflight"] = {"number": row["number"], "stage": label, "started_at": now()}
            checkpoint()
            ok, detail = invoke(row, action, state, label)
            result = "PASS_EXISTING" if ok and action == "apply" and row["number"] == 30 else ("PASS" if ok else "FAIL")
            record["installation" if action == "apply" else "configuration_validation"] = result
            record["updated_at"] = now()
            record["events"].append(dict(stage=label, result=result, **detail))
            if not ok:
                report["failure"] = {"number": row["number"], "stage": label, **detail}
                report["inflight"] = None
                checkpoint()
                return 2
            report["inflight"] = None
            checkpoint()
            print(f"[{result}] #{row['number']} {row['id']} / {label}", flush=True)
    report["completed"] = True
    report["completed_at"] = now()
    checkpoint()
    return 0

def require_recovery_clear(root):
    sentinel = root / ".wslpe45-recovery-required"
    if sentinel.exists() or sentinel.is_symlink():
        raise batch.BatchBlocked("Unresolved recovery journal; do not rerun or delete sentinel")
    return sentinel

def run(args):
    rows = selection()
    print("[SCOPE] WSLPE-WS01 only; selected=" + ",".join(map(str, SELECTED)), flush=True)
    print("[EXCLUDED] 25,36,38,40; #30 retained, inspected and tested without re-registration", flush=True)
    if not args.execute:
        print("[PLAN] 21 ordered apply/validate pairs; #30 existing-state validation; no guest access")
        return 0
    if not 60 <= args.timeout_seconds <= 3600:
        raise batch.BatchBlocked("Timeout must be 60..3600 seconds")
    head = provenance()
    pilot = helper("wslpe45-single-pilot.py")
    workspace = pilot.runtime_workspace(args.workspace)
    base = batch.trusted_safety()
    inv, varsfile, expected = base.exact_standalone(workspace)
    if ipaddress.ip_address(expected) in ipaddress.ip_network("10.4.0.0/16"):
        raise batch.BatchBlocked("Forbidden domain lab network")
    pilot.snapshot_gate(workspace)
    native = helper("wslpe-stage2-inspect.py")
    instance, metadata = native.find_instance(workspace)
    vmx = native.locate_registered_vm(instance)
    live = subprocess.run(["vmrun", "-T", "ws", "list"], capture_output=True,
                          text=True, timeout=30, check=False)
    if live.returncode or live.stdout.splitlines().count(str(vmx)) != 1:
        raise batch.BatchBlocked("Exact registered WSLPE guest is not uniquely running")
    venv = Path.home() / ".goad/.venv/bin"
    ansible, inventory = venv / "ansible-playbook", venv / "ansible-inventory"
    if not ansible.is_file() or not inventory.is_file():
        raise batch.BatchBlocked("Existing Ansible runtime unavailable")
    env = os.environ.copy()
    env.update(ANSIBLE_CONFIG=str(ROOT / "ansible/ansible.cfg"),
               ANSIBLE_ROLES_PATH=str(ROOT / "ansible/roles"),
               ANSIBLE_NOCOLOR="1", ANSIBLE_STDOUT_CALLBACK="default",
               ANSIBLE_DISPLAY_ARGS_TO_STDOUT="false")
    env["KINGDOMS_WSLPE_LEARNER_PASSWORD"] = learner_password(bootstrap=False, environ=env)
    resolved = subprocess.run(base.resolved_inventory_command(inventory, inv, varsfile),
                              cwd=ROOT, env=env, capture_output=True, text=True,
                              timeout=40, check=False)
    if resolved.returncode:
        raise batch.BatchBlocked("Cannot resolve standalone inventory")
    data = json.loads(resolved.stdout)
    base.check_inventory(data, expected)
    if set(data.get("_meta", {}).get("hostvars", {})) != {"ws01"}:
        raise batch.BatchBlocked("Unexpected inventory host")
    auth = helper("wslpe-https-auth-audit.py")
    tls = auth.tls_audit_module()
    pin = helper("wslpe40-stage.py").PIN
    der = tls.read_untrusted_tls_leaf(expected)
    fingerprint = tls.expected_fingerprint(pin)
    if tls.cert_fingerprint(der) != fingerprint:
        raise batch.BatchBlocked("Pinned management certificate mismatch")
    tls.verify_pinned_tls(expected, der, fingerprint)
    host = data["_meta"]["hostvars"]["ws01"]
    auth.authenticated_read_only_probe(expected, der, host["ansible_user"], host["ansible_password"])
    # Default state path is deliberately not overridable: a different report
    # directory must not bypass an outstanding batch/pilot recovery sentinel.
    root = batch.make_private_dir(str(STATE))
    fd = os.open(root / ".wslpe45-single-run.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        sentinel = require_recovery_clear(root)
        report = {"schema": "kingdoms.wslpe45.deploy21.v1", "commit": head,
                  "target": "WSLPE-WS01", "address": expected, "workspace": str(workspace),
                  "inventory": str(inv), "vmx": str(vmx),
                  "snapshot": helper("wslpe40-stage.py").SNAPSHOT, "created_at": now(), "completed": False,
                  "source_implemented": True, "learner_exploitation": "NOT_PROVEN_BY_THIS_RUN",
                  "baseline_count": 20, "baseline_count_basis": "operator reported; not recounted",
                  "exclusions": EXCLUDED, "inflight": None, "failure": None,
                  "scenarios": [{"number": r["number"], "name": r["id"],
                      "installation": "NOT_ATTEMPTED", "configuration_validation": "NOT_ATTEMPTED",
                      "exploitation": "NOT_TESTED", "events": []} for r in rows]}
        name = "wslpe45-deploy21-" + token_hex(8) + ".json"
        def checkpoint():
            report["runtime_configuration_pass_count"] = sum(
                r["configuration_validation"] == "PASS" for r in report["scenarios"])
            durable(root, name, report)
        checkpoint()
        print(f"[JOURNAL] {root / name}", flush=True)
        extra = {"wslpe_expected_address": expected,
                 "wslpe_pilot_shared_sha256": hashlib.sha256(
                     (ROOT / "ansible/files/wslpe45/WslpeFixture.psm1").read_bytes()).hexdigest().upper()}
        baseline = None
        def guard():
            nonlocal baseline
            rc, log = run_command(ansible_command(ansible, inv, varsfile, PREFLIGHT, extra),
                                  env, args.timeout_seconds)
            evidence = re.findall(r"WSLPE21_PRESERVED=([A-F0-9]{64})", log)
            ok = rc == 0 and log.count("WSLPE21_PREFLIGHT=PASS") == 1 and len(evidence) == 1
            if ok and baseline is not None and evidence[0] != baseline:
                ok = False
            if ok:
                baseline = evidence[0]
                report["preserved_state_sha256"] = baseline
            return ok, rc, log
        ok, rc, log = guard()
        if not ok:
            path = base.private_failure_log(root, "deploy21-preflight", log)
            report["failure"] = {"stage": "preflight", "exit_code": rc, "private_log": str(path)}
            checkpoint()
            print(f"[FAIL] Read-only preflight; evidence: {path}", flush=True)
            return 2
        # Journal pointer is durable before the first possible guest mutation.
        guardfd = os.open(sentinel, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(guardfd, "w") as handle:
            handle.write(name + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        checkpoint()
        def invoke(row, action, state, label):
            ok, rc, log = guard()
            if ok:
                cmd, marker = stage_command(ansible, inv, varsfile, row, expected, action, state, label)
                rc, log = run_command(cmd, env, args.timeout_seconds)
                ok = rc == 0 and log.count(marker) == 1
            if ok and row["number"] == 30:
                rc, fresh = run_command(ansible_command(ansible, inv, varsfile, JEA, extra),
                                        env, args.timeout_seconds)
                log += "\n" + fresh
                ok = rc == 0 and fresh.count("WSLPE21_JEA_ACTIVE=PASS") == 1
            if ok:
                safe, guardrc, guardlog = guard()
                log += "\n" + guardlog
                if not safe:
                    ok, rc = False, guardrc
            path = base.private_failure_log(root, f"deploy21-{row['number']}-{label}", log)
            return ok, {"exit_code": rc, "private_log": str(path),
                        "failure_details": None if ok else "Command, exact evidence or preservation check failed"}
        try:
            result = deployment_loop(rows, report, checkpoint, invoke)
        except BaseException as exc:
            report["failure"] = {"stage": "interrupted_or_exception",
                                 "type": type(exc).__name__, "inflight": report["inflight"]}
            checkpoint()
            raise
        if result:
            print(f"[STOP] Recovery required; previous successful scenarios retained. {root / name}")
            return result
        sentinel.unlink()
        checkpoint()
        print(f"[PASS] 21 selected configurations validated; #30 retained. Report: {root / name}")
        print("[PENDING] Do not infer 41 unique deployments or learner exploitation from source tests.")
        return 0
    finally:
        os.close(fd)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--workspace")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        detail = str(exc) if isinstance(exc, batch.BatchBlocked) else type(exc).__name__
        print("[BLOCKED] " + detail, flush=True)
        return 2
