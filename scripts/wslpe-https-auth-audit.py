#!/usr/bin/env python3
"""Authenticated, certificate-verified HTTPS/5986 WinRM probe for WSLPE only.

Read-only Windows query. The unique, running, registered WSLPE instance and
the pre-recorded HTTPS thumbprint must match before asking for credentials.
No persistent host resolver, trust-store, inventory, VMware or guest changes.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import importlib.util
import ipaddress
import json
import os
import subprocess
from pathlib import Path
import socket
import ssl
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TLS_AUDIT = ROOT / "scripts/wslpe-https-trust-audit.py"
HOST = "WSLPE-WS01"
PORT = 5986

# A read-only query, with no learner or Windows configuration mutations.
READ_ONLY = r'''
$ErrorActionPreference = 'Stop'
$machine = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
if ($env:COMPUTERNAME -ine 'WSLPE-WS01' -or $machine.PartOfDomain) {
    throw 'Not the standalone WSLPE workstation'
}
Write-Output 'WSLPE_HTTPS_AUTH=PASS'
Write-Output 'WSLPE_DOMAIN_FREE=PASS'
'''


def tls_audit_module():
    spec = importlib.util.spec_from_file_location("wslpe_auth_transport", TLS_AUDIT)
    if spec is None or spec.loader is None:
        raise ValueError("WSLPE pinned transport checker unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def scoped_wslpe_resolution(address: str):
    """Map only the exact WSLPE hostname/port for THIS one Python process.

    The URI and SNI stay WSLPE-WS01 (the certificate's verified DNS SAN).
    Do not mutate /etc/hosts, DNS, the OS resolver or other VMs.
    """
    real_getaddrinfo = socket.getaddrinfo

    def resolve(host, port, *args, **kwargs):
        if (isinstance(host, str) and host.casefold() == HOST.casefold()
                and str(port) == str(PORT)):
            return real_getaddrinfo(address, port, *args, **kwargs)
        raise OSError("WSLPE-only endpoint guard rejected an unexpected destination")

    with patch.object(socket, "getaddrinfo", resolve):
        yield


def checked_certificate(audit, expected_thumbprint: str) -> tuple[str, bytes]:
    fingerprint = audit.expected_fingerprint(expected_thumbprint)
    address = audit.registered_wslpe_address()
    der = audit.read_untrusted_tls_leaf(address)
    if audit.cert_fingerprint(der) != fingerprint:
        raise ValueError("HTTPS certificate did not match pre-recorded WSLPE pin")
    # Must validate chain, TLS and SAN before requesting a credential.
    audit.verify_pinned_tls(address, der, fingerprint)
    return address, der



def credentials_from_wslpe_inventory(address: str) -> tuple[str, str]:
    """Read existing native WSLPE operator credentials; never print them.

    This resolves Ansible's *existing WSLPE-only* inventory. No new password
    literal, file, keychain, or repository secret is created by the audit.
    """
    spec = importlib.util.spec_from_file_location(
        "wslpe_auth_inventory_stage2", ROOT / "scripts/wslpe-stage2-inspect.py"
    )
    if spec is None or spec.loader is None:
        raise ValueError("WSLPE native instance verification unavailable")
    stage2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stage2)

    instance, manifest = stage2.find_instance(stage2.WORKSPACE)
    stage2.locate_registered_vm(instance)
    if manifest.get("lab") != "WSLPE":
        raise ValueError("Operator inventory does not belong to WSLPE")
    inventory = instance / "inventory"
    base = ROOT / "ad/WSLPE/data/inventory_disable_vagrant"
    if (not inventory.is_file() or inventory.is_symlink()
            or not base.is_file() or base.is_symlink()):
        raise ValueError("Existing WSLPE operator inventories are unavailable")

    executable = Path.home() / ".goad/.venv/bin/ansible-inventory"
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError("Existing GOAD Ansible inventory executable unavailable")
    completed = subprocess.run(
        [str(executable), "-i", str(inventory), "-i", str(base),
         "--host", "ws01"], text=True, capture_output=True,
        check=False, timeout=20, cwd=str(ROOT),
    )
    if completed.returncode:
        raise ValueError("WSLPE operator inventory failed to resolve")
    try:
        data = json.loads(completed.stdout)
        if not isinstance(data, dict):
            raise ValueError("Invalid WSLPE inventory host object")
        if (str(ipaddress.ip_address(data.get("ansible_host", ""))) != address
                or data.get("ansible_connection") != "winrm"
                or str(data.get("ansible_port")) != "5985"
                or data.get("ansible_winrm_scheme") != "http"
                or data.get("ansible_winrm_transport") != "ntlm"):
            raise ValueError("WSLPE operator inventory endpoint mismatch")
        username = data.get("ansible_user")
        password = data.get("ansible_password")
        if (not isinstance(username, str) or not username.strip()
                or not isinstance(password, str) or not password):
            raise ValueError("WSLPE operator credentials missing from inventory")
        return username, password
    except (json.JSONDecodeError, ipaddress.AddressValueError) as exc:
        raise ValueError("WSLPE operator inventory unreadable") from exc


def operator_credentials(address: str) -> tuple[str, str]:
    """An explicit private environment override can support later rotation."""
    override = os.getenv("KINGDOMS_WSLPE_BOOTSTRAP_PASSWORD")
    if override is not None:
        user = os.getenv("KINGDOMS_WSLPE_BOOTSTRAP_USER", "vagrant")
        if not user.strip() or not override:
            raise ValueError("Incomplete WSLPE operator credential override")
        return user, override
    return credentials_from_wslpe_inventory(address)


def authenticated_read_only_probe(address: str, der: bytes,
                                  username: str, password: str) -> None:
    import winrm

    # A certificate anchor usable only by this process. No global CA import,
    # /etc/hosts change, Ansible inventory rewrite or permanent secret file.
    with tempfile.TemporaryDirectory(prefix="kingdoms-wslpe-https-") as folder:
        anchor = Path(folder) / "verified-leaf.pem"
        anchor.write_text(ssl.DER_cert_to_PEM_cert(der), encoding="ascii")
        anchor.chmod(0o600)
        session = winrm.Session(
            f"https://{HOST}:{PORT}/wsman",
            auth=(username, password),
            transport="ntlm",
            server_cert_validation="validate",
            ca_trust_path=str(anchor),
            proxy=None,
            operation_timeout_sec=20,
            read_timeout_sec=40,
        )
        transport = session.protocol.transport
        try:
            http = transport.build_session()
            # Disable env proxy, .netrc and CA environment injection.
            http.trust_env = False
            http.proxies = {}
            if http.verify != str(anchor):
                raise ValueError("WinRM client did not use the pinned certificate CA file")
            with scoped_wslpe_resolution(address):
                result = session.run_ps(READ_ONLY)
        finally:
            transport.close_session()

    if result.status_code != 0:
        raise ValueError("Windows rejected the authenticated HTTPS read-only query")
    lines = set(result.std_out.decode("utf-8", errors="replace").splitlines())
    if not {"WSLPE_HTTPS_AUTH=PASS", "WSLPE_DOMAIN_FREE=PASS"} <= lines:
        raise ValueError("Windows HTTPS identity proof returned unexpected output")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-thumbprint", required=True,
                        help="Independent WSLPE listener certificate SHA-1 thumbprint")
    args = parser.parse_args()
    print("KINGDOMS WSLPE | AUTHENTICATED WINRM HTTPS PROOF (READ ONLY)", flush=True)
    print("[NO VM CHANGES] No NORTH, VMware, DNS, Windows settings or shared CA writes")

    try:
        audit = tls_audit_module()
        address, certificate = checked_certificate(audit, args.expected_thumbprint)
        print(f"[PASS] WSLPE-only TLS pin, chain, SNI and SAN: {HOST} @ {address}:{PORT}")
        username, password = operator_credentials(address)
        print("[INFO] Operator credentials resolved from existing WSLPE configuration")
        authenticated_read_only_probe(address, certificate, username, password)
    except Exception as exc:
        # Avoid printing exception strings; HTTP libraries may include endpoint
        # headers, usernames or other unintended operational details.
        print(f"[BLOCKED] {type(exc).__name__} during WSLPE-only HTTPS verification")
        print("[NO VM CHANGES] Do not retry with certificate validation disabled")
        return 1
    print("[PASS] WSLPE_AUTHENTICATED_HTTPS=TRUE")
    print("[PASS] WSLPE_DOMAIN_FREE=TRUE")
    print("[NOT VERIFIED] Independent operator VLAN, learner RDP, permanent NAT guard,")
    print("               credential rotation, and guest-to-NORTH/host isolation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
