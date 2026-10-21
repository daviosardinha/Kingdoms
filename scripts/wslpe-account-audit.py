#!/usr/bin/env python3
"""Read-only WSLPE local-account release audit over pinned authenticated HTTPS.

No passwords, hashes, group member enumerations outside the exact allowlist,
guest mutation, VMware changes, NORTH, or credential rotation.
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
FIXTURES = ("kingdom.appsvc", "kingdom.autologon", "kingdom.deploy",
            "kingdom.pshistory", "kingdom.runas")
ACCOUNTS = ("vagrant", "lpe.trainee", "kingdom.operator", *FIXTURES)

READ_ONLY = r"""
$ErrorActionPreference = 'Stop'
$machine=Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
if ($env:COMPUTERNAME -cne 'WSLPE-WS01' -or $machine.PartOfDomain) {
    throw 'Not exact domain-free WSLPE guest'
}
$admins=Get-LocalGroup -SID 'S-1-5-32-544' -ErrorAction Stop
$members=@(Get-LocalGroupMember -Group $admins.Name -ErrorAction Stop)
$adminSids=@($members | ForEach-Object { $_.SID.Value })
$names=@('vagrant','lpe.trainee','kingdom.operator',
         'kingdom.appsvc','kingdom.autologon','kingdom.deploy',
         'kingdom.pshistory','kingdom.runas')
$items=@()
foreach($name in $names) {
    $account=Get-LocalUser -Name $name -ErrorAction SilentlyContinue
    if($null -eq $account) {
        $items+=@{name=$name;exists=$false;enabled=$false;admin=$false}
    } else {
        $items+=@{name=$name;exists=$true;enabled=[bool]$account.Enabled;
            admin=[bool]($adminSids -contains $account.SID.Value)}
    }
}
Write-Output ('WSLPE_ACCOUNT_AUDIT_JSON='+(
    ConvertTo-Json -InputObject @{machine='WSLPE-WS01';domain_joined=$false;
                                  accounts=@($items)} -Compress -Depth 4))
"""

def load_auth():
    spec = importlib.util.spec_from_file_location("wslpe_account_auth", AUTH)
    if spec is None or spec.loader is None:
        raise ValueError("Verified HTTPS WSLPE auth module missing")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def parse_result(output: bytes, *, require_learner: bool = True) -> dict:
    if not isinstance(output, bytes):
        raise ValueError("Invalid account audit output")
    values = [
        line.partition("WSLPE_ACCOUNT_AUDIT_JSON=")[2]
        for line in output.decode("utf-8", errors="strict").splitlines()
        if line.startswith("WSLPE_ACCOUNT_AUDIT_JSON=")
    ]
    if len(values) != 1:
        raise ValueError("Expected one exact WSLPE account audit record")
    data = json.loads(values[0])
    if (not isinstance(data, dict) or set(data) != {"machine", "domain_joined", "accounts"}
            or data["machine"] != "WSLPE-WS01" or data["domain_joined"] is not False
            or not isinstance(data["accounts"], list)
            or len(data["accounts"]) != len(ACCOUNTS)):
        raise ValueError("Untrusted WSLPE account evidence")
    seen = {}
    for row in data["accounts"]:
        if (not isinstance(row, dict) or set(row) != {"name", "exists", "enabled", "admin"}
                or row["name"] not in ACCOUNTS or row["name"] in seen
                or any(type(row[field]) is not bool for field in ("exists", "enabled", "admin"))
                or (not row["exists"] and (row["enabled"] or row["admin"]))):
            raise ValueError("Invalid account membership/status evidence")
        seen[row["name"]] = row
    if set(seen) != set(ACCOUNTS):
        raise ValueError("Incomplete local account evidence")
    # A foundation preflight must observe an untouched guest without
    # confusing a not-yet-created learner with a broken release candidate.
    # Never accept a privileged learner, even during preflight.
    if seen["lpe.trainee"]["admin"]:
        raise ValueError("Learner is unexpectedly privileged")
    if require_learner and (
        not seen["lpe.trainee"]["exists"] or not seen["lpe.trainee"]["enabled"]
    ):
        raise ValueError("Learner is missing or disabled")
    return seen

def query(auth, address: str, certificate: bytes, username: str, password: str,
          *, require_learner: bool = True) -> dict:
    import winrm
    with tempfile.TemporaryDirectory(prefix="wslpe-account-audit-") as tmp:
        anchor = Path(tmp) / "leaf.pem"
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
                raise ValueError("WinRM did not use the pinned certificate")
            with auth.scoped_wslpe_resolution(address):
                result = session.run_ps(READ_ONLY)
        finally:
            transport.close_session()
    if result.status_code != 0:
        raise ValueError("Windows rejected the read-only account audit")
    return parse_result(result.std_out, require_learner=require_learner)

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--expected-thumbprint", required=True)
    p.add_argument("--pre-foundation", action="store_true",
                   help="read-only inventory before learner/operator creation; never accepts a privileged learner")
    args = p.parse_args()
    print("KINGDOMS WSLPE | LOCAL ACCOUNT RELEASE AUDIT (READ ONLY)")
    print("[NO CHANGES] No user, credential, WinRM, VMware or NORTH modifications")
    try:
        auth = load_auth()
        address, cert = auth.checked_certificate(auth.tls_audit_module(),
                                                  args.expected_thumbprint)
        user, secret = auth.operator_credentials(address)
        rows = query(auth, address, cert, user, secret,
                     require_learner=not args.pre_foundation)
    except Exception as exc:
        print(f"[BLOCKED] {type(exc).__name__} during WSLPE account inventory")
        return 1
    for name in ACCOUNTS:
        row = rows[name]
        print(f"[ACCOUNT] {name}: exists={row['exists']} enabled={row['enabled']} admin={row['admin']}")
    if args.pre_foundation:
        learner = rows["lpe.trainee"]
        operator = rows["kingdom.operator"]
        if learner["exists"] and learner["enabled"] and not learner["admin"]:
            print("[PASS] WSLPE_LOCAL_LEARNER_STANDARD=TRUE")
        elif learner["exists"]:
            print("[BLOCKED] Existing learner is disabled or improperly configured; do not create/overwrite")
            return 1
        else:
            print("[FOUNDATION PENDING] Local nonadmin learner not yet installed")
        if operator["exists"]:
            print("[FOUNDATION PENDING] Existing operator requires independent credentials/handoff audit; do not recreate")
        else:
            print("[FOUNDATION PENDING] Dedicated operator not yet installed")
        print("[NOT PROVEN] Independent VM console recovery, per-instance TLS provenance, management isolation")
        print("[NO CHANGES] Neither learner nor operator was created")
        return 0
    print("[PASS] WSLPE_LOCAL_LEARNER_STANDARD=TRUE")
    if rows["vagrant"]["exists"] and rows["vagrant"]["enabled"]:
        print("[RELEASE BLOCKED] Default bootstrap administrator vagrant remains enabled")
    if not (rows["kingdom.operator"]["exists"] and
            rows["kingdom.operator"]["enabled"] and rows["kingdom.operator"]["admin"]):
        print("[RELEASE BLOCKED] Dedicated privileged operator not yet established")
    print("[RELEASE BLOCKED] Source-defined fixture credentials require WSLPE-only per-instance overrides")
    print("[NOT VERIFIED] HTTPS operator handoff, old-password rejection and host isolation")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
