#!/usr/bin/env python3
"""Targeted NORTH WS01 evaluation maintenance over its existing NAT WinRM.

Only a native, owner-verified NORTH guest. Uses the existing Kingdoms
settings/eval_rearm Ansible role; does not change activation enforcement,
VMware NIC definitions, domain membership, or any other guest.
"""
import argparse
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time


REPO = Path(__file__).resolve().parents[1]
PLAYBOOK = REPO / "ansible" / "north-ws01-eval-maintenance.yml"
VERIFY = REPO / "scripts" / "setup-vmware-networks.sh"
WS01_MAC = "00:50:56:20:10:31"


def vmx_identity(provider):
    provider = Path(provider).resolve(strict=True)
    if provider.name != "provider" or not provider.parent.name.endswith("-north-vmware"):
        raise ValueError("exact NORTH provider required")
    marker = provider / ".vagrant/machines/GOAD-WS01/vmware_desktop/id"
    if not marker.is_file() or marker.is_symlink():
        raise ValueError("original WS01 Vagrant VMX registration missing")
    vmx = Path(marker.read_text(encoding="utf-8").strip())
    expected_root = (provider / ".vagrant/machines/GOAD-WS01/vmware_desktop").resolve(strict=True)
    if (not vmx.is_absolute() or not vmx.is_file() or vmx.is_symlink()
            or not vmx.resolve(strict=True).is_relative_to(expected_root)):
        raise ValueError("WS01 VMX is missing or belongs to another instance")
    text = vmx.read_text(encoding="utf-8", errors="replace").lower()
    checks = (
        ('ethernet1.vnet', 'vmnet10'),
        ('ethernet1.connectiontype', 'custom'),
        ('ethernet1.address', WS01_MAC),
        ('ethernet1.present', 'true'),
    )
    for key, value in checks:
        # Accept standard VMware "key = \"value\"" and whitespace normalization.
        pattern = rf'(?mi)^\s*{re.escape(key)}\s*=\s*["\']?{re.escape(value)}["\']?\s*$'
        if not re.search(pattern, text):
            raise ValueError("WS01 VMware lab NIC contract differs: " + key)
    return provider, vmx


def forwarded_winrm_port(output):
    matches = re.findall(r'(?m)^\s*5985\s+\(guest\)\s*=>\s*(\d+)\s+\(host\)\s*$', output)
    if len(matches) != 1:
        raise ValueError("WS01 requires exactly one forwarded TCP/5985 mapping")
    port = int(matches[0])
    if not 1024 <= port <= 65535:
        raise ValueError("WS01 forwarded WinRM port invalid")
    return port


def checked(argv, **kwargs):
    return subprocess.run(argv, check=True, timeout=kwargs.pop("timeout", 60), **kwargs)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-dir", required=True)
    parser.add_argument(
        "--start-existing", action="store_true",
        help="Explicit operator recovery: power on ONLY the original WS01 VMX if stopped"
    )
    args = parser.parse_args(argv)
    provider, vmx = vmx_identity(args.provider_dir)

    checked(["sudo", "-n", "bash", str(VERIFY), "--north", "verify",
             "--provider-dir", str(provider)], timeout=75)
    raw = checked(["vmrun", "-T", "ws", "list"], capture_output=True, text=True).stdout
    vms = set(raw.splitlines()[1:])
    if str(vmx) not in vms:
        if not args.start_existing:
            raise ValueError("WS01 is powered off; refuse implicit startup")
        print("[INFO] Starting only the original NORTH WS01 VMX", flush=True)
        checked(["vmrun", "-T", "ws", "start", str(vmx), "nogui"], timeout=90)

    ports = checked(["vagrant", "port", "GOAD-WS01"], cwd=provider,
                    capture_output=True, text=True).stdout
    port = forwarded_winrm_port(ports)

    # A powered-on Windows guest is not necessarily listening on WinRM yet.
    deadline = time.monotonic() + 180
    while True:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=3):
                break
        except OSError:
            if time.monotonic() >= deadline:
                raise ValueError("WS01 NAT WinRM never opened; no licensing change attempted")
            time.sleep(5)

    ansible = Path.home() / ".goad/.venv/bin/ansible-playbook"
    if not ansible.is_file() or not PLAYBOOK.is_file():
        raise ValueError("Kingdoms Ansible installation or license playbook missing")

    with tempfile.TemporaryDirectory(prefix="kingdoms-north-ws01-eval-") as temp:
        inventory = Path(temp) / "ws01.ini"
        inventory.write_text(
            "[ws01]\n"
            f"ws01 ansible_host=127.0.0.1 ansible_port={port} "
            "ansible_connection=winrm ansible_user=vagrant "
            "ansible_password=vagrant ansible_winrm_transport=ntlm "
            "ansible_winrm_scheme=http\n",
            encoding="utf-8",
        )
        inventory.chmod(0o600)
        print("[INFO] Reusing settings/eval_rearm on original NORTH WS01", flush=True)
        checked([str(ansible), "-i", str(inventory), str(PLAYBOOK)],
                cwd=REPO / "ansible", timeout=2200)

    print("[PASS] NORTH_WS01_LICENSE_MAINTENANCE_COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        print(f"[BLOCKED] NORTH WS01 evaluation maintenance: {exc}", file=sys.stderr)
        sys.exit(1)
