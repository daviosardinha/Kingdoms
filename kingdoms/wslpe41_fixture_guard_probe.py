"""Only controller-side private WSLPE41 fixture guard proof.

Runs the *original* first play of scenario #1 with --limit localhost --check,
never contacting Windows. Requires the exact accepted existing-instance TLS
operator, exact local private overlay and one already blocked stage1 journal.
The test prints only fixed PASS/FAIL markers, never credential content or
Ansible stdout/stderr.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import subprocess
import yaml
from kingdoms.wslpe41_install_flow import InstallBlocked
from kingdoms.wslpe41_provided_install import (
    STATE_ROOT, INSTANCE, SCHEMA, _preflight, _stages, private_environment,
)
from kingdoms.wslpe41_stage_executor import _environment, _inventory
from kingdoms.wslpe41_provided_runtime import ROOT


def prove(report=print) -> bool:
    journal = STATE_ROOT / INSTANCE / "provided-install.json"
    if journal.is_symlink() or not journal.is_file():
        raise InstallBlocked("Expected blocked stage1 journal missing")
    old = json.loads(journal.read_text(encoding="utf-8"))
    gate = str(old.get("failure_gate", ""))
    if not (old.get("schema") == SCHEMA and old.get("instance") == INSTANCE
            and old.get("status") == "BLOCKED" and old.get("next_stage") == 0
            and old.get("inflight") == {"number": 1, "stage": "apply"}
            and old.get("proofs") == []
            and "last_task=Refuse source-visible fixture credentials in any non-status action" in gate):
        raise InstallBlocked("Not the exact second blocked private-fixture guard")
    context, operator, learner = _preflight()
    plan = _stages(context)
    stages = [item for item in plan if item.transport == "ansible"]
    if len(stages) != 82:
        raise InstallBlocked("Expected 82 Ansible stages and one console stage")
    token = "@" + str(context.private_vars)
    if not all(item.argv.count(token) == 1 for item in stages):
        raise InstallBlocked("Not all 82 Ansible stages load exact private overlay")
    first = plan[0]
    if (first.number != 1 or first.stage != "apply"
            or first.transport != "ansible"
            or first.argv.count("--limit") != 1
            or first.argv.count(token) != 1
            or first.argv.count("-e") != 2):
        raise InstallBlocked("Unapproved private fixture probe first-stage contract")
    yaml_file = ROOT / "ansible" / "wslpe-lpe-test.yml"
    if yaml_file.is_symlink() or not yaml_file.is_file():
        raise InstallBlocked("Canonical 20-stage controller source missing")
    plays = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
    first_play = plays[0] if isinstance(plays, list) and plays else {}
    tasks = first_play.get("tasks") if isinstance(first_play, dict) else None
    if (first_play.get("hosts") != "localhost" or not isinstance(tasks, list)
            or len(tasks) < 3 or any(set(t).difference({
                "name", "ansible.builtin.assert", "when", "no_log",
            }) for t in tasks)):
        raise InstallBlocked("Controller preflight is no longer assert-only")
    if not all("ansible.builtin.assert" in task for task in tasks):
        raise InstallBlocked("Controller preflight gained mutating task")
    args = list(first.argv)
    at = args.index("--limit")
    if args[at + 1] != "ws01,localhost":
        raise InstallBlocked("First-stage localhost isolation selector drift")
    args[at + 1] = "localhost"
    args.insert(1, "--check")
    with private_environment(context, operator, learner):
        env = _environment(context)
        _inventory(context, env)
        result = subprocess.run(
            args, cwd=ROOT, env=env, capture_output=True, text=True,
            stdin=subprocess.DEVNULL, timeout=120, check=False,
        )
    if result.returncode:
        names = re.findall(r"(?m)^TASK \[([^\r\n]{1,180})\]", result.stdout)
        last = re.sub(r"[^A-Za-z0-9 ._:/()-]", "_",
                      names[-1] if names else "no-task-marker")[:100]
        raise InstallBlocked(
            f"Private controller-only Ansible fixture guard FAILED: rc={result.returncode}; last_task={last}")
    for marker in ("Refuse source-visible fixture credentials in any non-status action",
                   "Require the local learner secret for technique application"):
        if result.stdout.count("TASK [" + marker + "]") != 1:
            raise InstallBlocked("Controller-only fixture guard did not execute all checks")
    report("[PASS] Actual controller-only fixture guard with private overlay")
    report("[PASS] All 82 Ansible stages reference the same private YAML")
    report("[NO CHANGES] --check --limit localhost; no Windows or journal writes")
    return True
