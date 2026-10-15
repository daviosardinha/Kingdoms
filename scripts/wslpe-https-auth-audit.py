#!/usr/bin/env python3
"""Authenticated, certificate-verified HTTPS/5986 WinRM probe for WSLPE only.

Read-only Windows query. The unique, running, registered WSLPE instance and
the pre-recorded HTTPS thumbprint must match before asking for credentials.
No persistent host resolver, trust-store, inventory, VMware or guest changes.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import getpass
import importlib.util
import os
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
        username = os.getenv("KINGDOMS_WSLPE_BOOTSTRAP_USER", "vagrant")
        if not username.strip():
            raise ValueError("WSLPE operator username missing")
        password = os.getenv("KINGDOMS_WSLPE_BOOTSTRAP_PASSWORD")
        if password is None:
            password = getpass.getpass("WSLPE operator WinRM password: ")
        if not password:
            raise ValueError("WSLPE operator password missing")
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
