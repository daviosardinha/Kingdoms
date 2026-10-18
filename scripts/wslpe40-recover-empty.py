#!/usr/bin/env python3
"""Explicit recovery of one verified zero-byte WSLPE40 staging temporary file.

This operation does not stage, execute, or uninstall the RPC host. It refuses
all partial data, unexpected files/host states, and any non-WSLPE guest.
The only possible deletion is the exact matching orphaned temporary file
for Wslpe40RpcOperator.psm1 in the existing protected WSLPE library.
"""
from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MODULES={
    "stage":ROOT/"scripts/wslpe40-stage.py",
    "audit":ROOT/"scripts/wslpe40-stage-audit.py",
}

RECOVER_ONLY=r"""
$ErrorActionPreference='Stop'
$machine=Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
if($env:COMPUTERNAME -cne 'WSLPE-WS01' -or $machine.PartOfDomain){throw 'Identity'}
$principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Token'}
$root='C:\ProgramData\KingdomsWSLPE45'
$lib=Join-Path $root 'lib'
foreach($path in @($root,$lib)){
  $item=Get-Item -LiteralPath $path -Force -ErrorAction Stop
  if(-not $item.PSIsContainer -or
     ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
     -not (Get-Acl -LiteralPath $path -ErrorAction Stop).AreAccessRulesProtected){throw 'ACL'}
}
$entries=@(Get-ChildItem -LiteralPath $lib -Force -ErrorAction Stop)
foreach($name in @('Wslpe40RpcOperator.psm1','Kingdom40LocalRpcServer.exe',
                   'Kingdom40LocalRpcClient.exe')){
  $found=@($entries | Where-Object {$_.Name -ceq $name})
  if($found.Count -ne 0){throw 'Target'}
}
$allPartial=@($entries | Where-Object {$_.Name -like '*.wslpe40-stage-*'})
if($allPartial.Count -ne 1){throw 'PartialCount'}
$entry=$allPartial[0]
if($entry.Name -cnotmatch '^Wslpe40RpcOperator[.]psm1[.]wslpe40-stage-[0-9a-f]{24}$' -or
   $entry.PSIsContainer -or $entry.Length -ne 0 -or
   ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'Partial'}
$running=@(Get-CimInstance Win32_Process -Filter "Name = 'Kingdom40LocalRpcServer.exe'" -ErrorAction Stop)
if($running.Count -ne 0){throw 'RPC'}
if(Test-Path -LiteralPath 'C:\ProgramData\KingdomsWSLPE45\fixtures\custom_rpc_authorization'){throw 'Fixture'}
$target=Join-Path $lib $entry.Name
$again=Get-Item -LiteralPath $target -Force -ErrorAction Stop
if($again.PSIsContainer -or $again.Length -ne 0 -or
   ($again.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'Changed'}
[IO.File]::Delete($target)
if(Test-Path -LiteralPath $target){throw 'NotDeleted'}
Write-Output 'WSLPE40_EMPTY_PARTIAL_REMOVED=PASS'
"""

def load(name):
    path=MODULES[name]
    spec=spec_from_file_location("wslpe40_orphan_"+name,path)
    if not spec or not spec.loader:
        raise ValueError("Required checked-in WSLPE module is missing")
    module=module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def validate_audit(evidence):
    if not evidence["token_elevated_admin"] or not evidence["library_acl_protected"]:
        raise ValueError("Remote token or protected WSLPE library mismatch")
    if evidence["rpc_host_count"]!=0:
        raise ValueError("Native RPC host already running")
    if any(entry["present"] for entry in evidence["exact_files"]):
        raise ValueError("Exact RPC staged file already present")
    parts=evidence["partial_files"]
    if (len(parts)!=1 or parts[0]["target"]!="Wslpe40RpcOperator.psm1"
            or parts[0]["size"]!=0 or parts[0]["linked"]
            or parts[0]["directory"]):
        raise ValueError("Not exactly one owned zero-byte operator temporary file")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recover",action="store_true",
                        help="explicitly delete one validated zero-byte temporary file")
    args=parser.parse_args()
    print("KINGDOMS WSLPE | #40 ZERO-BYTE TEMPORARY RECOVERY")
    print("[SCOPE] Only the known incomplete operator temporary file, never RPC execution")
    try:
        stage=load("stage")
        audit=load("audit")
        stage.local_source_head()
        preflight=stage.load_preflight()
        stage.verify_vm_snapshot(preflight)
        auth=preflight.load_auth()
        address,cert=auth.checked_certificate(auth.tls_audit_module(),stage.PIN)
        user,password=auth.operator_credentials(address)
        state=preflight.query(auth,address,cert,user,password)
        stage.ensure_safe_guest(state)
        with stage.managed_session(auth,address,cert,user,password) as session:
            response=session.run_ps(audit.READ_ONLY)
            if response.status_code!=0:
                raise ValueError("Remote read-only recovery audit rejected")
            evidence=audit.parse_record(response.std_out)
            validate_audit(evidence)
            print("[PASS] Exactly one zero-byte, regular #40 operator temporary file")
            print("[PASS] No native RPC server, final files or fixture; elevated WSLPE owner")
            if not args.recover:
                print("[PLAN ONLY] Nothing removed; use --recover only after explicit review")
                return 0
            # --recover is the explicit operator authorization.
            # Every exact-guest, empty-file, ownership and snapshot gate
            # above remains mandatory; no interactive phrase is required.
            stage.ps_checked(session,RECOVER_ONLY,step="RECOVER_ZERO_BYTE_OPERATOR")
            print("[PASS] WSLPE40_EMPTY_PARTIAL_REMOVED=TRUE")
            response=session.run_ps(audit.READ_ONLY)
            if response.status_code!=0:
                raise ValueError("Post-recovery audit rejected by Windows")
            final=audit.parse_record(response.std_out)
            if final["partial_files"] or any(x["present"] for x in final["exact_files"]):
                raise ValueError("Post-recovery staging state not clean")
            print("[PASS] WSLPE40_POST_RECOVERY_STAGE_INVENTORY=CLEAN")
            return 0
    except Exception as exc:
        print("[BLOCKED] "+type(exc).__name__+": preserve guest state for review")
        print("[NO AUTOMATIC RETRY] No native binaries started or executed")
        return 2

if __name__=="__main__":
    raise SystemExit(main())
