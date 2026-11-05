#!/usr/bin/env python3
"""Safely add only PURPLE-C2 to an already installed PURPLE VMware instance.

No new lab, Windows provisioning, network creation, or C2 software setup.
"""
from __future__ import annotations

import argparse
import ipaddress
import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ad/PURPLE/providers/vmware/Vagrantfile"
ORIGINALS = ("PURPLE-DC01", "PURPLE-WS01", "PURPLE-LX01", "PURPLE-WAZUH")
C2 = "PURPLE-C2"
IP = "172.28.233.60"
MAC = "00:50:56:10:04:60"


class UnsafeExtension(RuntimeError):
    pass


def c2_definition(source: str) -> str:
    matches = list(re.finditer(
        r'(?ms)^  \{ :name => "PURPLE-C2".*?^    :lab_linux_config_script => "[^"]+" \}(?=\n|$)', source
    ))
    if len(matches) != 1:
        raise UnsafeExtension("Canonical PURPLE-C2 definition missing or duplicated")
    entry = matches[0].group(0).replace("{{ip_range}}", "172.28.233")
    for item in (f':ip => "{IP}"', f':hostname => "c2"', f':lab_mac => "{MAC}"',
                 ':vnet => "vmnet4"', '"bento/debian-12"'):
        if item not in entry:
            raise UnsafeExtension(f"Canonical C2 definition missing {item}")
    return entry


def extend_vagrantfile(source: str, existing: str) -> tuple[str, bool]:
    entry = c2_definition(source)
    if existing.count('Vagrant.configure("2")') != 1 or existing.count('boxes.each do |box|') != 1:
        raise UnsafeExtension("Generated Vagrantfile does not match the PURPLE provider layout")
    matches = list(re.finditer(r'(?ms)^boxes = \[\n(?P<body>.*?)^\]', existing))
    if len(matches) != 1:
        raise UnsafeExtension("Expected exactly one top-level boxes array")
    match = matches[0]
    body = match.group("body")
    defined = re.findall(r':name => "([^"]+)"', body)
    if tuple(defined) != ORIGINALS:
        raise UnsafeExtension("Expected exactly the four original PURPLE machines in order")
    if '{{ip_range}}' in body or ':vnet => "vmnet4"' not in body:
        raise UnsafeExtension("Generated PURPLE networking does not match the installed pilot")
    if f':name => "{C2}"' in body:
        if entry in body and body.count(f':name => "{C2}"') == 1:
            return existing, False
        raise UnsafeExtension("An incompatible PURPLE-C2 machine is already defined")
    if IP in body or MAC in body:
        raise UnsafeExtension("C2 address/MAC are already referenced by another machine")
    if not body.rstrip().endswith('}'):
        raise UnsafeExtension("Cannot identify the last original VM definition")
    new_body = body.rstrip() + ",\n" + entry + "\n"
    return existing[:match.start("body")] + new_body + existing[match.end("body"):], True


def verify_existing_vmware(provider: Path) -> None:
    """Allow only the four owned pilot VMX files on vmnet4 before extending it."""
    from goad import purple_vmware_network as network

    networking = Path('/etc/vmware/networking')
    if networking.is_symlink() or not networking.is_file():
        raise UnsafeExtension("Cannot inspect existing VMware networking")
    network.validate_config(networking.read_text(encoding="utf-8"))
    addr = subprocess.run(['ip', '-o', '-4', 'addr', 'show', 'dev', 'vmnet4'],
                          capture_output=True, text=True, check=True)
    cidrs = re.findall(r'\binet\s+(\d+\.\d+\.\d+\.\d+/\d+)', addr.stdout)
    if len(cidrs) != 1 or ipaddress.ip_interface(cidrs[0]).network != network.CIDR:
        raise UnsafeExtension("Host vmnet4 does not have the expected 172.28.233.0/24")
    if ipaddress.ip_interface(cidrs[0]).ip == ipaddress.ip_address(IP):
        raise UnsafeExtension("Host vmnet4 already owns the C2 address")

    owned = set()
    for name in ORIGINALS:
        id_file = provider / '.vagrant' / 'machines' / name / 'vmware_desktop' / 'id'
        if id_file.is_symlink() or not id_file.is_file():
            raise UnsafeExtension(f"Cannot confirm the installed VMX identity of {name}")
        vmx = Path(id_file.read_text(encoding='utf-8').strip())
        if not vmx.is_absolute() or vmx.is_symlink() or not vmx.is_file():
            raise UnsafeExtension(f"Missing or unsafe VMX for {name}")
        owned.add(str(vmx.resolve()))

    registry = Path.home() / '.vmware/inventory.vmls'
    if registry.is_symlink() or not registry.is_file():
        raise UnsafeExtension("Cannot inspect VMware's registered VM inventory")
    inventory = registry.read_text(encoding='utf-8')
    for path in network.VMX_REGISTRY.findall(inventory):
        vmx = Path(path)
        if vmx.is_symlink() or not vmx.is_file():
            raise UnsafeExtension(f"Uninspectable registered VMware guest: {path}")
        contents = vmx.read_text(encoding='utf-8', errors='replace')
        nets = {n.lower() for n in network.VMX_NET.findall(contents)}
        macs = {m.lower() for m in network.VMX_MAC.findall(contents)}
        if network.VMNET in nets or network.MACS & macs:
            if str(vmx.resolve()) not in owned:
                raise UnsafeExtension(f"Non-PURPLE registered guest uses vmnet4 or a reserved MAC: {path}")
        if MAC in macs:
            raise UnsafeExtension(f"The C2 MAC is already present on a registered VM: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider-dir', required=True, type=Path)
    parser.add_argument('--apply', action='store_true', help='Back up and extend the generated Vagrantfile')
    args = parser.parse_args()
    provider = args.provider_dir.expanduser()
    if (provider.is_symlink() or provider.name != 'provider' or
            not re.fullmatch(r'[a-fA-F0-9]{6,}-purple-vmware', provider.parent.name) or
            not provider.is_dir()):
        parser.error('Expected an existing workspace/<id>-purple-vmware/provider directory')
    target = provider / 'Vagrantfile'
    if target.is_symlink() or not target.is_file():
        parser.error('Generated PURPLE Vagrantfile is missing or unsafe')
    try:
        original = target.read_text(encoding='utf-8')
        updated, changed = extend_vagrantfile(SOURCE.read_text(encoding='utf-8'), original)
        if not changed:
            print('[PASS] PURPLE-C2 already defined; no file changes')
            return 0
        if not args.apply:
            print('[PLAN] Add only PURPLE-C2 (Debian 12, 172.28.233.60) to this instance')
            print('[PLAN] Re-run with --apply to back up and extend the generated Vagrantfile')
            return 0
        verify_existing_vmware(provider)
        backup = provider / 'Vagrantfile.pre-purple-c2.bak'
        if backup.exists() or backup.is_symlink():
            raise UnsafeExtension(f'Backup already exists, refusing overwrite: {backup}')
        shutil.copy2(target, backup)
        mode = stat.S_IMODE(target.stat().st_mode)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=provider,
                                             prefix='.Vagrantfile.purple-c2.', delete=False) as tmp:
                tmp.write(updated)
                tmp_path = Path(tmp.name)
            os.chmod(tmp_path, mode)
            os.replace(tmp_path, target)
        finally:
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink()
        print(f'[PASS] Extended existing PURPLE instance Vagrantfile; backup: {backup}')
        print('[NEXT] cd to provider directory and run: vagrant up PURPLE-C2')
        return 0
    except Exception as exc:
        print(f'[BLOCKED] PURPLE-C2 extension: {exc}', file=__import__('sys').stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
