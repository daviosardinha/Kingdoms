"""Installation coordinator using existing WSLPE source and native safety gates.

Existing #30 is retained and independently validated, never re-registered.
No reset, recovery bypass, implicit resume, account creation or network changes.
"""
from __future__ import annotations
import argparse
import base64
import copy
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
import stat
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
INSPECT27 = ROOT / "ansible/wslpe45/deploy21-inspect27.yml"

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
                           capture_output=True, timeout=timeout, check=False, stdin=subprocess.DEVNULL)
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

def deployment_loop(rows, report, checkpoint, invoke, start_at=0):
    """Persist intent BEFORE each step; failure leaves prior successes intact."""
    for row, record in zip(rows[start_at:], report["scenarios"][start_at:]):
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

def save_log(base, root, label, diagnostics):
    path = base.private_failure_log(root, label, diagnostics)
    # Keep the complete private execution transcript rather than the legacy
    # helper's bounded failure tail, with the same exclusive private file.
    fd = os.open(path, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(diagnostics)
        stream.flush()
        os.fsync(stream.fileno())
    return path

def require_recovery_clear(root):
    sentinel = root / ".wslpe45-recovery-required"
    if sentinel.exists() or sentinel.is_symlink():
        raise batch.BatchBlocked("Unresolved recovery journal; do not rerun or delete sentinel")
    return sentinel

def read_private_evidence(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or info.st_size > 2_000_000):
            raise batch.BatchBlocked("Expected bounded owner-only regular evidence file")
        return stream.read(2_000_001)

def inspection_parent(root, requested, identity):
    path = Path(requested).expanduser()
    if path.parent != root or not re.fullmatch(r"wslpe45-deploy21-[a-f0-9]{16}\.json", path.name):
        raise batch.BatchBlocked("Inspection requires original journal in fixed private state directory")
    if read_private_evidence(root / ".wslpe45-recovery-required").decode().strip() != path.name:
        raise batch.BatchBlocked("Recovery sentinel does not identify requested journal")
    raw = read_private_evidence(path)
    parent = json.loads(raw)
    if (parent.get("schema") != "kingdoms.wslpe45.deploy21.v1"
            or parent.get("completed") is not False or parent.get("inflight") is not None):
        raise batch.BatchBlocked("Expected recorded incomplete deploy21 failure")
    if any(parent.get(k) != v for k, v in identity.items()):
        raise batch.BatchBlocked("Journal target/inventory/VM/snapshot identity changed")
    if parent.get("exclusions") != {str(k): v for k, v in EXCLUDED.items()}:
        raise batch.BatchBlocked("Journal exclusions differ")
    failure = parent.get("failure") or {}
    if (failure.get("number"), failure.get("stage"), failure.get("exit_code")) != (27, "apply", 2):
        raise batch.BatchBlocked("Inspection is specific to the recorded #27 apply failure")
    rows, records = selection(), parent.get("scenarios", [])
    if [(r.get("number"), r.get("name")) for r in records] != [(r["number"], r["id"]) for r in rows]:
        raise batch.BatchBlocked("Journal scenario identities/order changed")
    for index, record in enumerate(records):
        wanted = ("PASS", "PASS") if index < 5 else (
            ("FAIL", "NOT_ATTEMPTED") if index == 5 else ("NOT_ATTEMPTED", "NOT_ATTEMPTED"))
        if (record.get("installation"), record.get("configuration_validation")) != wanted:
            raise batch.BatchBlocked("Journal results differ from reviewed failure sequence")
    if parent.get("runtime_configuration_pass_count") != 5 or not re.fullmatch(
            r"[A-F0-9]{64}", parent.get("preserved_state_sha256", "")):
        raise batch.BatchBlocked("Original preservation evidence missing")
    return parent, hashlib.sha256(raw).hexdigest()


def inspectable_failure_parent(root, requested, identity):
    """Accept only the original #27 apply failure or its exact failed recovery.

    This extends read-only evidence collection, never mutation authorization.
    The outstanding sentinel must still name the original deploy21 journal.
    """
    path = Path(requested).expanduser()
    if re.fullmatch(r"wslpe45-deploy21-[a-f0-9]{16}\.json", path.name):
        return inspection_parent(root, requested, identity)
    if path.parent != root or not re.fullmatch(
            r"wslpe45-recovery27-[a-f0-9]{16}\.json", path.name):
        raise batch.BatchBlocked("Read-only inspection requires an exact known #27 recovery journal")
    raw = read_private_evidence(path)
    report = json.loads(raw)
    original = report.get("parent_journal")
    if not isinstance(original, str):
        raise batch.BatchBlocked("Failed recovery has no original journal")
    parent, digest = inspection_parent(root, original, identity)
    failure = report.get("failure") or {}
    if (report.get("schema") != "kingdoms.wslpe45.recovery27.v1"
            or report.get("completed") is not False
            or report.get("inflight") is not None
            or report.get("parent_sha256") != digest
            or any(report.get(k) != v for k, v in identity.items())
            or report.get("exclusions") != parent.get("exclusions")
            or report.get("preserved_state_sha256") != parent.get("preserved_state_sha256")
            or report.get("runtime_configuration_pass_count") != 5
            or report.get("resume_index") != 5
            or (failure.get("number"), failure.get("stage"), failure.get("exit_code"))
                != (27, "apply", 2)):
        raise batch.BatchBlocked("Not the reviewed #27 registered-state recovery failure")
    prior = report.get("scenarios") or []
    reference = parent.get("scenarios") or []
    if len(prior) != len(reference):
        raise batch.BatchBlocked("Scenario inventory changed since original deployment")
    for idx, (current, baseline) in enumerate(zip(prior, reference)):
        if (current.get("number"), current.get("name")) != (
                baseline.get("number"), baseline.get("name")):
            raise batch.BatchBlocked("Scenario identity or order changed")
        expected = ("PASS", "PASS") if idx < 5 else (
            ("FAIL", "NOT_ATTEMPTED") if idx == 5 else
            ("NOT_ATTEMPTED", "NOT_ATTEMPTED"))
        if (current.get("installation"), current.get("configuration_validation")) != expected:
            raise batch.BatchBlocked("Unreviewed deployment progress after #27 failure")
    required = ["existing_revalidation", "fresh_inspection", "cleanup", "verify"]
    events = report.get("recovery_events") or []
    for stage in required:
        if stage == "existing_revalidation":
            matches = [e for e in events if e.get("stage") == stage
                       and e.get("number") in (21, 22, 23, 24, 26)
                       and e.get("result") == "PASS" and e.get("exit_code") == 0]
            if len(matches) != 5:
                raise batch.BatchBlocked("Five original configurations were not revalidated")
        elif len([e for e in events if e.get("stage") == stage
                  and e.get("result") == "PASS" and e.get("exit_code") == 0]) != 1:
            raise batch.BatchBlocked("Reviewed #27 recovery stages are incomplete")
    if any(e.get("result") == "FAIL" for e in events):
        raise batch.BatchBlocked("Recovery evidence contains unreviewed earlier failure")
    evidence_path = Path(str(failure.get("private_log", "")))
    if (evidence_path.parent != root or not re.fullmatch(
            r"wslpe-recover27-resume-27-apply-[a-f0-9]{12}\.log", evidence_path.name)):
        raise batch.BatchBlocked("Unexpected #27 failed stage evidence path")
    return report, hashlib.sha256(raw).hexdigest()


def read_inspection_state(root, evidence_path):
    path = Path(evidence_path)
    if (path.parent != root or not re.fullmatch(
            r"wslpe-inspect27-state-[a-f0-9]{12}\.log", path.name)):
        raise batch.BatchBlocked("Not an exact private #27 inspection state log")
    records = []
    for line in read_private_evidence(path).decode("utf-8").splitlines():
        item = line.strip().rstrip(",")
        if not item.startswith('"WSLPE21_INSPECT27_JSON='):
            continue
        try:
            decoded = json.loads(item)
            records.append(json.loads(decoded.split("=", 1)[1]))
        except (ValueError, IndexError, TypeError) as exc:
            raise batch.BatchBlocked("Malformed original #27 state evidence") from exc
    if len(records) != 1:
        raise batch.BatchBlocked("Exactly one original #27 state snapshot required")
    return records[0]


def stable_inspection(snapshot):
    return {key: snapshot.get(key) for key in (
        "schema", "target", "learner_sid", "marker", "files",
        "registry", "tasks", "regasm_processes", "assessment", "guest_mutations")}


def validate_partial27(snapshot, identity):
    marker = snapshot.get("marker") or {}
    prefix = r"C:\ProgramData\KingdomsWSLPE45\fixtures\com_clsid_registration_hijack"
    expected_paths = {
        prefix, prefix + r"\.kingdoms-owned.json",
        prefix + r"\inbox", prefix + r"\Kingdom45ComServer.dll",
        prefix + r"\inbox\Kingdom45ComServer.dll"}
    files = snapshot.get("files") or []
    names = [file.get("path") for file in files]
    if (snapshot.get("schema") != "kingdoms.wslpe45.inspect27.v1"
            or snapshot.get("target") != identity["target"]
            or not re.fullmatch(r"S-1-5-21-(?:\d+-){3}\d+", str(snapshot.get("learner_sid", "")))
            or marker.get("schema") != "kingdoms.wslpe.fixture-owner.v1"
            or marker.get("machine") != identity["target"]
            or marker.get("number") != 27
            or marker.get("id") != "com_clsid_registration_hijack"
            or marker.get("learner_sid") != snapshot.get("learner_sid")
            or snapshot.get("assessment") != "RECOVERY_REVIEW_REQUIRED"
            or snapshot.get("guest_mutations") is not False
            or len(files) != 5 or set(names) != expected_paths
            or len(set(names)) != 5
            or snapshot.get("registry") != [] or snapshot.get("tasks") != []
            or snapshot.get("regasm_processes") != []):
        raise batch.BatchBlocked("Evidence differs from exact owned #27 pre-registration partial")
    for record in files:
        path = record["path"]
        if record.get("directory") is not (path in {prefix, prefix + r"\inbox"}):
            raise batch.BatchBlocked("Unexpected #27 file/directory identity")
        if not isinstance(record.get("sddl"), str) or not record["sddl"]:
            raise batch.BatchBlocked("Missing immutable ACL evidence")
        if not record["directory"] and (not re.fullmatch(
                r"[A-F0-9]{64}", str(record.get("sha256", "")))
                or not isinstance(record.get("length"), int)
                or record["length"] <= 0):
            raise batch.BatchBlocked("Missing immutable file evidence")
        if path.endswith(".dll") and not str(record.get("assembly_name", "")).startswith(
                "Kingdom45ComServer, Version="):
            raise batch.BatchBlocked("Unexpected owned COM assembly")


def original_inspection(root, requested, digest, identity, inspection_path):
    path = Path(inspection_path).expanduser()
    if path.parent != root or not re.fullmatch(
            r"wslpe45-inspect27-[a-f0-9]{16}\.json", path.name):
        raise batch.BatchBlocked("Exact prior read-only inspection JSON required")
    inspection = json.loads(read_private_evidence(path))
    if (inspection.get("schema") != "kingdoms.wslpe45.inspect27-controller.v1"
            or inspection.get("parent_journal") != str(requested)
            or inspection.get("parent_sha256") != digest
            or inspection.get("read_only") is not True
            or inspection.get("completed") is not True
            or inspection.get("inflight") is not None
            or inspection.get("assessment") != "RECOVERY_REVIEW_REQUIRED"
            or any(inspection.get(k) != v for k, v in identity.items())):
        raise batch.BatchBlocked("Original inspection mismatches protected recovery parent")
    events = inspection.get("events") or []
    if ([(e.get("stage"), e.get("result"), e.get("exit_code")) for e in events]
            != [("before", "PASS", 0), ("state", "PASS", 0), ("after", "PASS", 0)]):
        raise batch.BatchBlocked("All original inspection gates must pass")
    snapshot = read_inspection_state(root, events[1].get("private_log"))
    validate_partial27(snapshot, identity)
    return snapshot, path


def inspect_failure(root, requested, identity, head, base, ansible, inv, varsfile, env, timeout):
    parent, digest = inspectable_failure_parent(root, requested, identity)
    name = "wslpe45-inspect27-" + token_hex(8) + ".json"
    report = {"schema": "kingdoms.wslpe45.inspect27-controller.v1", "commit": head,
              "parent_journal": str(requested), "parent_sha256": digest,
              "created_at": now(), "read_only": True, "completed": False,
              "assessment": "RECOVERY_REVIEW_REQUIRED", "events": [], **identity}
    durable(root, name, report)
    extra = {"wslpe_expected_address": identity["address"],
             "wslpe_pilot_shared_sha256": hashlib.sha256(
                 (ROOT / "ansible/files/wslpe45/WslpeFixture.psm1").read_bytes()).hexdigest().upper()}
    for label, playbook in (("before", PREFLIGHT), ("state", INSPECT27), ("after", PREFLIGHT)):
        report["inflight"] = label
        durable(root, name, report)
        rc, log = run_command(ansible_command(ansible, inv, varsfile, playbook, extra), env, timeout)
        if playbook == PREFLIGHT:
            evidence = re.findall(r"WSLPE21_PRESERVED=([A-F0-9]{64})", log)
            ok = (rc == 0 and log.count("WSLPE21_PREFLIGHT=PASS") == 1
                  and evidence == [parent["preserved_state_sha256"]])
        else:
            ok = rc == 0 and log.count("WSLPE21_INSPECT27=PASS") == 1
        path = save_log(base, root, "inspect27-" + label, log)
        report["events"].append({"stage": label, "result": "PASS" if ok else "FAIL",
                                 "exit_code": rc, "private_log": str(path), "at": now()})
        report["inflight"] = None
        durable(root, name, report)
        print(f"[INSPECT] {label}: {'PASS' if ok else 'FAIL'}; evidence: {path}", flush=True)
        if not ok:
            print(f"[STOP] Read-only inspection incomplete; report: {root / name}")
            return 2
    report["completed"] = True
    report["completed_at"] = now()
    durable(root, name, report)
    print(f"[INSPECT] Evidence collected; original journal and sentinel retained. Report: {root / name}")
    print("[PENDING] Review inspected #27 registry/task state before any repair; no guest changes made.")
    return 0


def recover27_and_resume(root, requested, prior_inspection, identity, head,
                         base, ansible, inv, varsfile, expected_address, env, timeout, rows):
    """Only the previously inspected, unchanged #27 pre-registration partial may be recovered.

    The original journal and recovery sentinel remain untouched. A new linked
    journal records every attempt; any interruption leaves the sentinel in place.
    """
    parent, digest = inspection_parent(root, requested, identity)
    saved, inspection_path = original_inspection(
        root, requested, digest, identity, prior_inspection)
    sentinel = root / ".wslpe45-recovery-required"
    if read_private_evidence(sentinel).decode("utf-8").strip() != Path(requested).name:
        raise batch.BatchBlocked("Recovery pointer changed")
    report = copy.deepcopy(parent)
    report.update(schema="kingdoms.wslpe45.recovery27.v1", commit=head,
                  parent_journal=str(requested), parent_sha256=digest,
                  prior_inspection=str(inspection_path), created_at=now(),
                  completed=False, failure=None, inflight=None,
                  recovery_events=[], resume_index=5)
    name = "wslpe45-recovery27-" + token_hex(8) + ".json"

    def checkpoint():
        report["runtime_configuration_pass_count"] = sum(
            r["configuration_validation"] == "PASS" for r in report["scenarios"])
        durable(root, name, report)

    checkpoint()
    print(f"[RECOVERY] Protected original journal retained; new journal: {root / name}", flush=True)
    extra = {"wslpe_expected_address": expected_address,
             "wslpe_pilot_shared_sha256": hashlib.sha256(
                 (ROOT / "ansible/files/wslpe45/WslpeFixture.psm1").read_bytes()
             ).hexdigest().upper()}
    recovery_extra = dict(extra,
        wslpe_recover27_expected_b64=base64.b64encode(
            json.dumps(saved, separators=(",", ":")).encode("utf-8")
        ).decode("ascii"))
    baseline = parent["preserved_state_sha256"]

    def guard(stage):
        rc, log = run_command(ansible_command(ansible, inv, varsfile, PREFLIGHT, extra),
                              env, timeout)
        observed = re.findall(r"WSLPE21_PRESERVED=([A-F0-9]{64})", log)
        ok = rc == 0 and log.count("WSLPE21_PREFLIGHT=PASS") == 1 and observed == [baseline]
        evidence = save_log(base, root, "recover27-" + stage + "-preflight", log)
        report["recovery_events"].append(
            {"stage": stage + "-preflight", "result": "PASS" if ok else "FAIL",
             "exit_code": rc, "private_log": str(evidence)})
        checkpoint()
        return ok

    def stop(stage, detail):
        report["failure"] = {"number": 27, "stage": stage, "reason": detail}
        report["inflight"] = None
        checkpoint()
        print(f"[STOP] #27 recovery needs review at {stage}; report: {root / name}", flush=True)
        return 2

    if not guard("before"):
        return stop("initial_preservation", "Preflight differs from original preserved digest")

    # Previous successes are not re-applied. Validate their live configurations
    # read-only before relying on the parent journal's five PASS assertions.
    for previous in rows[:5]:
        report["inflight"] = {"number": previous["number"], "stage": "existing_revalidation"}
        checkpoint()
        command, marker = stage_command(ansible, inv, varsfile, previous,
                                        expected_address, "validate", "vulnerable", "vulnerable")
        rc, log = run_command(command, env, timeout)
        ok = rc == 0 and log.count(marker) == 1
        evidence = save_log(base, root, f"recover27-existing-{previous['number']}", log)
        report["recovery_events"].append(
            {"number": previous["number"], "stage": "existing_revalidation",
             "result": "PASS" if ok else "FAIL", "exit_code": rc,
             "private_log": str(evidence)})
        report["inflight"] = None
        checkpoint()
        if not ok:
            return stop(f"existing_revalidation-{previous['number']}",
                        "Previously validated configuration no longer passes")
    if not guard("after_existing_revalidation"):
        return stop("prior_configuration_preservation", "Protected state changed during read-only checks")

    report["inflight"] = {"number": 27, "stage": "fresh_inspection"}
    checkpoint()
    rc, log = run_command(ansible_command(ansible, inv, varsfile, INSPECT27, extra),
                          env, timeout)
    evidence = save_log(base, root, "recover27-fresh-inspection", log)
    try:
        # Fresh Ansible logs have the same exact controller-emitted evidence shape.
        fresh_lines = []
        for line in log.splitlines():
            item = line.strip().rstrip(",")
            if item.startswith('"WSLPE21_INSPECT27_JSON='):
                fresh_lines.append(json.loads(json.loads(item).split("=", 1)[1]))
        matching = len(fresh_lines) == 1 and stable_inspection(fresh_lines[0]) == stable_inspection(saved)
    except (ValueError, TypeError, IndexError):
        matching = False
    ok = rc == 0 and log.count("WSLPE21_INSPECT27=PASS") == 1 and matching
    report["recovery_events"].append(
        {"stage": "fresh_inspection", "result": "PASS" if ok else "FAIL",
         "exit_code": rc, "private_log": str(evidence)})
    report["inflight"] = None
    checkpoint()
    if not ok:
        return stop("fresh_inspection", "Guest fixture differs from reviewed read-only evidence")
    if not guard("before_cleanup"):
        return stop("pre_cleanup_preservation", "Protected shared state changed")

    def recovery_action(mode):
        report["inflight"] = {"number": 27, "stage": mode, "started_at": now()}
        checkpoint()
        vars_ = dict(recovery_extra, wslpe_recover27_operation=mode)
        rc, log = run_command(ansible_command(
            ansible, inv, varsfile, ROOT / "ansible/wslpe45/deploy21-recover27.yml", vars_),
            env, timeout)
        marker = "WSLPE21_RECOVER27=" + mode + ":PASS"
        ok = rc == 0 and log.count(marker) == 1
        evidence = save_log(base, root, "recover27-" + mode, log)
        report["recovery_events"].append(
            {"stage": mode, "result": "PASS" if ok else "FAIL",
             "exit_code": rc, "private_log": str(evidence)})
        report["inflight"] = None
        checkpoint()
        return ok

    if not recovery_action("cleanup"):
        return stop("cleanup", "Exact owned #27 cleanup did not complete")
    if not guard("after_cleanup"):
        return stop("post_cleanup_preservation", "Protected state changed during cleanup")
    if not recovery_action("verify"):
        return stop("verify_clean", "Owned #27 fixture not completely absent")
    if not guard("before_resume"):
        return stop("resume_preservation", "Protected state changed before installation")

    # Previous successful scenarios are retained exactly as recorded.
    prior_record = report["scenarios"][5]
    prior_record["installation"] = "NOT_ATTEMPTED"
    prior_record["events"].append({
        "stage": "exact_owned_recovery", "result": "PASS",
        "note": "Old failed apply preserved in events; only owned #27 partial files cleaned"})
    checkpoint()

    def invoke(row, action, state, label):
        if row["number"] in (21, 22, 23, 24, 26):
            raise batch.BatchBlocked("Recovery refuses replay of previous successful scenarios")
        if not guard(f"step-{row['number']}-{label}-before"):
            return False, {"exit_code": 2, "failure_details": "Preservation preflight changed"}
        cmd, marker = stage_command(ansible, inv, varsfile, row, expected_address,
                                    action, state, label)
        rc, log = run_command(cmd, env, timeout)
        ok = rc == 0 and log.count(marker) == 1
        if ok and row["number"] == 30:
            jea_rc, fresh = run_command(ansible_command(
                ansible, inv, varsfile, JEA, extra), env, timeout)
            log += "\n" + fresh
            ok = jea_rc == 0 and fresh.count("WSLPE21_JEA_ACTIVE=PASS") == 1
        if ok:
            ok = guard(f"step-{row['number']}-{label}-after")
        path = save_log(base, root, f"recover27-resume-{row['number']}-{label}", log)
        return ok, {"exit_code": rc, "private_log": str(path),
                    "failure_details": None if ok else "Windows result or preservation check failed"}

    try:
        result = deployment_loop(rows, report, checkpoint, invoke, start_at=5)
    except BaseException as exc:
        report["failure"] = {"stage": "interrupted_or_exception",
                             "type": type(exc).__name__, "inflight": report["inflight"]}
        checkpoint()
        raise
    if result:
        print(f"[STOP] Resume blocked; original recovery sentinel retained. {root / name}", flush=True)
        return result
    if read_private_evidence(sentinel).decode("utf-8").strip() != Path(requested).name:
        return stop("sentinel_final", "Original recovery pointer changed")
    sentinel.unlink()
    checkpoint()
    print(f"[PASS] Remaining 16 selected scenarios validated, prior five retained. {root / name}",
          flush=True)
    print("[PENDING] Learner exploitation remains a separate acceptance gate.", flush=True)
    return 0


def run(args):
    rows = selection()
    print("[SCOPE] WSLPE-WS01 only; selected=" + ",".join(map(str, SELECTED)), flush=True)
    print("[EXCLUDED] 25,36,38,40; #30 retained, inspected and tested without re-registration", flush=True)
    inspection = getattr(args, "inspect_failure", None)
    recovery = getattr(args, "recover_failure", None)
    prior_inspection = getattr(args, "inspection_report", None)
    if recovery and (not args.execute or not prior_inspection or inspection):
        raise batch.BatchBlocked("Recovery requires --execute, --recover-failure and --inspection-report")
    if prior_inspection and not recovery:
        raise batch.BatchBlocked("Inspection report is only accepted for exact recovery")
    if inspection and args.execute:
        raise batch.BatchBlocked("Read-only inspection cannot be combined with --execute")
    if not args.execute and not inspection and not recovery:
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
    doc = subprocess.run([str(venv / "ansible-doc"), "--json", "ansible.windows.win_powershell"],
                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=40,
                         check=False, stdin=subprocess.DEVNULL)
    if doc.returncode or "sensitive_parameters" not in json.loads(doc.stdout).get(
            "ansible.windows.win_powershell", {}).get("doc", {}).get("options", {}):
        raise batch.BatchBlocked("Installed win_powershell lacks required secure credential parameters")
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
        if inspection:
            identity = {"target": "WSLPE-WS01", "address": expected, "workspace": str(workspace),
                        "inventory": str(inv), "vmx": str(vmx),
                        "snapshot": helper("wslpe40-stage.py").SNAPSHOT}
            return inspect_failure(root, inspection, identity, head, base, ansible, inv,
                                   varsfile, env, args.timeout_seconds)
        if recovery:
            identity = {"target": "WSLPE-WS01", "address": expected, "workspace": str(workspace),
                        "inventory": str(inv), "vmx": str(vmx),
                        "snapshot": helper("wslpe40-stage.py").SNAPSHOT}
            return recover27_and_resume(root, recovery, prior_inspection, identity, head,
                                        base, ansible, inv, varsfile, expected, env,
                                        args.timeout_seconds, rows)
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
            path = save_log(base, root, "deploy21-preflight", log)
            report["failure"] = {"stage": "preflight", "exit_code": rc, "private_log": str(path)}
            checkpoint()
            print("[REASON] " + pilot.diagnostic_summary(log), flush=True)
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
            path = save_log(base, root, f"deploy21-{row['number']}-{label}", log)
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
    parser.add_argument("--inspect-failure", metavar="JOURNAL",
                        help="Read-only #27 failure inspection; retains recovery sentinel")
    parser.add_argument("--recover-failure", metavar="JOURNAL",
                        help="Explicit inspected #27 cleanup and resume from #27, not from #21")
    parser.add_argument("--inspection-report", metavar="INSPECTION_JSON",
                        help="Original completed read-only #27 inspection report")
    parser.add_argument("--workspace")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        detail = str(exc) if isinstance(exc, batch.BatchBlocked) else type(exc).__name__
        print("[BLOCKED] " + detail, flush=True)
        return 2
