"""One native WSLPE41 learner bootstrap using the EXISTING foundation playbook.

This is a bounded developer-stage bridge for a fresh PROVIDED WSLPE guest,
not the production operator/isolation handoff or the 41-scenario runner.
Authentication follows the native Vagrant bootstrap forward (NTLM message
encryption); independent HTTPS pin/SAN/Windows account evidence brackets the
mutation. Never creates/retries VMs, changes NORTH or deploys vulnerabilities.
"""
from __future__ import annotations

import importlib.util
import ipaddress
import os
from pathlib import Path
import re
import subprocess

from goad.log import Log
from goad.utils import PROVIDED
from kingdoms.wslpe_license_maintenance import (
    READ_ONLY_LICENSE_PROOF, _approved_inventory, _exact_instance,
)
from kingdoms.wslpe_stage1 import GUEST, inspect_vmware_guest
from kingdoms.wslpe_stage1_repair import _guest_proof
from kingdoms.wslpe_learner_credentials import learner_password


TIMEOUT_SECONDS = 2100
ROOT = Path(__file__).resolve().parents[1]
AUDITOR = ROOT / "scripts/wslpe-account-audit.py"
PIN_MARKER = "WSLPE_HTTPS_THUMBPRINT="
RDP_MARKER = b"WSLPE_LEARNER_RDP=PASS"

# An *already authenticated* native Vagrant WinRM session obtains the HTTPS
# listener binding; an arbitrary unauthenticated remote certificate is NEVER
# trusted on first sight. Exactly one HTTPS listener and a valid hash required.
READ_ONLY_HTTPS_BINDING = r"""
$ErrorActionPreference = 'Stop'
$c = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
if ($env:COMPUTERNAME -cne 'WSLPE-WS01' -or $c.PartOfDomain) {
    throw 'WSLPE_HTTPS_WRONG_GUEST'
}
$listeners = @(Get-ChildItem -Path WSMan:\localhost\Listener -ErrorAction Stop |
    Where-Object { @($_.Keys) -contains 'Transport=HTTPS' })
if ($listeners.Count -ne 1) { throw 'WSLPE_HTTPS_LISTENER_NOT_UNIQUE' }
$thumb = [string](Get-Item -Path (
    $listeners[0].PSPath + '\CertificateThumbprint'
) -ErrorAction Stop).Value
if ($thumb -notmatch '^[A-Fa-f0-9]{40}$') {
    throw 'WSLPE_HTTPS_INVALID_CERTIFICATE_BINDING'
}
Write-Output ('WSLPE_HTTPS_THUMBPRINT=' + $thumb.ToUpperInvariant())
"""

READ_ONLY_RDP = r"""
$ErrorActionPreference='Stop'
$c = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
if ($env:COMPUTERNAME -cne 'WSLPE-WS01' -or $c.PartOfDomain) {
    throw 'WSLPE_LEARNER_WRONG_GUEST'
}
$learner = Get-LocalUser -Name 'lpe.trainee' -ErrorAction Stop
if (-not $learner.Enabled) { throw 'WSLPE_LEARNER_DISABLED' }
$admins = Get-LocalGroup -SID 'S-1-5-32-544' -ErrorAction Stop
$adminMembers = @(Get-LocalGroupMember -Group $admins.Name -ErrorAction Stop)
if ($adminMembers.SID.Value -contains $learner.SID.Value) {
    throw 'WSLPE_LEARNER_IS_ADMIN'
}
$rdp = Get-LocalGroup -SID 'S-1-5-32-555' -ErrorAction Stop
$rdpMembers = @(Get-LocalGroupMember -Group $rdp.Name -ErrorAction Stop)
if ($rdpMembers.SID.Value -notcontains $learner.SID.Value) {
    throw 'WSLPE_LEARNER_NOT_IN_RDP_GROUP'
}
Write-Output 'WSLPE_LEARNER_RDP=PASS'
"""


def _account_module():
    spec = importlib.util.spec_from_file_location("wslpe41_pinned_account", AUDITOR)
    if spec is None or spec.loader is None:
        raise ValueError("Existing pinned HTTPS WSLPE audit is missing")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    return audit


def _read_only_result(provider, port: int, script: str) -> bytes:
    result = provider._winrm_session(port).run_ps(script)
    if (result.status_code != 0 or not isinstance(result.std_out, bytes)
            or len(result.std_out) > 20_000):
        raise ValueError("Existing native WSLPE WinRM read-only proof failed")
    return result.std_out


def _trusted_binding(provider, port: int, account, expected_address: str):
    raw = _read_only_result(provider, port, READ_ONLY_HTTPS_BINDING)
    try:
        lines = [line.strip() for line in raw.decode("ascii").splitlines()]
    except UnicodeDecodeError as exc:
        raise ValueError("Windows HTTPS certificate binding evidence invalid") from exc
    records = [line[len(PIN_MARKER):] for line in lines if line.startswith(PIN_MARKER)]
    if len(records) != 1 or not re.fullmatch(r"[A-F0-9]{40}", records[0]):
        raise ValueError("Windows HTTPS binding evidence is incomplete")
    auth = account.load_auth()
    # This existing audit independently proves registered VMX, chain/pin, SAN
    # and TLS handshake. It checks the SAME native instance workspace.
    address, certificate = auth.checked_certificate(
        auth.tls_audit_module(), records[0],
    )
    if address != expected_address:
        raise ValueError("HTTPS certificate resolved to a different WSLPE instance")
    return auth, address, certificate, records[0]


def _audit_accounts(account, auth, address: str, certificate: bytes):
    # The existing inventory was already verified to contain the known
    # provisioning identity. Password is NEVER printed or placed in argv.
    rows = account.query(
        auth, address, certificate, "vagrant", "vagrant",
        require_learner=False,
    )
    return rows


def _preflight(manager):
    instance, provider, root, directory = _exact_instance(manager)
    if instance.get_status() != PROVIDED:
        raise ValueError("Learner bootstrap requires the recovered PROVIDED native guest")
    expected = str(
        ipaddress.IPv4Network(instance.ip_range + ".0/24").network_address + 31
    )
    port = provider._winrm_forwarded_port(GUEST)
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Exact native WSLPE forwarded management port unavailable")
    if not inspect_vmware_guest(provider) or not _guest_proof(
        provider, instance.ip_range, complete=True,
    ):
        raise ValueError("Registered Windows guest/NAT MAC/VMware Tools proof failed")
    native, defaults = _approved_inventory(root, directory, expected)
    if _read_only_result(provider, port, READ_ONLY_LICENSE_PROOF).count(
        b"WSLPE_LICENSE_READY=PASS"
    ) != 1:
        raise ValueError("Windows license gate is no longer ready")
    account = _account_module()
    auth, address, certificate, thumbprint = _trusted_binding(
        provider, port, account, expected,
    )
    rows = _audit_accounts(account, auth, address, certificate)
    if not (rows["vagrant"]["exists"] and rows["vagrant"]["enabled"]
            and rows["vagrant"]["admin"]):
        raise ValueError("WSLPE bootstrap administrator is not available")
    if rows["lpe.trainee"]["exists"]:
        raise ValueError("WSLPE learner already exists; never overwrite an installed account")
    if rows["kingdom.operator"]["exists"]:
        raise ValueError("Unexpected existing operator; learner bootstrap must not overwrite")
    if any(rows[name]["exists"] for name in account.FIXTURES):
        raise ValueError("Unexpected fixture accounts; this is not a clean learner foundation")
    return (instance, provider, root, native, defaults, port, account,
            auth, address, certificate, thumbprint)


def bootstrap_native_wslpe_learner(manager, *, confirmed: bool = False) -> bool:
    """Apply the EXISTING learner foundation once, then verify via pinned TLS.

    Every failure stops at the current guest state. A retry must be reviewed:
    Ansible may have partially created the user. No automatic replay.
    """
    if confirmed is not True:
        Log.error("Exact WSLPE learner-foundation approval required")
        return False
    try:
        (instance, provider, root, native, defaults, port, account,
         auth, address, certificate, thumbprint) = _preflight(manager)
        ansible = Path.home() / ".goad/.venv/bin/ansible-playbook"
        playbook = root / "ansible/wslpe-foundation.yml"
        if (not ansible.is_file() or ansible.is_symlink()
                or not os.access(ansible, os.X_OK)
                or not playbook.is_file() or playbook.is_symlink()):
            raise ValueError("Original KINGDOMS WSLPE foundation playbook unavailable")
        private_path = (
            Path.home() / ".local/state/kingdoms-wslpe41-foundation"
            / instance.instance_id / "learner.credential"
        )
        if private_path.exists() or private_path.is_symlink():
            raise ValueError("Existing learner credential requires reviewed resume; never replay")
    except (OSError, ValueError) as exc:
        Log.error(f"WSLPE learner preflight blocked: {exc}")
        return False

    # Reuse our existing strong-password generator/storage, but scope a secret
    # to THIS instance, not the original standalone/master development guest.
    try:
        password = learner_password(
            bootstrap=True, path=private_path, environ={},
        )
    except (OSError, ValueError) as exc:
        Log.error(f"WSLPE private learner credential unavailable: {type(exc).__name__}")
        return False

    env = os.environ.copy()
    env.update({
        "KINGDOMS_WSLPE_LEARNER_PASSWORD": password,
        "ANSIBLE_CONFIG": str(root / "ansible/ansible.cfg"),
        "ANSIBLE_ROLES_PATH": str(root / "ansible/roles"),
        "ANSIBLE_NOCOLOR": "1",
    })
    # Same original, credentialed native Vagrant channel as Stage 1 and the
    # already-proven license fix, with an exact loopback port and a validated
    # registered VMware NAT-MAC proof. This is NOT the final isolated operator
    # channel, which remains a separate mandatory gate.
    import json
    overrides = json.dumps({
        "ansible_host": "127.0.0.1",
        "ansible_port": port,
        "ansible_connection": "winrm",
        "ansible_winrm_scheme": "http",
        "ansible_winrm_transport": "ntlm",
    }, separators=(",", ":"))
    Log.info("WSLPE: running existing standalone learner foundation exactly once")
    try:
        result = subprocess.run(
            [str(ansible), "-i", str(native), "-i", str(defaults),
             "--limit", "ws01,localhost", str(playbook), "-e", overrides],
            cwd=root, env=env, capture_output=True, text=True,
            check=False, stdin=subprocess.DEVNULL, timeout=TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        Log.error(f"WSLPE learner foundation interrupted: {type(exc).__name__}")
        return False
    if result.returncode != 0:
        # Raw Ansible output can include secrets; no raw transcript printed.
        Log.error(
            f"Existing learner foundation did not finish (exit {result.returncode}); "
            "do not rerun until partial Windows changes are reviewed"
        )
        return False
    try:
        if not inspect_vmware_guest(provider) or not _guest_proof(
            provider, instance.ip_range, complete=True,
        ):
            raise ValueError("Native guest identity or networking changed during learner foundation")
        # The exact HTTPS certificate binding must remain constant.
        latest_auth, latest_address, latest_cert, latest_pin = _trusted_binding(
            provider, port, account, address,
        )
        if latest_pin != thumbprint or latest_cert != certificate:
            raise ValueError("Guest TLS identity changed during learner provisioning")
        rows = _audit_accounts(account, latest_auth, latest_address, latest_cert)
        if not (
            rows["lpe.trainee"]["exists"]
            and rows["lpe.trainee"]["enabled"]
            and rows["lpe.trainee"]["admin"] is False
            and rows["kingdom.operator"]["exists"] is False
        ):
            raise ValueError("Learner permission or operator absence proof failed")
        if _read_only_result(provider, port, READ_ONLY_RDP).count(RDP_MARKER) != 1:
            raise ValueError("Windows learner RDP-group proof missing")
    except (OSError, ValueError) as exc:
        Log.error(f"WSLPE learner Windows validation blocked: {type(exc).__name__}")
        return False

    Log.success(
        f"WSLPE_LEARNER_FOUNDATION=PASS on native {instance.instance_id}; "
        "nonadmin and RDP membership proven; operator/scenarios NOT installed"
    )
    Log.warning(
        "Learner actual RDP login, dedicated operator TLS management, "
        "WinRM-independent recovery and lab isolation remain pending"
    )
    return True
