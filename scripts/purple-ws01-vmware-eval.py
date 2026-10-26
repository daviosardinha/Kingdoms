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


def runner(verify: bool, probe: bool = False, fresh_install: bool = False) -> str:
    ip_gate = (r"""
if ($ips.Count -ne 1) {
    if ($ips.Count -ne 0) { throw 'Unexpected PURPLE WS01 address state' }
    $active = @(Get-NetAdapter -ErrorAction Stop | Where-Object Status -eq 'Up')
    if ($active.Count -lt 2) { throw 'Fresh WS01 does not yet have both VMware interfaces' }
    Add-Content -LiteralPath $log -Value 'PURPLE_WS01_IP=PENDING_VAGRANT_SETUP'
}
""" if fresh_install else r"""
if ($ips.Count -ne 1) { throw 'Selected guest does not own expected PURPLE WS01 address' }
""")
    if probe:
        return r"""
$ErrorActionPreference = 'Stop'
$log = 'C:\Windows\Temp\purple-ws01-eval-result.txt'
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
if ([int]$os.ProductType -ne 1) { throw 'Expected Windows client' }
$ips = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
    Where-Object IPAddress -eq '172.28.233.31')
'PURPLE_VMWARE_BOOT=' + $os.LastBootUpTime.ToUniversalTime().ToString('o') |
    Out-File -LiteralPath $log -Encoding ascii
""" + ip_gate + r"""
Add-Content -LiteralPath $log -Value 'PURPLE_VMWARE_GUEST_OPERATION=PASS'
"""
    arg = "-Verify" if verify else ""
    return (r"""
$ErrorActionPreference = 'Stop'
$log = 'C:\Windows\Temp\purple-ws01-eval-result.txt'
Remove-Item -LiteralPath $log -Force -ErrorAction SilentlyContinue
try {
    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
    if ([int]$os.ProductType -ne 1) { throw 'Expected a Windows client, not a server' }
    $bootTime = $os.LastBootUpTime.ToUniversalTime().ToString('o')
    Add-Content -LiteralPath $log -Value ("PURPLE_VMWARE_BOOT=" + $bootTime)
    $ips = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
        Where-Object IPAddress -eq '172.28.233.31')
""" + ip_gate + r"""
    & 'C:\Windows\Temp\purple-ws01-eval-rearm.ps1' """ + arg + r""" 2>&1 |
        Out-File -LiteralPath $log -Encoding ascii -Append
    if (-not $?) { throw 'Windows evaluation script returned an error' }
    Add-Content -LiteralPath $log -Value 'PURPLE_VMWARE_GUEST_OPERATION=PASS'
} catch {
    Add-Content -LiteralPath $log -Value ("PURPLE_VMWARE_GUEST_OPERATION=FAIL " + $_.Exception.Message)
    exit 1
}
""").lstrip()


def vmrun_phase(vmx: Path, source: Path, runner_path: Path, output_path: Path, verify: bool, probe: bool = False,
                fresh_install: bool = False):
    runner_path.write_text(runner(verify, probe=probe,
                                  fresh_install=fresh_install), encoding="utf-8")
    guest_command(vmx, "copyFileFromHostToGuest", str(source), GUEST_SCRIPT)
    guest_command(vmx, "copyFileFromHostToGuest", str(runner_path), GUEST_RUNNER)
    # A shell command is fully executed in the guest, independent of WinRM.
    command_error = None
    try:
        guest_command(vmx, "runProgramInGuest", POWERSHELL,
                      "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                      "-File", GUEST_RUNNER, timeout=180)
    except PurpleEvaluationError as exc:
        command_error = exc
    try:
        guest_command(vmx, "copyFileFromGuestToHost", GUEST_OUTPUT, str(output_path))
        output = output_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, PurpleEvaluationError) as exc:
        if command_error is not None:
            raise command_error from exc
        raise PurpleEvaluationError("Cannot retrieve in-guest evaluation output") from exc
    print(output.strip(), flush=True)
    if command_error is not None:
        raise PurpleEvaluationError("Guest PowerShell failed: " + output[-500:]) from command_error
    if "PURPLE_VMWARE_GUEST_OPERATION=PASS" not in output:
        raise PurpleEvaluationError("In-guest evaluation phase did not report success")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-dir", required=True)
    parser.add_argument(
        "--fresh-install", action="store_true",
        help="Permit the lab IP to be pending during first boot, before Vagrant fix_ip.ps1",
    )
    parser.add_argument(
        "--resume-pending-rearm", action="store_true",
        help="Reboot and verify an already successful WS01 /rearm without running /rearm again",
    )
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
        if args.resume_pending_rearm:
            # The prior run wrote these markers after slmgr /rearm returned
            # success, but crashed before reboot because it overwrote the
            # boot-time marker. Require the on-guest result, never guess.
            guest_command(vmx, "copyFileFromGuestToHost", GUEST_OUTPUT, str(result))
            pending = result.read_text(encoding="utf-8", errors="replace")
            if (not re.search(r"(?m)^PURPLE_WS01_EVAL=REARMED\s*$", pending) or
                    not re.search(r"(?m)^PURPLE_VMWARE_GUEST_OPERATION=PASS\s*$", pending)):
                raise PurpleEvaluationError(
                    "No proven successful pending rearm in the registered guest; refusing reboot")
            print("[INFO] Previously successful /rearm confirmed from guest log", flush=True)
            result.unlink()
            before = vmrun_phase(vmx, SOURCE, runner_path, result,
                                 verify=False, probe=True,
                                 fresh_install=args.fresh_install)
            prior = re.search(r"(?m)^PURPLE_VMWARE_BOOT=(.+)$", before)
        else:
            print("[INFO] Evaluating Windows grace period through VMware Tools", flush=True)
            output = vmrun_phase(vmx, SOURCE, runner_path, result, verify=False,
                                 fresh_install=args.fresh_install)
            prior = re.search(r"(?m)^PURPLE_VMWARE_BOOT=(.+)$", output)
        if args.resume_pending_rearm or "PURPLE_WS01_EVAL=REARMED" in output:
            if not prior:
                raise PurpleEvaluationError("Cannot prove WS01 boot identity before rearm reboot")
            print("[INFO] Evaluation rearmed. Rebooting only PURPLE-WS01.", flush=True)
            checked(["vmrun", "-T", "ws", "reset", str(vmx), "soft"], timeout=120)
            deadline = time.monotonic() + 300
            time.sleep(15)
            while time.monotonic() < deadline:
                try:
                    if (checked(["vmrun", "-T", "ws", "checkToolsState", str(vmx)],
                                timeout=15).strip().lower() != "running"):
                        time.sleep(5)
                        continue
                    guest_command(vmx, "listProcessesInGuest", timeout=20)
                    result.unlink(missing_ok=True)
                    verified = vmrun_phase(vmx, SOURCE, runner_path, result, verify=True,
                                           fresh_install=args.fresh_install)
                    current = re.search(r"(?m)^PURPLE_VMWARE_BOOT=(.+)$", verified)
                    if current and current.group(1).strip() != prior.group(1).strip():
                        break
                except PurpleEvaluationError:
                    pass
                time.sleep(5)
            else:
                raise PurpleEvaluationError("WS01 evaluation or reboot could not be verified")
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
