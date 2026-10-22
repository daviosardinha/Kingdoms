"""Finish only the existing bf5369 operator handoff using native foundations.

The host/VMX/credential/TLS helpers remain authoritative. No VM creation,
network edits, scenario execution, account rotation or automatic rollback.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import errno
import gzip
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import ssl
import subprocess
import tempfile

from kingdoms import wslpe41_management_nic as nic
from kingdoms.wslpe41_native_identity import inspect_native_registration
from kingdoms.wslpe_learner_credentials import learner_password
from kingdoms.wslpe_management_guard import parse_vagrant_ports
from kingdoms.wslpe_operator_credentials import operator_secret, _private_file
from kingdoms.wslpe_nic_contract import parse_vmx_networks

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/wslpe41-operator-management.ps1"
ADDRESS = "172.28.233.31"
SOURCE = "172.28.233.254"
LEARNER = "172.28.232.31"
USER = r"WSLPE-WS01\kingdom.operator"
RECOVERY = r"C:\ProgramData\Kingdoms\OperatorManagement-bf5369\management.ps1"
JSON_MARKER = "WSLPE_OPERATOR_JSON="


class ManagementBlocked(RuntimeError):
    """Safe diagnostic; never embed remote output or credentials."""


def command(argv, *, cwd=ROOT, timeout=40):
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                            stdin=subprocess.DEVNULL, timeout=timeout, check=False)
    if result.returncode or len(result.stdout) > 1_000_000:
        raise ManagementBlocked("Read-only command failed: " + Path(argv[0]).name)
    return result.stdout


def exact_target():
    target = nic.identify(Path.home(), existing_ok=True)
    if target.instance.parent.parent.resolve() != ROOT:
        raise ManagementBlocked("Run from the existing kingdoms-wslpe41-fresh checkout")
    registration = inspect_native_registration(
        target.instance, command(["vmrun", "-T", "ws", "list"]),
    )
    if registration.instance_id != nic.INSTANCE or registration.vmx != str(target.vmx):
        raise ManagementBlocked("Exact fresh running VMware registration changed")
    slots = parse_vmx_networks(target.original.decode("utf-8"))
    expected = ("00:0c:29:2f:d7:5b", "00:0c:29:2f:d7:65", "00:0c:29:2f:d7:6f")
    if tuple(slots[i].get("generatedaddress", "").lower() for i in range(3)) != expected:
        raise ManagementBlocked("Fresh VM MAC identities differ from the accepted instance")
    # Existing keeper's --check is read-only; no host-network reconfiguration.
    nic.host_operator_network_ready()
    route = json.loads(command(["ip", "-j", "-4", "route", "get", ADDRESS]))
    if (len(route) != 1 or route[0].get("dev") != "vmnet4"
            or route[0].get("prefsrc", route[0].get("src")) != SOURCE
            or route[0].get("gateway")):
        raise ManagementBlocked("Management route is not direct vmnet4 from 172.28.233.254")
    return target


def auth_helper():
    path = ROOT / "scripts/wslpe-https-auth-audit.py"
    spec = importlib.util.spec_from_file_location("wslpe41_existing_https", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def invoke(session, mode: str, *, nonce="", install=False):
    if mode not in {"Inspect", "Prepare", "Harden", "Verify", "ConsoleStatus"}:
        raise ManagementBlocked("Unsupported remote management operation")
    if nonce and not re.fullmatch(r"[a-f0-9]{32}", nonce):
        raise ManagementBlocked("Invalid console recovery nonce")
    if mode == "ConsoleStatus":
        script = (
            "$ErrorActionPreference='Stop'; $s=Import-Clixml '"
            + RECOVERY.rsplit("\\", 1)[0] + "\\state.clixml'; "
            + "if($s.Instance -cne 'bf5369-wslpe-vmware' -or $s.Nonce -cne '" + nonce
            + "' -or $s.ConsoleNonce -cne '" + nonce + "'){throw 'Console check pending'}; "
            + "Write-Output 'WSLPE_OPERATOR_CONSOLE=PASS'"
        )
    else:
        # Compress the public source to stay below Windows' 32767-character
        # CreateProcess limit after pywinrm's UTF-16LE EncodedCommand expansion.
        # The installed console recovery copy is the original readable source.
        encoded = base64.b64encode(gzip.compress(SCRIPT.read_bytes(), mtime=0)).decode("ascii")
        script = (
            "$b='" + encoded + "'; $m=New-Object IO.MemoryStream(,([Convert]::FromBase64String($b))); "
            "$g=New-Object IO.Compression.GzipStream($m,[IO.Compression.CompressionMode]::Decompress); "
            "$o=New-Object IO.MemoryStream; $g.CopyTo($o); $g.Dispose(); "
            "$bytes=$o.ToArray(); $o.Dispose(); $s=[Text.Encoding]::UTF8.GetString($bytes); "
            "try { & ([scriptblock]::Create($s)) "
            f"-Mode {mode} -Nonce '{nonce}'"
            + (" -SourceBase64 ([Convert]::ToBase64String($bytes))" if install else "")
            + " } catch { Write-Output ('WSLPE_OPERATOR_ERROR=' + $_.Exception.Message); exit 1 }"
        )
        if len(base64.b64encode(script.encode("utf-16le"))) > 30_000:
            raise ManagementBlocked("Management source exceeds the Windows command transport limit")
    result = session.run_ps(script)
    if result.status_code != 0 or len(result.std_out) > 100_000:
        # This management script never receives a password. Its bounded error
        # marker is safe to show; raw CLIXML/HTTP/Ansible diagnostics are not.
        messages = [line.partition("=")[2] for line in result.std_out.decode("utf-8", errors="replace").splitlines()
                    if line.startswith("WSLPE_OPERATOR_ERROR=")]
        detail = messages[0][:240] if len(messages) == 1 else "no success evidence"
        raise ManagementBlocked(f"Windows {mode} failed: {detail}; recovery state retained")
    if mode == "Inspect":
        return parse_inspection(result.std_out)
    marker = {"Prepare": "WSLPE_OPERATOR_PREPARED=PASS",
              "Harden": "WSLPE_OPERATOR_POLICY=PASS",
              "Verify": "WSLPE_OPERATOR_POLICY=PASS",
              "ConsoleStatus": "WSLPE_OPERATOR_CONSOLE=PASS"}[mode]
    if result.std_out.decode("utf-8-sig").splitlines().count(marker) != 1:
        raise ManagementBlocked(f"Windows {mode} proof missing")
    return None


def parse_inspection(raw: bytes) -> dict:
    lines = [line[len(JSON_MARKER):] for line in raw.decode("utf-8-sig").splitlines()
             if line.startswith(JSON_MARKER)]
    if len(lines) != 1:
        raise ManagementBlocked("Windows identity/certificate evidence missing")
    data = json.loads(lines[0])
    if (set(data) != {"Instance", "Certificate", "Thumbprint", "OperatorExists", "NatAddress", "Identity"}
            or data["Instance"] != nic.INSTANCE or type(data["OperatorExists"]) is not bool):
        raise ManagementBlocked("Unexpected Windows identity evidence")
    der = base64.b64decode(data["Certificate"], validate=True)
    if (not der or hashlib.sha1(der).hexdigest().upper() != data["Thumbprint"]
            or not ipaddress.IPv4Address(data["NatAddress"]).is_private):
        raise ManagementBlocked("Windows certificate or NAT evidence is invalid")
    return data


@contextmanager
def bootstrap_session(port):
    # Reuse the provider's existing NTLM bootstrap; require message encryption.
    from goad.provider.vagrant.vmware import VmwareProvider
    session = VmwareProvider._winrm_session(port, operation_timeout_sec=20, read_timeout_sec=30)
    transport = session.protocol.transport
    # build_session performs NTLM's encryption handshake immediately on HTTP.
    # Prevent proxy use BEFORE that call, not only before the later run_ps.
    transport.proxy = None
    transport.message_encryption = "always"
    try:
        http = transport.build_session()
        http.trust_env = False
        http.proxies = {}
        yield session
    finally:
        transport.close_session()


@contextmanager
def operator_session(auth, der, password, *, username=USER):
    import winrm
    audit = auth.tls_audit_module()
    fingerprint = hashlib.sha1(der).hexdigest().upper()
    # A fresh verified TLS handshake BEFORE sending any private operator secret.
    audit.verify_pinned_tls(ADDRESS, der, fingerprint)
    with tempfile.TemporaryDirectory(prefix="wslpe41-operator-tls-") as directory:
        anchor = Path(directory) / "leaf.pem"
        anchor.write_text(ssl.DER_cert_to_PEM_cert(der), encoding="ascii")
        anchor.chmod(0o600)
        session = winrm.Session(
            "https://WSLPE-WS01:5986/wsman", auth=(username, password), transport="ntlm",
            server_cert_validation="validate", ca_trust_path=str(anchor), proxy=None,
            operation_timeout_sec=20, read_timeout_sec=30,
        )
        transport = session.protocol.transport
        try:
            http = transport.build_session()
            http.trust_env = False
            http.proxies = {}
            if http.verify != str(anchor):
                raise ManagementBlocked("WinRM certificate validation anchor changed")
            with auth.scoped_wslpe_resolution(ADDRESS):
                yield session
        finally:
            transport.close_session()


def receipt_path():
    return Path.home() / ".local/state/kingdoms-wslpe-operator" / nic.INSTANCE / "management.json"


def read_receipt(path, target):
    _private_file(path)
    data = json.loads(path.read_text())
    if (data.get("instance") != nic.INSTANCE or data.get("vmx") != str(target.vmx)
            or not re.fullmatch(r"[a-f0-9]{32}", data.get("nonce", ""))):
        raise ManagementBlocked("Existing management receipt belongs to another transaction")
    der = base64.b64decode(data["certificate"], validate=True)
    if hashlib.sha256(der).hexdigest() != data.get("sha256"):
        raise ManagementBlocked("Saved certificate integrity mismatch")
    return data


def save_receipt(path, data):
    # Parent is the existing, checked private operator credential directory.
    if path.exists() or path.is_symlink():
        _private_file(path)
    fd, temporary = tempfile.mkstemp(prefix=".management-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def create_operator(target, port, password):
    from kingdoms.wslpe_license_maintenance import _approved_inventory
    native, defaults = _approved_inventory(ROOT, target.instance, LEARNER)
    learner = learner_password(
        bootstrap=False, environ={}, path=Path.home()
        / ".local/state/kingdoms-wslpe41-foundation" / nic.INSTANCE / "learner.credential",
    )
    if learner == password:
        raise ManagementBlocked("Operator and learner credentials must be independent")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("ANSIBLE_", "KINGDOMS_WSLPE_"))}
    env.update({
        "KINGDOMS_WSLPE_OPERATOR_PASSWORD": password,
        "KINGDOMS_WSLPE_LEARNER_PASSWORD": learner,
        "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg"),
        "ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles"),
        "ANSIBLE_NOCOLOR": "1", "ANSIBLE_LOG_PATH": os.devnull,
    })
    overrides = {
        "ansible_host": "127.0.0.1", "ansible_port": port,
        "ansible_connection": "winrm", "ansible_winrm_scheme": "http",
        "ansible_winrm_transport": "ntlm", "ansible_winrm_message_encryption": "always",
        "wslpe_operator_handoff_approved": True,
    }
    result = subprocess.run(
        [str(Path.home() / ".goad/.venv/bin/ansible-playbook"),
         "-i", str(native), "-i", str(defaults), "--limit", "ws01,localhost",
         str(ROOT / "ansible/wslpe-operator-foundation.yml"), "-e", json.dumps(overrides)],
        cwd=ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True,
        text=True, check=False, timeout=300,
    )
    if result.returncode:
        raise ManagementBlocked("Existing operator foundation failed; credential retained, no rotation")


def deny_probe(destination, port, source):
    # Binding a real host address proves source filtering without sending any
    # traffic to NORTH or altering its interfaces/routes/guests.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(3)
        sock.bind((source, 0))
        try:
            sock.connect((destination, port))
        except OSError as exc:
            if exc.errno in (errno.ECONNREFUSED, errno.ETIMEDOUT) or isinstance(exc, TimeoutError):
                return
            raise ManagementBlocked("Negative probe inconclusive: source/route/socket failure") from exc
    raise ManagementBlocked(f"Forbidden WinRM path is reachable: {source} -> {destination}:{port}")


def negative_probes(nat_address):
    interfaces = json.loads(command(["ip", "-j", "-4", "addr", "show"]))
    sources = [(item["ifname"], address["local"]) for item in interfaces
               for address in item.get("addr_info", []) if address.get("family") == "inet"]
    learner = [ip for interface, ip in sources if interface == "vmnet3"
               and ipaddress.ip_address(ip) in ipaddress.ip_network("172.28.232.0/24")]
    north = [ip for interface, ip in sources if interface.startswith("vmnet")
             and ipaddress.ip_address(ip) in ipaddress.ip_network("10.4.0.0/16")]
    nat_sources = [ip for interface, ip in sources if interface.startswith("vmnet")
                   and ipaddress.ip_address(nat_address) in ipaddress.ip_network(ip + "/24", strict=False)]
    if len(learner) != 1 or not north or len(nat_sources) != 1:
        raise ManagementBlocked("Learner/NORTH/NAT source addresses unavailable for negative acceptance")
    for port in (5985, 5986):
        deny_probe(LEARNER, port, learner[0])
        deny_probe(nat_address, port, nat_sources[0])
    deny_probe(ADDRESS, 5985, SOURCE)
    for source in (learner[0], *north):
        deny_probe(ADDRESS, 5986, source)


def prove_operator(auth, certificate, password, *, mode="Inspect", nonce=""):
    with operator_session(auth, certificate, password) as session:
        data = invoke(session, "Inspect")
        if data["Identity"].casefold() != USER.casefold() or not data["OperatorExists"]:
            raise ManagementBlocked("Fresh HTTPS session is not the dedicated operator")
        if mode != "Inspect":
            invoke(session, mode, nonce=nonce)
        return data


def run(*, apply=False, prompt=input, report=print):
    target = exact_target()
    try:
        password = operator_secret(nic.INSTANCE)  # Existing secret only: never generate/rotate.
    except (ValueError, OSError) as exc:
        raise ManagementBlocked("Prepared per-instance operator credential missing or unsafe; restore the original") from exc
    path = receipt_path()
    auth = auth_helper()
    if not apply:
        if not path.exists():
            raise ManagementBlocked("No completed management receipt; run --apply first")
        receipt = read_receipt(path, target)
        certificate = base64.b64decode(receipt["certificate"], validate=True)
        data = prove_operator(auth, certificate, password, mode="Verify", nonce=receipt["nonce"])
        negative_probes(data["NatAddress"])
        report("[PASS] WSLPE_OPERATOR_MANAGEMENT=PASS (live HTTPS, console record, policy and source probes)")
        return

    receipt = read_receipt(path, target) if path.exists() or path.is_symlink() else None
    # An interrupted post-account handoff may already have retired HTTP. Resume
    # with the saved certificate + existing secret; never recreate that account.
    if receipt:
        certificate = base64.b64decode(receipt["certificate"], validate=True)
        try:
            data = prove_operator(auth, certificate, password)
        except Exception:
            data = None
        if data:
            report("[PASS] Existing operator authenticated; account will be reused")
            _finish(target, auth, certificate, password, receipt, prompt, report)
            return

    ports = parse_vagrant_ports(command(["vagrant", "port", "WSLPE-WS01"], cwd=target.instance / "provider"))
    with bootstrap_session(ports[5985]) as bootstrap:
        data = invoke(bootstrap, "Inspect")
        certificate = base64.b64decode(data["Certificate"], validate=True)
        if receipt and receipt["certificate"] != data["Certificate"]:
            raise ManagementBlocked("Existing recovery certificate differs; do not replace the pin")
        if not receipt:
            receipt = {"instance": nic.INSTANCE, "vmx": str(target.vmx),
                       "certificate": data["Certificate"], "sha256": hashlib.sha256(certificate).hexdigest(),
                       "nonce": secrets.token_hex(16), "phase": "preparing"}
            save_receipt(path, receipt)
        report("[PASS] Exact guest and existing HTTPS certificate obtained through native bootstrap")
        invoke(bootstrap, "Prepare", nonce=receipt["nonce"], install=True)
        # Test TLS and bootstrap over the management NIC before creating any account.
        with operator_session(auth, certificate, "vagrant", username="vagrant") as recovery:
            invoke(recovery, "Inspect")
        _console(bootstrap, receipt["nonce"], prompt, report)
        if not data["OperatorExists"]:
            report("[APPLY] Existing operator foundation, using the prepared per-instance secret")
            create_operator(target, ports[5985], password)
        # If creation partially succeeded before interruption, this authentication
        # (not a blind win_user replay) is the only accepted resume proof.
        prove_operator(auth, certificate, password)
        report("[PASS] kingdom.operator authenticated and elevated over certificate-validated HTTPS")
        # A distinct bootstrap session still works immediately before restriction.
        with bootstrap_session(ports[5985]) as independent:
            invoke(independent, "Inspect")
    _finish(target, auth, certificate, password, receipt, prompt, report)


def _console(session, nonce, prompt, report):
    try:
        invoke(session, "ConsoleStatus", nonce=nonce)
        return
    except ManagementBlocked:
        pass
    report("Run this ONCE in elevated Windows PowerShell in the fresh VMware console:")
    report(f"& '{RECOVERY}' -Mode ConsoleCheck -Nonce '{nonce}'")
    prompt("After WSLPE_OPERATOR_CONSOLE=PASS, press Enter here: ")
    invoke(session, "ConsoleStatus", nonce=nonce)


def _finish(target, auth, certificate, password, receipt, prompt, report):
    # Recheck identity and existing host isolation immediately before narrowing
    # access. This cannot power off or modify any VM or VMware network.
    if exact_target().vmx != target.vmx:
        raise ManagementBlocked("VM identity changed during handoff")
    with operator_session(auth, certificate, password) as session:
        _console(session, receipt["nonce"], prompt, report)
        invoke(session, "Harden", nonce=receipt["nonce"])
    # Fresh connection, not an already-open WinRM shell surviving the rule change.
    data = prove_operator(auth, certificate, password, mode="Verify", nonce=receipt["nonce"])
    # Keep the original account as an independent HTTPS/console recovery identity.
    with operator_session(auth, certificate, "vagrant", username="vagrant") as recovery:
        invoke(recovery, "Inspect")
    negative_probes(data["NatAddress"])
    receipt["phase"] = "accepted"
    save_receipt(receipt_path(), receipt)
    report("[PASS] WSLPE_OPERATOR_MANAGEMENT=PASS (live HTTPS, console record, policy and source probes)")
    report("[STOP] Management repair only; no scenario deployment or main merge")
