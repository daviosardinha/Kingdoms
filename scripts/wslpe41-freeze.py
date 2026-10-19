#!/usr/bin/env python3
"""Freeze the completed WSLPE41 development guest as a guarded VMware snapshot.

Operator-only: default is read-only. --execute creates exactly one snapshot.
Never deploys, resets, reverts, runs student exploits, or contacts NORTH.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kingdoms import wslpe45_deploy21 as deployment
from kingdoms import wslpe45_batch_operator as batch

NAME = "KINGDOMS-WSLPE41-CONFIG-VALIDATED"
FINAL = "wslpe45-resume-registered27-77c4f73d6782a328.json"
SOURCE = "6b612e9abf2547dc76e4d4a89f4df1be6137f6e6"
OLD = "KINGDOMS-WSLPE-PRE-LPE40-20261018"
FINGERPRINT = "9AB97BF7EB5D424B87F2893D41816BE78683F7BAC407C68B4ADAC2E5BB724D26"
SELECTED = tuple(n for n in range(21, 46) if n not in (25, 36, 38, 40))


def validate_report(report: dict) -> None:
    """A completion claim alone is not evidence: check all 21 final records."""
    if (report.get("schema") != "kingdoms.wslpe45.resume_registered27.v1"
            or report.get("commit") != SOURCE
            or report.get("target") != "WSLPE-WS01"
            or report.get("snapshot") != OLD
            or report.get("completed") is not True
            or report.get("failure") is not None
            or report.get("inflight") is not None
            or report.get("runtime_configuration_pass_count") != 21
            or report.get("baseline_count") != 20
            or report.get("baseline_count_basis") != "operator reported; not recounted"
            or report.get("preserved_state_sha256") != FINGERPRINT
            or report.get("learner_exploitation") != "NOT_PROVEN_BY_THIS_RUN"
            or set(map(int, report.get("exclusions", {}).keys())) != {25, 36, 38, 40}):
        raise batch.BatchBlocked("Final deployment evidence differs from reviewed WSLPE41 contract")
    records = report.get("scenarios")
    if (not isinstance(records, list) or len(records) != 21
            or tuple(r.get("number") for r in records) != SELECTED):
        raise batch.BatchBlocked("Final 21-scenario record list differs")
    for record in records:
        if (record.get("installation") not in ("PASS", "PASS_EXISTING")
                or record.get("configuration_validation") != "PASS"
                or record.get("exploitation") != "NOT_TESTED"):
            raise batch.BatchBlocked(f"Scenario #{record.get('number')} is not configuration-validated")
    if (any(e.get("result") != "PASS" or e.get("exit_code") != 0
            for e in report.get("resume_events", []))
            or not report.get("resume_events")
            or any(e.get("stage") == "in-place-completion" and e.get("result") != "PASS"
                   for e in report["resume_events"])):
        raise batch.BatchBlocked("Final protected recovery/continuation events do not all pass")


def snapshot_names(vmx: Path) -> list[str]:
    result = subprocess.run(["vmrun", "-T", "ws", "listSnapshots", str(vmx)],
                            cwd=ROOT, text=True, capture_output=True,
                            timeout=90, check=False)
    if result.returncode or "Total snapshots:" not in result.stdout:
        raise batch.BatchBlocked("Cannot read exact registered guest snapshot inventory")
    return [line.strip() for line in result.stdout.splitlines()[1:] if line.strip()]


def run(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="Explicitly create the guarded post-deployment VMware snapshot")
    args = parser.parse_args(argv)

    # The private final journal and Git provenance are part of freeze identity.
    head = deployment.provenance()
    root = batch.make_private_dir(str(deployment.STATE))
    journal_path = root / FINAL
    raw = deployment.read_private_evidence(journal_path)
    report = json.loads(raw)
    validate_report(report)
    workspace = Path(report["workspace"]).expanduser()
    pilot = deployment.helper("wslpe45-single-pilot.py")
    if pilot.runtime_workspace(str(workspace)) != workspace.resolve(strict=True):
        raise batch.BatchBlocked("Original native WSLPE workspace differs")
    pilot.snapshot_gate(workspace)
    native = deployment.helper("wslpe-stage2-inspect.py")
    instance, metadata = native.find_instance(workspace)
    vmx = native.locate_registered_vm(instance)
    if (str(vmx) != report["vmx"]
            or str(instance / "inventory") != report["inventory"]
            or f"{metadata['ip_range']}.31" != report["address"]):
        raise batch.BatchBlocked("Registered VMware guest differs from final journal")
    current = snapshot_names(vmx)
    if current.count(OLD) != 1:
        raise batch.BatchBlocked("Original pinned recovery snapshot is absent or ambiguous")
    if current.count(NAME) != 0:
        raise batch.BatchBlocked("Freeze snapshot already exists; never replace or silently adopt it")
    print("[PASS] Exact Windows workgroup WSLPE guest and original recovery snapshot verified")
    print("[PASS] Final 21/21 deployment configuration records and protection fingerprint verified")
    print("[PLAN] Single VMware Workstation snapshot:", NAME)
    print("[NO ACTION] No learner execution or Windows fixture changes")
    if not args.execute:
        print("[READY] Explicit --execute required to create the frozen master snapshot")
        return 0

    receipt = {
        "schema": "kingdoms.wslpe41.freeze.v1", "created_at": datetime.now(timezone.utc).isoformat(),
        "operator_source_commit": head, "deployed_source_commit": SOURCE,
        "source_journal": str(journal_path), "source_journal_sha256": hashlib.sha256(raw).hexdigest(),
        "vmx": str(vmx), "snapshot": NAME, "previous_snapshot": OLD,
        "fingerprint": FINGERPRINT, "status": "STARTED",
        "learner_exploitation": "NOT_TESTED",
    }
    receipt_name = "wslpe41-freeze-" + __import__("secrets").token_hex(8) + ".json"
    deployment.durable(root, receipt_name, receipt)
    result = subprocess.run(["vmrun", "-T", "ws", "snapshot", str(vmx), NAME],
                            cwd=ROOT, text=True, capture_output=True,
                            timeout=360, check=False)
    # On any ambiguous VMware failure keep the STARTED receipt and do not retry automatically.
    if result.returncode:
        print("[STOP] VMware snapshot did not confirm success; inspect VM state before any retry")
        print("[RECEIPT]", root / receipt_name)
        return 2
    try:
        verified = snapshot_names(vmx).count(NAME) == 1
    except (OSError, batch.BatchBlocked, subprocess.TimeoutExpired):
        verified = False
    if not verified:
        print("[STOP] Snapshot result ambiguous; preserve VM and inspect before any retry")
        print("[RECEIPT]", root / receipt_name)
        return 2
    receipt["status"] = "PASS"
    receipt["completed_at"] = datetime.now(timezone.utc).isoformat()
    deployment.durable(root, receipt_name, receipt)
    print("[PASS] Dedicated reference snapshot now exists:", NAME)
    print("[RECEIPT]", root / receipt_name)
    print("[NEXT] Learner acceptance must use independently scoped scenario proofs, not redeployment")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except (ValueError, OSError, subprocess.TimeoutExpired, KeyError) as error:
        print("[BLOCKED] Freeze prerequisites could not be proven: " + str(error), file=sys.stderr)
        raise SystemExit(2)
