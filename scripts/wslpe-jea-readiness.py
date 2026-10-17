#!/usr/bin/env python3
"""Read-only JEA activation preflight for the unique standalone WSLPE guest.

Reuses the verified TLS pin, hostname, credential and destination guards.
Never registers/unregisters endpoints, restarts WinRM, installs fixtures,
modifies VMware, or contacts NORTH. A PASS is *not* activation approval.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import ssl
import tempfile

ROOT = Path(__file__).resolve().parents[1]
AUTH_SCRIPT = ROOT / "scripts/wslpe-https-auth-audit.py"
ENDPOINT = "Kingdoms45JEA"

# Fixed command: inspection only, no arguments controlled by the caller.
READ_ONLY_JEA = r"""
$ErrorActionPreference = 'Stop'
$machine=Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
if ($env:COMPUTERNAME -cne 'WSLPE-WS01' -or $machine.PartOfDomain) {
    throw 'Not exact non-domain WSLPE workstation'
}
$learner=Get-LocalUser -Name 'lpe.trainee' -ErrorAction Stop
$admins=Get-LocalGroup -SID 'S-1-5-32-544'
foreach($member in @(Get-LocalGroupMember -Group $admins.Name)) {
    if($member.SID.Value -eq $learner.SID.Value) {
        throw 'Learner unexpectedly administrator'
    }
}
$endpoint=@(Get-PSSessionConfiguration -Name 'Kingdoms45JEA' -ErrorAction SilentlyContinue)
$module='C:\Program Files\WindowsPowerShell\Modules\Kingdoms45JEA'
$fixture='C:\ProgramData\KingdomsWSLPE45\fixtures\jea_role_capability_misconfig'
$service=Get-Service -Name WinRM -ErrorAction Stop
$state=[ordered]@{
    machine='WSLPE-WS01'
    domain_joined=$false
    learner_enabled=[bool]$learner.Enabled
    winrm_running=($service.Status -eq 'Running')
    endpoint_count=[int]$endpoint.Count
    module_present=[bool](Test-Path -LiteralPath $module)
    fixture_present=[bool](Test-Path -LiteralPath $fixture)
}
Write-Output ('WSLPE_JEA_PREFLIGHT_JSON='+(ConvertTo-Json -InputObject $state -Compress))
"""

def auth_module():
    spec = importlib.util.spec_from_file_location("wslpe_jea_auth", AUTH_SCRIPT)
    if spec is None or spec.loader is None:
        raise ValueError("Pinned WSLPE HTTPS auth module missing")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def parse_result(output: bytes) -> dict:
    if not isinstance(output, bytes):
        raise ValueError("Invalid WinRM read-only output")
    lines = output.decode("utf-8", errors="strict").splitlines()
    values = [line[len("WSLPE_JEA_PREFLIGHT_JSON="):]
              for line in lines if line.startswith("WSLPE_JEA_PREFLIGHT_JSON=")]
    if len(values) != 1:
        raise ValueError("Expected exactly one JEA status result")
    state = json.loads(values[0])
    fields = {"machine", "domain_joined", "learner_enabled",
              "winrm_running", "endpoint_count", "module_present", "fixture_present"}
    if not isinstance(state, dict) or set(state) != fields:
        raise ValueError("Unexpected JEA evidence schema")
    if (state["machine"] != "WSLPE-WS01"
            or state["domain_joined"] is not False
            or state["learner_enabled"] is not True
            or state["winrm_running"] is not True
            or type(state["endpoint_count"]) is not int
            or state["endpoint_count"] < 0
            or any(type(state[k]) is not bool
                   for k in ("module_present", "fixture_present"))):
        raise ValueError("JEA prerequisites were not met")
    return state

def query_jea_state(auth, address: str, certificate: bytes,
                    username: str, password: str) -> dict:
    import winrm
    with tempfile.TemporaryDirectory(prefix="wslpe-jea-readonly-") as temp:
        anchor = Path(temp) / "leaf.pem"
        anchor.write_text(ssl.DER_cert_to_PEM_cert(certificate), encoding="ascii")
        anchor.chmod(0o600)
        session = winrm.Session(
            "https://WSLPE-WS01:5986/wsman", auth=(username, password),
            transport="ntlm", server_cert_validation="validate",
            ca_trust_path=str(anchor), proxy=None,
            operation_timeout_sec=20, read_timeout_sec=40,
        )
        transport = session.protocol.transport
        try:
            http = transport.build_session()
            http.trust_env = False
            http.proxies = {}
            if http.verify != str(anchor):
                raise ValueError("WinRM ignored pinned certificate anchor")
            with auth.scoped_wslpe_resolution(address):
                result = session.run_ps(READ_ONLY_JEA)
        finally:
            transport.close_session()
    if result.status_code != 0:
        raise ValueError("JEA read-only status query rejected by Windows")
    return parse_result(result.std_out)

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-thumbprint", required=True)
    args = parser.parse_args()
    print("KINGDOMS WSLPE | JEA ENDPOINT READ-ONLY PREFLIGHT")
    print("[NO CHANGES] JEA, WinRM, VMware, firewall, NORTH and guest remain unchanged")
    try:
        auth = auth_module()
        address, certificate = auth.checked_certificate(
            auth.tls_audit_module(), args.expected_thumbprint)
        username, password = auth.operator_credentials(address)
        state = query_jea_state(auth, address, certificate, username, password)
        print("[PASS] Certificate-verified, authenticated WSLPE-only management")
        print("[PASS] Exact workgroup host, enabled non-admin learner, WinRM running")
        print(f"[INFO] Kingdoms45JEA registrations: {state['endpoint_count']}")
        print(f"[INFO] Dedicated JEA module exists: {state['module_present']}")
        print(f"[INFO] Dedicated JEA fixture exists: {state['fixture_present']}")
        if any((state["endpoint_count"] != 0, state["module_present"], state["fixture_present"])):
            print("[BLOCKED] JEA already present or partial state; review before any apply")
            return 2
    except Exception as exc:
        print(f"[BLOCKED] {type(exc).__name__} during read-only JEA preflight")
        print("[NO CHANGES] Never use certificate-ignore or blind WinRM restart")
        return 1
    print("[PASS] WSLPE_JEA_CLEAN_PREEXISTING_STATE=TRUE")
    print("[NOT VERIFIED] Learner JEA activation, independent WinRM recovery and RDP")
    print("[NOT AUTHORIZED] No JEA registration, WinRM restart or batch execution")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
