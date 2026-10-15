#!/usr/bin/env python3
"""Investigate the WSLPE WinRM host-port binding, without changing anything.

Designed for the existing native WSLPE instance after Stage 2 reports a
wildcard-bound WinRM forward. Does not run Vagrant up/reload, touch VMware,
read credentials, restart networking, or alter instance/guest state.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "scripts/wslpe-stage2-inspect.py"
SPEC = importlib.util.spec_from_file_location("wslpe_stage2_inspector", SRC)
if SPEC is None or SPEC.loader is None:
    raise SystemExit("[BLOCKED] Stage 2 source not available")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def matching_listeners(text: str, port: int) -> list[str]:
    matches = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0] != "LISTEN":
            continue
        endpoint = parts[3]
        try:
            bound_port = int(endpoint.rsplit(":", 1)[1])
        except (ValueError, IndexError):
            continue
        if bound_port == port:
            matches.append(line.strip())
    return matches


def get_listeners(port: int) -> list[str]:
    try:
        result = subprocess.run(
            ["ss", "-H", "-ltnp"], capture_output=True, text=True,
            timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"Unable to inspect forwarded port listener: {type(exc).__name__}") from exc
    if result.returncode != 0:
        raise ValueError("ss listener enumeration failed")
    return matching_listeners(result.stdout, port)


def vagrant_winrm_declarations(source: str) -> list[str]:
    """Show only network forwarding settings; never print WinRM credentials."""
    evidence = []
    for i, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if (
            ("target.vm.network" in stripped or "config.vm.network" in stripped)
            and ("forwarded_port" in stripped or "winrm" in stripped)
        ):
            evidence.append(f"L{i}: {stripped}")
        if ("host_ip:" in stripped or "guest: 5985" in stripped) and (
            "target.vm.network" in stripped or "config.vm.network" in stripped
        ):
            evidence.append(f"L{i}: {stripped}")
    return list(dict.fromkeys(evidence))


def main() -> int:
    print("KINGDOMS WSLPE | READ-ONLY WINRM FORWARDING DIAGNOSTIC", flush=True)
    print("[NO CHANGES] No VM, Vagrant, firewall or Windows modifications")
    try:
        instance, info = MOD.find_instance(MOD.WORKSPACE)
        port = MOD.forwarded_winrm_port(instance)
        vmx = MOD.locate_registered_vm(instance)
        provider_file = instance / "provider" / "Vagrantfile"
        if provider_file.is_symlink() or not provider_file.is_file():
            raise ValueError("Native WSLPE instance Vagrantfile is missing or symlinked")
        source = provider_file.read_text(encoding="utf-8")
        listeners = get_listeners(port)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"[BLOCKED] {exc}")
        return 1

    print(f"[PASS] Native lab: {info['lab']} | instance={info['id']}")
    print(f"[PASS] Registered running VMX: {vmx.name}")
    print(f"[INFO] Guest WinRM TCP/5985 -> host TCP/{port} (from Vagrant)")
    print("[INFO] Actual host socket listeners:")
    for line in listeners:
        print("  " + line)
    if not listeners:
        print("  [BLOCKED] No listener reported for Vagrant host port")
    print("[INFO] Explicit forwarding lines in rendered instance Vagrantfile:")
    settings = vagrant_winrm_declarations(source)
    for line in settings:
        print("  " + line)
    if not settings:
        print("  (no explicit WinRM override; Vagrant communicator/provider defaults apply)")

    # Inspect the local endpoint, never the remote peer address column.
    nonloopback = []
    for line in listeners:
        host = line.split()[3].rsplit(":", 1)[0].strip("[]")
        if host not in ("127.0.0.1", "::1"):
            nonloopback.append(host)
    if nonloopback:
        print("[FINDING] WinRM forwarding listener is not restricted to loopback")
        print("[INFO] Non-loopback bind addresses: " + ", ".join(sorted(set(nonloopback))))
        print("[NEXT] Determine whether VMware NAT, Vagrant, or another process owns")
        print("       the listener before any WSLPE-only remediation")
        return 1
    if not listeners:
        return 1
    print("[INFO] WinRM forwarding listener appears loopback-only at this time")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
