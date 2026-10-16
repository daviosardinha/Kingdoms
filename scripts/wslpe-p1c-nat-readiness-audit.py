#!/usr/bin/env python3
"""Single WSLPE-only NAT handoff PRE-CHANGE AUDIT (no NIC, VM or firewall writes).

Collects VMware identity, Windows IPv4/IPv6/routes, guarded HTTPS,
host nft runtime and persistence indicators in one read-only pass.
This cannot authorize a VMware power-cycle without a proven independent
guest-NIC restore mechanism. No NORTH traffic or changes.
"""
from __future__ import annotations

import importlib.util
import ipaddress
import json
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kingdoms.wslpe_nat_readiness import (
    vmx_snapshot, windows_snapshot, cutover_blockers,
)

PIN = "C773EC26D02940F559FE715B83628FEDAE2AA92D"
PILOT_SCRIPT = ROOT / "scripts/wslpe-p1c-host-filter-pilot.py"
AUTH_SCRIPT = ROOT / "scripts/wslpe-https-auth-audit.py"

WINDOWS_NETWORK = r'''
$ErrorActionPreference = 'Stop'
$machine = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
if ($env:COMPUTERNAME -ine 'WSLPE-WS01' -or $machine.PartOfDomain) {
  throw 'Not the domain-free WSLPE-WS01'
}
$adapters = @(Get-NetAdapter -ErrorAction Stop | ForEach-Object {
  [pscustomobject]@{ Mac = [string]$_.MacAddress; Index=[int]$_.ifIndex;
                     Alias=[string]$_.Name; Status=[string]$_.Status }
})
$v4 = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
  Where-Object { $_.IPAddress -notlike '127.*' } | ForEach-Object {
  [pscustomobject]@{ Address=[string]$_.IPAddress; Index=[int]$_.InterfaceIndex;
                     Prefix=[int]$_.PrefixLength }
})
$v6 = @(Get-NetIPAddress -AddressFamily IPv6 -ErrorAction Stop |
  Where-Object { $_.IPAddress -ne '::1' } | ForEach-Object {
  [pscustomobject]@{ Address=[string]$_.IPAddress; Index=[int]$_.InterfaceIndex;
                     Prefix=[int]$_.PrefixLength }
})
$r4 = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
  ForEach-Object { [pscustomobject]@{ Index=[int]$_.InterfaceIndex } })
$r6 = @(Get-NetRoute -AddressFamily IPv6 -DestinationPrefix '::/0' -ErrorAction SilentlyContinue |
  ForEach-Object { [pscustomobject]@{ Index=[int]$_.InterfaceIndex } })
$snapshot = @{
  Machine = [string]$env:COMPUTERNAME
  DomainJoined = [bool]$machine.PartOfDomain
  Adapters = $adapters
  IPv4 = $v4
  IPv6 = $v6
  DefaultRoutes4 = $r4
  DefaultRoutes6 = $r6
}
Write-Output ('WSLPE_NAT_READY_JSON=' + ($snapshot | ConvertTo-Json -Compress -Depth 6))
'''


def imported(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("WSLPE verifier source missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pinned_windows_snapshot(auth, address: str, cert: bytes) -> dict:
    """Read-only, verified TLS; no new creds or persistent certificate changes."""
    import winrm
    username, password = auth.operator_credentials(address)
    with tempfile.TemporaryDirectory(prefix="wslpe-nat-readiness-") as folder:
        anchor = Path(folder) / "wslpe-only.pem"
        anchor.write_text(ssl.DER_cert_to_PEM_cert(cert), encoding="ascii")
        anchor.chmod(0o600)
        session = winrm.Session(
            "https://WSLPE-WS01:5986/wsman",
            auth=(username, password), transport="ntlm",
            server_cert_validation="validate", ca_trust_path=str(anchor),
            proxy=None, operation_timeout_sec=20, read_timeout_sec=50,
        )
        transport = session.protocol.transport
        try:
            client = transport.build_session()
            client.trust_env = False
            client.proxies = {}
            if client.verify != str(anchor):
                raise ValueError("WinRM TLS pin was not retained")
            with auth.scoped_wslpe_resolution(address):
                result = session.run_ps(WINDOWS_NETWORK)
        finally:
            transport.close_session()
    if result.status_code:
        raise ValueError("Authenticated WSLPE Windows audit failed")
    stdout = result.std_out.decode("utf-8", "replace")
    matches = [line[len("WSLPE_NAT_READY_JSON="):] for line in stdout.splitlines()
               if line.startswith("WSLPE_NAT_READY_JSON=")]
    if len(matches) != 1 or len(matches[0]) > 20000:
        raise ValueError("WSLPE Windows audit returned ambiguous evidence")
    data = json.loads(matches[0])
    if not isinstance(data, dict):
        raise ValueError("WSLPE Windows audit JSON was not an object")
    return data


def nft_local_snapshot(pilot) -> dict:
    entries = pilot.nft_json("ruleset")
    names = set()
    for record in entries:
        item = record.get("table") if isinstance(record, dict) else None
        if isinstance(item, dict):
            names.add((item.get("family"), item.get("name")))
    cmd = subprocess.run(
        ["systemctl", "is-enabled", "nftables"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    service = cmd.stdout.strip() if cmd.stdout.strip() else "unknown"
    return {
        "host_guard_table": ("inet", "kingdoms_wslpe_winrm") in names,
        "exercise_table_active": ("inet", "kingdoms_wslpe_exercise") in names,
        "nftables_boot_service": service,
    }


def main() -> int:
    print("KINGDOMS WSLPE | CONSOLIDATED NAT HANDOFF PRE-CHANGE EVIDENCE")
    print("[NO CHANGES] No NORTH, NAT, VMware, firewall, Windows or route mutations")
    try:
        pilot = imported(PILOT_SCRIPT, "wslpe_nat_pilot")
        auth = imported(AUTH_SCRIPT, "wslpe_nat_auth")
        # Existing pilot requires exact native running VMX, unique vmnet,
        # host route, co-tenant checks, nft --check and no existing table.
        candidate, vmnet, host, guest = pilot.local_preflight()
        stage2 = pilot.load_script(pilot.PLAN, "wslpe_nat_plan")
        runtime = stage2.import_script(stage2.STAGE2_PATH, "wslpe_nat_stage2")
        instance, manifest = runtime.find_instance(runtime.WORKSPACE)
        vmx = runtime.locate_registered_vm(instance)
        source = vmx.read_text(encoding="utf-8", errors="replace")
        metadata = vmx_snapshot(source, vmnet)
        audit = auth.tls_audit_module()
        address, der = auth.checked_certificate(audit, PIN)
        if address != guest:
            raise ValueError("WSLPE TLS destination differs from native guest")
        guest_data = pinned_windows_snapshot(auth, address, der)
        windows = windows_snapshot(
            guest_data, metadata, host, guest
        )
        host_fw = nft_local_snapshot(pilot)
        ipv6_host = subprocess.run(
            ["ip", "-j", "-6", "address", "show", "dev", vmnet],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if ipv6_host.returncode:
            raise ValueError("Host exercise IPv6 interface check unavailable")
        host_ipv6 = json.loads(ipv6_host.stdout)
        if not isinstance(host_ipv6, list) or len(host_ipv6) != 1:
            raise ValueError("Host vmnet IPv6 inventory ambiguous")
    except Exception as exc:
        # Hide lower-level WinRM request, account or certificate details.
        print(f"[BLOCKED] {type(exc).__name__}: evidence incomplete")
        print("[NO CHANGES] Any cutover must remain locked")
        return 1

    print(f"[PASS] Exact WSLPE VMware VMX and separate {vmnet}: {vmx.name}")
    print(f"[PASS] Two exact Windows NIC MAC identities match registered VMware VMX")
    print(f"[PASS] Dedicated exercise IPv4={guest}/24; Kali={host}")
    print(f"[PASS] Windows default routes absent from exercise NIC")
    print(f"[PASS] Verified pinned HTTPS/5986 to standalone, domain-free WSLPE-WS01")
    print(f"[INFO] Windows NAT NIC index={windows['nat_index']}; exercise NIC index={windows['exercise_index']}")
    print(f"[INFO] Windows routes on provisioning NAT={windows['nat_default_route_count']}")
    print(f"[INFO] Exercise IPv6 addresses={windows['exercise_ipv6_count']} (L2/IPv6 exposure NOT disproved)")
    print(f"[INFO] Host guard table present={host_fw['host_guard_table']}")
    print(f"[INFO] Proposed exercise filter active={host_fw['exercise_table_active']}")
    print(f"[INFO] nftables boot service={host_fw['nftables_boot_service']}")
    print("[PASS] VM guest NAT currently attached; managed exercise network remains reachable")

    blocked = cutover_blockers(
        nat_is_attached=True,
        host_filter_persistent=False,  # Requires separate reboot-validated proof
        independent_vm_rollback=False,  # No host-side VMX rescue runner has been proved
        l2_isolation=False,             # Guest SYSTEM and hypervisor paths remain untested
    )
    print("\n===== ONE CONSOLIDATED RELEASE/BLOCKER REPORT =====")
    for item in blocked:
        print(f"[RELEASE BLOCKED] {item}")
    print("[NOT VERIFIED] VMware offline VMX persistence, automatic NAT restore,")
    print("               untrusted guest ARP/IPv6, co-tenant/hypervisor boundaries,")
    print("               host firewall reboot persistence, learner RDP and scenarios")
    print(f"[RESULT] WSLPE_NAT_READINESS_AUDIT=PASS; REMAINING_GATES={len(blocked)}")
    print("[RESULT] WSLPE_NAT_CUTOVER_AUTHORIZED=FALSE")
    print("[NO CHANGES] WSLPE PROVIDE-only development state; NORTH untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
