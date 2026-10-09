#!/usr/bin/env python3
"""Offline validation of the rendered four-VM Kingdoms Course 1 artifacts.

No Vagrant/VMware operations, no Ansible plays, no network calls. A private
temporary directory is used and deleted at exit. All Ansible inventory output
(which includes existing lab fixture credentials) is captured, never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/course1"))
from importlib.machinery import SourceFileLoader

generator = SourceFileLoader("kingdoms_course1_generator", str(ROOT / "scripts/course1/generate-profile.py")).load_module()

EXPECTED = {
    "domain": {"dc01", "dc02", "srv02", "ws01"},
    "dc": {"dc01", "dc02"},
    "server": {"srv02"},
    "workstation": {"ws01"},
    "parent_dc": {"dc01"},
    "child_dc": {"dc02"},
    "trust": set(),
    "adcs": {"dc01"},
    "mssql": {"srv02"},
}
REQUIRED_DEFAULT = {"dc01", "dc02", "srv02", "ws01"}
FORBIDDEN = {"dc03", "srv03"}
WIN_HOSTS = set(REQUIRED_DEFAULT)


class ArtifactError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ArtifactError(message)


def run_checked(argv: list[str], *, timeout: int = 25) -> str:
    """Capture all output; no credentials or native command output on success."""
    try:
        proc = subprocess.run(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=timeout, check=False,
            cwd=ROOT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ArtifactError(f"Offline tool failed to run: {Path(argv[0]).name}") from exc
    if proc.returncode != 0:
        # Deliberately do not echo stderr: inventory parsers can echo line
        # contents, including credentials.
        raise ArtifactError(
            f"{Path(argv[0]).name} rejected the generated artifact "
            f"(exit status {proc.returncode}). Output withheld to protect lab credentials."
        )
    return proc.stdout


def inventory_check(tool: str, filename: Path, *, kind: str) -> None:
    output = run_checked([tool, "-i", str(filename), "--list"])
    try:
        data = json.loads(output)
    except ValueError as exc:
        raise ArtifactError("Ansible inventory returned invalid JSON") from exc

    require(kind in ("provision", "post", "provider"), "unknown inventory kind")
    expected = (EXPECTED if kind == "provision"
                else {"domain": REQUIRED_DEFAULT, "default": REQUIRED_DEFAULT}
                if kind == "post" else {"default": REQUIRED_DEFAULT})
    for group, wanted in expected.items():
        result = set(data.get(group, {}).get("hosts", []))
        require(result == wanted,
                f"{filename.name}: inventory group [{group}] mismatch: "
                f"expected {len(wanted)} hosts, got {len(result)}")

    known = set(data.get("_meta", {}).get("hostvars", {}))
    require(WIN_HOSTS.issubset(known), "Ansible inventory missing NORTH or parent host identities")
    require(not FORBIDDEN.intersection(known), "ESSOS host remains in Ansible inventory")
    if kind == "post":
        ws01 = data["_meta"]["hostvars"]["ws01"]
        srv02 = data["_meta"]["hostvars"]["srv02"]
        require(ws01.get("ansible_host") == "10.4.10.31", "WS01 post-Vagrant management address differs")
        require(ws01.get("ansible_user") == srv02.get("ansible_user"),
                "WS01 and SRV02 NORTH management identity must match")
        require(ws01.get("ansible_password") == srv02.get("ansible_password"),
                "WS01 and SRV02 NORTH management credential must match")


def check_external() -> None:
    ruby = shutil.which("ruby")
    ansible = (shutil.which("ansible-inventory") or
               str(Path.home() / ".goad/.venv/bin/ansible-inventory"))
    require(bool(ruby), "Ruby CLI is required for syntax-only Vagrant validation")
    require(Path(ansible).is_file() or shutil.which("ansible-inventory") is not None,
            "ansible-inventory not found (check ~/.goad/.venv/bin/ansible-inventory)")
    rendered = generator.render()
    require(rendered["manifest.json"].find("PREVIEW_ONLY_NOT_INSTALLABLE") != -1,
            "Only a non-deployable preview may be checked")
    require(not any(name in rendered["instance-preview/Vagrantfile"]
                    for name in ("GOAD-DC03", "GOAD-SRV03")),
            "ESSOS guest in generated Vagrantfile")

    old_umask = os.umask(0o077)
    try:
        with tempfile.TemporaryDirectory(prefix="kingdoms-course1-offline-") as td:
            root = Path(td)
            root.chmod(0o700)
            files = {
                "instance-preview/Vagrantfile": rendered["instance-preview/Vagrantfile"],
                "data/inventory": rendered["data/inventory"],
                "data/inventory_disable_vagrant": rendered["data/inventory_disable_vagrant"],
                "providers/vmware/inventory": rendered["providers/vmware/inventory"],
            }
            for name, contents in files.items():
                dest = root / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(contents, encoding="utf-8")
                dest.chmod(0o600)
            ruby_output = run_checked([ruby, "-c", str(root / "instance-preview/Vagrantfile")])
            require("Syntax OK" in ruby_output, "Ruby did not confirm syntax")
            print("[PASS] Rendered four-VM Vagrantfile: ruby -c Syntax OK")
            inventory_check(ansible, root / "data/inventory", kind="provision")
            print("[PASS] Ansible provisioning inventory: correct four-VM scope/groups")
            inventory_check(ansible, root / "data/inventory_disable_vagrant", kind="post")
            print("[PASS] Ansible post-Vagrant inventory: four-VM endpoints and WS01 credentials")
            inventory_check(ansible, root / "providers/vmware/inventory", kind="provider")
            print("[PASS] Vagrant provider inventory: four-VM management endpoints")
            print("[PASS] Source and external artifacts agree; temp evidence deleted")
            print("[BLOCKED] Installer/start/mode controller cannot activate Course 1 yet")
    finally:
        os.umask(old_umask)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="Run only external read-only Vagrant/Ansible parsing checks")
    args = parser.parse_args()
    if not args.check:
        parser.error("Explicit --check is required; no deployment operation exists")
    try:
        check_external()
    except (ArtifactError, ValueError) as exc:
        print("[FAIL] " + str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
