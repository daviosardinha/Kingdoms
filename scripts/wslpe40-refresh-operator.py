#!/usr/bin/env python3
"""Refresh ONLY the staged WSLPE40 PowerShell operator's console guard.

Source-pinned, snapshot-protected, encrypted WinRM and content-hash verified.
No native RPC binary transfer, service execution, fixture mutation or JEA changes.
--apply authorizes a single verified atomic module replacement without a prompt.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
from pathlib import Path
import subprocess
import tempfile

from importlib.util import module_from_spec, spec_from_file_location

ROOT=Path(__file__).resolve().parents[1]
OPERATOR="Wslpe40RpcOperator.psm1"
SOURCE=ROOT/"ansible/files/wslpe45"/OPERATOR
PRIOR_COMMIT="a297b9f90aea6ff056274fb812a26cf18182f55f"
PRIOR_NATIVE_RUN=39134058008
REMOTE=r"C:\ProgramData\KingdomsWSLPE45\lib"
CHUNK_BYTES=512

def imported(filename: str,name: str):
    spec=spec_from_file_location(name,ROOT/"scripts"/filename)
    if not spec or not spec.loader: raise ValueError("Required WSLPE module unavailable")
    mod=module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def digest(buf:bytes)->str:
    return hashlib.sha256(buf).hexdigest().upper()

def old_operator_source()->bytes:
    result=subprocess.run(["git","show",
        PRIOR_COMMIT+":ansible/files/wslpe45/"+OPERATOR],
        cwd=ROOT,capture_output=True,check=False)
    if result.returncode or not result.stdout:
        raise ValueError("Pinned original operator source unavailable")
    return result.stdout

def validate_guest(preflight,audit,poststage,hashes):
    if not preflight["rpc_operator_staged"] or preflight["rpc_host_count"]!=0:
        raise ValueError("RPC operator or host state mismatch")
    poststage.validate_runtime(preflight,audit,hashes)

READ_ONLY_REFRESH_GUARD=r"""
$ErrorActionPreference='Stop'
$hostinfo=Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
if($env:COMPUTERNAME -cne 'WSLPE-WS01' -or $hostinfo.PartOfDomain){throw 'Wrong guest'}
$identity=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if(-not $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Not admin'}
$lib='C:\ProgramData\KingdomsWSLPE45\lib'
$base=Get-Item -LiteralPath $lib -Force -ErrorAction Stop
if(-not $base.PSIsContainer -or
   ($base.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
   -not (Get-Acl -LiteralPath $lib).AreAccessRulesProtected){throw 'Library ACL'}
if(Test-Path -LiteralPath 'C:\ProgramData\KingdomsWSLPE45\fixtures\custom_rpc_authorization'){throw 'Fixture'}
if(@(Get-CimInstance Win32_Process -Filter "Name='Kingdom40LocalRpcServer.exe'").Count -ne 0){throw 'Host running'}
"""


def diagnosed_check(session,stage,command,step):
    """Only expose a checked-in operation name and restricted error category."""
    try:
        return stage.ps_checked(session,command,step=step)
    except ValueError as exc:
        reason=str(exc)
        import re
        if re.fullmatch(
            r"(?:WINRM_ENCODED_COMMAND_TOO_LONG|"
            r"WINDOWS_COMMAND_LINE_TOO_LONG|WINDOWS_ACCESS_DENIED) at [A-Z0-9_]{3,72}|"
            r"Guest rejected stage step: [A-Z0-9_]{3,72} \(status=[0-9]{1,3}\)|"
            r"WinRM transport rejected stage step: [A-Z0-9_]{3,72} \([A-Za-z][A-Za-z0-9_]{0,63}\)",
            reason
        ):
            print("[DIAG] "+reason)
        else:
            print("[DIAG] "+step+" failed ("+type(exc).__name__+")")
        raise


def diagnose_prewrite(session,stage,old_hash):
    """Prove the actual first guest guard and original file digest; no writes."""
    diagnosed_check(session,stage,READ_ONLY_REFRESH_GUARD,"GUARD_OPERATOR_REFRESH")
    verified=f"""
$ErrorActionPreference='Stop'
$target='C:\\ProgramData\\KingdomsWSLPE45\\lib\\Wslpe40RpcOperator.psm1'
$entry=Get-Item -LiteralPath $target -Force -ErrorAction Stop
if($entry.PSIsContainer -or ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){{
    throw 'Unsafe target'
}}
if((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -cne '{old_hash}'){{
    throw 'Old hash mismatch'
}}
Write-Output 'WSLPE40_OPERATOR_REFRESH_PREWRITE=PASS'
"""
    diagnosed_check(session,stage,verified,"VERIFY_EXISTING_OPERATOR")
    print("[PASS] WSLPE40_OPERATOR_REFRESH_PREWRITE=TRUE")
    print("[PLAN ONLY] No Windows files created, opened for write or replaced")


def checked_transfer(session,stage,old_hash,new_bytes:bytes):
    """Target exists and matches old hash; create a new protected staging leaf.

    Final File.Replace is same-volume/atomic. On any error, no guest retry.
    An orphan temp is preserved for independent review.
    """
    new_hash=digest(new_bytes)
    target=REMOTE+"\\"+OPERATOR
    # Short exact known staging name, with random suffix; no arbitrary paths.
    from secrets import token_hex
    temp=target+".wslpe40-refresh-"+token_hex(10)
    old_guard=f"""
$target='{target}'
$old=Get-Item -LiteralPath $target -Force -ErrorAction Stop
if($old.PSIsContainer -or ($old.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){{
    throw 'Unexpected operator type'
}}
if((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -cne '{old_hash}'){{
    throw 'Existing module differs from pinned source'
}}
$temp='{temp}'
if(Test-Path -LiteralPath $temp){{throw 'Temporary file already exists'}}
$stream=[IO.File]::Open($temp,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
$stream.Dispose()
"""
    diagnosed_check(session,stage,READ_ONLY_REFRESH_GUARD,"GUARD_OPERATOR_REFRESH")
    diagnosed_check(session,stage,old_guard,"CREATE_OPERATOR_REFRESH")
    for offset in range(0,len(new_bytes),CHUNK_BYTES):
        encoded=base64.b64encode(new_bytes[offset:offset+CHUNK_BYTES]).decode("ascii")
        segment=f"""
$ErrorActionPreference='Stop'
$stream=[IO.File]::Open('{temp}',[IO.FileMode]::Open,[IO.FileAccess]::Write,[IO.FileShare]::None)
try{{
  $null=$stream.Seek(0,[IO.SeekOrigin]::End)
  $data=[Convert]::FromBase64String('{encoded}')
  $stream.Write($data,0,$data.Length)
}} finally {{$stream.Dispose()}}
"""
        diagnosed_check(session,stage,segment,"UPLOAD_OPERATOR_CHUNK_"+str(offset//CHUNK_BYTES+1))
    # No backup file because the named recovery snapshot is mandatory.
    # File.Replace preserves an atomic old-or-new file, never partial target.
    finish=f"""
$ErrorActionPreference='Stop'
$old='{target}'
$temp='{temp}'
if((Get-FileHash -LiteralPath $temp -Algorithm SHA256).Hash -cne '{new_hash}'){{
    throw 'New module digest does not match'
}}
if((Get-FileHash -LiteralPath $old -Algorithm SHA256).Hash -cne '{old_hash}'){{
    throw 'Old module changed while staging'
}}
$entry=Get-Item -LiteralPath $temp -Force -ErrorAction Stop
if($entry.PSIsContainer -or ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){{
    throw 'Unsafe temporary file'
}}
[IO.File]::Replace($temp,$old,$null)
if((Get-FileHash -LiteralPath $old -Algorithm SHA256).Hash -cne '{new_hash}'){{
    throw 'Operator replacement digest mismatch'
}}
Write-Output 'WSLPE40_OPERATOR_CONSOLE_PATCH=PASS'
"""
    diagnosed_check(session,stage,finish,"COMMIT_OPERATOR_REFRESH")
    return new_hash

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply",action="store_true",
        help="Replace the sole verified operator module, with no interactive prompt")
    parser.add_argument("--diagnose",action="store_true",
        help="Run actual prewrite guard and old-source hash without guest mutations")
    args=parser.parse_args()
    print("KINGDOMS WSLPE | #40 CONSOLE GUARD REFRESH (OPERATOR ONLY)")
    print("[SCOPE] No native server/client, RPC host, fixture, JEA or NORTH mutations")
    try:
        stage=imported("wslpe40-stage.py","wslpe40_refresh_stage")
        audit=imported("wslpe40-stage-audit.py","wslpe40_refresh_audit")
        post=imported("wslpe40-poststage-verify.py","wslpe40_refresh_poststage")
        stage.local_source_head()
        pre=stage.load_preflight()
        stage.verify_vm_snapshot(pre)
        source_new=SOURCE.read_bytes()
        source_old=old_operator_source()
        if (SOURCE.is_symlink() or source_new==source_old or
                b"WTSGetActiveConsoleSessionId" not in source_new or
                b"$env:SESSIONNAME" in source_new or
                b"$env:SESSIONNAME" not in source_old):
            raise ValueError("Unexpected native console operator source delta")
        # Revalidate original source against exact previously green native run.
        source_commit=post.expected_sha(stage,PRIOR_NATIVE_RUN)
        if source_commit!=PRIOR_COMMIT:
            raise ValueError("Previous compiled native run identity mismatch")
        with tempfile.TemporaryDirectory(prefix="wslpe40-refresh-hashes-") as tmp:
            _,artifact=stage.evidence_from_runner(PRIOR_NATIVE_RUN,PRIOR_COMMIT,Path(tmp))
            expected={name:digest(path.read_bytes()) for name,path in artifact.items()}
            expected[OPERATOR]=digest(source_old)
            auth=pre.load_auth()
            address,cert=auth.checked_certificate(auth.tls_audit_module(),stage.PIN)
            user,password=auth.operator_credentials(address)
            pre_state=pre.query(auth,address,cert,user,password)
            with stage.managed_session(auth,address,cert,user,password) as session:
                observed=session.run_ps(audit.READ_ONLY)
                if observed.status_code!=0:
                    raise ValueError("Guest rejected read-only inventory")
                inventory=audit.parse_record(observed.std_out)
                validate_guest(pre_state,inventory,post,expected)
                print("[PASS] Old operator, native binaries and JEA #30 unchanged")
                print("[PASS] Exact WSLPE pre-#40 snapshot and protected library")
                if args.diagnose:
                    diagnose_prewrite(session,stage,expected[OPERATOR])
                    return 0
                if not args.apply:
                    print("[PLAN ONLY] No guest mutation; use --apply to patch operator module")
                    return 0
                new_hash=checked_transfer(session,stage,expected[OPERATOR],source_new)
                verify=session.run_ps(audit.READ_ONLY)
                if verify.status_code!=0:
                    raise ValueError("Guest rejected post-update read-only audit")
                state=audit.parse_record(verify.std_out)
                post.validate_runtime(pre_state,state,{**expected,OPERATOR:new_hash})
        print("[PASS] WSLPE40_OPERATOR_CONSOLE_GUARD_REFRESHED=TRUE")
        print("[NO RPC EXECUTION] Native server/client unchanged; JEA #30 preserved")
        return 0
    except Exception as exc:
        print("[BLOCKED] "+type(exc).__name__+": preserve guest and snapshot for inspection")
        print("[NO AUTOMATIC RETRY] Do not repeat without fresh read-only inventory")
        return 2

if __name__=="__main__":
    raise SystemExit(main())
