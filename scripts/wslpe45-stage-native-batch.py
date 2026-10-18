#!/usr/bin/env python3
"""Copy-only, source-pinned staging for WSLPE #25/#36/#38.

#40 RPC native server and client are already independently staged on
WSLPE-WS01. Its updated operator has its own atomic refresh contract.
No MSI installation, WMI provider registration, DCOM registration, RPC host
launch, JEA edit, or NORTH traffic happens in this operation.

--apply authorizes the exact bounded copy operation; no manual phrases.
A failed copy leaves its uniquely named partial for a read-only investigation
rather than blindly retrying or changing ACLs.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
from pathlib import Path
import re
import subprocess
import tempfile
from secrets import token_hex

ROOT=Path(__file__).resolve().parents[1]
BRANCH="feature/windows-lpe-45-batch"
REPO="daviosardinha/Kingdoms"
DEST=r"C:\ProgramData\KingdomsWSLPE45\lib"
SOURCE_MAP={
    "Wslpe25MsiOperator.psm1":"ansible/files/wslpe45/Wslpe25MsiOperator.psm1",
    "Wslpe25RepairInspection.psm1":"ansible/files/wslpe45/Wslpe25RepairInspection.psm1",
    "Wslpe25RepairPreparation.psm1":"ansible/files/wslpe45/Wslpe25RepairPreparation.psm1",
}
ARTIFACTS={
    "wslpe25-source-review-":{
        "Kingdom25Repair.msi":"msi_sha256",
        "Kingdom25Repair.dll":"custom_action_dll_sha256",
    },
    "wslpe36-38-native-source-review-":{
        "Kingdom36WmiProvider.exe":"Kingdom36WmiProvider.exe_sha256",
        "Kingdom38DcomServer.exe":"Kingdom38DcomServer.exe_sha256",
        "Kingdom38DcomClient.exe":"Kingdom38DcomClient.exe_sha256",
    },
}
MANIFEST={
    "wslpe25-source-review-":"Kingdom25Repair.provenance.txt",
    "wslpe36-38-native-source-review-":"Kingdom36_38.provenance.txt",
}

def load_stage():
    spec=importlib.util.spec_from_file_location(
        "kingdoms_wslpe45_stage_contract",ROOT/"scripts/wslpe40-stage.py")
    if spec is None or spec.loader is None:
        raise ValueError("Exact source-pinned TLS staging contract missing")
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

def cmd(*args,timeout=120):
    r=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=timeout,check=False)
    if r.returncode:
        raise ValueError("Source/artifact retrieval failed")
    return r.stdout.strip()

def hashed(path:Path)->str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size==0:
        raise ValueError("Missing or linked source artifact")
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def manifest(path:Path)->dict:
    data={}
    for line in path.read_text("utf-8-sig").splitlines():
        if not line:
            continue
        if line.count("=")!=1:
            raise ValueError("Malformed artifact provenance")
        k,v=line.split("=",1)
        if k in data:
            raise ValueError("Duplicate artifact provenance field")
        data[k]=v
    return data

def obtain_artifacts(run:int,head:str,folder:Path)->dict[str,Path]:
    import json
    remote=json.loads(cmd("gh","api",f"repos/{REPO}/actions/runs/{run}"))
    if remote.get("head_sha")!=head or remote.get("head_branch")!=BRANCH or remote.get("conclusion")!="success":
        raise ValueError("Expected successful exact branch SHA in Windows build run")
    files={}
    for prefix,names in ARTIFACTS.items():
        directory=folder/prefix.rstrip("-")
        directory.mkdir(mode=0o700)
        cmd("gh","run","download",str(run),"--repo",REPO,
            "--name",prefix+head,"--dir",str(directory))
        expected=set(names)|{MANIFEST[prefix]}
        actual=list(directory.iterdir())
        if {p.name for p in actual}!=expected or any(
            p.is_symlink() or not p.is_file() for p in actual
        ):
            raise ValueError("Unexpected or linked native artifact contents")
        data=manifest(directory/MANIFEST[prefix])
        if data.get("commit")!=head or data.get("state")!="unqualified-not-deployable":
            raise ValueError("Native artifact provenance not from current source")
        if prefix.startswith("wslpe25"):
            if data.get("installation_executed")!="false" or data.get("learner_proof")!="pending":
                raise ValueError("MSI source proof inconsistent")
        else:
            if (data.get("guest")!="WSLPE-WS01" or data.get("registered")!="false"
                or data.get("executed")!="false" or data.get("learner_proof")!="pending"):
                raise ValueError("WMI/DCOM provenance inconsistent")
        for filename,key in names.items():
            path=directory/filename
            if hashed(path)!=data.get(key,"").upper():
                raise ValueError("Native artifact digest mismatch")
            files[filename]=path
    for filename,relative in SOURCE_MAP.items():
        path=ROOT/relative
        hashed(path)
        files[filename]=path
    if len(files)!=8:
        raise ValueError("Unexpected staged artifact cardinality")
    return files

REMOTE_GUARD=r"""
$ErrorActionPreference='Stop'
$system=Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
if($env:COMPUTERNAME -cne 'WSLPE-WS01' -or $system.PartOfDomain) {throw 'Wrong workgroup guest'}
$principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Not admin'}
$lib='C:\ProgramData\KingdomsWSLPE45\lib'
$dir=Get-Item -LiteralPath $lib -Force -ErrorAction Stop
if(-not $dir.PSIsContainer -or ($dir.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
  -not (Get-Acl -LiteralPath $lib -ErrorAction Stop).AreAccessRulesProtected){throw 'Unprotected lib'}
foreach($name in @('Wslpe40RpcOperator.psm1','Kingdom40LocalRpcServer.exe',
                   'Kingdom40LocalRpcClient.exe')){
  $f=Get-Item -LiteralPath (Join-Path $lib $name) -Force -ErrorAction Stop
  if($f.PSIsContainer -or ($f.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'Wrong RPC artifact'}
}
if(@(Get-CimInstance Win32_Process -Filter "Name='Kingdom40LocalRpcServer.exe'").Count -ne 0){throw 'RPC host running'}
foreach($id in @('msi_repair_custom_action','wmi_privileged_provider_authorization',
                 'dcom_server_launch_acl','custom_rpc_authorization')){
  if(Test-Path -LiteralPath (Join-Path 'C:\ProgramData\KingdomsWSLPE45\fixtures' $id)){
    throw 'Unexpected existing native fixture'
  }
}
Write-Output 'WSLPE45_SOURCE_STAGING_SCOPE=PASS'
"""

def staged(session,stage,name:str,path:Path)->str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+",name):
        raise ValueError("Unexpected native destination")
    body=path.read_bytes()
    digest=hashed(path)
    target=DEST+"\\"+name
    partial=target+".wslpe45-native-"+token_hex(10)
    # Exact Windows directory inventory is checked before any file creation.
    prefix=f"""
$ErrorActionPreference='Stop'
$root='{DEST}'
$entries=@(Get-ChildItem -LiteralPath $root -Force -ErrorAction Stop)
if(@($entries | Where-Object {{$_.Name -ceq '{name}'}}).Count -ne 0){{
  throw 'Native target already exists'
}}
if(@($entries | Where-Object {{$_.Name -like '*.wslpe45-native-*'}}).Count -ne 0){{
  throw 'Existing incomplete staging file'
}}
$stream=[IO.File]::Open('{partial}',[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
$stream.Dispose()
"""
    stage.ps_checked(session,prefix,step="CREATE_WSLPE45_NATIVE")
    from base64 import b64encode
    for offset in range(0,len(body),stage.WINRM_CHUNK_BYTES):
        segment=b64encode(body[offset:offset+stage.WINRM_CHUNK_BYTES]).decode("ascii")
        payload=f"""
$ErrorActionPreference='Stop'
$stream=[IO.File]::Open('{partial}',[IO.FileMode]::Open,[IO.FileAccess]::Write,[IO.FileShare]::None)
try{{
  $null=$stream.Seek(0,[IO.SeekOrigin]::End)
  $bytes=[Convert]::FromBase64String('{segment}')
  $stream.Write($bytes,0,$bytes.Length)
}} finally{{$stream.Dispose()}}
"""
        stage.ps_checked(session,payload,step="APPEND_WSLPE45_NATIVE")
    final=f"""
$ErrorActionPreference='Stop'
if((Get-FileHash -LiteralPath '{partial}' -Algorithm SHA256).Hash -cne '{digest}'){{throw 'Artifact digest mismatch'}}
if(Test-Path -LiteralPath '{target}'){{throw 'Unexpected existing source'}}
[IO.File]::Move('{partial}','{target}')
if((Get-FileHash -LiteralPath '{target}' -Algorithm SHA256).Hash -cne '{digest}'){{throw 'Guest artifact digest mismatch'}}
Write-Output 'WSLPE45_NATIVE_FILE_VERIFIED=PASS'
"""
    output=stage.ps_checked(session,final,step="FINALIZE_WSLPE45_NATIVE")
    if output.count("WSLPE45_NATIVE_FILE_VERIFIED=PASS")!=1:
        raise ValueError("Missing independent staged artifact marker")
    return digest

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id",type=int,required=True)
    parser.add_argument("--apply",action="store_true")
    args=parser.parse_args(argv)
    print("[SCOPE] WSLPE-WS01 copy-only #25/#36/#38; #40 unchanged; NORTH untouched",flush=True)
    try:
        stage=load_stage()
        head=stage.local_source_head()
        pre=stage.load_preflight()
        stage.verify_vm_snapshot(pre)
        with tempfile.TemporaryDirectory(prefix="wslpe45-native-") as tmp:
            files=obtain_artifacts(args.run_id,head,Path(tmp))
            auth=pre.load_auth()
            addr,cert=auth.checked_certificate(auth.tls_audit_module(),stage.PIN)
            user,password=auth.operator_credentials(addr)
            guest=pre.query(auth,addr,cert,user,password)
            if not guest["jea_module_present"] or not guest["library_acl_protected"] or guest["rpc_host_count"]!=0:
                raise ValueError("Guest baseline outside contract")
            print("[PASS] Exact source, native hashes, pinned HTTPS and pre-LPE40 snapshot",flush=True)
            with stage.managed_session(auth,addr,cert,user,password) as session:
                guard=stage.ps_checked(session,REMOTE_GUARD,step="GUARD_WSLPE45_NATIVE")
                if guard.count("WSLPE45_SOURCE_STAGING_SCOPE=PASS")!=1:
                    raise ValueError("Remote exact guest guard failed")
                if not args.apply:
                    print("[PLAN ONLY] No native files copied; use --apply",flush=True)
                    return 0
                for name,path in sorted(files.items()):
                    digest=staged(session,stage,name,path)
                    print("[PASS] "+name+" "+digest,flush=True)
        print("[PASS] All eight source/native files staged; no vulnerability activated",flush=True)
        return 0
    except Exception as exc:
        print("[BLOCKED] "+type(exc).__name__+"; preserve guest, partials and snapshot",flush=True)
        print("[NO AUTOMATIC RETRY] Inspect independent guest inventory before repeating",flush=True)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
