#!/usr/bin/env python3
"""NORTH installed exercise-mode authenticated DC02 PowerShell transport.

Purpose: exercise isolation's DC02 readiness must reuse the working guest IP
/ NTLM / WinRM HTTPS endpoint, NOT a Vagrant NAT forwarded port. This module
does not modify network settings, choose a peer or change time configuration;
it executes exactly the preexisting bounded lab-mode PowerShell probe/repair.
Other labs and other NORTH guests retain their existing transport.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys

HOST = "10.4.10.11"
MACHINE = "GOAD-DC02"
SCRIPT_LIMIT = 5000  # encoded PowerShell command stays within Windows limit


def validate_provider(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise ValueError("NORTH provider path must be an existing absolute directory")
    if not re.fullmatch(r"[0-9a-f]{6}-north-vmware", path.parent.name):
        raise ValueError("Refusing non-NORTH instance")
    if path.name != "provider" or path.parent.parent.name != "workspace":
        raise ValueError("Refusing a non-instance provider")
    id_path = path / ".vagrant" / "machines" / MACHINE / "vmware_desktop" / "id"
    if not id_path.is_file() or id_path.is_symlink():
        raise ValueError("Installed NORTH DC02 registration missing")
    vmx = Path(id_path.read_text(encoding="utf-8").strip())
    if not vmx.is_absolute() or not vmx.is_file() or vmx.is_symlink():
        raise ValueError("Installed NORTH DC02 VMX missing")
    if os.path.commonpath((str(path.resolve()), str(vmx.resolve()))) != str(path.resolve()):
        raise ValueError("VMX is not owned by the selected NORTH instance")
    return path


def run(script: str, *, timeout: int, machine: str, provider: str):
    if machine != MACHINE:
        raise ValueError("Only the NORTH child-domain controller is allowed")
    if type(timeout) is not int or not 1 <= timeout <= 90:
        raise ValueError("Invalid bounded WinRM timeout")
    validate_provider(provider)
    if not script.strip() or len(script.encode("utf-8")) > SCRIPT_LIMIT:
        raise ValueError("Refusing missing/oversized PowerShell payload")

    # Imported after validation so tests and read-only diagnosis do not require
    # Windows packages until an authenticated WinRM probe is genuinely needed.
    import winrm

    # The exercise controller gives NORTH/DC02 a 75-second bounded probe.
    # Reuse the operation/read budgets proven by installed startup instead of
    # timing out PowerShell/DC Locator after only 5/10 seconds. Preserve a
    # shorter pair for any final probe clipped by the remaining global budget.
    operation_timeout = 30 if timeout >= 60 else 5
    read_timeout = 45 if timeout >= 60 else 10
    session = winrm.Session(
        f"https://{HOST}:5986/wsman",
        auth=("vagrant", "vagrant"),
        transport="ntlm",
        server_cert_validation="ignore",
        operation_timeout_sec=operation_timeout,
        read_timeout_sec=read_timeout,
    )
    result = session.run_ps(script)
    stdout = result.std_out.decode("utf-8", errors="replace")
    stderr = result.std_err.decode("utf-8", errors="replace")
    if stdout:
        sys.stdout.write(stdout)
    if stderr:
        sys.stderr.write(stderr)
    if result.status_code:
        raise RuntimeError(f"Authenticated DC02 PowerShell returned {result.status_code}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--machine", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--timeout", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        run(sys.stdin.read(), timeout=args.timeout,
            machine=args.machine, provider=args.provider)
    except (ValueError, RuntimeError, OSError, ImportError, Exception) as exc:
        # No credentials printed; caller's remaining-readiness budget controls
        # retry policy. Exit nonzero without silently switching to NAT forwarding.
        print(
            f"NORTH_DIRECT_WINRM_ERROR machine={args.machine} "
            f"type={type(exc).__name__} detail={exc}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
