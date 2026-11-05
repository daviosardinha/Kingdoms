"""Restart an installed PURPLE range via VMware, not Vagrant WinRM boot.

Reuse KINGDOMS' existing-machine pattern: prove exact registered VMX files,
start machines using vmrun in AD dependency order, then prove authenticated
guest readiness. This never creates/reprovisions VMs or modifies VMware vmnets.
"""
from __future__ import annotations

from pathlib import Path
import re
import socket
import subprocess
import time

from goad.log import Log

ROSTER = (
    ("PURPLE-DC01", "172.28.233.30", "windows"),
    ("PURPLE-WS01", "172.28.233.31", "windows"),
    ("PURPLE-LX01", "172.28.233.32", "linux"),
    ("PURPLE-WAZUH", "172.28.233.51", "linux"),
    ("PURPLE-C2", "172.28.233.60", "linux"),
)
GUEST_USER = "vagrant"
GUEST_PASSWORD = "vagrant"  # Mayfly's fixed lab-only Windows management identity.


class PurpleStartBlocked(RuntimeError):
    """Installed-VM identity or guest readiness could not be established."""


def owned_provider(path: str | Path) -> Path:
    raw = Path(path).expanduser()
    if (raw.is_symlink() or raw.name != "provider"
            or not re.fullmatch(r"[0-9a-f]{6}-purple-vmware", raw.parent.name)):
        raise PurpleStartBlocked("Expected an existing PURPLE VMware provider directory")
    provider = raw.resolve(strict=True)
    if not (provider / "Vagrantfile").is_file():
        raise PurpleStartBlocked("Existing PURPLE Vagrantfile not found")
    source = (provider / "Vagrantfile").read_text(encoding="utf-8")
    for name, _, _ in ROSTER:
        if source.count(':name => "' + name + '"') != 1:
            raise PurpleStartBlocked(f"PURPLE installed provider has no unique {name} definition")
    return provider


def owned_vmx(provider: Path, machine: str) -> Path:
    identity = provider / ".vagrant" / "machines" / machine / "vmware_desktop" / "id"
    if not identity.is_file() or identity.is_symlink():
        raise PurpleStartBlocked(f"{machine} has no existing Vagrant VMware ID")
    target = Path(identity.read_text(encoding="utf-8").strip())
    if (not target.is_absolute() or target.is_symlink() or not target.is_file()):
        raise PurpleStartBlocked(f"{machine} has no valid existing VMX")
    parent = identity.parent.resolve(strict=True)
    if not target.resolve(strict=True).is_relative_to(parent):
        raise PurpleStartBlocked(f"{machine} VMX is not owned by this instance")
    if target.suffix.lower() != ".vmx":
        raise PurpleStartBlocked(f"{machine} VM identity does not point to a VMX")
    return target.resolve(strict=True)


class ExistingPurpleStarter:
    """No Vagrant commands or provisioning operations may be used by this class."""

    def __init__(self, provider: str | Path):
        self.provider = owned_provider(provider)
        self.vmx = {machine: owned_vmx(self.provider, machine)
                    for machine, _, _ in ROSTER}

    def vmrun(self, *args: str, timeout: int = 60) -> str:
        result = subprocess.run(
            ["vmrun", "-T", "ws", *map(str, args)],
            check=False, capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode:
            raise PurpleStartBlocked(
                "VMware command failed; verify Workstation registration and guest state: "
                + (result.stderr or result.stdout).strip()[-280:]
            )
        return result.stdout.strip()

    def running_vmxs(self) -> set[str]:
        output = self.vmrun("list", timeout=30).splitlines()
        if not output or not output[0].startswith("Total running VMs:"):
            raise PurpleStartBlocked("VMware did not return a valid running guest inventory")
        return set(output[1:])

    def power_on(self, machine: str, running: set[str]) -> None:
        vmx = str(self.vmx[machine])
        if vmx in running:
            Log.info(f"PURPLE: {machine} already running, no restart or Vagrant reconfiguration")
            return
        Log.info(f"PURPLE: starting registered {machine} via VMware (no Vagrant NAT lookup)")
        self.vmrun("start", vmx, "nogui", timeout=90)
        running.add(vmx)

    @staticmethod
    def windows_ready(machine: str, address: str) -> bool:
        import winrm
        # Lab-side, authenticated WinRM, not stale VMware NAT forwarding.
        try:
            session = winrm.Session(
                f"http://{address}:5985/wsman",
                auth=(GUEST_USER, GUEST_PASSWORD),
                transport="ntlm",
                operation_timeout_sec=15,
                read_timeout_sec=25,
            )
            verify = rf"""
$ErrorActionPreference = 'Stop'
$ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
    Where-Object {{ $_.IPAddress -eq '{address}' }}
$remote = Get-Service WinRM -ErrorAction Stop
$computer = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
$domain = $computer.PartOfDomain -and $computer.Domain -ieq 'purple.lab'
$ad = $true
if ('{machine}' -eq 'PURPLE-DC01') {{
    $ad = (Get-Service NTDS -ErrorAction Stop).Status -eq 'Running'
}}
if ($ip -and $remote.Status -eq 'Running' -and $domain -and $ad) {{
    Write-Output 'PURPLE_INSTALLED_WINDOWS_READY'
}}
"""
            result = session.run_ps(verify)
            return (result.status_code == 0 and
                    b"PURPLE_INSTALLED_WINDOWS_READY" in result.std_out)
        except Exception:
            return False

    def restore_winrm_service(self, machine: str) -> bool:
        """One authenticated, narrowly scoped VMware Tools recovery attempt.

        Do not alter NICs/firewall, rerun evaluation rearm, install Tools, or
        repeat the Vagrant adapter setup. If the management service cannot
        be restored, fail with a diagnostic instead.
        """
        vmx = str(self.vmx[machine])
        try:
            tools = self.vmrun("checkToolsState", vmx, timeout=20).strip().lower()
            if tools != "running":
                Log.warning(f"PURPLE: {machine} VMware Tools unavailable; not restarting WinRM")
                return False
            powershell = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
            script = (
                "$ErrorActionPreference='Stop'; "
                "Set-Service -Name WinRM -StartupType Automatic; "
                "if ((Get-Service WinRM).Status -ne 'Running') { Start-Service WinRM }"
            )
            self.vmrun(
                "-gu", GUEST_USER, "-gp", GUEST_PASSWORD,
                "runProgramInGuest", vmx, powershell, "-NoProfile",
                "-NonInteractive", "-Command", script, timeout=60,
            )
            Log.info(f"PURPLE: requested existing WinRM service readiness on {machine}")
            return True
        except (OSError, subprocess.TimeoutExpired, PurpleStartBlocked):
            Log.warning(f"PURPLE: {machine} VMware Tools WinRM recovery unavailable")
            return False

    @staticmethod
    def linux_ssh_ready(address: str) -> bool:
        try:
            with socket.create_connection((address, 22), timeout=2):
                return True
        except OSError:
            return False

    def wait_ready(self, machine: str, address: str, kind: str, timeout: int) -> None:
        deadline = time.monotonic() + timeout
        attempted_winrm = False
        started = time.monotonic()
        while time.monotonic() < deadline:
            ok = (self.windows_ready(machine, address) if kind == "windows"
                  else self.linux_ssh_ready(address))
            if ok:
                Log.success(f"PURPLE: {machine} authenticated guest readiness verified at {address}")
                return
            if kind == "windows" and not attempted_winrm and time.monotonic() - started >= 30:
                attempted_winrm = True
                self.restore_winrm_service(machine)
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(5, remaining))
        raise PurpleStartBlocked(
            f"{machine} is running but {kind} readiness not proven on {address}; "
            "check in-guest network and management service (no Vagrant retry attempted)"
        )

    def start(self, vm_name: str | None = None) -> bool:
        names = [row[0] for row in ROSTER]
        if vm_name is not None and vm_name not in names:
            raise PurpleStartBlocked(f"Unsupported PURPLE guest: {vm_name}")
        # Prove all registered VMX identities before changing any VM state.
        running = self.running_vmxs()
        targets = ROSTER if vm_name is None else tuple(
            row for row in ROSTER
            if row[0] == "PURPLE-DC01" or row[0] == vm_name
        )
        # Exactly like KINGDOMS' installed-instance lifecycle, powering on
        # is independent from Vagrant/WinRM guest provisioning. Start all
        # requested registered guests first, in AD dependency order. A live
        # WS01 desktop must never strand LX01, WAZUH or C2 powered off.
        power_failures = []
        booted = []
        for machine, address, kind in targets:
            try:
                self.power_on(machine, running)
                booted.append((machine, address, kind))
            except (PurpleStartBlocked, OSError, subprocess.TimeoutExpired) as exc:
                Log.error(f"PURPLE: {machine} could not be powered on: {exc}")
                power_failures.append(machine)
                # Remaining VMs are independent VMware guests: still bring
                # them up and report all failures after the power-on pass.
        if power_failures:
            Log.warning("PURPLE: power-on failures: " + ", ".join(power_failures))
        Log.info("PURPLE: power-on pass completed; checking guest readiness without Vagrant")
        readiness_failures = []
        for machine, address, kind in booted:
            try:
                self.wait_ready(machine, address, kind, timeout=240 if kind == "windows" else 120)
            except PurpleStartBlocked as exc:
                Log.error(str(exc))
                readiness_failures.append(machine)
        if power_failures or readiness_failures:
            Log.error("PURPLE: startup incomplete; powered-on VMs left intact. "
                      "Guest readiness still missing for: "
                      + ", ".join(power_failures + readiness_failures))
            return False
        Log.success("PURPLE: installed guests ready without Vagrant WinRM boot handshake")
        return True


def start_existing_purple(provider_dir: str | Path, vm_name: str | None = None) -> bool:
    try:
        return ExistingPurpleStarter(provider_dir).start(vm_name=vm_name)
    except (PurpleStartBlocked, OSError, subprocess.TimeoutExpired) as exc:
        Log.error(f"PURPLE: installed-guest startup blocked: {exc}")
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-dir", required=True, type=Path)
    parser.add_argument("--vm", choices=[row[0] for row in ROSTER])
    args = parser.parse_args()
    raise SystemExit(0 if start_existing_purple(args.provider_dir, args.vm) else 1)
