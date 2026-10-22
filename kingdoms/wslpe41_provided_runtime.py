"""Existing-guest, one-time secure WSLPE41 Ansible runtime preparation.

This creates private *host-side* instance files only. It neither connects to
NORTH nor changes guest configuration, machine accounts, WinRM or VMware. The
existing management receipt, authentic TLS leaf and per-instance operator and
learner secrets are prerequisites, never regenerated. A partial runtime is a
hard stop requiring operator review, not an automatic retry.
"""
from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import json
import os
from pathlib import Path
import ssl
import stat

import yaml

from kingdoms import wslpe41_operator_management as management
from kingdoms import wslpe41_management_nic as nic
from kingdoms.wslpe41_install_flow import FreshGuestIdentity, InstallBlocked
from kingdoms.wslpe41_stage_executor import AnsibleStageContext
from kingdoms.wslpe_operator_credentials import operator_secret
from kingdoms.wslpe_learner_credentials import learner_password, _strong_password

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = "bf5369-wslpe-vmware"
FIXTURE_NAMES = (
    "windows_lpe_unattend_credentials",
    "windows_lpe_powershell_history_credentials",
    "windows_lpe_hardcoded_application_credentials",
    "windows_lpe_stored_runas_credentials",
    "windows_lpe_stored_winlogon_credentials",
)
LEARNER_SECRET = (Path.home() / ".local/state/kingdoms-wslpe41-foundation"
                  / INSTANCE / "learner.credential")


def existing_management() -> tuple[object, dict, bytes, str, str]:
    """Read and authenticate the already committed operator management."""
    target = management.exact_target()
    if target.instance.name != INSTANCE:
        raise InstallBlocked("Existing provided WSLPE instance has changed")
    mgmt = management.receipt_path()
    if mgmt.is_symlink() or not mgmt.is_file():
        raise InstallBlocked("Accepted operator management receipt missing")
    receipt = management.read_receipt(mgmt, target)
    if receipt.get("phase") != "accepted":
        raise InstallBlocked("Operator management was not committed")
    certificate = base64.b64decode(receipt["certificate"], validate=True)
    username = operator_secret(INSTANCE)
    learner = learner_password(bootstrap=False, path=LEARNER_SECRET, environ={})
    if username == learner:
        raise InstallBlocked("Operator and learner credentials cannot be identical")
    # The existing runner independently checks pinned TLS, authenticated
    # identity, firewall rules, local source isolation, and console record.
    proofs: list[str] = []
    management.run(apply=False, report=proofs.append)
    if len([p for p in proofs if p.startswith("[PASS] WSLPE_OPERATOR_MANAGEMENT=PASS")]) != 1:
        raise InstallBlocked("Independent live operator management acceptance missing")
    return target, receipt, certificate, username, learner


def _store(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.chmod(path, 0o600)


def _fixture_variables() -> dict:
    import copy
    defaults_path = ROOT / "ansible/roles/windows_lpe/defaults/main.yml"
    if defaults_path.is_symlink() or not defaults_path.is_file():
        raise InstallBlocked("Shared Windows LPE defaults unavailable")
    defaults = yaml.safe_load(defaults_path.read_text(encoding="utf-8"))
    fixture = {
        "wslpe_fixture_private": True,
        "wslpe_fixture_instance_id": INSTANCE,
    }
    for name in FIXTURE_NAMES:
        original = defaults.get(name)
        if not isinstance(original, dict) or not isinstance(original.get("password"), str):
            raise InstallBlocked("Canonical credential fixture source drift")
        row = copy.deepcopy(original)
        row["password"] = _strong_password()
        if name == "windows_lpe_stored_runas_credentials":
            row["credential_target"] = r"WSLPE-WS01\kingdom.runas"
        fixture[name] = row
    return fixture


def _inventory(path: Path, *, password: str) -> bytes:
    # The server's X.509 certificate has exact DNS SAN WSLPE-WS01.
    # A process-scoped Python resolver maps only that hostname/5986 to vmnet4.
    info = {
        "all": {
            "vars": {
                "domain_name": "WSLPE",
                "ansible_connection": "winrm",
                "ansible_host": "WSLPE-WS01",
                "ansible_port": 5986,
                "ansible_winrm_scheme": "https",
                "ansible_winrm_transport": "ntlm",
                "ansible_winrm_server_cert_validation": "validate",
                "ansible_winrm_ca_trust_path": str(path.parent / "operator-ca.pem"),
                "ansible_user": r"WSLPE-WS01\kingdom.operator",
                "ansible_password": password,
                "ansible_winrm_operation_timeout_sec": 400,
                "ansible_winrm_read_timeout_sec": 500,
                "force_dns_server": False,
                "add_route": False,
                "enable_http_proxy": False,
            },
            "children": {
                "wslpe": {"hosts": {"ws01": {}}},
                "windows_lpe_standalone": {"hosts": {"ws01": {}}},
            },
        },
    }
    return ("---\n" + yaml.safe_dump(info, sort_keys=False)).encode("utf-8")


def prepare() -> AnsibleStageContext:
    target, receipt, certificate, operator, learner = existing_management()
    folder = target.instance / "ansible"
    if folder.is_symlink() or folder.exists():
        raise InstallBlocked(
            "Exact instance Ansible runtime path already exists; inspect it, never overwrite")
    fixture = _fixture_variables()
    pem = ssl.DER_cert_to_PEM_cert(certificate).encode("ascii")
    folder.mkdir(mode=0o700)
    if (folder.stat().st_uid != os.geteuid()
            or stat.S_IMODE(folder.stat().st_mode) != 0o700):
        raise InstallBlocked("Runtime directory not owner-private")

    # Create an explicit prepare-intent receipt BEFORE making runtime files.
    # No automated retry or implicit cleanup after partial failure.
    path = folder / "runtime.json"
    record = {
        "schema": "kingdoms.wslpe41.provided-runtime.v1",
        "status": "prepared",
        "instance": INSTANCE, "vmx": str(target.vmx),
        "certificate_sha256": hashlib.sha256(certificate).hexdigest(),
        "management_receipt_sha256": hashlib.sha256(
            management.receipt_path().read_bytes()).hexdigest(),
    }
    _store(path, json.dumps(record, sort_keys=True).encode("utf-8"))
    inventory = folder / "inventory.yml"
    varsfile = folder / "private-vars.yml"
    anchor = folder / "operator-ca.pem"
    _store(anchor, pem)
    _store(inventory, _inventory(inventory, password=operator))
    _store(varsfile, ("---\n" + yaml.safe_dump(fixture, sort_keys=False)).encode("utf-8"))
    record["status"] = "committed"
    # Never unlink the prepared record and recreate it if interrupted;
    # replace it only after every private file has been created and verified.
    from kingdoms.wslpe41_install_flow import checkpoint
    checkpoint(path, record)
    identity = FreshGuestIdentity(
        instance_id=INSTANCE,
        workspace=str(target.instance.parent),
        vmx=str(target.vmx),
        subnet="172.28.232.0/24",
        source_commit="0" * 40,  # Not a fresh-creation attestation.
    )
    return AnsibleStageContext(
        identity=identity, instance_dir=target.instance,
        ansible=Path.home() / ".goad/.venv/bin/ansible-playbook",
        inventory=inventory, private_vars=varsfile,
        expected_address="172.28.232.31", management_address="172.28.233.31",
    )
