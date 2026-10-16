#!/usr/bin/env python3
"""WSLPE-only fast-track qualification of NORTH's shared 20 LPE techniques.

Defaults to PLAN ONLY. With --execute, runs each technique serially through
the existing WSLPE adapter: apply / validate(vulnerable) / reset /
validate(clean) / reapply / validate(vulnerable). Stops at the FIRST failure,
writes a private per-step report, and never targets NORTH or a domain member.

Prerequisites: existing trusted local WSLPE development VM, completed
wslpe-foundation.yml learner account, valid WSLPE-only inventory and
KINGDOMS_WSLPE_LEARNER_PASSWORD secret (prompted only for --execute).
This is NOT an isolation or commercial learner-release gate.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "ansible/roles/windows_lpe/defaults/main.yml"
PLAYBOOK = ROOT / "ansible/wslpe-lpe-test.yml"
STAGE = ROOT / "scripts/wslpe-stage2-inspect.py"

FLOW = (
    ("apply", None),
    ("validate", "vulnerable"),
    ("reset", None),
    ("validate", "clean"),
    ("apply", None),
    ("validate", "vulnerable"),
)

def load_catalog() -> tuple[str, ...]:
    import yaml
    body = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    implemented = body.get("windows_lpe_implemented_techniques")
    all_tech = body.get("windows_lpe_catalog")
    candidates = body.get("windows_lpe_candidate_techniques")
    if (not isinstance(implemented, list) or len(implemented) != 20
            or len(set(implemented)) != 20
            or set(implemented) != set(all_tech)
            or candidates != [] or not all(
                isinstance(x, str) and re.fullmatch("[a-z_]+", x)
                for x in implemented)):
        raise ValueError("NORTH shared role catalog changed; manual review required")
    return tuple(implemented)

def exact_standalone() -> tuple[Path, Path, str]:
    spec = importlib.util.spec_from_file_location("wslpe_batch_stage2", STAGE)
    if spec is None or spec.loader is None:
        raise ValueError("Native WSLPE registration helper missing")
    stage = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stage)
    identity, meta = stage.find_instance(stage.WORKSPACE)
    if meta.get("lab") != "WSLPE" or meta.get("provider") != "vmware":
        raise ValueError("Target is not the native VMware WSLPE instance")
    vmx = stage.locate_registered_vm(identity)
    if vmx.is_symlink() or not vmx.resolve(strict=True).is_relative_to(
            stage.WORKSPACE.resolve()):
        raise ValueError("Untrusted registered WSLPE VMX")
    inventory = (stage.WORKSPACE / str(identity) / "inventory").resolve(strict=True)
    if inventory.is_symlink() or not inventory.is_file():
        raise ValueError("WSLPE native inventory unavailable")
    base = (ROOT / "ad/WSLPE/data/inventory_disable_vagrant").resolve(strict=True)
    expected = f"{meta['ip_range']}.31"
    if not re.fullmatch(r"(?:[0-9]{1,3}\.){3}[0-9]{1,3}", expected):
        raise ValueError("Native WSLPE expected guest address is invalid")
    return inventory, base, expected

def check_inventory(data: dict, expected: str) -> None:
    groups = data if isinstance(data, dict) else {}
    for group in ("wslpe", "windows_lpe_standalone"):
        if groups.get(group, {}).get("hosts") != ["ws01"]:
            raise ValueError("Expected exactly one standalone WSLPE host")
    host = groups.get("_meta", {}).get("hostvars", {}).get("ws01", {})
    if str(host.get("ansible_host")) != expected or host.get("ansible_connection") != "winrm":
        raise ValueError("Inventory does not target exact WSLPE management address")
    if not host.get("ansible_user") or host.get("domain_name") != "WSLPE":
        raise ValueError("WSLPE-only management identity not resolved")
    for forbidden in ("dc", "domain"):
        if groups.get(forbidden, {}).get("hosts"):
            raise ValueError("Domain/DC hosts appear in WSLPE inventory")

def invocation(ansible: Path, inventory: Path, varsfile: Path,
               technique: str, action: str, state: str | None) -> list[str]:
    if technique not in load_catalog() or action not in {"apply", "validate", "reset"}:
        raise ValueError("Unknown WSLPE technique/action")
    variables = {"wslpe_action": action, "wslpe_techniques": [technique]}
    if state:
        if action != "validate" or state not in {"vulnerable", "clean"}:
            raise ValueError("Invalid WSLPE validation state")
        variables["windows_lpe_validate_state"] = state
    return [str(ansible), "-i", str(inventory), "-i", str(varsfile),
            "--limit", "ws01", str(PLAYBOOK), "-e",
            json.dumps(variables, separators=(",", ":"))]

def run(args) -> int:
    catalog = load_catalog()
    inventory, varsfile, expected = exact_standalone()
    if not PLAYBOOK.is_file():
        raise ValueError("Existing WSLPE-only harness is missing")
    print("KINGDOMS WSLPE | FAST-TRACK 20 SCENARIO QUALIFICATION")
    print("[SCOPE] Native WSLPE only; NORTH untouched; no domain provisioning")
    print(f"[TARGET] Exact standalone guest {expected}; {len(catalog)} existing techniques")
    print(f"[FLOW] Each: {' → '.join(a + ('/'+s if s else '') for a,s in FLOW)}")
    print("[SAFETY] Stop on first failure; private report; no parallel guest changes")
    if not args.execute:
        print("[PLAN ONLY] No VMware, Windows, Ansible or firewall writes")
        print("[PREREQ] WSLPE foundation learner lpe.trainee must already exist")
        for n, technique in enumerate(catalog, 1):
            print(f"  {n:02d}. {technique}")
        return 0

    if not sys.stdin.isatty():
        raise ValueError("Interactive local Kali terminal required for execution")
    print("[WARNING] This intentionally installs/resets vulnerable LPE scenarios")
    print("[WARNING] Trusted WSLPE development ONLY; not safe for student access")
    confirmation = input("Type QUALIFY WSLPE 20 to authorize guest changes: ")
    if confirmation != "QUALIFY WSLPE 20":
        raise ValueError("Exact operator approval was not supplied")

    import getpass
    secret = os.environ.get("KINGDOMS_WSLPE_LEARNER_PASSWORD")
    if not secret:
        secret = getpass.getpass("WSLPE local learner password: ")
    if len(secret) < 12:
        raise ValueError("WSLPE local learner secret must have at least 12 characters")
    env = os.environ.copy()
    env["KINGDOMS_WSLPE_LEARNER_PASSWORD"] = secret
    env["ANSIBLE_CONFIG"] = str(ROOT / "ansible/ansible.cfg")
    env["ANSIBLE_ROLES_PATH"] = str(ROOT / "ansible/roles")
    env["ANSIBLE_NOCOLOR"] = "1"
    venv = Path.home() / ".goad/.venv/bin"
    ansible = venv / "ansible-playbook"
    ansible_inv = venv / "ansible-inventory"
    if not ansible.is_file() or not ansible_inv.is_file():
        raise ValueError("Existing trusted GOAD Ansible environment missing")

    validate = subprocess.run(
        [str(ansible_inv), "-i", str(inventory), "-i", str(varsfile),
         "--list", "--export"], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=40, check=False,
    )
    if validate.returncode:
        raise ValueError("WSLPE Ansible inventory resolution failed")
    check_inventory(json.loads(validate.stdout), expected)

    # Optional, explicitly approved local learner foundation using
    # the existing WSLPE playbook, not NORTH's domain-joined baseline.
    # Its first guest task asserts exact hostname and no AD membership
    # before changing Windows settings or creating the learner account.
    if args.bootstrap_learner:
        foundation = ROOT / "ansible/wslpe-foundation.yml"
        print("[RUN] WSLPE-only local learner foundation (may perform a license reboot)")
        setup = subprocess.run(
            [str(ansible), "-i", str(inventory), "-i", str(varsfile),
             "--limit", "ws01", str(foundation)],
            cwd=ROOT, env=env, capture_output=True, text=True,
            timeout=3600, check=False,
        )
        if setup.returncode:
            print(f"[BLOCKED] Standalone learner foundation exit={setup.returncode}")
            print("[STOP] No LPE scenario was applied")
            return 2
        print("[PASS] WSLPE standalone learner foundation")

    # Must prove local (not AD) learner before any scenario mutation.
    # The WSLPE status adapter performs exact COMPUTERNAME/PartOfDomain
    # checks and requires an existing enabled local lpe.trainee.
    status_cmd = [str(ansible), "-i", str(inventory), "-i", str(varsfile),
                  "--limit", "ws01", str(PLAYBOOK),
                  "-e", '{"wslpe_action":"status","wslpe_techniques":[]}']
    status = subprocess.run(status_cmd, cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=600)
    if status.returncode:
        print("[BLOCKED] WSLPE status/learner preflight failed; no scenarios changed")
        print("[NEXT] Complete the standalone learner foundation, then rerun")
        return 2

    root = Path(args.report_dir).expanduser().resolve()
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise ValueError("Untrusted report directory")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.stat().st_uid != os.geteuid() or root.stat().st_mode & 0o077:
        raise ValueError("Report directory must be owned by operator and mode 0700")
    report = root / ("wslpe-qualification-" +
                     datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    records = []
    for technique in catalog:
        for action, state in FLOW:
            cmd = invocation(ansible, inventory, varsfile, technique, action, state)
            print(f"[RUN] {technique}: {action}" + (f"/{state}" if state else ""), flush=True)
            try:
                task = subprocess.run(cmd, cwd=ROOT, env=env, text=True,
                    capture_output=True, timeout=args.timeout_seconds, check=False)
                outcome, diagnostic = task.returncode, (task.stdout + "\n" + task.stderr)
            except subprocess.TimeoutExpired:
                outcome, diagnostic = 124, "Per-technique step timed out"
            entry = {"technique": technique, "action": action,
                     "state": state, "exit_code": outcome}
            # Store only command exit statuses, never secrets/playbook output.
            records.append(entry)
            report.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
            report.chmod(0o600)
            if outcome:
                print(f"[BLOCKED] Failed: {technique} {action}/{state or '-'} (exit {outcome})")
                print(f"[REPORT] {report}")
                print("[STOP] No additional scenario will be modified")
                return 1
            print("[PASS]", flush=True)
    print("[PASS] WSLPE_STANDALONE_20_TECHNIQUES_ACCEPTED=TRUE")
    print("[INFO] Each scenario was left in the intended vulnerable state")
    print(f"[REPORT] {report}")
    print("[NOT VERIFIED] Learner isolation, RDP and course documentation")
    return 0

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="explicitly qualify all scenarios on trusted local WSLPE")
    parser.add_argument("--bootstrap-learner", action="store_true",
                        help="on --execute, first apply the existing WSLPE-only local foundation")
    parser.add_argument("--report-dir", default=str(
        Path.home() / ".local/state/kingdoms-wslpe-qualification"))
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()
    if not 120 <= args.timeout_seconds <= 3600:
        parser.error("Per-step timeout must be between 120 and 3600 seconds")
    if args.bootstrap_learner and not args.execute:
        parser.error("--bootstrap-learner requires explicit --execute")
    try:
        return run(args)
    except (OSError, ValueError, KeyError, TypeError,
            json.JSONDecodeError) as exc:
        print(f"[BLOCKED] WSLPE qualification aborted: {type(exc).__name__}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
