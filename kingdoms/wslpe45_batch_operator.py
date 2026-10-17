"""One operator run for ALL 25 standalone Windows LPE additions.

Plan mode is completely offline. --execute is fail-closed unless every
standalone-only scenario has an independently implemented, source-checked
playbook. NORTH is never a target and the existing 20-tech role is immutable.

This coordinates ONLY the six-step deployment lifecycle. Real non-admin
exploitation and student release are separate acceptance gates.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from secrets import token_hex

import yaml
from kingdoms.wslpe_batch_catalog import catalog

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "kingdoms/wslpe45_implementation_index.yml"
SAFETY = ROOT / "scripts/wslpe-fast-track-20.py"
SCENARIOS = ROOT / "ansible/wslpe45"
FLOW = (
    ("apply", None, "apply"),
    ("validate", "vulnerable", "vulnerable"),
    ("reset", None, "reset"),
    ("validate", "clean", "clean"),
    ("apply", None, "reapply"),
    ("validate", "vulnerable", "revulnerable"),
)
REQUIRED_STAGE_COUNT = 25 * len(FLOW)
EXPECTED_GROUPS = ("wslpe", "windows_lpe_standalone")


class BatchBlocked(ValueError):
    pass


def index_rows() -> list[dict]:
    if INDEX.is_symlink() or not INDEX.is_file():
        raise BatchBlocked("Standalone batch index missing or symlinked")
    data = yaml.safe_load(INDEX.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise BatchBlocked("Invalid batch index")
    contract = {
        "schema": "kingdoms.wslpe45.impl-index.v1",
        "scope": "standalone-wslpe-only",
        "target": "WSLPE-WS01",
        "shared_north_role_frozen": True,
    }
    approval = data.get("batch_execution_authorized")
    if type(approval) is not bool:
        raise BatchBlocked("Execution approval must be an explicit boolean")
    for field, expected in contract.items():
        if type(data.get(field)) is not type(expected) or data[field] != expected:
            raise BatchBlocked(f"Invalid standalone index contract: {field}")
    rows = data.get("techniques")
    ids = [r["id"] for r in catalog()[20:]]
    if not isinstance(rows, list) or len(rows) != 25:
        raise BatchBlocked("Index must contain exactly all 25 additions")
    for n, (row, expected_id) in enumerate(zip(rows, ids), 21):
        if not isinstance(row, dict) or type(row.get("number")) is not int:
            raise BatchBlocked("Invalid scenario record")
        if row.get("number") != n or row.get("id") != expected_id:
            raise BatchBlocked("Scenario index does not match frozen source catalog")
        if row.get("status") not in ("planned", "candidate"):
            raise BatchBlocked("Scenario status must not claim live acceptance")
        if row.get("source_ci") not in ("pending", "passed"):
            raise BatchBlocked("Invalid source CI status")
        if row.get("learner_proof") != "pending":
            raise BatchBlocked("Learner proof must be tracked separately from lifecycle")
        if row.get("six_stage_qualification") != "pending":
            raise BatchBlocked("Six-stage qualification cannot be forged before guest execution")
        expected_path = (
            "ansible/wslpe45/traversal.yml" if n == 35
            else f"ansible/wslpe45/{expected_id}.yml"
        )
        if row.get("playbook") != expected_path:
            raise BatchBlocked("Refusing alternate path or non-standalone playbook")
    return rows



def controller_source_blockers(playbook: Path, plays: list[dict]) -> list[str]:
    """Resolve all candidate-local copies/imports before guest access.

    Only canonical owned WSLPE sources and the fixed protective task file
    are allowed. This is a controller-side dependency check, not proof that
    the deployed Windows consumer works.
    """
    problems: list[str] = []
    source_dir = (ROOT / "ansible/files/wslpe45").resolve()
    copied: list[Path] = []
    imports = 0
    for play in plays:
        for section in ("pre_tasks", "tasks", "post_tasks"):
            tasks = play.get(section, [])
            if not isinstance(tasks, list):
                problems.append(f"{section} must be a task list")
                continue
            for task in tasks:
                if not isinstance(task, dict):
                    problems.append("invalid task mapping")
                    continue
                source = task.get("ansible.windows.win_copy")
                if source is not None:
                    if not isinstance(source, dict):
                        problems.append("win_copy must be a mapping")
                        continue
                    name = source.get("src")
                    if not isinstance(name, str) or not re.fullmatch(
                        r"\.\./files/wslpe45/[A-Za-z0-9_-]+\.(?:psm1|cs)", name
                    ):
                        problems.append(f"noncanonical controller copy source: {name!r}")
                        continue
                    candidate = playbook.parent / name
                    if (candidate.is_symlink() or not candidate.is_file()
                            or candidate.resolve().parent != source_dir):
                        problems.append(f"missing or unsafe controller copy source: {name}")
                    else:
                        copied.append(candidate.resolve())
                imported = task.get("ansible.builtin.import_tasks")
                if imported is not None:
                    imports += 1
                    if (imported != "lockdown-library.yml"
                            or (playbook.parent / imported).is_symlink()
                            or not (playbook.parent / imported).is_file()):
                        problems.append("unsafe or missing WSLPE library lockdown import")
    if sum(item.name == "WslpeFixture.psm1" for item in copied) != 1:
        problems.append("each candidate must copy one ownership library")
    if imports != 1:
        problems.append("each candidate must import exactly one library lockdown")
    if not copied:
        problems.append("candidate has no resolvable Windows source copies")
    return problems


def source_readiness() -> tuple[list[dict], list[str]]:
    rows = index_rows()
    blockers: list[str] = []
    for row in rows:
        path = ROOT / row["playbook"]
        if row["status"] != "candidate" or row["source_ci"] != "passed":
            blockers.append(f"#{row['number']:02d} {row['id']}: no source-qualified fixture")
            continue
        if path.is_symlink() or not path.is_file():
            blockers.append(f"#{row['number']:02d} {row['id']}: fixture file missing")
            continue
        try:
            plays = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, yaml.YAMLError):
            blockers.append(f"#{row['number']:02d} {row['id']}: invalid fixture YAML")
            continue
        if (not isinstance(plays, list) or len(plays) != 2
                or not isinstance(plays[0], dict) or not isinstance(plays[1], dict)
                or plays[0].get("hosts") != "localhost"
                or plays[1].get("hosts") != "wslpe"):
            blockers.append(f"#{row['number']:02d} {row['id']}: unsafe fixture plays")
            continue
        for reason in controller_source_blockers(path, plays):
            blockers.append(f"#{row['number']:02d} {row['id']}: {reason}")
        text = path.read_text(encoding="utf-8")
        if any(fragment in text for fragment in (
            "ansible/ws01-lpe-install.yml", "hosts: domain", "hosts: dc",
            "GOAD-WS01", "10.4.10.31", "ansible/roles/windows_lpe",
        )):
            blockers.append(f"#{row['number']:02d} {row['id']}: NORTH reference in fixture")
            continue
        # Require a real stage marker *emitted by the fixture*, not by the
        # batch coordinator. CI also checks the actual Windows scripts.
        if "WSLPE45_BATCH_STAGE=" not in text:
            blockers.append(f"#{row['number']:02d} {row['id']}: missing lifecycle evidence marker")
    return rows, blockers


def trusted_safety():
    if SAFETY.is_symlink() or not SAFETY.is_file():
        raise BatchBlocked("Exact native WSLPE operator safety harness missing")
    spec = importlib.util.spec_from_file_location("wslpe45_existing_safety", SAFETY)
    if spec is None or spec.loader is None:
        raise BatchBlocked("Cannot resolve trusted WSLPE guard")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def command(ansible: Path, inventory: Path, varsfile: Path,
            row: dict, expected: str, action: str,
            state: str | None, stage: str | None = None) -> list[str]:
    if row["id"] not in [r["id"] for r in catalog()[20:]]:
        raise BatchBlocked("Unrecognized standalone scenario")
    if action not in ("apply", "validate", "reset"):
        raise BatchBlocked("Invalid scenario action")
    if action == "validate" and state not in ("clean", "vulnerable"):
        raise BatchBlocked("Invalid validation state")
    if action != "validate" and state is not None:
        raise BatchBlocked("Validation state on non-validation action")
    allowed = {"apply": ("apply", "reapply"), "reset": ("reset",),
               "validate": (("clean",) if state == "clean" else ("vulnerable", "revulnerable"))}
    if stage is None:
        stage = {"apply": "apply", "reset": "reset",
                 "validate": state}[action]
    if stage not in allowed[action]:
        raise BatchBlocked("Requested stage label does not match action and validation state")
    variables = {
        "wslpe_expected_address": expected,
        "wslpe_45_action": action,
        "wslpe_45_technique": row["id"],
        "wslpe_45_stage_label": stage,
    }
    if state is not None:
        variables["wslpe_45_validate_state"] = state
    return [
        str(ansible), "-i", str(inventory), "-i", str(varsfile),
        "--limit", "ws01,localhost", str(ROOT / row["playbook"]),
        "-e", json.dumps(variables, separators=(",", ":")),
    ]


def make_private_dir(location: str) -> Path:
    path = Path(location).expanduser()
    if path.is_symlink():
        raise BatchBlocked("Unsafe private evidence directory")
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    if (not path.is_dir() or path.stat().st_uid != os.geteuid()
            or path.stat().st_mode & 0o077):
        raise BatchBlocked("Evidence directory must be owner-only (0700)")
    return path.resolve(strict=True)


def atomic_report(root: Path, name: str, content: dict) -> Path:
    if not re.fullmatch(r"[a-z0-9_-]+\.json", name):
        raise BatchBlocked("Invalid private report filename")
    destination = root / name
    temp = root / ("." + name + "." + token_hex(8))
    fd = os.open(temp, os.O_CREAT | os.O_WRONLY | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, destination)
    finally:
        if temp.exists():
            temp.unlink()
    return destination


def run(args) -> int:
    rows, blockers = source_readiness()
    print("[SCOPE] Standalone WSLPE-WS01 exclusively; NORTH/GOAD untouched", flush=True)
    print(f"[BATCH] {len(rows)} additional scenarios, {REQUIRED_STAGE_COUNT} guest lifecycle stages", flush=True)
    print(f"[READINESS] source-qualified={25-len(blockers)}/25", flush=True)
    if not args.execute:
        for message in blockers:
            print("[PENDING] " + message, flush=True)
        print("[PLAN ONLY] No VMware, WinRM or Ansible connection", flush=True)
        return 0
    if blockers:
        print(f"[BLOCKED] All 25 source fixtures required before ANY guest change; remaining={len(blockers)}", flush=True)
        return 2
    if yaml.safe_load(INDEX.read_text(encoding="utf-8"))["batch_execution_authorized"] is not True:
        print("[BLOCKED] Independent live-execution approval is still disabled", flush=True)
        return 2
    if args.timeout_seconds < 60 or args.timeout_seconds > 3600:
        raise BatchBlocked("Timeout must be within 60-3600 seconds")

    # Only now may any native WSLPE inventory/VMware operation occur.
    base = trusted_safety()
    inv, varsfile, expected = base.exact_standalone()
    venv = Path.home() / ".goad/.venv/bin"
    ansible, ansible_inv = venv / "ansible-playbook", venv / "ansible-inventory"
    if not ansible.is_file() or not ansible_inv.is_file():
        raise BatchBlocked("Approved Ansible runtime missing")
    env = os.environ.copy()
    env.update({
        "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg"),
        "ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles"),
        "ANSIBLE_NOCOLOR": "1",
    })
    inventory = subprocess.run(
        base.resolved_inventory_command(ansible_inv, inv, varsfile),
        cwd=ROOT, env=env, text=True, capture_output=True, timeout=40, check=False)
    if inventory.returncode:
        raise BatchBlocked("Exact WSLPE inventory cannot be resolved")
    base.check_inventory(json.loads(inventory.stdout), expected)

    root = make_private_dir(args.report_dir)
    sentinel = root / ".wslpe45-recovery-required"
    if sentinel.exists() or sentinel.is_symlink():
        raise BatchBlocked("Earlier incomplete live batch needs inspected recovery; never blindly rerun")
    lockfile = root / ".wslpe45-single-run.lock"
    fd = os.open(lockfile, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        report = {
            "schema": "kingdoms.wslpe45.live-lifecycle.v1",
            "scope": "standalone-wslpe-only",
            "target": "WSLPE-WS01",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed": False, "learner_exploitation": "not_verified",
            "events": [],
        }
        report_name = "wslpe45-qualification-" + token_hex(8) + ".json"
        report_path = atomic_report(root, report_name, report)
        # Durable marker before first mutation. The marker is removed only
        # following all 150 stages, otherwise interruption requires recovery.
        guardfd = os.open(sentinel, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(guardfd)
        for row in rows:
            for action, state, label in FLOW:
                requested = command(ansible, inv, varsfile, row, expected, action, state, label)
                try:
                    response = subprocess.run(
                        requested, cwd=ROOT, env=env, capture_output=True,
                        text=True, timeout=args.timeout_seconds, check=False)
                    diagnostics = response.stdout + "\n" + response.stderr
                    rc = response.returncode
                except subprocess.TimeoutExpired:
                    diagnostics, rc = "Standalone guest step timed out", 124
                expected_marker = f"WSLPE45_BATCH_STAGE={row['id']}:{label}:PASS"
                accepted = rc == 0 and diagnostics.count(expected_marker) == 1
                report["events"].append({
                    "number": row["number"], "id": row["id"],
                    "stage": label, "exit_code": rc, "accepted": accepted,
                })
                atomic_report(root, report_name, report)
                if not accepted:
                    failure = base.private_failure_log(
                        root, f"batch-{row['number']}-{label}", diagnostics)
                    print(f"[BLOCKED] #{row['number']} {row['id']} / {label}", flush=True)
                    print(f"[PRIVATE] {failure} (redact before sharing)", flush=True)
                    print(f"[RECOVERY] State journal: {report_path}", flush=True)
                    return 2
                print(f"[PASS] #{row['number']} {row['id']} / {label}", flush=True)
        if len(report["events"]) != REQUIRED_STAGE_COUNT:
            raise BatchBlocked("Missing guest lifecycle stages")
        report["completed"] = True
        report["completed_at"] = datetime.now(timezone.utc).isoformat()
        atomic_report(root, report_name, report)
        sentinel.unlink()
        print(f"[PASS] All {REQUIRED_STAGE_COUNT} standalone guest lifecycle stages accepted", flush=True)
        print(f"[REPORT] {report_path}", flush=True)
        print("[PENDING] Real learner exploitation is a separate proof requirement", flush=True)
        return 0
    finally:
        os.close(fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="run ALL 25 after every source fixture is independently qualified")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--report-dir", default="~/.local/state/kingdoms-wslpe45-live")
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError, json.JSONDecodeError) as error:
        printable = str(error) if type(error) in (BatchBlocked, ValueError) else type(error).__name__
        print("[BLOCKED] WSLPE45 batch operator: " + printable, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
