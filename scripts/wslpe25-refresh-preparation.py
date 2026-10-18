#!/usr/bin/env python3
"""WSLPE #25 exact owned preparation-source refresh only.

Source-pinned old/new hashes, snapshot-backed WSLPE, pinned HTTPS/NTLM and
a read-only marker-only fixture gate. Never installs/repairs any MSI.
--apply authorizes one atomic update of only Wslpe25RepairPreparation.psm1.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import importlib.util
from pathlib import Path
import re
import subprocess
import tempfile
from secrets import token_hex

ROOT=Path(__file__).resolve().parents[1]
BASE_COMMIT="920684e585676b567beb391b74fe373b322e01f3"
RELATIVE="ansible/files/wslpe45/Wslpe25RepairPreparation.psm1"
DEST=r"C:\ProgramData\KingdomsWSLPE45\lib\Wslpe25RepairPreparation.psm1"
CHUNK=512

def sha(data:bytes)->str:
    return hashlib.sha256(data).hexdigest().upper()

def load_stage():
    spec=importlib.util.spec_from_file_location(
        "wslpe25_readonly_pinned_winrm",ROOT/"scripts/wslpe40-stage.py")
    if not spec or not spec.loader:
        raise ValueError("Pinned WSLPE transport source missing")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# Read-only guard is source-canonical; only accepts the exact interrupted
# WSLPE25 state (one owned marker and no request/ledger/proof/product).
GUARD=r"""
$ErrorActionPreference='Stop'
$computer=Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
if($env:COMPUTERNAME -cne 'WSLPE-WS01' -or $computer.PartOfDomain){
  throw 'Wrong guest'
}
$learner=Get-LocalUser -Name 'lpe.trainee' -ErrorAction Stop
if(-not $learner.Enabled){throw 'Learner disabled'}
$administrators=Get-LocalGroup -SID 'S-1-5-32-544' -ErrorAction Stop
if(@(Get-LocalGroupMember -Group $administrators.Name |
   Where-Object {$_.SID.Value -eq $learner.SID.Value}).Count -ne 0){
  throw 'Learner elevated'
}
$root='C:\ProgramData\KingdomsWSLPE45'
$lib=Join-Path $root 'lib'
$fixture=Join-Path $root 'fixtures\msi_repair_custom_action'
foreach($dir in @($root,$lib,$fixture)){
  $obj=Get-Item -LiteralPath $dir -Force -ErrorAction Stop
  if(-not $obj.PSIsContainer -or
    ($obj.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
    -not (Get-Acl -LiteralPath $dir -ErrorAction Stop).AreAccessRulesProtected){
    throw 'Unprotected or linked fixture ancestor'
  }
}
$items=@(Get-ChildItem -LiteralPath $fixture -Force -ErrorAction Stop)
if($items.Count -ne 1 -or $items[0].Name -cne '.kingdoms-owned.json' -or
   $items[0].PSIsContainer -or
   ($items[0].Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){
   throw 'Not exact interrupted prepare state'
}
$marker=Get-Content -LiteralPath $items[0].FullName -Raw -ErrorAction Stop |
  ConvertFrom-Json -ErrorAction Stop
if($marker.schema -cne 'kingdoms.wslpe.fixture-owner.v1' -or
   [int]$marker.number -ne 25 -or
   $marker.machine -cne 'WSLPE-WS01' -or
   $marker.id -cne 'msi_repair_custom_action' -or
   $marker.learner_sid -cne $learner.SID.Value){
   throw 'Wrong owned fixture marker'
}
if(Test-Path -LiteralPath 'C:\Program Files\KingdomsWSLPE25'){
  throw 'MSI payload already present'
}
if(@(Get-CimInstance Win32_Process -Filter "Name='msiexec.exe'").Count -gt 0){
  throw 'MSI install already in progress'
}
$dirItems=@(Get-ChildItem -LiteralPath $lib -Force -ErrorAction Stop)
if(@($dirItems | Where-Object {$_.Name -like 'Wslpe25RepairPreparation.psm1.wslpe25-update-*'}).Count -ne 0){
  throw 'Prior incomplete module update'
}
Write-Output 'WSLPE25_PARTIAL_MARKER_ONLY=PASS'
"""

def checked(session,stage,source,step):
    return stage.ps_checked(session,source,step=step)

def verify(session,stage,old_hash:str):
    mark=checked(session,stage,GUARD,"WSLPE25_OWNED_PARTIAL_GUARD")
    if mark.count("WSLPE25_PARTIAL_MARKER_ONLY=PASS")!=1:
        raise ValueError("Missing read-only marker-only proof")
    script=f"""
$ErrorActionPreference='Stop'
$path='{DEST}'
$obj=Get-Item -LiteralPath $path -Force -ErrorAction Stop
if($obj.PSIsContainer -or ($obj.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){{
  throw 'Unsafe existing preparation module'
}}
if((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -cne '{old_hash}'){{
  throw 'Existing preparation module differs from original source'
}}
Write-Output 'WSLPE25_OLD_PREPARATION_HASH=PASS'
"""
    result=checked(session,stage,script,"WSLPE25_OLD_MODULE_HASH")
    if result.count("WSLPE25_OLD_PREPARATION_HASH=PASS")!=1:
        raise ValueError("Existing module hash was not proven")

def replace(session,stage,new:bytes,old_hash:str)->str:
    new_hash=sha(new)
    temp=DEST+".wslpe25-update-"+token_hex(12)
    create=f"""
$ErrorActionPreference='Stop'
if(Test-Path -LiteralPath '{temp}'){{throw 'Update temp exists'}}
$stream=[IO.File]::Open('{temp}',[IO.FileMode]::CreateNew,
  [IO.FileAccess]::Write,[IO.FileShare]::None)
$stream.Dispose()
"""
    checked(session,stage,create,"WSLPE25_CREATE_TEMP")
    for offset in range(0,len(new),CHUNK):
        payload=base64.b64encode(new[offset:offset+CHUNK]).decode("ascii")
        append=f"""
$ErrorActionPreference='Stop'
$stream=[IO.File]::Open('{temp}',[IO.FileMode]::Open,
  [IO.FileAccess]::Write,[IO.FileShare]::None)
try{{
  $null=$stream.Seek(0,[IO.SeekOrigin]::End)
  $bytes=[Convert]::FromBase64String('{payload}')
  $stream.Write($bytes,0,$bytes.Length)
}} finally {{$stream.Dispose()}}
"""
        checked(session,stage,append,"WSLPE25_APPEND_"+str(offset//CHUNK+1))
    commit=f"""
$ErrorActionPreference='Stop'
$old='{DEST}'
$temp='{temp}'
if((Get-FileHash -LiteralPath $temp -Algorithm SHA256).Hash -cne '{new_hash}'){{
  throw 'New module digest mismatch'
}}
if((Get-FileHash -LiteralPath $old -Algorithm SHA256).Hash -cne '{old_hash}'){{
  throw 'Original module changed during upload'
}}
if(-not ('Kingdoms.Wslpe25AtomicMove' -as [type])) {{
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace Kingdoms {{
  public static class Wslpe25AtomicMove {{
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode,
               SetLastError=true, EntryPoint="MoveFileExW")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool Execute(string source, string target, uint flags);
  }}
}}
'@ -ErrorAction Stop
}}
# Same-volume atomic replacement with write through. Never copy-overwrite.
if(-not [Kingdoms.Wslpe25AtomicMove]::Execute($temp,$old,9)){{
  throw 'Atomic owned module update rejected'
}}
if((Get-FileHash -LiteralPath $old -Algorithm SHA256).Hash -cne '{new_hash}'){{
  throw 'Updated module hash mismatch'
}}
Write-Output 'WSLPE25_PREPARATION_REFRESH=PASS'
"""
    marker=checked(session,stage,commit,"WSLPE25_ATOMIC_COMMIT")
    if marker.count("WSLPE25_PREPARATION_REFRESH=PASS")!=1:
        raise ValueError("Missing exact atomic update proof")
    return new_hash

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply",action="store_true")
    args=p.parse_args(argv)
    print("[SCOPE] Exact WSLPE25 preparation module only; no MSI operations or #40/NORTH/JEA writes")
    try:
        stage=load_stage()
        stage.local_source_head()
        pre=stage.load_preflight()
        stage.verify_vm_snapshot(pre)
        before=subprocess.run(["git","show",BASE_COMMIT+":"+RELATIVE],
            cwd=ROOT,check=False,capture_output=True)
        if before.returncode or not before.stdout:
            raise ValueError("Original pinned source missing")
        new=ROOT.joinpath(RELATIVE).read_bytes()
        if (before.stdout==new or b"ValidateSet('Inspect','Prepare','Resume')" not in new
            or b"New-Item -LiteralPath $request" in new or
            b"New-Item -Path $request -ItemType File" not in new):
            raise ValueError("Expected narrow PowerShell compatibility delta absent")
        auth=pre.load_auth()
        addr,cert=auth.checked_certificate(auth.tls_audit_module(),stage.PIN)
        user,password=auth.operator_credentials(addr)
        state=pre.query(auth,addr,cert,user,password)
        if (not state["learner_standard"] or state["jea_endpoint_count"]!=1
            or not state["library_acl_protected"] or state["library_linked"]
            or not state["rpc_operator_staged"] or not state["rpc_server_staged"]
            or not state["rpc_client_staged"] or state["rpc_host_count"]!=0):
            raise ValueError("Unexpected existing WSLPE/JEA/RPC state")
        with stage.managed_session(auth,addr,cert,user,password) as session:
            verify(session,stage,sha(before.stdout))
            print("[PASS] Original module digest and exact marker-only interrupted MSI fixture")
            if not args.apply:
                print("[PLAN ONLY] No guest mutation; run --apply after reviewing inventory")
                return 0
            digest=replace(session,stage,new,sha(before.stdout))
            print("[PASS] WSLPE25_PREPARATION_SOURCE_UPDATED="+digest)
        return 0
    except Exception as exc:
        detail=str(exc)
        if re.fullmatch(
            r"Guest rejected stage step: [A-Z0-9_]{3,72} \(status=[0-9]{1,3}\)",detail
        ):
            print("[BLOCKED] "+detail)
        else:
            print("[BLOCKED] "+type(exc).__name__+": exact update not confirmed")
        print("[NO AUTOMATIC RETRY] Keep owned guest state for review")
        return 2

if __name__=="__main__":
    raise SystemExit(main())
