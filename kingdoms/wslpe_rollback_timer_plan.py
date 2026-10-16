"""WSLPE-only systemd rollback timer *planning* contract.

A timer must be scheduled as a system-level unit running as the WSLPE
VMware account, not as a user-session timer. No unit is installed by
this module. The schedule is only authorized AFTER host boot-order
isolation and standalone VMX-recovery acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class TimerPreview:
    unit: str
    argv: tuple[str, ...]
    delay_seconds: int
    arm_authorized: bool = False


def make_timer_preview(*, owner: str, vmx: Path, bundle: Path, pin: str,
                       python: Path, worker: Path, unit: str,
                       delay_seconds: int = 240) -> TimerPreview:
    if (not isinstance(owner, str) or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", owner)
            or not isinstance(unit, str)
            or not re.fullmatch(r"kingdoms-wslpe-restore-[a-f0-9]{16}", unit)
            or not isinstance(delay_seconds, int) or not 180 <= delay_seconds <= 900
            or not isinstance(pin, str) or not re.fullmatch(r"[a-f0-9]{64}", pin)):
        raise ValueError("Invalid WSLPE-only host rollback timer identity")
    if not all(isinstance(p, Path) and p.is_absolute()
               for p in (vmx, bundle, python, worker)):
        raise ValueError("Timer requires exact absolute VMware owner paths")
    if vmx.name != "windows_10.vmx" or bundle.name != "recovery.json":
        raise ValueError("Timer is not targeting the native registered WSLPE recovery bundle")
    argv = (
        "sudo", "-n", "systemd-run", "--quiet", "--collect",
        "--unit", unit, f"--on-active={delay_seconds}s",
        f"--property=User={owner}",
        str(python), str(worker),
        "--bundle", str(bundle),
        "--approved-sha256", pin,
        "--restore",
    )
    return TimerPreview(unit, argv, delay_seconds)


def approve_arming(*, boot_guard_reboot_verified: bool,
                   management_return_route_verified: bool,
                   exact_workstation_vm_owner_verified: bool,
                   recovery_live_test_verified: bool,
                   host_l2_isolation_verified: bool,
                   deployment_scope: str = "learner") -> list[str]:
    """Separate trusted local engineering from untrusted learner release.

    This is a planning gate, NEVER execution authorization. Both scopes
    require actual VMware recovery and host-boot readiness; local_dev
    alone may accept a host-connected exercise interface temporarily.
    """
    if deployment_scope not in ("local_dev", "learner"):
        raise ValueError("Unknown WSLPE deployment scope")
    missing = []
    for checked, description in (
        (boot_guard_reboot_verified, "No reboot-proven WSLPE boot firewall"),
        (management_return_route_verified, "No independent management recovery"),
        (exact_workstation_vm_owner_verified, "No exact WSLPE VMX owner proof"),
        (recovery_live_test_verified, "No real VMware owner restore acceptance"),
    ):
        if type(checked) is not bool or not checked:
            missing.append(description)
    if type(host_l2_isolation_verified) is not bool:
        raise ValueError("Layer 2 acceptance must be explicitly proven or denied")
    if deployment_scope == "learner" and not host_l2_isolation_verified:
        missing.append("No guest-to-host L2 isolation proof")
    return missing
