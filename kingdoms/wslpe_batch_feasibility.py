"""One-shot read-only native feasibility sweep of WSLPE advanced/expert #21–45.

No new LPE fixture is installed. Default local plan never contacts a VM.
--execute checks the exact registered WSLPE guest and reads 25 API surfaces
with one Ansible invocation, then writes an owner-only structured report.
"""
from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

from kingdoms.wslpe_batch_catalog import catalog

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "scripts/wslpe-fast-track-20.py"
PLAY = ROOT / "ansible/wslpe-45-feasibility.yml"
MARKER = re.compile(r"WSLPE_45_FEASIBILITY_B64=([A-Za-z0-9+/=]+)")

def base_module():
    if BASE.is_symlink() or not BASE.is_file():
        raise ValueError("Standalone WSLPE safety harness missing")
    spec = importlib.util.spec_from_file_location("wslpe_45_trusted_guard", BASE)
    if spec is None or spec.loader is None:
        raise ValueError("Standalone WSLPE safety harness is not importable")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="run the one-shot READ-ONLY WSLPE Windows API sweep")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--report-dir",
                        default="~/.local/state/kingdoms-wslpe-feasibility")
    return parser

def interpret(diagnostic: str, expected_ids: list[str]) -> dict:
    markers = MARKER.findall(diagnostic)
    if len(markers) != 1 or len(markers[0]) > 65536:
        raise ValueError("Missing, repeated or overlong WSLPE feasibility marker")
    try:
        blob = base64.b64decode(markers[0], validate=True)
        if len(blob) > 49152:
            raise ValueError("Oversized native feasibility report")
        payload = json.loads(blob.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid native feasibility JSON") from exc
    if not isinstance(payload, dict) or any((
        payload.get("schema") != "kingdoms.wslpe.feasibility.v1",
        payload.get("hostname") != "WSLPE-WS01",
        payload.get("domain_joined") is not False,
        payload.get("os") != "Windows 10",
        payload.get("readonly") is not True,
    )):
        raise ValueError("Guest identity or feasibility payload contract mismatch")
    results = payload.get("results")
    if not isinstance(results, list) or [r.get("id") if isinstance(r, dict) else None for r in results] != expected_ids:
        raise ValueError("Guest reported wrong, duplicated or missing technique IDs")
    for item in results:
        if set(item) != {"id", "native_api", "fixture", "learner_exploitation"}:
            raise ValueError("Unexpected guest feasibility fields")
        if (item["native_api"] not in {"native_api_available", "native_api_blocked"}
                or item["fixture"] != "not_implemented"
                or item["learner_exploitation"] != "not_tested"):
            raise ValueError("Feasibility may not claim implementation or learner exploitation")
    return payload

def run(args) -> int:
    if not 60 <= args.timeout_seconds <= 1800:
        raise ValueError("Timeout must be 60–1800 seconds")
    if PLAY.is_symlink() or not PLAY.is_file():
        raise ValueError("Standalone feasibility playbook missing")
    rowset = catalog()
    additions = [row["id"] for row in rowset[20:]]
    print("[SCOPE] Standalone WSLPE-WS01 only; NORTH WS01 is forbidden", flush=True)
    print("[MATRIX] 20 previously qualified + 25 new candidates", flush=True)
    if not args.execute:
        print("[PLAN] The 25 native API checks use one batch, read-only execution", flush=True)
        print("[PLAN] No VM, WinRM or Ansible interaction; no fixture deployment", flush=True)
        return 0

    base = base_module()
    inventory, varsfile, expected = base.exact_standalone()
    tools = Path.home() / ".goad/.venv/bin"
    ansible = tools / "ansible-playbook"
    ansible_inventory = tools / "ansible-inventory"
    if not ansible.is_file() or not ansible_inventory.is_file():
        raise ValueError("Trusted WSLPE Ansible operator environment missing")
    env = os.environ.copy()
    env.update({"ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg"),
                "ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles"),
                "ANSIBLE_NOCOLOR": "1"})
    resolved = subprocess.run(
        base.resolved_inventory_command(ansible_inventory, inventory, varsfile),
        cwd=ROOT, env=env, capture_output=True, text=True,
        timeout=40, check=False)
    if resolved.returncode:
        raise ValueError("Unable to resolve the exact standalone inventory")
    base.check_inventory(json.loads(resolved.stdout), expected)

    cmd = [str(ansible), "-i", str(inventory), "-i", str(varsfile),
           "--limit", "ws01,localhost", str(PLAY), "-e",
           json.dumps({"wslpe_expected_address": expected}, separators=(",", ":"))]
    print("[TARGET] Exact standalone instance, WinRM host and WSLPE inventory accepted", flush=True)
    print("[RUN] Read-only Windows-native feasibility sweep #21–45", flush=True)
    try:
        reply = subprocess.run(cmd, cwd=ROOT, env=env,
                               capture_output=True, text=True,
                               timeout=args.timeout_seconds, check=False)
        output = reply.stdout + "\n" + reply.stderr
        code = reply.returncode
    except subprocess.TimeoutExpired:
        output, code = "Native feasibility inspection timed out", 124
    root = base.private_report_dir(args.report_dir)
    if code or len(output) > 350_000:
        path = base.private_failure_log(root, "batch-feasibility", output)
        print(f"[BLOCKED] Guest feasibility sweep failed, exit={code}", flush=True)
        print(f"[DIAGNOSTIC] Owner-only log: {path} (redact before sharing)", flush=True)
        return 2
    try:
        payload = interpret(output, additions)
    except ValueError:
        path = base.private_failure_log(root, "batch-marker", output)
        print("[BLOCKED] Guest returned invalid feasibility evidence", flush=True)
        print(f"[DIAGNOSTIC] Owner-only log: {path} (redact before sharing)", flush=True)
        return 2

    from secrets import token_hex
    report = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "standalone-wslpe-only",
        "native_api_probes": payload,
        "new_fixture_count": 0,
        "eligible_for_live_qualification": False,
    }
    path = root / f"wslpe-batch-feasibility-{token_hex(6)}.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    passed = sum(x["native_api"] == "native_api_available" for x in payload["results"])
    blocked = len(additions) - passed
    print(f"[RESULT] Native APIs available={passed} blocked={blocked} total=25", flush=True)
    for row in payload["results"]:
        print(f"  {row['id']}: {row['native_api']}", flush=True)
    print(f"[REPORT] Private structured report: {path}", flush=True)
    print("[NEXT] Implement and qualify 25 distinct fixtures; NO new vulnerability was deployed", flush=True)
    return 0

def main() -> int:
    args = build_parser().parse_args()
    try:
        return run(args)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError,
            subprocess.TimeoutExpired) as exc:
        message = str(exc) if type(exc) is ValueError else type(exc).__name__
        print(f"[BLOCKED] WSLPE-only feasibility preflight: {message}", flush=True)
        return 1
