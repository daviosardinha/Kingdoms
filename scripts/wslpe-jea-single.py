#!/usr/bin/env python3
"""WSLPE #30 JEA source plan or guarded source STAGING only.

Windows PowerShell 5.1 JEA registration can stop WinRM. Registration/removal
MUST be executed by the independent elevated VMware guest-console runner.
This script can ONLY copy audited PowerShell modules using pinned WSLPE WinRM.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kingdoms.wslpe45_batch_operator import index_rows, controller_source_blockers, trusted_safety
from kingdoms.wslpe_vmrun_recovery import verify_vmrun_output

EXPECTED_ID="jea_role_capability_misconfig"
STAGE_SOURCE=ROOT/"ansible/wslpe45/jea_local_stage.yml"
STAGE_INSPECT=ROOT/"scripts/wslpe-stage2-inspect.py"
HTTPS_AUDIT=ROOT/"scripts/wslpe-https-auth-audit.py"
THUMB="C773EC26D02940F559FE715B83628FEDAE2AA92D"
SNAPSHOT="KINGDOMS-WSLPE-PRE-JEA"

def local_candidate() -> dict:
    row=next((r for r in index_rows() if r["number"]==30),None)
    if (not row or row["id"]!=EXPECTED_ID or row["source_ci"]!="passed"
            or row["status"]!="candidate"):
        raise ValueError("JEA #30 source candidate unavailable")
    path=ROOT/row["playbook"]
    if path.is_symlink() or not path.is_file():
        raise ValueError("JEA fixture source missing")
    plays=yaml.safe_load(path.read_text(encoding="utf-8"))
    if (not isinstance(plays,list) or len(plays)!=2
            or [p.get("hosts") for p in plays]!=["localhost","wslpe"]
            or controller_source_blockers(path,plays)):
        raise ValueError("JEA fixture source dependencies invalid")
    guard=plays[1].get("pre_tasks",[])
    if (not guard or "ansible.builtin.fail" not in guard[0]
            or guard[0].get("when")!=
            "(wslpe_45_action | default('')) in ['apply', 'reset']"):
        raise ValueError("Remote apply/reset guard missing")
    staged=yaml.safe_load(STAGE_SOURCE.read_text(encoding="utf-8"))
    if (STAGE_SOURCE.is_symlink() or len(staged)!=2
            or [p.get("hosts") for p in staged]!=["localhost","wslpe"]
            or controller_source_blockers(STAGE_SOURCE,staged)):
        raise ValueError("Staging provenance or scope invalid")
    text=STAGE_SOURCE.read_text(encoding="utf-8")
    if any(v not in text for v in (
            "wslpe_jea_stage_approved", "WslpeJeaLocal.psm1",
            "WSLPE45_JEA_LOCAL_SOURCE=STAGED_NOT_EXECUTED")):
        raise ValueError("Missing copy-only JEA staging contract")
    if any(x in text for x in (
            "Register-PSSessionConfiguration", "Unregister-PSSessionConfiguration",
            "Invoke-Wslpe45Jea -Action", "Restart-Service")):
        raise ValueError("Staging source attempts an endpoint operation")
    return row

def exact_running_vm_and_snapshot() -> None:
    spec=importlib.util.spec_from_file_location("wslpe_jea_native_stage2",STAGE_INSPECT)
    if spec is None or spec.loader is None:
        raise ValueError("Native WSLPE registration helper unavailable")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    directory, meta=mod.find_instance(mod.WORKSPACE)
    if meta.get("lab")!="WSLPE" or meta.get("provider")!="vmware":
        raise ValueError("Not native standalone WSLPE")
    vmx=mod.locate_registered_vm(directory)
    if (vmx.is_symlink() or not vmx.is_file()
            or not vmx.resolve(strict=True).is_relative_to(mod.WORKSPACE.resolve())
            or vmx.stat().st_uid!=os.geteuid()):
        raise ValueError("VM owner or canonical path mismatch")
    active=subprocess.run(["vmrun","-T","ws","list"],text=True,
                          capture_output=True,timeout=35,check=False)
    if active.returncode:
        raise ValueError("VMware inventory unavailable")
    verify_vmrun_output(active.stdout,vmx)
    snap=subprocess.run(["vmrun","-T","ws","listSnapshots",str(vmx)],
                        text=True,capture_output=True,timeout=70,check=False)
    if snap.returncode or snap.stdout.splitlines().count(SNAPSHOT)!=1:
        raise ValueError("Pre-JEA snapshot missing or ambiguous")
    print("[PASS] Exact registered running WSLPE and recovery snapshot")

def pinned_https_preflight() -> None:
    check=subprocess.run([sys.executable,str(HTTPS_AUDIT),
                          "--expected-thumbprint",THUMB],
                         cwd=ROOT,capture_output=True,text=True,timeout=80,
                         check=False)
    if check.returncode or "[PASS] WSLPE_AUTHENTICATED_HTTPS=TRUE" not in check.stdout:
        raise ValueError("Pinned WSLPE management HTTPS not available")
    print("[PASS] WSLPE-only pinned authenticated WinRM HTTPS")

def verify_source_checkout() -> None:
    branch=subprocess.run(
        ["git","branch","--show-current"],cwd=ROOT,capture_output=True,
        text=True,timeout=12,check=False)
    dirty=subprocess.run(
        ["git","status","--porcelain"],cwd=ROOT,capture_output=True,
        text=True,timeout=12,check=False)
    if (branch.returncode or branch.stdout.strip()!="feature/windows-lpe-45-batch"
            or dirty.returncode or dirty.stdout.strip()):
        raise ValueError("Source checkout must be clean and on exact WSLPE branch")

def stage_sources() -> None:
    verify_source_checkout()
    exact_running_vm_and_snapshot()
    pinned_https_preflight()
    guard=trusted_safety()
    inventory,varsfile,address=guard.exact_standalone()
    bin=Path.home()/".goad/.venv/bin"
    ansible,ansible_inv=bin/"ansible-playbook",bin/"ansible-inventory"
    if not ansible.is_file() or not ansible_inv.is_file():
        raise ValueError("Pinned Ansible runtime missing")
    env=os.environ.copy()
    env.update({"ANSIBLE_CONFIG":str(ROOT/"ansible/ansible.cfg"),
                "ANSIBLE_ROLES_PATH":str(ROOT/"ansible/roles"),
                "ANSIBLE_NOCOLOR":"1"})
    resolved=subprocess.run(
        guard.resolved_inventory_command(ansible_inv,inventory,varsfile),
        cwd=ROOT,env=env,capture_output=True,text=True,timeout=45,check=False)
    if resolved.returncode:
        raise ValueError("Effective inventory lookup failed")
    guard.check_inventory(json.loads(resolved.stdout),address)
    print("[SCOPE] Copy three WSLPE-only PowerShell modules; NO JEA changes",flush=True)
    confirmation=input("Type STAGE WSLPE JEA 30 to copy files only: ").strip()
    if confirmation!="STAGE WSLPE JEA 30":
        raise ValueError("Stage confirmation cancelled")
    args=[
        str(ansible),"-i",str(inventory),"-i",str(varsfile),
        "--limit","ws01,localhost",str(STAGE_SOURCE),
        "-e",json.dumps({"wslpe_expected_address":address,
                         "wslpe_45_action":"stage",
                         "wslpe_45_technique":EXPECTED_ID,
                         "wslpe_jea_stage_approved":True},
                        separators=(",",":")),
    ]
    result=subprocess.run(args,cwd=ROOT,env=env,timeout=240,check=False)
    if result.returncode:
        raise ValueError("Staging failed; inspect exact owned library before retry")
    print("[PASS] JEA local-console source STAGED; NO endpoint registration",flush=True)
    print("[NEXT] Use elevated VMware console to Inspect existing #30 before lifecycle")

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    exclusive=parser.add_mutually_exclusive_group()
    exclusive.add_argument("--stage",action="store_true",
                           help="explicit copy-only source stage to exact WSLPE guest")
    exclusive.add_argument("--apply",action="store_true",
                           help="always refused: remote JEA endpoint mutation unsafe")
    parser.add_argument("--recovery-rehearsed",action="store_true",
                        help="legacy flag; cannot authorize remote mutation")
    args=parser.parse_args()
    print("KINGDOMS WSLPE | JEA #30 INDEPENDENT LIFECYCLE",flush=True)
    try:
        local_candidate()
        print("[PASS] Source and fail-closed WinRM mutation guard verified")
        if args.apply or args.recovery_rehearsed:
            print("[BLOCKED] Remote JEA endpoint apply/reset is forbidden on PS5.1")
            return 2
        if not args.stage:
            print("[PLAN ONLY] No VMware, WinRM, Ansible or NORTH actions")
            print("[NEXT] --stage copies modules; console-local Inspect/Apply/Reset")
            return 0
        if not sys.stdin.isatty():
            raise ValueError("Stage requires interactive operator confirmation")
        stage_sources()
        return 0
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError,
            subprocess.SubprocessError) as exc:
        print(f"[BLOCKED] {type(exc).__name__}; no automatic retry/rollback",flush=True)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
