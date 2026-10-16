#!/usr/bin/env python3
"""WSLPE-only fast-track qualification of NORTH's shared 20 LPE techniques.

Defaults to PLAN ONLY. With --execute, runs each technique serially through
the existing WSLPE adapter: apply / validate(vulnerable) / reset /
validate(clean) / reapply / validate(vulnerable). Stops at the FIRST failure,
writes a private per-step report, and never targets NORTH or a domain member.

Prerequisites: existing trusted local WSLPE development VM, completed
wslpe-foundation.yml learner account, valid WSLPE-only inventory and
KINGDOMS_WSLPE_LEARNER_PASSWORD from an operator-only local store.
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
sys.path.insert(0, str(ROOT))

from kingdoms.wslpe_learner_credentials import learner_password, read_local_access
from kingdoms.wslpe_fast_track_resume import load_private_checkpoint, load_chained_private_checkpoint
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
    # find_instance returns the actual native instance DIRECTORY, not
    # its ID. Never reconstruct a path from an identifier/string.
    if not isinstance(identity, Path) or identity.is_symlink():
        raise ValueError("Untrusted native WSLPE instance directory")
    inventory_path = identity / "inventory"
    if inventory_path.is_symlink() or not inventory_path.is_file():
        raise ValueError("WSLPE native inventory unavailable or symlinked")
    inventory = inventory_path.resolve(strict=True)
    if not inventory.is_relative_to(stage.WORKSPACE.resolve()):
        raise ValueError("WSLPE inventory escapes the native workspace")
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
        # Never expose credentials or full host variables in diagnostics.
        # We can safely report only the IP and connection transport.
        actual_ip = host.get("ansible_host", "<absent>")
        actual_transport = host.get("ansible_connection", "<absent>")
        raise ValueError(
            "Resolved WSLPE inventory mismatch: "
            f"expected host={expected}, connection=winrm; "
            f"resolved host={actual_ip}, connection={actual_transport}"
        )
    if not host.get("ansible_user") or host.get("domain_name") != "WSLPE":
        raise ValueError("WSLPE-only management identity not resolved")
    for forbidden in ("dc", "domain"):
        if groups.get(forbidden, {}).get("hosts"):
            raise ValueError("Domain/DC hosts appear in WSLPE inventory")

def resolved_inventory_command(ansible_inventory: Path, inventory: Path,
                               varsfile: Path) -> list[str]:
    """Use Ansible's merged effective hostvars, not --export source layout."""
    return [
        str(ansible_inventory), "-i", str(inventory), "-i", str(varsfile),
        "--list",
    ]


def invocation(ansible: Path, inventory: Path, varsfile: Path,
               technique: str, action: str, state: str | None) -> list[str]:
    if technique not in load_catalog() or action not in {"apply", "validate", "reset"}:
        raise ValueError("Unknown WSLPE technique/action")
    variables = {"wslpe_action": action, "wslpe_techniques": [technique]}
    if state:
        if action != "validate" or state not in {"vulnerable", "clean"}:
            raise ValueError("Invalid WSLPE validation state")
        variables["windows_lpe_validate_state"] = state
    # Include localhost so the first play's WSLPE-only authorization
    # assertions are not silently skipped by --limit ws01.
    return [str(ansible), "-i", str(inventory), "-i", str(varsfile),
            "--limit", "ws01,localhost", str(PLAYBOOK), "-e",
            json.dumps(variables, separators=(",", ":"))]

def private_report_dir(location: str) -> Path:
    # Do not resolve a symlink and mistake it for an approved private store.
    target = Path(location).expanduser()
    if target.is_symlink():
        raise ValueError("WSLPE report directory is a symlink")
    target.mkdir(parents=True, mode=0o700, exist_ok=True)
    if (not target.is_dir() or target.stat().st_uid != os.geteuid()
            or target.stat().st_mode & 0o077):
        raise ValueError("WSLPE report directory must be owner-only (0700)")
    return target.resolve()


def private_failure_log(root: Path, label: str, diagnostic: str) -> Path:
    from secrets import token_hex
    if not re.fullmatch(r"[a-z0-9_-]+", label):
        raise ValueError("Invalid WSLPE failure log label")
    logfile = root / f"wslpe-{label}-{token_hex(6)}.log"
    fd = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(diagnostic[-120_000:])
        stream.write("\n")
    return logfile


AIE_PREPARE = ROOT / "ansible/wslpe-always-install-elevated-preflight.yml"


def prepare_standalone_aie(*, ansible: Path, inventory: Path, varsfile: Path,
                           env: dict, report_root: Path, timeout: int) -> bool:
    """Only WSLPE: create the local learner profile and reconcile an
    EMPTY, untracked directory from the previous failed apply.
    The safety assertions live in the WSLPE-only playbook.
    """
    if not AIE_PREPARE.is_file():
        raise ValueError("WSLPE-only AIE profile preflight is missing")
    command = [
        str(ansible), "-i", str(inventory), "-i", str(varsfile),
        "--limit", "ws01,localhost", str(AIE_PREPARE),
    ]
    print("[RUN] WSLPE-only local profile and failed-apply preflight", flush=True)
    try:
        result = subprocess.run(
            command, cwd=ROOT, env=env, capture_output=True, text=True,
            timeout=timeout, check=False)
        status = result.returncode
        diagnostic = result.stdout + "\n" + result.stderr
    except subprocess.TimeoutExpired:
        status, diagnostic = 124, "WSLPE-only profile preparation timed out"
    if status:
        path = private_failure_log(report_root, "aie-profile-preflight", diagnostic)
        print(f"[BLOCKED] WSLPE profile preparation exit={status}")
        print(f"[DIAGNOSTIC] Private Ansible log: {path} (redact before sharing)")
        return False
    print("[PASS] WSLPE-only learner profile ready and partial fixture reconciled")
    return True


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
        if args.resume_report:
            root = private_report_dir(args.report_dir)
            position = (
                load_chained_private_checkpoint(
                    args.resume_prefix_report, args.resume_report, root, catalog, FLOW)
                if args.resume_prefix_report else
                load_private_checkpoint(args.resume_report, root, catalog, FLOW)
            )
            print(f"[RESUME PLAN] Revalidate {position} previously passed scenarios")
            print(f"[RESUME PLAN] Start from {position+1:02d}. {catalog[position]}")
            if args.recover_aie_reset:
                if catalog[position] != "always_install_elevated":
                    raise ValueError("AIE recovery only permitted at the exact seventh-technique checkpoint")
                print("[RESUME PLAN] WSLPE-only failed-reset snapshot recovery before AIE clean check")
        else:
            for n, technique in enumerate(catalog, 1):
                print(f"  {n:02d}. {technique}")
        return 0

    print("[WARNING] This intentionally installs/resets vulnerable LPE scenarios")
    print("[WARNING] Trusted WSLPE development ONLY; not safe for student access")
    # --execute is explicit operator authorization; no terminal-dependent
    # prompt or fragile confirmation phrase is required.
    env = os.environ.copy()
    env["ANSIBLE_CONFIG"] = str(ROOT / "ansible/ansible.cfg")
    env["ANSIBLE_ROLES_PATH"] = str(ROOT / "ansible/roles")
    env["ANSIBLE_NOCOLOR"] = "1"
    venv = Path.home() / ".goad/.venv/bin"
    ansible = venv / "ansible-playbook"
    ansible_inv = venv / "ansible-inventory"
    if not ansible.is_file() or not ansible_inv.is_file():
        raise ValueError("Existing trusted GOAD Ansible environment missing")

    validate = subprocess.run(
        # Use effective merged hostvars, never the export-oriented format.
        resolved_inventory_command(ansible_inv, inventory, varsfile),
        cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=40, check=False,
    )
    if validate.returncode:
        raise ValueError("WSLPE Ansible inventory resolution failed")
    check_inventory(json.loads(validate.stdout), expected)
    report_root = private_report_dir(args.report_dir)
    if args.resume_report and args.bootstrap_learner:
        raise ValueError("Resume cannot also bootstrap/modify the existing learner foundation")
    resume_index = (
        (
            load_chained_private_checkpoint(
                args.resume_prefix_report, args.resume_report,
                report_root, catalog, FLOW)
            if args.resume_prefix_report else
            load_private_checkpoint(args.resume_report, report_root, catalog, FLOW)
        ) if args.resume_report else 0
    )
    if args.resume_report:
        print(f"[RESUME] Approved checkpoint failure at {catalog[resume_index]}; "
              f"revalidating {resume_index} earlier scenarios, not resetting them")

    # Generate ONE unique local learner credential on the first approved
    # bootstrap and reuse it on every subsequent qualification. No prompt.
    # Do not create any secret before exact WSLPE target/inventory checks.
    env["KINGDOMS_WSLPE_LEARNER_PASSWORD"] = learner_password(
        bootstrap=args.bootstrap_learner, environ=env)
    print("[PASS] Reusable WSLPE-WS01 local learner credential resolved")

    # Optional, explicitly approved local learner foundation using
    # the existing WSLPE playbook, not NORTH's domain-joined baseline.
    # Its first guest task asserts exact hostname and no AD membership
    # before changing Windows settings or creating the learner account.
    if args.bootstrap_learner:
        foundation = ROOT / "ansible/wslpe-foundation.yml"
        print("[RUN] WSLPE-only local learner foundation (may perform a license reboot)")
        setup = subprocess.run(
            [str(ansible), "-i", str(inventory), "-i", str(varsfile),
             "--limit", "ws01,localhost", str(foundation)],
            cwd=ROOT, env=env, capture_output=True, text=True,
            timeout=3600, check=False,
        )
        if setup.returncode:
            private_log = private_failure_log(
                report_root, "learner-foundation", setup.stdout + "\n" + setup.stderr)
            print(f"[BLOCKED] Standalone learner foundation exit={setup.returncode}")
            print(f"[DIAGNOSTIC] Private Ansible log: {private_log} (redact before sharing)")
            print("[STOP] No LPE scenario was applied")
            return 2
        print("[PASS] WSLPE standalone learner foundation")

    # Must prove local (not AD) learner before any scenario mutation.
    # The WSLPE status adapter performs exact COMPUTERNAME/PartOfDomain
    # checks and requires an existing enabled local lpe.trainee.
    status_cmd = [str(ansible), "-i", str(inventory), "-i", str(varsfile),
                  "--limit", "ws01,localhost", str(PLAYBOOK),
                  "-e", '{"wslpe_action":"status","wslpe_techniques":[]}']
    status = subprocess.run(status_cmd, cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=600)
    if status.returncode:
        private_log = private_failure_log(
            report_root, "learner-status", status.stdout + "\n" + status.stderr)
        print("[BLOCKED] WSLPE status/learner preflight failed; no scenarios changed")
        print(f"[DIAGNOSTIC] Private Ansible log: {private_log} (redact before sharing)")
        print("[NEXT] Inspect the precise WSLPE-only failure above, not NORTH")
        return 2

    # The previous report alone is NOT evidence of current guest state.
    # Verify every skipped technique without applying or resetting it.
    for technique in catalog[:resume_index]:
        cmd = invocation(ansible, inventory, varsfile, technique, "validate", "vulnerable")
        checked = subprocess.run(
            cmd, cwd=ROOT, env=env, capture_output=True, text=True,
            timeout=args.timeout_seconds, check=False)
        if checked.returncode:
            private_log = private_failure_log(
                report_root, "resume-preflight", checked.stdout + "\n" + checked.stderr)
            print(f"[BLOCKED] Existing vulnerable state drift: {technique}")
            print(f"[DIAGNOSTIC] {private_log} (redact before sharing)")
            return 2
        print(f"[PASS] Previous WSLPE scenario still vulnerable: {technique}", flush=True)

    prepared_aie = False
    if args.resume_report:
        # A failed apply may have left its working directory behind.
        # For technique 7, first validate/create the local learner profile
        # and remove ONLY the empty, untracked exact candidate directory.
        # This does not mutate the six previously accepted techniques.
        failed_technique = catalog[resume_index]
        if args.recover_user_rights:
            if failed_technique not in {"sebackup_privilege", "seimpersonate_privilege"}:
                raise ValueError("Rights recovery must target the exact failed SeBackup/SeImpersonate apply")
            print(f"[RECOVERY] Reset exact WSLPE-only {failed_technique} state through direct LSA", flush=True)
            reset_cmd = invocation(
                ansible, inventory, varsfile, failed_technique, "reset", None)
            recovery = subprocess.run(
                reset_cmd, cwd=ROOT, env=env, capture_output=True, text=True,
                timeout=args.timeout_seconds, check=False)
            if recovery.returncode:
                private_log = private_failure_log(
                    report_root, "rights-reset-recovery",
                    recovery.stdout + "\n" + recovery.stderr)
                print(f"[BLOCKED] WSLPE {failed_technique} snapshot recovery exit={recovery.returncode}")
                print(f"[DIAGNOSTIC] {private_log} (redact before sharing)")
                return 2
            print(f"[PASS] WSLPE-only {failed_technique} snapshot restored", flush=True)
        if args.recover_aie_reset:
            if failed_technique != "always_install_elevated":
                raise ValueError("Scoped AIE reset recovery cannot target any other technique")
            # The prior APPLY checkpoint proves exactly six prior complete
            # cycles; revalidate each one before entering this repair.
            # A more recent report shows AIE applied and reset failed.
            print("[RECOVERY] Restore exact WSLPE AIE registry snapshot before resume", flush=True)
            reset_cmd = invocation(
                ansible, inventory, varsfile, failed_technique, "reset", None)
            reset = subprocess.run(
                reset_cmd, cwd=ROOT, env=env, capture_output=True, text=True,
                timeout=args.timeout_seconds, check=False)
            if reset.returncode:
                private_log = private_failure_log(
                    report_root, "aie-reset-recovery", reset.stdout + "\n" + reset.stderr)
                print(f"[BLOCKED] WSLPE-only AIE snapshot reset exit={reset.returncode}")
                print(f"[DIAGNOSTIC] {private_log} (redact before sharing)")
                return 2
            print("[PASS] WSLPE AIE snapshot restored and temporary hive unloaded", flush=True)
        if failed_technique == "always_install_elevated":
            if not prepare_standalone_aie(
                ansible=ansible, inventory=inventory, varsfile=varsfile,
                env=env, report_root=report_root,
                timeout=args.timeout_seconds):
                return 2
            prepared_aie = True
        clean_cmd = invocation(
            ansible, inventory, varsfile, failed_technique, "validate", "clean")
        clean = subprocess.run(
            clean_cmd, cwd=ROOT, env=env, capture_output=True, text=True,
            timeout=args.timeout_seconds, check=False)
        if clean.returncode:
            private_log = private_failure_log(
                report_root, "resume-clean-check", clean.stdout + "\n" + clean.stderr)
            print(f"[BLOCKED] Previous failed apply may have partial state: {failed_technique}")
            print(f"[DIAGNOSTIC] {private_log} (redact before sharing)")
            print("[STOP] Inspect and restore the exact WSLPE fixture before retry")
            return 2
        print(f"[PASS] Previously failed scenario is clean: {failed_technique}")

    report = report_root / ("wslpe-qualification-" +
                     datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    records = []
    for technique in catalog[resume_index:]:
        if technique == "always_install_elevated" and not prepared_aie:
            if not prepare_standalone_aie(
                ansible=ansible, inventory=inventory, varsfile=varsfile,
                env=env, report_root=report_root,
                timeout=args.timeout_seconds):
                print("[STOP] No AlwaysInstallElevated apply or further scenario changes")
                return 2
            prepared_aie = True
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
                private_log = private_failure_log(
                    report_root, "scenario", diagnostic)
                print(f"[BLOCKED] Failed: {technique} {action}/{state or '-'} (exit {outcome})")
                print(f"[DIAGNOSTIC] Private Ansible log: {private_log} (redact before sharing)")
                print(f"[REPORT] {report}")
                print("[STOP] No additional scenario will be modified")
                return 1
            print("[PASS]", flush=True)
    print("[PASS] WSLPE_STANDALONE_20_TECHNIQUES_ACCEPTED=TRUE")
    if resume_index:
        print(f"[PASS] {resume_index} previous technique states independently revalidated")
    print("[INFO] Each scenario was left in the intended vulnerable state")
    print(f"[REPORT] {report}")
    print("[NOT VERIFIED] Learner isolation, RDP and course documentation")
    return 0

def build_parser() -> argparse.ArgumentParser:
    """Single source of truth for runtime and test argument defaults."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="explicitly qualify all scenarios on trusted local WSLPE")
    parser.add_argument("--resume-report", type=Path,
                        help="resume a failed APPLY checkpoint after revalidating earlier vulnerable scenarios")
    parser.add_argument("--resume-prefix-report", type=Path,
                        help="optional original WSLPE checkpoint when --resume-report contains only continuation techniques")
    parser.add_argument("--recover-aie-reset", action="store_true",
                        help="with --execute and original AIE checkpoint: finish partial WSLPE-only AIE reset first")
    parser.add_argument("--recover-user-rights", action="store_true",
                        help="with --execute and exact failed SeBackup/SeImpersonate APPLY checkpoint: restore one partial rights fixture")
    parser.add_argument("--bootstrap-learner", action="store_true",
                        help="on --execute, first create/reuse a unique local learner and apply the WSLPE-only foundation")
    parser.add_argument("--show-learner-access", action="store_true",
                        help="explicitly display local WSLPE learner credentials (never in routine logs)")
    parser.add_argument("--report-dir", default=str(
        Path.home() / ".local/state/kingdoms-wslpe-qualification"))
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not 120 <= args.timeout_seconds <= 3600:
        parser.error("Per-step timeout must be between 120 and 3600 seconds")
    if args.bootstrap_learner and not args.execute:
        parser.error("--bootstrap-learner requires explicit --execute")
    if args.resume_report and args.bootstrap_learner:
        parser.error("Resume cannot rerun learner foundation; choose one path")
    if args.resume_prefix_report and not args.resume_report:
        parser.error("--resume-prefix-report requires the later --resume-report")
    if args.recover_user_rights and not args.resume_prefix_report:
        parser.error("--recover-user-rights requires the original --resume-prefix-report")
    if args.recover_aie_reset and (not args.execute or not args.resume_report or args.bootstrap_learner):
        parser.error("--recover-aie-reset requires --execute and original --resume-report, no bootstrap")
    if args.recover_user_rights and (not args.execute or not args.resume_report or args.bootstrap_learner or args.recover_aie_reset):
        parser.error("--recover-user-rights requires --execute and original --resume-report, no bootstrap or AIE recovery")
    if args.show_learner_access and (args.execute or args.bootstrap_learner):
        parser.error("--show-learner-access is a separate, read-only operation")
    try:
        if args.show_learner_access:
            user, password = read_local_access()
            print("[LOCAL DEVELOPMENT ACCOUNT — NOT LEARNER RELEASE AUTHORIZATION]")
            print(f"Windows username: {user}")
            print(f"Windows password: {password}")
            return 0
        return run(args)
    except json.JSONDecodeError:
        print("[BLOCKED] WSLPE qualification: Ansible inventory returned invalid JSON")
        return 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # Our custom errors are actionable; do not display raw Ansible
        # stdout, arbitrary secret values or credentials in diagnostics.
        safe = str(exc) if type(exc) is ValueError else type(exc).__name__
        print(f"[BLOCKED] WSLPE qualification: {safe}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
