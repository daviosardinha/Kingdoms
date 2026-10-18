#!/usr/bin/env python3
"""WSLPE #40 independent read-only native post-staging integrity gate.

Checks the pinned WinRM guest, immutable native GitHub run, exact uploaded
native artifact digests and operator source, existing protected library,
no symlinked/stale/partial objects and no running privileged RPC server.
Never creates a Windows fixture, starts RPC, grants access or changes JEA.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
REPO="daviosardinha/Kingdoms"
NATIVE_NAMES=("Kingdom40LocalRpcServer.exe","Kingdom40LocalRpcClient.exe")
OPERATOR="Wslpe40RpcOperator.psm1"

def imported(path, name):
    spec=spec_from_file_location(name,ROOT/"scripts"/path)
    if spec is None or spec.loader is None:
        raise ValueError("Required WSLPE-only verification module missing")
    mod=module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def expected_sha(stage,run):
    data=json.loads(stage.command(
        "gh","api",f"repos/{REPO}/actions/runs/{run}"
    ))
    sha=data.get("head_sha")
    if (data.get("conclusion")!="success" or
            data.get("head_branch")!=stage.BRANCH or
            not isinstance(sha,str) or len(sha)!=40 or
            any(c not in "0123456789abcdef" for c in sha.lower())):
        raise ValueError("Native GitHub run is not approved for review")
    # The native sources must not have changed since the build was produced.
    changed=subprocess.run(
        ["git","diff","--quiet",sha,"HEAD","--",
         "ansible/files/wslpe45/Kingdom40LocalRpcServer.cpp",
         "ansible/files/wslpe45/Kingdom40LocalRpcClient.cpp",
         "ansible/files/wslpe45/Kingdom40LocalRpc.idl"],
        cwd=ROOT,capture_output=True,check=False,
    )
    if changed.returncode!=0:
        raise ValueError("Native RPC source diverges from pinned Windows build")
    return sha

def validate_runtime(state,audit,paths):
    required={
        "machine":"WSLPE-WS01",
        "domain_joined":False,
        "learner_standard":True,
        "winrm_running":True,
        "jea_endpoint_count":1,
        "jea_module_present":True,
        "library_present":True,
        "library_acl_protected":True,
        "library_linked":False,
        "rpc_fixture_present":False,
        "rpc_fixture_linked":False,
        "rpc_proof_present":False,
        "rpc_proof_linked":False,
        "rpc_operator_staged":True,
        "rpc_server_staged":True,
        "rpc_client_staged":True,
        "rpc_host_count":0,
    }
    for key,value in required.items():
        if state.get(key)!=value:
            raise ValueError("WSLPE guest baseline mismatch: "+key)
    if (not audit["token_elevated_admin"] or
            not audit["library_acl_protected"] or
            audit["rpc_host_count"]!=0 or
            audit["partial_files"]):
        raise ValueError("Guest ownership or transfer-cleanup state mismatch")
    records={item["name"]:item for item in audit["exact_files"]}
    if set(records)!=set(paths):
        raise ValueError("Unexpected RPC final-stage inventory")
    for name,expected in paths.items():
        evidence=records[name]
        if (not evidence["present"] or evidence["linked"] or
                evidence["size"]<=0 or
                evidence["sha256"].upper()!=expected.upper()):
            raise ValueError("Staged artifact checksum/integrity mismatch: "+name)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id",required=True,type=int)
    args=p.parse_args()
    print("KINGDOMS WSLPE | #40 INDEPENDENT POSTSTAGE AUDIT (READ ONLY)")
    print("[NO GUEST CHANGES] No fixture, RPC listener, installer, ACL or JEA actions")
    try:
        stage=imported("wslpe40-stage.py","wslpe40_poststage_source")
        audit=imported("wslpe40-stage-audit.py","wslpe40_poststage_audit")
        pre=stage.load_preflight()
        stage.local_source_head()
        stage.verify_vm_snapshot(pre)
        sha=expected_sha(stage,args.run_id)
        with tempfile.TemporaryDirectory(prefix="wslpe40-poststage-") as temp:
            _,native=stage.evidence_from_runner(args.run_id,sha,Path(temp))
            local_operator=ROOT/"ansible/files/wslpe45"/OPERATOR
            if local_operator.is_symlink():
                raise ValueError("Linked operator source")
            hashes={
                name:hashlib.sha256(path.read_bytes()).hexdigest().upper()
                for name,path in native.items()
            }
            hashes[OPERATOR]=hashlib.sha256(local_operator.read_bytes()).hexdigest().upper()
            auth=pre.load_auth()
            address,certificate=auth.checked_certificate(auth.tls_audit_module(),stage.PIN)
            user,password=auth.operator_credentials(address)
            state=pre.query(auth,address,certificate,user,password)
            with stage.managed_session(auth,address,certificate,user,password) as session:
                response=session.run_ps(audit.READ_ONLY)
                if response.status_code!=0:
                    raise ValueError("Windows rejected poststage read-only audit")
                observed=audit.parse_record(response.std_out)
            validate_runtime(state,observed,hashes)
    except Exception as exc:
        print("[BLOCKED] "+type(exc).__name__+": preserve guest state")
        return 2
    print("[PASS] Exact snapshot-backed WSLPE-WS01 and standard learner")
    print("[PASS] Staged operator, native server and client match pinned SHA-256")
    print("[PASS] Protected library; no partial transfers; no privileged RPC host")
    print("[PASS] JEA #30 endpoint and module still present")
    print("[PASS] WSLPE40_INDEPENDENT_POSTSTAGE_VERIFIED=TRUE")
    print("[NOT EXECUTED] Privileged-host and learner authorization require separate acceptance")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
