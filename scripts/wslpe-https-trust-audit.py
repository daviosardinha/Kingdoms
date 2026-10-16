#!/usr/bin/env python3
"""Read-only WSLPE WinRM HTTPS certificate pin and hostname verification.

Only the unique registered, running WSLPE-WS01 is contacted. This probe sends
NO HTTP requests or authentication credentials; it does not change guest,
VMware, nftables, DNS, trust stores, or any other machine.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
from pathlib import Path
import re
import socket
import ssl
import subprocess


ROOT = Path(__file__).resolve().parents[1]
STAGE2 = ROOT / "scripts/wslpe-stage2-inspect.py"
GUEST = "WSLPE-WS01"
PORT = 5986
TIMEOUT = 6


def expected_fingerprint(value: str) -> str:
    """Windows uses a SHA-1 hex thumbprint for the HTTPS listener binding."""
    cleaned = value.strip().replace(":", "").upper()
    if not re.fullmatch(r"[A-F0-9]{40}", cleaned) or cleaned == "0" * 40:
        raise ValueError("Expected WSLPE certificate thumbprint must be 40 hex digits")
    return cleaned


def cert_fingerprint(der: bytes) -> str:
    if not der:
        raise ValueError("TLS peer provided no leaf certificate")
    return hashlib.sha1(der).hexdigest().upper()


def require_dns_san(cert: dict, hostname: str = GUEST) -> None:
    """Never silently rely on legacy CN-only verification."""
    names = cert.get("subjectAltName", ())
    if not isinstance(names, (tuple, list)):
        raise ValueError("Verified certificate lacks DNS Subject Alternative Names")
    dns_names = [value for kind, value in names
                 if kind == "DNS" and isinstance(value, str)]
    if hostname.casefold() not in {name.casefold() for name in dns_names}:
        raise ValueError(
            "Verified HTTPS certificate lacks the exact WSLPE hostname DNS SAN"
        )


def registered_wslpe_address() -> str:
    """Reuse the native instance, status, VMX and NORTH-exclusion gate."""
    spec = importlib.util.spec_from_file_location("wslpe_https_stage2", STAGE2)
    if spec is None or spec.loader is None:
        raise ValueError("Native WSLPE inspector missing")
    stage2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stage2)
    instance, metadata = stage2.find_instance(stage2.WORKSPACE)
    stage2.locate_registered_vm(instance)
    prefix = metadata["ip_range"]  # Validated /24 and NORTH exclusion in stage2.
    address = f"{prefix}.31"
    if address != str(socket.gethostbyname(address)):
        raise ValueError("Invalid WSLPE private IPv4 endpoint")
    return address


def read_untrusted_tls_leaf(address: str) -> bytes:
    """Discovery only; don't treat this first connection as authenticated."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    with socket.create_connection((address, PORT), timeout=TIMEOUT) as tcp:
        with context.wrap_socket(tcp, server_hostname=GUEST) as tls:
            tls.settimeout(TIMEOUT)
            return tls.getpeercert(binary_form=True)


def verify_pinned_tls(address: str, der: bytes, fingerprint: str) -> dict:
    """Second handshake must use exact certificate as the only trust anchor.

    The Windows evaluation box may have a self-signed HTTPS certificate.
    This is direct *certificate pin* trust, not external enterprise PKI.
    """
    pem = ssl.DER_cert_to_PEM_cert(der)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    context.load_verify_locations(cadata=pem)
    with socket.create_connection((address, PORT), timeout=TIMEOUT) as tcp:
        with context.wrap_socket(tcp, server_hostname=GUEST) as tls:
            tls.settimeout(TIMEOUT)
            verified_der = tls.getpeercert(binary_form=True)
            if cert_fingerprint(verified_der) != fingerprint:
                raise ValueError("Verified TLS certificate changed between handshakes")
            certificate = tls.getpeercert()
            require_dns_san(certificate, GUEST)
            return {
                "tls_version": tls.version(),
                "cipher": tls.cipher()[0] if tls.cipher() else "(unknown)",
                "sha256": hashlib.sha256(verified_der).hexdigest().upper(),
            }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expected-thumbprint", required=True,
        help="40-digit SHA1 thumbprint from separate WSLPE guest audit; NEVER an arbitrary remote fingerprint",
    )
    args = parser.parse_args()
    print("KINGDOMS WSLPE | PINNED HTTPS TRANSPORT AUDIT (READ ONLY)", flush=True)
    print("[NO CHANGES] No credentials, VM lifecycle, host DNS or trust-store writes")
    try:
        fingerprint = expected_fingerprint(args.expected_thumbprint)
        address = registered_wslpe_address()
        print(f"[INFO] Exact registered WSLPE: {GUEST} | {address}:{PORT}")
        discovered_der = read_untrusted_tls_leaf(address)
        observed = cert_fingerprint(discovered_der)
        print(f"[INFO] Observed HTTPS certificate SHA1: {observed}")
        if observed != fingerprint:
            raise ValueError("HTTPS peer certificate does not match WSLPE audit thumbprint")
        print("[PASS] WinRM HTTPS leaf matches pre-recorded WSLPE certificate pin")
        details = verify_pinned_tls(address, discovered_der, fingerprint)
        print(f"[PASS] TLS {details['tls_version']} validated against pinned leaf and DNS SAN {GUEST}")
        print(f"[INFO] Verified certificate SHA256: {details['sha256']}")
    except (ValueError, OSError, ssl.SSLError, subprocess.TimeoutExpired) as exc:
        print(f"[BLOCKED] {type(exc).__name__}: {exc}")
        print("[NO CHANGES] No NORTH, WSLPE, host, VMware or firewall modification")
        return 1
    print("[NOT VERIFIED] Authenticated WinRM HTTPS, independent operator-only route,")
    print("               persistent NAT guard, learner RDP, and guest isolation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
