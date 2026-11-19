#!/usr/bin/env python3
"""NORTH Climb the Keep: one-command, 20-topic configuration audit.

Default mode is source-only and does not contact guest machines.
Configuration mode invokes existing Ansible *validate* actions in isolation.
It never applies, resets or exploits a scenario, and never claims SYSTEM.
The existing validation actions may temporarily mount a registry hive,
write an export file, or grant and restore a test account's batch-logon right.
Explicit acknowledgement is required before enabling configuration mode.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TECHNIQUES = (
    ("01", "unattend_credentials", "Recovered credentials"),
    ("02", "hardcoded_application_credentials", "Application credentials"),
    ("03", "powershell_history_credentials", "PowerShell history"),
    ("04", "stored_winlogon_credentials", "Winlogon credentials"),
    ("05", "stored_runas_credentials", "Saved RunAs"),
    ("06", "weak_service_dacl", "Service DACL"),
    ("07", "weak_service_binary_permissions", "Service binary"),
    ("08", "unquoted_service_path", "Unquoted service path"),
    ("09", "writable_program_directory", "Program directory"),
    ("10", "weak_service_registry_permissions", "SCM Registry path"),
    ("11", "insecure_service_registry", "Application HelperPath"),
    ("12", "service_dll_hijacking", "Missing DLL"),
    ("13", "path_search_order_hijacking", "PATH helper search"),
    ("14", "scheduled_task_binary_permissions", "Scheduled task executable"),
    ("15", "scheduled_task_directory_permissions", "Scheduled task directory"),
    ("16", "writable_startup_folder", "Common Startup folder"),
    ("17", "registry_run_keys", "HKLM Run value"),
    ("18", "always_install_elevated", "AlwaysInstallElevated"),
    ("19", "sebackup_privilege", "SeBackupPrivilege"),
    ("20", "seimpersonate_privilege", "SeImpersonatePrivilege"),
)
EXPECTED = {name for _, name, _ in TECHNIQUES}
SPECIAL_VALIDATOR = ROOT / "ansible/roles/windows_lpe/files/stored_runas/30_lifecycle.ps1"
DEFAULTS = ROOT / "ansible/roles/windows_lpe/defaults/main.yml"
REPORT_DIR = Path.home() / "Kingdoms-evidence/north-climb-the-keep"


def source_audit():
    defaults = DEFAULTS.read_text(encoding="utf-8")
    catalog = defaults.split("windows_lpe_catalog:", 1)[1].split("\nwindows_lpe_candidate_techniques:", 1)[0]
    results = []
    for number, name, title in TECHNIQUES:
        path = ROOT / "ansible/roles/windows_lpe/tasks/techniques" / (name + ".yml")
        failures = []
        if not path.is_file():
            failures.append("Technique source missing")
            text = ""
        else:
            text = path.read_text(encoding="utf-8")
        if not re.search(r"(?m)^\s+- " + re.escape(name) + r"\s*$", catalog):
            failures.append("Technique missing from role catalog")
        if "windows_lpe_action == 'validate'" not in text and "windows_lpe_action in ['apply', 'validate']" not in text:
            # Stored RunAs forwards Action=validate to the referenced PS1 lifecycle.
            if name != "stored_runas_credentials":
                failures.append("No validate action in role")
        if name == "stored_runas_credentials":
            lifecycle = SPECIAL_VALIDATOR.read_text(encoding="utf-8") if SPECIAL_VALIDATOR.exists() else ""
            if "elseif ($Action -eq 'validate'" not in lifecycle:
                failures.append("Stored RunAs validation lifecycle missing")
            if "WINDOWS_LPE_STORED_RUNAS_CREDENTIALS=VULNERABLE" not in lifecycle:
                failures.append("Stored RunAs PASS marker missing")
        elif "=VULNERABLE" not in text:
            failures.append("Vulnerable-state validation marker missing")
        results.append({
            "topic": number, "technique": name, "title": title,
            "source": "PASS" if not failures else "FAIL",
            "configuration": "NOT_RUN",
            "interactive_system": "NOT_RUN",
            "details": failures
        })
    return results


def invoke(argv, env=None):
    return subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True, check=False)


def configuration_audit(records, provider):
    expected_provider = (ROOT / "workspace/0da0a9-north-vmware/provider").resolve()
    if provider.resolve() != expected_provider:
        raise ValueError("Provider does not match the approved disposable NORTH workspace")
    if not provider.is_dir():
        raise ValueError("NORTH provider directory does not exist")
    guest = provider / ".vagrant/machines/GOAD-WS01/vmware_desktop/id"
    if not guest.is_file():
        raise ValueError("NORTH WS01 VMware machine identifier is missing")
    instance_inventory = provider.parent / "inventory"
    lab_inventory = ROOT / "ad/GOAD/data/inventory"
    global_inventory = ROOT / "globalsettings.ini"
    playbook = ROOT / "ansible/windows-lpe.yml"
    ansible = Path.home() / ".goad/.venv/bin/ansible-playbook"
    for file in (instance_inventory, lab_inventory, global_inventory, playbook, ansible):
        if not file.is_file():
            raise ValueError("Required NORTH validation input missing: " + str(file))

    gate = invoke(["bash", str(ROOT / "scripts/verify-test-source.sh")])
    if gate.returncode:
        raise RuntimeError("Git source gate failed: " + gate.stderr[-1200:])

    env = os.environ.copy()
    env["ANSIBLE_CONFIG"] = str(ROOT / "ansible/ansible.cfg")
    command = [
        str(ansible),
        "-i", str(lab_inventory),
        "-i", str(instance_inventory),
        "-i", str(global_inventory),
        str(playbook),
        "-e", "windows_lpe_action=validate",
        "-e", "windows_lpe_validate_state=vulnerable",
    ]
    for record in records:
        if record["source"] != "PASS":
            record["configuration"] = "BLOCKED_SOURCE"
            continue
        per_topic = command + ["-e", json.dumps({"windows_lpe_techniques": [record["technique"]]})]
        proc = invoke(per_topic, env=env)
        output = proc.stdout + "\n" + proc.stderr
        marker = "WINDOWS_LPE_" + record["technique"].upper() + "=VULNERABLE"
        # Stored RunAs, Topic 07 and other techniques use this same marker convention.
        if proc.returncode == 0 and marker in output:
            record["configuration"] = "PASS"
        elif proc.returncode == 0:
            record["configuration"] = "NO_MARKER"
            record["details"].append("Playbook returned success without the expected per-topic marker")
        else:
            record["configuration"] = "FAIL"
            record["details"].append("Playbook exit code " + str(proc.returncode))
            record["details"].append(output[-1800:])
    return records


def write_report(records, mode):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result = {
        "created_utc": stamp,
        "mode": mode,
        "scope": "NORTH WS01 only",
        "status_semantics": {
            "source_PASS": "Technique source and static validation markers are present",
            "configuration_PASS": "Existing source-based Ansible validation accepted current WS01 state",
            "interactive_system_NOT_RUN": "No interactive SYSTEM exploitation was attempted"
        },
        "topics": records
    }
    output = REPORT_DIR / ("configuration-" + stamp + ".json")
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("source", "configuration"), default="source")
    parser.add_argument("--acknowledge-temporary-guest-changes", action="store_true")
    parser.add_argument("--provider", type=Path)
    args = parser.parse_args(argv)
    if args.mode == "configuration" and not args.acknowledge_temporary_guest_changes:
        parser.error("Configuration mode requires --acknowledge-temporary-guest-changes")
    records = source_audit()
    if args.mode == "configuration":
        provider = args.provider or Path(os.environ.get("GOAD_PROVIDER_DIR", ""))
        if not str(provider) or str(provider) == ".":
            parser.error("Configuration mode requires GOAD_PROVIDER_DIR or --provider")
        try:
            configuration_audit(records, provider)
        except (ValueError, RuntimeError) as exc:
            print("[FAIL] " + str(exc), file=sys.stderr)
            return 2
    for record in records:
        print("{topic} {title:<28} source={source:<4} config={configuration:<16} SYSTEM={interactive_system}".format(**record))
    report = write_report(records, args.mode)
    print("\nReport:", report)
    print("No interactive SYSTEM exploitation was attempted.")
    source_fail = any(r["source"] != "PASS" for r in records)
    config_fail = args.mode == "configuration" and any(r["configuration"] != "PASS" for r in records)
    return 1 if source_fail or config_fail else 0


if __name__ == "__main__":
    sys.exit(main())
