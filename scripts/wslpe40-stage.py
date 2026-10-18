#!/usr/bin/env python3
"""WSLPE #40: copy-only native RPC artifact staging to the exact snapshot-backed guest.

Explicit --stage and console confirmation required. No RPC listener start,
no fixture creation, no account/JEA modifications, no NORTH access.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import ssl
from secrets import token_hex

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "scripts/wslpe40-runtime-preflight.py"
PIN = "C773EC26D02940F559FE715B83628FEDAE2AA92D"
SNAPSHOT = "KINGDOMS-WSLPE-PRE-LPE40-20261018"
REPO = "daviosardinha/Kingdoms"
BRANCH = "feature/windows-lpe-45-batch"
GUEST_DIR = r"C:\ProgramData\KingdomsWSLPE45\lib"
NAME_MAP = {
    "Kingdom40LocalRpcServer.exe": "server_sha256",
    "Kingdom40LocalRpcClient.exe": "client_sha256",
}
OPER = "Wslpe40RpcOperator.psm1"
EXPECTED = {"schema":"kingdoms.wslpe40.local-rpc-source.v1",
            "state":"unqualified-not-deployable", "transport":"ncalrpc",
            "server_role":"protected-privileged-host",
            "client_role":"separate-local-learner",
            "native_binaries_executed":"false", "learner_proof":"pending"}


def command(*args, timeout=45):
    result = subprocess.run(args, cwd=ROOT, capture_output=True,
                            text=True, timeout=timeout, check=False)
    if result.returncode:
        raise ValueError("Required local tool failed: " + args[0])
    return result.stdout.strip()


def load_preflight():
    spec=importlib.util.spec_from_file_location("wslpe40_staging_preflight", PREFLIGHT)
    if spec is None or spec.loader is None:
        raise ValueError("WSLPE-only runtime baseline source unavailable")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def local_source_head():
    if command("git","branch","--show-current") != BRANCH:
        raise ValueError("Unexpected Git branch")
    if command("git","status","--porcelain"):
        raise ValueError("Source checkout must be clean")
    return command("git","rev-parse","HEAD")


def verify_vm_snapshot(preflight):
    stage2=preflight.load_auth().tls_audit_module()
    # Resolve exact registered WSLPE VM through its existing native workspace.
    spec=importlib.util.spec_from_file_location(
        "wslpe40_registered_vm",ROOT/"scripts/wslpe-stage2-inspect.py")
    if not spec or not spec.loader:
        raise ValueError("Registered WSLPE workspace guard unavailable")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    instance,meta=mod.find_instance(mod.WORKSPACE)
    if meta.get("lab")!="WSLPE" or meta.get("provider")!="vmware":
        raise ValueError("Not isolated WSLPE VM")
    vmx=mod.locate_registered_vm(instance)
    if not vmx.is_file() or vmx.is_symlink() or "GOAD" in str(vmx).upper():
        raise ValueError("Unsafe VM registration")
    snaps=command("vmrun","-T","ws","listSnapshots",str(vmx),timeout=90)
    if snaps.splitlines().count(SNAPSHOT)!=1:
        raise ValueError("Missing or ambiguous WSLPE pre-LPE40 snapshot")


def evidence_from_runner(run: int, head: str, folder: Path) -> tuple[dict,dict[str,Path]]:
    run_data=json.loads(command("gh","api",
        f"repos/{REPO}/actions/runs/{run}"))
    if (run_data.get("head_sha")!=head or run_data.get("conclusion")!="success"
            or run_data.get("head_branch")!=BRANCH):
        raise ValueError("Run is not successful for the exact checked-out commit")
    name="wslpe40-native-source-review-"+head
    command("gh","run","download",str(run),"--repo",REPO,
            "--name",name,"--dir",str(folder),timeout=120)
    expected=set(NAME_MAP)|{"Kingdom40LocalRpc.provenance.txt"}
    entries=list(folder.iterdir())
    if {p.name for p in entries}!=expected or any(
            not p.is_file() or p.is_symlink() for p in entries):
        raise ValueError("Untrusted artifact inventory")
    raw=(folder/"Kingdom40LocalRpc.provenance.txt").read_text(
        encoding="utf-8-sig").splitlines()
    pairs=[line.split("=",1) for line in raw if line]
    if any(len(p)!=2 for p in pairs) or len(set(k for k,v in pairs))!=len(pairs):
        raise ValueError("Ambiguous provenance")
    data=dict(pairs)
    if data.get("commit")!=head or any(data.get(k)!=v for k,v in EXPECTED.items()):
        raise ValueError("Source manifest does not match intended native build")
    native_log=command("gh","run","view",str(run),"--repo",REPO,"--log",timeout=120)
    paths={}
    for filename,key in NAME_MAP.items():
        path=folder/filename
        digest=hashlib.sha256(path.read_bytes()).hexdigest().upper()
        marker="WSLPE40_"+("SERVER" if key.startswith("server") else "CLIENT")+"_SHA256="
        independent=re.findall(re.escape(marker)+r"([A-Fa-f0-9]{64})",native_log)
        if digest!=data.get(key,"").upper() or not independent or digest!=independent[-1].upper():
            raise ValueError("Binary mismatch with independent Windows CI logs")
        paths[filename]=path
    operator=ROOT/"ansible/files/wslpe45"/OPER
    if operator.is_symlink() or not operator.is_file():
        raise ValueError("Operator source missing or linked")
    paths[OPER]=operator
    return data,paths


def ensure_safe_guest(state):
    required={
        "jea_endpoint_count":1,"jea_module_present":True,
        "library_present":True,"library_acl_protected":True,
        "library_linked":False,"rpc_fixture_present":False,
        "rpc_proof_present":False,"rpc_operator_staged":False,
        "rpc_server_staged":False,"rpc_client_staged":False,
        "rpc_host_count":0,
    }
    for k,v in required.items():
        if state[k]!=v:
            raise ValueError("Guest state differs from exact clean staging contract: "+k)
    if state["rpc_fixture_linked"] or state["rpc_proof_linked"]:
        raise ValueError("Linked RPC fixture or proof; refusing stage")


@contextmanager
def managed_session(auth,address,cert,username,password):
    import winrm
    with tempfile.TemporaryDirectory(prefix="wslpe40-tls-") as tmp:
        anchor=Path(tmp)/"leaf.pem"
        anchor.write_text(ssl.DER_cert_to_PEM_cert(cert),encoding="ascii")
        anchor.chmod(0o600)
        session=winrm.Session(
            "https://WSLPE-WS01:5986/wsman",auth=(username,password),
            transport="ntlm",server_cert_validation="validate",
            ca_trust_path=str(anchor),proxy=None,
            operation_timeout_sec=20,read_timeout_sec=40)
        transport=session.protocol.transport
        try:
            http=transport.build_session()
            http.trust_env=False
            http.proxies={}
            if http.verify!=str(anchor):
                raise ValueError("WinRM certificate anchor differs from expected leaf")
            with auth.scoped_wslpe_resolution(address):
                yield session
        finally:
            transport.close_session()


def ps_checked(session,source):
    result=session.run_ps(source)
    if result.status_code != 0:
        raise ValueError("Guest refused copy-only stage; no automatic retry")
    return result.std_out.decode("utf-8",errors="strict").strip()


def stage(session,files:dict[str,Path]):
    # Tight allowlist; everything lands in existing protected lib, which
    # grants Users RX but never write. No arbitrary destination parameters.
    names=(OPER,"Kingdom40LocalRpcServer.exe","Kingdom40LocalRpcClient.exe")
    ps_checked(session,r"""
$ErrorActionPreference='Stop'
$machine=Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
if($env:COMPUTERNAME -cne 'WSLPE-WS01' -or $machine.PartOfDomain){
    throw 'Not isolated WSLPE'
}
$principal=[Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent())
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
    throw 'Staging requires administrative WinRM identity'
}
$lib='C:\ProgramData\KingdomsWSLPE45\lib'
$item=Get-Item -LiteralPath $lib -Force -ErrorAction Stop
if(-not $item.PSIsContainer -or
   (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) -or
   -not (Get-Acl -LiteralPath $lib).AreAccessRulesProtected){
    throw 'RPC staging root is not protected'
}
foreach($file in @('Wslpe40RpcOperator.psm1',
                   'Kingdom40LocalRpcServer.exe',
                   'Kingdom40LocalRpcClient.exe')){
    if(Test-Path -LiteralPath (Join-Path $lib $file)){
        throw 'Refusing existing native RPC destination'
    }
}
if(@(Get-CimInstance Win32_Process -Filter "Name='Kingdom40LocalRpcServer.exe'").Count -ne 0){
    throw 'RPC host already running'
}
""")
    for name in names:
        path=files[name]
        body=path.read_bytes()
        digest=hashlib.sha256(body).hexdigest().upper()
        suffix=token_hex(12)
        target=GUEST_DIR+"\\"+name
        partial=target+".wslpe40-stage-"+suffix
        # Only bytes to exact fixed destination, never executing staged files.
        ps_checked(session,f"""
$ErrorActionPreference='Stop'
$partial='{partial}'
$target='{target}'
if(Test-Path -LiteralPath $partial){{throw 'Conflicting partial file'}}
if(Test-Path -LiteralPath $target){{throw 'Conflicting destination'}}
$stream=[IO.File]::Open($partial,[IO.FileMode]::CreateNew,
    [IO.FileAccess]::Write,[IO.FileShare]::None)
$stream.Dispose()
""")
        # WinRM SOAP messages are size-bounded. Transfer small fixed chunks
        # and reject partial writes; partial files remain for manual review.
        import base64
        for offset in range(0,len(body),8192):
            segment=base64.b64encode(body[offset:offset+8192]).decode("ascii")
            ps_checked(session,f"""
$ErrorActionPreference='Stop'
$bytes=[Convert]::FromBase64String('{segment}')
$stream=[IO.File]::Open('{partial}',[IO.FileMode]::Open,
    [IO.FileAccess]::Write,[IO.FileShare]::None)
try{{
    $null=$stream.Seek(0,[IO.SeekOrigin]::End)
    $stream.Write($bytes,0,$bytes.Length)
}} finally {{$stream.Dispose()}}
""")
        ps_checked(session,f"""
$ErrorActionPreference='Stop'
$partial='{partial}'
$target='{target}'
if((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash -cne '{digest}'){{
    throw 'Staged RPC artifact SHA-256 differs'
}}
if(Test-Path -LiteralPath $target){{throw 'Refusing existing target'}}
[IO.File]::Move($partial,$target)
Write-Output 'WSLPE40_STAGED_{name}=PASS'
""")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id",required=True,type=int)
    parser.add_argument("--stage",action="store_true")
    args=parser.parse_args()
    print("KINGDOMS WSLPE | #40 COPY-ONLY NATIVE STAGING")
    print("[SCOPE] Exact WSLPE-WS01; no RPC process, fixture, JEA or NORTH changes")
    try:
        head=local_source_head()
        preflight=load_preflight()
        verify_vm_snapshot(preflight)
        with tempfile.TemporaryDirectory(prefix="wslpe40-artifact-") as folder:
            _,files=evidence_from_runner(args.run_id,head,Path(folder))
            print("[PASS] Native build and operator sources match pinned run")
            auth=preflight.load_auth()
            address,cert=auth.checked_certificate(auth.tls_audit_module(),PIN)
            user,password=auth.operator_credentials(address)
            guest=preflight.query(auth,address,cert,user,password)
            ensure_safe_guest(guest)
            print("[PASS] Exact snapshot-backed guest and no existing RPC state")
            if not args.stage:
                print("[PLAN ONLY] No Windows files copied")
                return 0
            if not sys.stdin.isatty() or input(
                "Type STAGE WSLPE40 SOURCE ONLY to approve binary copy: "
            ).strip()!="STAGE WSLPE40 SOURCE ONLY":
                raise ValueError("Operator staging approval absent")
            with managed_session(auth,address,cert,user,password) as session:
                stage(session,files)
        print("[PASS] WSLPE40_SOURCE_STAGED=TRUE")
        print("[NOT EXECUTED] No RPC server or proof operation started")
        print("[NEXT] Run independent read-only runtime baseline again")
        return 0
    except Exception as exc:
        print(f"[BLOCKED] {type(exc).__name__}: review exact owned guest state")
        print("[NO AUTOMATIC RETRY] Preserve guest/snapshot for inspection")
        return 2

if __name__=="__main__":
    raise SystemExit(main())
