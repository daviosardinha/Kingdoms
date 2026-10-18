#!/usr/bin/env python3
"""Diagnose WSLPE #40 first-chunk failure without transferring or altering file bytes.

Exact snapshot-backed workgroup WSLPE-WS01 only. Uses pinned WinRM HTTPS,
verifies exactly one zero-byte orphan, then tests whether the same privileged
token can reopen that exact orphan with write access. Closes handle immediately:
does not create, delete, append, launch, fix permissions, or execute RPC.
"""
from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json
import re

ROOT=Path(__file__).resolve().parents[1]
MARKER="WSLPE40_APPEND_DIAGNOSTIC_JSON="
FAILURE_MARKER="WSLPE40_APPEND_FAILURE_JSON="
REMOTELY_NONWRITING=r"""
$ErrorActionPreference='Stop'
$diagPhase='IDENTITY'
try {
$machine=Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop
if($env:COMPUTERNAME -cne 'WSLPE-WS01' -or $machine.PartOfDomain){
    throw 'Refusing non-WSLPE standalone guest'
}
$principal=[Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent())
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
    throw 'Expected elevated WSLPE owner'
}
$diagPhase='LIBRARY'
$lib='C:\ProgramData\KingdomsWSLPE45\lib'
$entry=Get-Item -LiteralPath $lib -Force -ErrorAction Stop
if(-not $entry.PSIsContainer -or
   (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) -or
   -not (Get-Acl -LiteralPath $lib -ErrorAction Stop).AreAccessRulesProtected){
    throw 'Protected library check rejected'
}
$diagPhase='FILES'
$all=@(Get-ChildItem -LiteralPath $lib -Force -ErrorAction Stop)
$names=@('Wslpe40RpcOperator.psm1','Kingdom40LocalRpcServer.exe',
         'Kingdom40LocalRpcClient.exe')
foreach($name in $names){
    $matches=@($all | Where-Object {$_.Name -ceq $name})
    if($matches.Count -ne 0){throw 'Final staged file exists'}
}
$diagPhase='ORPHAN'
$temp=@($all | Where-Object {$_.Name -like '*.wslpe40-stage-*'})
if($temp.Count -ne 1){throw 'Not exactly one orphaned transfer'}
$file=$temp[0]
if($file.Name -cnotmatch '^Wslpe40RpcOperator[.]psm1[.]wslpe40-stage-[0-9a-f]{24}$' -or
   $file.PSIsContainer -or $file.Length -ne 0 -or
   (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)){
    throw 'Unexpected partial transfer state'
}
$diagPhase='RPC'
$rpc=@(Get-CimInstance -ClassName Win32_Process -Filter "Name = 'Kingdom40LocalRpcServer.exe'" -ErrorAction Stop)
if($rpc.Count -ne 0){throw 'Unexpected running RPC host'}
if(Test-Path -LiteralPath 'C:\ProgramData\KingdomsWSLPE45\fixtures\custom_rpc_authorization'){
    throw 'Unexpected RPC fixture'
}
$diagPhase='RECORD'
$record=[ordered]@{
    machine='WSLPE-WS01'
    orphan_count=1
    before_bytes=[int64]$file.Length
    after_bytes=-1
    can_reopen_write=$false
    open_failure='NONE'
    open_hresult=0
    base64_decode_ok=$false
}
$diagPhase='FILE_OPEN'
try {
    # Diagnostic uses a write-capable HANDLE but never calls Write/SetLength.
    # It neither creates nor changes file content, then immediately closes.
    $handle=[IO.File]::Open($file.FullName,[IO.FileMode]::Open,
        [IO.FileAccess]::Write,[IO.FileShare]::None)
    try {
        $record.can_reopen_write=$true
    } finally {
        $handle.Dispose()
    }
} catch {
    $ex=$_.Exception
    $allowed=@('UnauthorizedAccessException','IOException',
               'SecurityException','ArgumentException','NotSupportedException')
    $kind=$ex.GetType().Name
    $record.open_failure=if($kind -in $allowed){$kind}else{'OTHER'}
    $record.open_hresult=[int]$ex.HResult
}
$diagPhase='BASE64'
$known=[Convert]::FromBase64String('QUJD')
$record.base64_decode_ok=($known.Length -eq 3 -and
    $known[0] -eq 65 -and $known[1] -eq 66 -and $known[2] -eq 67)
$diagPhase='POST_CHECK'
$after=Get-Item -LiteralPath $file.FullName -Force -ErrorAction Stop
if($after.PSIsContainer -or
   (($after.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)){
    throw 'Unexpected change in orphaned transfer'
}
$record.after_bytes=[int64]$after.Length
$diagPhase='EMIT'
Write-Output ('WSLPE40_APPEND_DIAGNOSTIC_JSON='+
    (ConvertTo-Json -InputObject $record -Compress))
} catch {
    # Use an allowlisted *phase*, never remote exception strings. The type
    # and numeric HRESULT allow exact triage without secrets or path leakage.
    $kind=$_.Exception.GetType().Name
    if($kind -cnotmatch '^[A-Za-z][A-Za-z0-9]{0,62}$'){$kind='OTHER'}
    $failure=@{phase=$diagPhase; exception_type=$kind;
               hresult=[int]$_.Exception.HResult}
    Write-Output ('WSLPE40_APPEND_FAILURE_JSON='+
        (ConvertTo-Json -InputObject $failure -Compress))
}
"""

def module_from(path:Path, name:str):
    spec=spec_from_file_location(name,path)
    if spec is None or spec.loader is None:
        raise ValueError("Required pinned guest module unavailable")
    obj=module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

def parse(raw:bytes)->dict:
    values=[line[len(MARKER):] for line in raw.decode("utf-8","strict").splitlines()
            if line.startswith(MARKER)]
    if len(values)!=1:
        raise ValueError("Expected exactly one scoped append diagnostic record")
    data=json.loads(values[0])
    if not isinstance(data,dict) or set(data)!={
        "machine","orphan_count","before_bytes","after_bytes","can_reopen_write",
        "open_failure","open_hresult","base64_decode_ok"}:
        raise ValueError("Unexpected remote diagnostic schema")
    if data["machine"]!="WSLPE-WS01" or type(data["orphan_count"]) is not int or data["orphan_count"]!=1:
        raise ValueError("Unexpected guest or orphan count")
    if any(type(data[field]) is not int for field in
           ("before_bytes","after_bytes","open_hresult")):
        raise ValueError("Bad length or HRESULT type")
    if type(data["can_reopen_write"]) is not bool or type(data["base64_decode_ok"]) is not bool:
        raise ValueError("Unexpected diagnostic status type")
    if data["open_failure"] not in {
        "NONE","UnauthorizedAccessException","IOException","SecurityException",
        "ArgumentException","NotSupportedException","OTHER"}:
        raise ValueError("Unknown remote exception classifier")
    if data["before_bytes"]!=0 or data["after_bytes"]!=0:
        raise ValueError("Orphan content changed: preserve snapshot and stop")
    if data["can_reopen_write"] and data["open_failure"]!="NONE":
        raise ValueError("Contradictory remote diagnostic")
    return data

def parse_failure(raw:bytes)->dict:
    lines=raw.decode('utf-8','strict').splitlines()
    failures=[line[len(FAILURE_MARKER):] for line in lines if line.startswith(FAILURE_MARKER)]
    if len(failures)!=1:
        raise ValueError('Missing or duplicate classified remote failure')
    data=json.loads(failures[0])
    stages={'IDENTITY','LIBRARY','FILES','ORPHAN','RPC','RECORD',
            'FILE_OPEN','BASE64','POST_CHECK','EMIT'}
    if (not isinstance(data,dict) or set(data)!={'phase','exception_type','hresult'}
            or data.get('phase') not in stages
            or not isinstance(data.get('exception_type'),str)
            or not re.fullmatch(r'[A-Za-z][A-Za-z0-9]{0,62}',data['exception_type'])
            or type(data.get('hresult')) is not int):
        raise ValueError('Unexpected classified remote failure')
    return data


def main():
    print("KINGDOMS WSLPE | #40 FIRST-CHUNK DIAGNOSTIC (NO FILE CONTENT WRITES)")
    try:
        stage=module_from(ROOT/"scripts/wslpe40-stage.py","wslpe40_diag_stage")
        audit=module_from(ROOT/"scripts/wslpe40-stage-audit.py","wslpe40_diag_audit")
        recovery=module_from(ROOT/"scripts/wslpe40-recover-empty.py","wslpe40_diag_recovery")
        stage.local_source_head()
        preflight=stage.load_preflight()
        stage.verify_vm_snapshot(preflight)
        auth=preflight.load_auth()
        address,cert=auth.checked_certificate(auth.tls_audit_module(),stage.PIN)
        user,password=auth.operator_credentials(address)
        guest=preflight.query(auth,address,cert,user,password)
        stage.ensure_safe_guest(guest)
        with stage.managed_session(auth,address,cert,user,password) as session:
            before=session.run_ps(audit.READ_ONLY)
            if before.status_code!=0: raise ValueError("Remote baseline audit rejected")
            recovery.validate_audit(audit.parse_record(before.std_out))
            response=session.run_ps(REMOTELY_NONWRITING)
            if response.status_code!=0:
                print("[BLOCKED] Guest rejected diagnostic PowerShell; no remote exception text displayed")
                return 2
            failure=None
            if FAILURE_MARKER.encode() in response.std_out:
                failure=parse_failure(response.std_out)
            else:
                record=parse(response.std_out)
            # Always re-verify the unmodified guest inventory, even if the
            # diagnostic returned an error classifier, before reporting it.
            after=session.run_ps(audit.READ_ONLY)
            if after.status_code!=0: raise ValueError("Postdiagnostic guest audit rejected")
            recovery.validate_audit(audit.parse_record(after.std_out))
            if failure is not None:
                print('[BLOCKED] WSLPE40 diagnostic phase='+failure['phase'])
                print('[STATE] exception_type='+failure['exception_type'])
                print('[STATE] exception_hresult='+str(failure['hresult']))
                print('[PASS] Postdiagnostic zero-byte orphan still unchanged')
                return 2
    except Exception as exc:
        print("[BLOCKED] "+type(exc).__name__+" during diagnostic preflight")
        return 2
    print("[PASS] Exact guest, snapshot, elevated operator and one zero-byte partial confirmed")
    print("[STATE] file_open_for_write="+str(record["can_reopen_write"]))
    print("[STATE] file_open_failure="+record["open_failure"])
    print("[STATE] file_open_hresult="+str(record["open_hresult"]))
    print("[STATE] base64_decode_ok="+str(record["base64_decode_ok"]))
    print("[PASS] File content remains zero bytes; native RPC host untouched")
    if record["can_reopen_write"] and record["base64_decode_ok"]:
        print("[NEXT] File access and base64 decode both work; inspect append script semantics")
    else:
        print("[NEXT] Fix exact classified permission/file-open condition before recovery or retry")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
