#!/usr/bin/env python3
"""Recover only the original PURPLE WS01 evaluation via authenticated VMware Tools.

Unlike Vagrant's shell provisioner, vmrun guest operations do not need WinRM.
Windows evaluation is checked/rearmed using PURPLE's existing PowerShell source,
then WS01 alone is rebooted and checked. No changes to DC01, NORTH, or VMnets.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ad/PURPLE/providers/vmware/activate-ws01.ps1"
MACHINE = "PURPLE-WS01"
GUEST_SCRIPT = r"C:\Windows\Temp\purple-ws01-eval-rearm.ps1"
GUEST_RUNNER = r"C:\Windows\Temp\purple-ws01-eval-runner.ps1"
GUEST_OUTPUT = r"C:\Windows\Temp\purple-ws01-eval-result.txt"
POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
GUEST_USER = "vagrant"
GUEST_PASSWORD = "vagrant"  # Original Mayfly box test credential, not an activation key.


class PurpleEvaluationError(RuntimeError):
    pass


def checked(args: list[str], *, timeout=75) -> str:
    try:
        completed = subprocess.run(args, check=False, timeout=timeout,
                                   capture_output=True, text=True)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PurpleEvaluationError("Command unavailable or timed out: " + args[0]) from exc
    if completed.returncode != 0:
        raise PurpleEvaluationError(
            "Command failed (" + args[0] + "): "
            + (completed.stderr or completed.stdout).strip()[-650:]
        )
    return completed.stdout


def owned_vmx(provider_dir: str) -> Path:
    provider = Path(provider_dir).expanduser()
    if (not provider.is_absolute() or provider.is_symlink() or
            provider.name != "provider" or
            not re.fullmatch(r"[a-f0-9]{6}-purple-vmware", provider.parent.name)):
        raise PurpleEvaluationError("Expected exact installed PURPLE provider directory")
    provider = provider.resolve(strict=True)
    if not (provider / "Vagrantfile").is_file():
        raise PurpleEvaluationError("PURPLE generated Vagrantfile not found")
    ident = provider / ".vagrant/machines" / MACHINE / "vmware_desktop/id"
    if not ident.is_file() or ident.is_symlink():
        raise PurpleEvaluationError("WS01 VMware ID not found")
    vmx = Path(ident.read_text(encoding="utf-8").strip())
    owned_root = ident.parent.resolve(strict=True)
    if (not vmx.is_absolute() or not vmx.is_file() or vmx.is_symlink() or
            vmx.resolve(strict=True) != vmx or
            not vmx.is_relative_to(owned_root)):
        raise PurpleEvaluationError("WS01 VMX does not belong to selected PURPLE instance")
    active = checked(["vmrun", "-T", "ws", "list"], timeout=30).splitlines()[1:]
    if active.count(str(vmx)) != 1:
        raise PurpleEvaluationError("Selected WS01 is not uniquely running; refusing guest changes")
    return vmx


def guest_command(vmx: Path, *args: str, timeout=120) -> str:
    return checked(["vmrun", "-T", "ws", "-gu", GUEST_USER,
                    "-gp", GUEST_PASSWORD, *args[:1], str(vmx), *args[1:]],
                   timeout=timeout)


def runner(verify: bool) -> str:
    arg = "-Verify" if verify else ""
    return (r"""
$ErrorActionPreference = 'Stop'
$log = 'C:\Windows\Temp\purple-ws01-eval-result.txt'
Remove-Item -LiteralPath $log -Force -ErrorAction SilentlyContinue
try {
    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
    if ([int]$os.ProductType -ne 1) { throw 'Expected a Windows client, not a server' }
    $ips = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
        Where-Object IPAddress -eq '172.28.233.31')
    if ($ips.Count -ne 1) { throw 'Selected guest does not own the expected PURPLE WS01 address' }
    & 'C:\Windows\Temp\purple-ws01-eval-rearm.ps1' """ + arg + r""" 2>&1 |
        Out-File -LiteralPath $log -Encoding ascii
    if (-not $?) { throw 'Windows evaluation script returned an error' }
    Add-Content -LiteralPath $log -Value 'PURPLE_VMWARE_GUEST_OPERATION=PASS'
} catch {
    Add-Content -LiteralPath $log -Value ("PURPLE_VMWARE_GUEST_OPERATION=FAIL " + $_.Exception.Message)
    exit 1
}
""").lstrip()


def vmrun_phase(vmx: Path, source: Path, runner_path: Path, output_path: Path, verify: bool):
    runner_path.write_text(runner(verify), encoding="utf-8")
    guest_command(vmx, "copyFileFromHostToGuest", str(source), GUEST_SCRIPT)
    guest_command(vmx, "copyFileFromHostToGuest", str(runner_path), GUEST_RUNNER)
    # A shell command is fully executed in the guest, independent of WinRM.
    guest_command(vmx, "runProgramInGuest", POWERSHELL,
                  "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                  "-File", GUEST_RUNNER, timeout=180)
    guest_command(vmx, "copyFileFromGuestToHost", GUEST_OUTPUT, str(output_path))
    output = output_path.read_text(encoding="utf-8", errors="replace")
    print(output.strip(), flush=True)
    if "PURPLE_VMWARE_GUEST_OPERATION=PASS" not in output:
        raise PurpleEvaluationError("In-guest evaluation phase did not report success")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-dir", required=True)
    args = parser.parse_args()
    vmx = owned_vmx(args.provider_dir)
    if not SOURCE.is_file():
        raise PurpleEvaluationError("PURPLE evaluation PowerShell source is missing")
    print("[INFO] Owned PURPLE-WS01 identified: " + str(vmx), flush=True)
    if checked(["vmrun", "-T", "ws", "checkToolsState", str(vmx)]).strip().lower() != "running":
        raise PurpleEvaluationError("VMware Tools is not running on PURPLE-WS01")
    # VMware Tools authentication already works in this lab: avoid Vagrant/WinRM.
    guest_command(vmx, "listProcessesInGuest", timeout=30)
    with tempfile.TemporaryDirectory(prefix="purple-ws01-eval-") as temporary:
        base = Path(temporary)
        runner_path, result = base / "runner.ps1", base / "result.txt"
        print("[INFO] Evaluating Windows grace period through VMware Tools", flush=True)
        output = vmrun_phase(vmx, SOURCE, runner_path, result, verify=False)
        if "PURPLE_WS01_EVAL=REARMED" in output:
            print("[INFO] Evaluation rearmed. Rebooting only PURPLE-WS01.", flush=True)
            checked(["vmrun", "-T", "ws", "reset", str(vmx), "soft"], timeout=120)
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                try:
                    if (checked(["vmrun", "-T", "ws", "checkToolsState", str(vmx)],
                                timeout=15).strip().lower() == "running"):
                        guest_command(vmx, "listProcessesInGuest", timeout=20)
                        break
                except PurpleEvaluationError:
                    pass
                time.sleep(5)
            else:
                raise PurpleEvaluationError("WS01 VMware Tools did not recover after reboot")
        else:
            print("[INFO] No Windows evaluation rearm was necessary", flush=True)
        result.unlink(missing_ok=True)
        print("[INFO] Verifying Windows evaluation state", flush=True)
        vmrun_phase(vmx, SOURCE, runner_path, result, verify=True)
    print("[PASS] PURPLE_WS01_EVAL_MAINTENANCE_COMPLETE", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, PurpleEvaluationError) as exc:
        print("[BLOCKED] PURPLE-WS01 evaluation maintenance: " + str(exc), file=sys.stderr)
        sys.exit(1)
