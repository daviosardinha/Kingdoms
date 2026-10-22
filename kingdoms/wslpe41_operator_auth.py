"""Read-only operator authentication proof using the existing Ansible/WinRM path.

No new VM manager, bootstrap account, guest mutation or raw secret in argv.
The probe is deliberately not an install entry point.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
import subprocess
import tempfile

from kingdoms.wslpe41_install_flow import InstallBlocked
from kingdoms.wslpe41_stage_executor import (
    AnsibleStageContext, _environment, _guest, _inventory, _regular,
)


def authenticate_native_operator(context: AnsibleStageContext) -> bool:
    """Prove the exact native guest accepts its dedicated operator over TLS.

    The inventory must already be pinned to HTTPS/5986 and certificate
    validation. Credentials are passed through a mode-0600 temporary vars
    file, never command-line extra-vars or diagnostic output.
    """
    if (context.inventory.parent != context.instance_dir / "ansible"
            or context.private_vars.parent != context.instance_dir / "ansible"):
        raise InstallBlocked("Operator probe is not bound to native instance inventory")
    for path in (context.ansible, context.inventory):
        _regular(path)
    _regular(context.private_vars, private=True)
    if not os.access(context.ansible, os.X_OK):
        raise InstallBlocked("Approved Ansible executable missing")
    _guest(context)
    env = _environment(context)
    _inventory(context, env)
    password = env["KINGDOMS_WSLPE_OPERATOR_PASSWORD"]
    if password == env["KINGDOMS_WSLPE_LEARNER_PASSWORD"]:
        raise InstallBlocked("Operator and learner credentials must be independent")
    ansible = context.ansible.with_name("ansible")
    _regular(ansible)
    if not os.access(ansible, os.X_OK):
        raise InstallBlocked("Approved Ansible ad-hoc executable missing")
    # Refuse inherited insecure connection overrides; explicit extra-vars
    # have the highest precedence and pin the actual probe transport.
    overrides = {
        "ansible_user": r".\kingdom.operator",
        "ansible_password": password,
        "ansible_connection": "winrm",
        "ansible_winrm_scheme": "https",
        "ansible_port": 5986,
        "ansible_winrm_server_cert_validation": "validate",
        "ansible_host": ("WSLPE-WS01" if getattr(context, "management_address", None) else context.expected_address),
    }
    try:
        with tempfile.TemporaryDirectory(prefix="wslpe41-operator-") as directory:
            secret = Path(directory) / "operator.json"
            fd = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(overrides, handle)
            result = subprocess.run(
                ([str(ansible), "-i", str(context.inventory)] +
                 ([] if getattr(context, "management_address", None) else ["-i", str(context.private_vars)]) +
                 ["ws01", "-m", "ansible.windows.win_ping",
                  "-e", "@" + str(secret)]),
                cwd=Path(__file__).resolve().parents[1], env=env,
                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                check=False, timeout=min(context.timeout_seconds, 120),
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallBlocked("Operator HTTPS authentication probe unavailable") from exc
    _guest(context)
    # Only the exact successful win_ping result counts. Never log stdout:
    # Ansible output can contain sensitive transport diagnostics.
    if result.returncode != 0 or not result.stdout or len(result.stdout) > 100_000:
        raise InstallBlocked("Operator HTTPS authentication failed")
    match = re.fullmatch(
        r"ws01\s+\|\s+SUCCESS\s+=>\s*(\{.*\})\s*",
        result.stdout.strip(), flags=re.DOTALL,
    )
    if match is None:
        raise InstallBlocked("Operator HTTPS authentication proof missing")
    try:
        payload = json.loads(match.group(1))
    except (ValueError, TypeError) as exc:
        raise InstallBlocked("Operator HTTPS authentication proof invalid") from exc
    if not isinstance(payload, dict) or payload.get("ping") != "pong" or payload.get("failed"):
        raise InstallBlocked("Operator HTTPS authentication proof missing")
    return True
