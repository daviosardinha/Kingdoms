#!/usr/bin/env python3
"""WSLPE-only controlled TCP packet-path acceptance through authenticated HTTPS.

Default --baseline: one temporary host-only TCP listener and a read-only,
local Windows TCP connect proof. --execute (explicit confirmation) additionally
runs a previously vetted 180-second WSLPE-only nft pilot, checks that the
guest->host path is dropped, waits for independent rollback, and rechecks
positive connectivity. NEVER disconnects NAT, contacts NORTH or changes a VM.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import ssl
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kingdoms.wslpe_packet_path import (
    PORT, ControlledHostListener, parse_windows_probe,
    validate_target, windows_tcp_probe,
)

PILOT_PATH = ROOT / "scripts/wslpe-p1c-host-filter-pilot.py"
AUTH_PATH = ROOT / "scripts/wslpe-https-auth-audit.py"
EXPECTED_SHA1 = "C773EC26D02940F559FE715B83628FEDAE2AA92D"
CONFIRM = "PROVE WSLPE PACKET ISOLATION"
PILOT_SECONDS = 180


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("Missing WSLPE source module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def authenticated_guest(auth, address: str, der: bytes):
    """Process-scoped Windows management. Never import a global CA or log creds."""
    import winrm
    username, password = auth.operator_credentials(address)
    with tempfile.TemporaryDirectory(prefix="kingdoms-wslpe-packet-") as folder:
        anchor = Path(folder) / "pinned-wslpe-leaf.pem"
        anchor.write_text(ssl.DER_cert_to_PEM_cert(der), encoding="ascii")
        anchor.chmod(0o600)
        session = winrm.Session(
            "https://WSLPE-WS01:5986/wsman",
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
            http.trust_env = False
            http.proxies = {}
            if http.verify != str(anchor):
                raise ValueError("WinRM did not retain the pinned certificate anchor")
            yield lambda host: probe_guest(auth, session, address, host)
        finally:
            transport.close_session()


def probe_guest(auth, session, address: str, host: str) -> bool:
    # Only a single exact WSLPE-WS01 HTTPS destination can resolve in-process.
    with auth.scoped_wslpe_resolution(address):
        result = session.run_ps(windows_tcp_probe(host, PORT))
    return parse_windows_probe(result.status_code, result.std_out)


def verified_guest_connection(witness, probe, host: str) -> None:
    count = witness.count()
    if not probe(host):
        raise ValueError("Positive control: WSLPE guest could not reach owned host listener")
    for _ in range(20):
        if witness.count() > count:
            print("[PASS] WSLPE_GUEST_HOST_TCP_OPEN=TRUE", flush=True)
            print("[PASS] Listener saw a connection from exact WSLPE guest IPv4")
            return
        time.sleep(0.05)
    raise ValueError("Guest TCP positive result lacks matching host listener evidence")


def verified_guest_deny(witness, probe, host: str) -> None:
    before = witness.count()
    if probe(host):
        raise ValueError("WSLPE guest TCP connection OPEN despite active host filter")
    time.sleep(0.25)
    if witness.count() != before:
        raise ValueError("WSLPE owned host listener accepted guest during deny phase")
    print("[PASS] WSLPE_GUEST_HOST_TCP_BLOCKED_WHILE_FILTERED=TRUE", flush=True)


def wait_for_table_removal(pilot, seconds: int, started: float) -> None:
    """Give the host-side timer its full window independently of SSH."""
    remaining = max(0, seconds + 18 - (time.monotonic() - started))
    print(f"[INFO] Awaiting independent WSLPE table removal (~{int(remaining)}s)")
    if remaining:
        time.sleep(remaining)
    if pilot.scoped_objects(pilot.nft_json("ruleset")):
        raise ValueError("WSLPE nft table remains after bounded host timer window")
    print("[PASS] WSLPE_FILTER_TABLE_ABSENT_AFTER_TIMER_WINDOW=TRUE")


def execute_phases(pilot, witness, probe, host: str, vmnet: str) -> None:
    """All 3 proof phases while one exact host-only listener is alive."""
    print("===== BASELINE: POSITIVE GUEST -> OWNED KALI LISTENER =====", flush=True)
    verified_guest_connection(witness, probe, host)

    print("===== TEMPORARY FILTER: EXPECT GUEST -> KALI DENIAL =====", flush=True)
    # pilot.pilot rechecks unique VMX, SSH route, short timer smoke, HTTPS,
    # dedicated nft ownership and rollback timer before applying anything.
    started = time.monotonic()
    pilot.pilot(PILOT_SECONDS, remote=True)
    if not pilot.installed_exact_policy(vmnet):
        raise ValueError("WSLPE filter was not installed with expected identity")
    verified_guest_deny(witness, probe, host)

    print("===== AUTOMATIC ROLLBACK: REPEAT POSITIVE CONTROL =====", flush=True)
    wait_for_table_removal(pilot, PILOT_SECONDS, started)
    verified_guest_connection(witness, probe, host)
    if not pilot.check_https():
        raise ValueError("Authenticated WSLPE HTTPS failed after rollback")
    print("[PASS] WSLPE_HOST_FILTER_PACKET_PROOF_AND_ROLLBACK=TRUE", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--baseline", action="store_true",
                       help="read-only packet connectivity baseline (default)")
    modes.add_argument("--execute", action="store_true",
                       help="explicit, temporary nft pilot; needs confirmation")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    print("KINGDOMS WSLPE | P1-C GUEST-TO-HOST PACKET PATH ACCEPTANCE", flush=True)
    print("[SCOPE] WSLPE->dedicated Kali listener only; no NORTH IP traffic")
    print("[SCOPE] No VMware, NAT, routing, domain or Windows settings modified")
    pilot = None
    applied = False
    try:
        if args.execute:
            if args.confirm != CONFIRM:
                raise ValueError("Exact WSLPE packet proof confirmation required")
            if not os.environ.get("SSH_CONNECTION"):
                raise ValueError("Remote packet proof requires guarded SSH route")
        elif args.confirm:
            raise ValueError("Confirmation requires --execute")

        pilot = load(PILOT_PATH, "wslpe_packet_policy")
        auth = load(AUTH_PATH, "wslpe_packet_https_auth")
        policy, vmnet, host, guest = pilot.local_preflight()
        network = str(__import__("ipaddress").ip_interface(f"{host}/24").network)
        validate_target(host, guest, network, PORT)
        print(f"[PASS] WSLPE-only native target={guest} listener={host}:{PORT}")
        if os.environ.get("SSH_CONNECTION"):
            # Timer smoke creates an ephemeral /run marker only.
            pilot.remote_preflight(vmnet, host)
        audit = auth.tls_audit_module()
        address, der = auth.checked_certificate(audit, EXPECTED_SHA1)
        if address != guest:
            raise ValueError("Verified WinRM management IP differs from WSLPE instance")
        with ControlledHostListener(host, guest) as witness:
            with authenticated_guest(auth, address, der) as probe:
                if args.execute:
                    # Once started, cleanup below fails closed if any phase aborts.
                    # This flag is set before invocation because pilot may have
                    # installed the table before raising an error.
                    applied = True
                    execute_phases(pilot, witness, probe, host, vmnet)
                else:
                    verified_guest_connection(witness, probe, host)
                    print("[PASS] WSLPE_PACKET_BASELINE=TRUE")
                    print("[NO FIREWALL CHANGES] Owned listener closed after this audit")
    except Exception as exc:
        # Do not print library error contents: they could contain credentials.
        print(f"[BLOCKED] {type(exc).__name__}; WSLPE-only acceptance incomplete")
        if applied and pilot is not None:
            try:
                if pilot.scoped_objects(pilot.nft_json("ruleset")):
                    pilot.rollback_now()
                    print("[PASS] Emergency WSLPE-only table rollback completed")
                else:
                    print("[PASS] WSLPE pilot table already absent")
            except Exception:
                print("[WARNING] Scoped rollback not verified; independent host timer must run")
                print("[NEXT] Wait 210s, then use wslpe-remote-operator.sh --verify")
        return 1

    print("[NOT VERIFIED] NAT disconnection, guest L2/ARP and IPv6 denial,")
    print("               host/hypervisor service isolation and learner SYSTEM")
    print("[RELEASE BLOCKED] WSLPE stays PROVIDED; NORTH was not contacted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
