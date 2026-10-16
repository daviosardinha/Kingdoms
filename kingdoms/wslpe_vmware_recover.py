"""WSLPE-only VMware recovery state machine. NEVER invoked automatically.

Runs no operation unless caller explicitly sets execute=True and supplies
a checksum-bound WSLPE RecoveryPlan plus the independently resolved exact
registered VMX. NORTH VMX paths are not accepted by upstream plan creation.
"""
from __future__ import annotations
from pathlib import Path
import os
import re
import subprocess
import time

from kingdoms.wslpe_exact_restore import (
    RecoveryPlan, inspect_recovery_state, atomic_restore_offline,
)


def parse_inventory(output: str, expected: Path) -> bool:
    lines = [x.strip() for x in output.splitlines() if x.strip()]
    if not lines or not re.fullmatch(r"Total running VMs:\s*\d+", lines[0]):
        raise ValueError("Untrusted VMware inventory")
    count = int(lines[0].split(":", 1)[1].strip())
    if count != len(lines) - 1 or len(set(lines[1:])) != count:
        raise ValueError("VMware inventory count/paths inconsistent")
    return sum(1 for name in lines[1:]
               if Path(name).resolve() == expected.resolve()) == 1


def vmrun_list(vmrun: str, execute=subprocess.run) -> str:
    result = execute([vmrun, "-T", "ws", "list"], capture_output=True,
                     text=True, timeout=30, check=False)
    if result.returncode:
        raise ValueError("Owner VMware inventory failed")
    return result.stdout


def wait_power(vmx: Path, vmrun: str, want_running: bool, *,
               execute=subprocess.run, pause=time.sleep, tries=60) -> None:
    for _ in range(tries):
        if parse_inventory(vmrun_list(vmrun, execute), vmx) is want_running:
            return
        pause(2)
    raise ValueError("WSLPE exact VM power-state wait timed out")


def owner_recover(plan: RecoveryPlan, registered: Path, vmrun: str, *,
                  execute=False, runner=subprocess.run, pause=time.sleep) -> str:
    """No force-stop, no guest credentials, no network change.

    The only permitted mutation is WSLPE's exact offline candidate to
    original bytes, plus its optional soft stop/start. Fails closed if
    VMware has rewritten the VMX outside the approved candidate.
    """
    if not execute:
        raise ValueError("Live WSLPE rollback is not authorized")
    if (plan.vmx.is_symlink() or registered.is_symlink()
            or plan.vmx.resolve(strict=True) != registered.resolve(strict=True)):
        raise ValueError("Registered WSLPE VMX changed")
    if (plan.owner_uid <= 0 or os.geteuid() != plan.owner_uid
            or plan.vmx.stat().st_uid != plan.owner_uid):
        raise ValueError("WSLPE VMware owner changed; do not stop machine")
    was_running = parse_inventory(vmrun_list(vmrun, runner), registered)
    current = plan.vmx.read_bytes()
    if current == plan.original:
        return "ALREADY_ORIGINAL"
    # Reject metadata drift *before* issuing vmrun stop.
    if current != plan.candidate:
        raise ValueError("VMX differs from the exact approved NAT candidate")
    if was_running:
        stop = runner([vmrun, "-T", "ws", "stop", str(registered), "soft"],
                      capture_output=True, text=True, check=False, timeout=45)
        if stop.returncode:
            raise ValueError("WSLPE soft stop failed; no forced poweroff")
        wait_power(registered, vmrun, False, execute=runner, pause=pause)
    else:
        wait_power(registered, vmrun, False, execute=runner, pause=pause, tries=2)
    # Power-off was confirmed; rechecks VMX hashes before atomic restore.
    restored = atomic_restore_offline(plan, registered=registered,
                                      still_running=False)
    if was_running:
        start = runner([vmrun, "-T", "ws", "start", str(registered), "nogui"],
                       capture_output=True, text=True, check=False, timeout=45)
        if start.returncode:
            raise ValueError("Original VMX restored; VMware restart failed")
        wait_power(registered, vmrun, True, execute=runner, pause=pause)
    return restored
