#!/usr/bin/env python3
"""Read-only diagnosis of a blocked WSLPE40 copy-only handoff.

Uses the established leaf-pinned WinRM transport, current WSLPE inventory,
and immutable exact paths. Prints no usernames, passwords or remote stderr.
No guest writes or automatic retries.
"""
from __future__ import annotations

import json
from pathlib import Path

from importlib.util import module_from_spec, spec_from_file_location

ROOT=Path(__file__).resolve().parents[1]
PREFLIGHT=ROOT/"scripts/wslpe40-runtime-preflight.py"
MARKER="WSLPE40_STAGE_AUDIT_JSON="

READ_ONLY=r"""
$ErrorActionPreference='Stop'
$machine=Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop
if($env:COMPUTERNAME -cne 'WSLPE-WS01' -or $machine.PartOfDomain){
    throw 'Unexpected guest identity'
}
$learner=Get-LocalUser -Name 'lpe.trainee' -ErrorAction Stop
if(-not $learner.Enabled){throw 'Learner account not enabled'}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=[Security.Principal.WindowsPrincipal]::new($identity)
$admin=[bool]$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$lib='C:\ProgramData\KingdomsWSLPE45\lib'
$item=Get-Item -LiteralPath $lib -Force -ErrorAction Stop
if(-not $item.PSIsContainer -or
   (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)){
    throw 'Not the exact protected WSLPE library'
}
$protected=[bool](Get-Acl -LiteralPath $lib -ErrorAction Stop).AreAccessRulesProtected
$names=@('Wslpe40RpcOperator.psm1','Kingdom40LocalRpcServer.exe',
         'Kingdom40LocalRpcClient.exe')
$report=[ordered]@{
    machine='WSLPE-WS01'
    token_elevated_admin=$admin
    library_acl_protected=$protected
    exact_files=@()
    partial_files=@()
    rpc_host_count=0
}
$entries=@(Get-ChildItem -LiteralPath $lib -Force -ErrorAction Stop)
foreach($name in $names){
    $matches=@($entries|Where-Object {$_.Name -ceq $name})
    if($matches.Count -gt 1){throw 'Duplicate exact-path entries'}
    if($matches.Count -eq 0){
        $report.exact_files+=@{name=$name;present=$false;linked=$false;size=0;sha256=''}
    } else {
        $it=$matches[0]
        $linked=[bool](($it.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)
        $hash=''
        if(-not $linked -and -not $it.PSIsContainer){
            $hash=(Get-FileHash -LiteralPath $it.FullName -Algorithm SHA256 -ErrorAction Stop).Hash
        }
        $report.exact_files+=@{name=$name;present=$true;linked=$linked;
                              size=[int64]$it.Length;sha256=$hash}
    }
    $prefix=$name+'.wslpe40-stage-'
    $temp=@($entries|Where-Object {$_.Name.StartsWith($prefix,[StringComparison]::Ordinal)})
    foreach($it in $temp){
        $report.partial_files+=@{
            target=$name
            size=[int64]$it.Length
            linked=[bool](($it.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)
            directory=[bool]$it.PSIsContainer
        }
    }
}
$rpc=@(Get-CimInstance -ClassName Win32_Process -Filter "Name = 'Kingdom40LocalRpcServer.exe'" -ErrorAction Stop)
$report.rpc_host_count=[int]$rpc.Count
Write-Output ('WSLPE40_STAGE_AUDIT_JSON='+(ConvertTo-Json -InputObject $report -Compress -Depth 6))
"""

NAMES=("Wslpe40RpcOperator.psm1","Kingdom40LocalRpcServer.exe",
       "Kingdom40LocalRpcClient.exe")

def parse_record(raw: bytes):
    lines=raw.decode("utf-8",errors="strict").splitlines()
    found=[v[len(MARKER):] for v in lines if v.startswith(MARKER)]
    if len(found)!=1: raise ValueError("Missing or duplicate stage audit evidence")
    result=json.loads(found[0])
    if not isinstance(result,dict) or result.get("machine")!="WSLPE-WS01":
        raise ValueError("Unexpected stage audit target")
    if type(result.get("token_elevated_admin")) is not bool:
        raise ValueError("Invalid remote admin evidence")
    if type(result.get("library_acl_protected")) is not bool:
        raise ValueError("Invalid library ACL evidence")
    if type(result.get("rpc_host_count")) is not int or result["rpc_host_count"]<0:
        raise ValueError("Invalid RPC host evidence")
    records=result.get("exact_files")
    if not isinstance(records,list) or len(records)!=3:
        raise ValueError("Unexpected exact-stage inventory")
    if {r.get("name") for r in records if isinstance(r,dict)}!=set(NAMES):
        raise ValueError("Unexpected staged file name")
    for entry in records:
        if (type(entry.get("present")) is not bool
                or type(entry.get("linked")) is not bool
                or type(entry.get("size")) is not int
                or entry["size"]<0
                or not isinstance(entry.get("sha256"),str)):
            raise ValueError("Malformed staged file entry")
        digest=entry["sha256"]
        if digest and (len(digest)!=64 or any(c not in "0123456789abcdefABCDEF" for c in digest)):
            raise ValueError("Invalid staged-file digest")
    partial=result.get("partial_files")
    if not isinstance(partial,list):
        raise ValueError("Malformed partial-stage inventory")
    for item in partial:
        if (not isinstance(item,dict) or item.get("target") not in NAMES
                or type(item.get("size")) is not int or item["size"]<0
                or type(item.get("linked")) is not bool
                or type(item.get("directory")) is not bool):
            raise ValueError("Invalid partial-stage item")
    return result

def main():
    print("KINGDOMS WSLPE | #40 STAGE FAILURE AUDIT (READ ONLY)")
    print("[NO MUTATION] Exact Windows paths and WinRM token only")
    try:
        spec=spec_from_file_location("wslpe40_audit_transport",PREFLIGHT)
        if not spec or not spec.loader:
            raise ValueError("Pinned transport source unavailable")
        module=module_from_spec(spec)
        spec.loader.exec_module(module)
        auth=module.load_auth()
        address,cert=auth.checked_certificate(auth.tls_audit_module(),
            "C773EC26D02940F559FE715B83628FEDAE2AA92D")
        user,password=auth.operator_credentials(address)
        # Use the exact pinned HTTPS session established by the preflight,
        # but a read-only query with extra staging failure evidence.
        import ssl
        import tempfile
        import winrm
        with tempfile.TemporaryDirectory(prefix="wslpe40-stage-audit-") as tmp:
            trust=Path(tmp)/"leaf.pem"
            trust.write_text(ssl.DER_cert_to_PEM_cert(cert),encoding="ascii")
            trust.chmod(0o600)
            session=winrm.Session(
                "https://WSLPE-WS01:5986/wsman",auth=(user,password),
                transport="ntlm",server_cert_validation="validate",
                ca_trust_path=str(trust),proxy=None,
                operation_timeout_sec=20,read_timeout_sec=40)
            transport=session.protocol.transport
            try:
                http=transport.build_session()
                http.trust_env=False
                http.proxies={}
                if http.verify!=str(trust):
                    raise ValueError("Incorrect WinRM pinned trust")
                with auth.scoped_wslpe_resolution(address):
                    response=session.run_ps(READ_ONLY)
            finally:
                transport.close_session()
        if response.status_code != 0:
            raise ValueError("Windows rejected read-only stage audit")
        evidence=parse_record(response.std_out)
    except Exception as exc:
        print("[BLOCKED] "+type(exc).__name__+" during read-only guest audit")
        return 2
    print("[STATE] remote_elevated_admin="+str(evidence["token_elevated_admin"]))
    print("[STATE] library_acl_protected="+str(evidence["library_acl_protected"]))
    print("[STATE] rpc_host_count="+str(evidence["rpc_host_count"]))
    for item in evidence["exact_files"]:
        print("[STATE] "+item["name"]+" present="+str(item["present"])+
              " linked="+str(item["linked"])+" size="+str(item["size"]))
    print("[STATE] incomplete_transfer_count="+str(len(evidence["partial_files"])))
    for item in evidence["partial_files"]:
        print("[STATE] partial_for="+item["target"]+" size="+str(item["size"])+
              " linked="+str(item["linked"])+" directory="+str(item["directory"]))
    if evidence["partial_files"] or any(x["present"] for x in evidence["exact_files"]):
        print("[BLOCKED] Partial/complete staged object exists; do not retry copy")
    elif not evidence["token_elevated_admin"]:
        print("[BLOCKED] WinRM operator token lacks local elevated administrator permissions")
    elif not evidence["library_acl_protected"]:
        print("[BLOCKED] Protected library ACL mismatch")
    else:
        print("[PASS] No files staged; failure occurred before destination creation")
    print("[NO AUTOMATIC RETRY] Guest remains unchanged by this audit")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
