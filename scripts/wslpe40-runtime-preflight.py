#!/usr/bin/env python3
"""Read-only #40 guest baseline over WSLPE-only certificate-pinned WinRM HTTPS.

No RPC listener launch, fixture creation, MSI staging, JEA changes, or guest writes.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import ssl
import tempfile

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "scripts/wslpe-https-auth-audit.py"
MARKER = "WSLPE40_RUNTIME_PREFLIGHT_JSON="

READ_ONLY = r"""
$ErrorActionPreference='Stop'
$machine=Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
if($env:COMPUTERNAME -cne 'WSLPE-WS01' -or $machine.PartOfDomain) {
    throw 'Wrong guest or domain joined'
}
$learner=Get-LocalUser -Name 'lpe.trainee' -ErrorAction Stop
$admins=Get-LocalGroup -SID 'S-1-5-32-544' -ErrorAction Stop
$adminSids=@(Get-LocalGroupMember -Group $admins.Name -ErrorAction Stop |
    ForEach-Object {$_.SID.Value})
if(-not $learner.Enabled -or $adminSids -contains $learner.SID.Value) {
    throw 'Expected enabled non-admin learner'
}
$base='C:\ProgramData\KingdomsWSLPE45'
$lib=Join-Path $base 'lib'
$fixture=Join-Path $base 'fixtures\custom_rpc_authorization'
$proof=Join-Path $fixture 'rpc-proof.txt'
$jeaModule='C:\Program Files\WindowsPowerShell\Modules\Kingdoms45JEA'
function ItemPresent([string]$Path) {
    return $null -ne (Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue)
}
function IsLinked([string]$Path) {
    $entry=Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    return ($null -ne $entry -and (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0))
}
function ProtectedAcl([string]$Path) {
    $entry=Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if($null -eq $entry -or -not $entry.PSIsContainer) { return $false }
    return [bool](Get-Acl -LiteralPath $Path -ErrorAction Stop).AreAccessRulesProtected
}
$endpoint=@(Get-PSSessionConfiguration -Name 'Kingdoms45JEA' -ErrorAction SilentlyContinue)
$rpcHosts=@(Get-CimInstance -ClassName Win32_Process -Filter "Name = 'Kingdom40LocalRpcServer.exe'" -ErrorAction Stop)
$winrm=Get-Service -Name 'WinRM' -ErrorAction Stop
$report=[ordered]@{
    machine='WSLPE-WS01'
    domain_joined=$false
    learner_standard=$true
    winrm_running=($winrm.Status -eq 'Running')
    jea_endpoint_count=[int]$endpoint.Count
    jea_module_present=[bool](ItemPresent $jeaModule)
    library_present=[bool](ItemPresent $lib)
    library_acl_protected=[bool](ProtectedAcl $lib)
    library_linked=[bool](IsLinked $lib)
    rpc_fixture_present=[bool](ItemPresent $fixture)
    rpc_fixture_linked=[bool](IsLinked $fixture)
    rpc_proof_present=[bool](ItemPresent $proof)
    rpc_proof_linked=[bool](IsLinked $proof)
    rpc_operator_staged=[bool](ItemPresent (Join-Path $lib 'Wslpe40RpcOperator.psm1'))
    rpc_server_staged=[bool](ItemPresent (Join-Path $lib 'Kingdom40LocalRpcServer.exe'))
    rpc_client_staged=[bool](ItemPresent (Join-Path $lib 'Kingdom40LocalRpcClient.exe'))
    rpc_host_count=[int]$rpcHosts.Count
}
Write-Output ('WSLPE40_RUNTIME_PREFLIGHT_JSON='+(ConvertTo-Json -InputObject $report -Compress))
"""

FIELDS = {
    "machine": str, "domain_joined": bool, "learner_standard": bool,
    "winrm_running": bool, "jea_endpoint_count": int,
    "jea_module_present": bool, "library_present": bool,
    "library_acl_protected": bool, "library_linked": bool,
    "rpc_fixture_present": bool, "rpc_fixture_linked": bool,
    "rpc_proof_present": bool, "rpc_proof_linked": bool,
    "rpc_operator_staged": bool, "rpc_server_staged": bool,
    "rpc_client_staged": bool, "rpc_host_count": int,
}

def load_auth():
    spec = importlib.util.spec_from_file_location("wslpe40_pin", AUTH)
    if spec is None or spec.loader is None:
        raise ValueError("Pinned WSLPE transport unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def parse_evidence(output: bytes) -> dict:
    lines = output.decode("utf-8", errors="strict").splitlines()
    values = [line[len(MARKER):] for line in lines if line.startswith(MARKER)]
    if len(values) != 1:
        raise ValueError("Expected one WSLPE40 read-only record")
    data = json.loads(values[0])
    if not isinstance(data, dict) or set(data) != set(FIELDS):
        raise ValueError("Unexpected WSLPE40 evidence fields")
    if any(type(data[key]) is not kind for key, kind in FIELDS.items()):
        raise ValueError("Unexpected WSLPE40 evidence types")
    if (data["machine"] != "WSLPE-WS01" or data["domain_joined"]
            or not data["learner_standard"] or not data["winrm_running"]
            or data["jea_endpoint_count"] > 1
            or data["rpc_host_count"] < 0):
        raise ValueError("Guest identity or expected baseline unsafe")
    return data

def query(auth, address: str, certificate: bytes, user: str, password: str):
    import winrm
    with tempfile.TemporaryDirectory(prefix="wslpe40-readonly-") as tmp:
        trust = Path(tmp) / "leaf.pem"
        trust.write_text(ssl.DER_cert_to_PEM_cert(certificate), encoding="ascii")
        trust.chmod(0o600)
        session = winrm.Session(
            "https://WSLPE-WS01:5986/wsman", auth=(user, password),
            transport="ntlm", server_cert_validation="validate",
            ca_trust_path=str(trust), proxy=None,
            operation_timeout_sec=20, read_timeout_sec=40)
        transport = session.protocol.transport
        try:
            http = transport.build_session()
            http.trust_env = False
            http.proxies = {}
            if http.verify != str(trust):
                raise ValueError("Unexpected WinRM trust anchor")
            with auth.scoped_wslpe_resolution(address):
                response = session.run_ps(READ_ONLY)
        finally:
            transport.close_session()
    if response.status_code != 0:
        raise ValueError("Windows rejected the read-only #40 baseline")
    return parse_evidence(response.std_out)

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-thumbprint", required=True)
    args = parser.parse_args()
    print("KINGDOMS WSLPE | #40 RUNTIME BASELINE (READ ONLY)")
    print("[NO GUEST CHANGES] No installer, RPC listener, fixture, JEA or NORTH mutation")
    try:
        auth = load_auth()
        address, certificate = auth.checked_certificate(
            auth.tls_audit_module(), args.expected_thumbprint)
        user, password = auth.operator_credentials(address)
        state = query(auth, address, certificate, user, password)
    except Exception as exc:
        print(f"[BLOCKED] {type(exc).__name__} during #40 read-only baseline")
        return 2
    print("[PASS] Exact workgroup WSLPE, standard learner and WinRM")
    for key, value in state.items():
        if key not in ("machine", "domain_joined", "learner_standard", "winrm_running"):
            print(f"[STATE] {key}={value}")
    if (state["library_linked"] or state["rpc_fixture_linked"]
            or state["rpc_proof_linked"] or state["rpc_host_count"] != 0
            or (state["library_present"] and not state["library_acl_protected"])):
        print("[BLOCKED] Unsafe/pre-existing #40 state needs review before staging")
        return 2
    print("[PASS] WSLPE40_READ_ONLY_RUNTIME_BASELINE=TRUE")
    print("[NOT AUTHORIZED] No native RPC staging or privilege-boundary test yet")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
