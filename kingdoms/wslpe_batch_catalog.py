"""Source-only 45-technique WSLPE batch manifest and NORTH immutability guard."""
from __future__ import annotations

import json
from pathlib import Path
import re
import yaml

ROOT = Path(__file__).resolve().parents[1]
NORTH_SOURCE = ROOT / "ansible/roles/windows_lpe/defaults/main.yml"
ADVANCED = ROOT / "kingdoms/wslpe_advanced_catalog.yml"
EXPERT = ROOT / "kingdoms/wslpe_expert_catalog.yml"

FROZEN_FOUNDATION = (
    "unquoted_service_path", "weak_service_dacl",
    "weak_service_binary_permissions", "weak_service_registry_permissions",
    "service_dll_hijacking", "path_search_order_hijacking",
    "always_install_elevated", "registry_run_keys", "writable_startup_folder",
    "scheduled_task_binary_permissions", "scheduled_task_directory_permissions",
    "unattend_credentials", "powershell_history_credentials",
    "hardcoded_application_credentials", "stored_runas_credentials",
    "stored_winlogon_credentials", "sebackup_privilege",
    "seimpersonate_privilege", "writable_program_directory",
    "insecure_service_registry",
)


def load(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing or symlinked catalog: " + path.name)
    result = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Expected YAML mapping: " + path.name)
    return result


def catalog() -> list[dict]:
    north = load(NORTH_SOURCE)
    old = list(FROZEN_FOUNDATION)
    if (north.get("windows_lpe_catalog") != old
            or north.get("windows_lpe_implemented_techniques") != old
            or north.get("windows_lpe_candidate_techniques") != []):
        raise ValueError("NORTH frozen 20-technique source has changed")

    rows = [
        {"number": i, "id": name, "stage": "foundation",
         "status": "lifecycle-qualified", "learner_exploited": False}
        for i, name in enumerate(old, start=1)
    ]
    for path, stage, low, count, schema in (
        (ADVANCED, "advanced", 21, 15, "kingdoms.wslpe.advanced.v1"),
        (EXPERT, "expert", 36, 10, "kingdoms.wslpe.expert.v1"),
    ):
        data = load(path)
        checks = {
            "schema": schema, "scope": "standalone-wslpe-only",
            "platform": "windows-10-workgroup",
            "target_total": 45, "foundation_count": 20,
            "advanced_count": 15, "learner": r"WSLPE-WS01\lpe.trainee",
            "shared_north_role_frozen": True, "status": "planned",
        }
        if stage == "expert":
            checks["expert_count"] = 10
        for key, expected in checks.items():
            if type(data.get(key)) is not type(expected) or data[key] != expected:
                raise ValueError(f"{stage} unsafe scope field: {key}")
        entries = data.get("techniques")
        if not isinstance(entries, list) or len(entries) != count:
            raise ValueError(f"{stage} expected exactly {count} candidates")
        for offset, entry in enumerate(entries):
            number = low + offset
            if not isinstance(entry, dict) or type(entry.get("number")) is not int or entry["number"] != number:
                raise ValueError(f"{stage} numbering violation")
            identifier = entry.get("id")
            if not isinstance(identifier, str) or re.fullmatch(r"[a-z_]+", identifier) is None:
                raise ValueError("Invalid candidate ID")
            if entry.get("status") != "planned":
                raise ValueError("Source planning must not claim implementation")
            for field in ("name", "mechanic", "prerequisite", "fixture", "feasibility_gate"):
                if not isinstance(entry.get(field), str) or len(entry[field].strip()) < 12:
                    raise ValueError(f"{identifier}: missing {field}")
            overlaps = entry.get("distinct_from")
            if not isinstance(overlaps, list) or not overlaps or not all(
                isinstance(item, str) and re.fullmatch(r"[a-z_]+", item) for item in overlaps
            ):
                raise ValueError(f"{identifier}: missing overlap analysis")
            rows.append({"number": number, "id": identifier, "stage": stage,
                         "status": "planned", "learner_exploited": False})
    if len(rows) != 45 or len(set(r["id"] for r in rows)) != 45:
        raise ValueError("Require 45 uniquely named standalone techniques")
    return rows


def summary() -> dict:
    rows = catalog()
    return {"scope": "standalone-wslpe-only", "machine": "WSLPE-WS01",
            "north_mutation": False, "total": 45,
            "foundation_lifecycle_qualified": 20, "planned": 25,
            "newly_implemented": 0, "learner_exploitation_accepted": 0,
            "ready_for_live_batch": False, "techniques": rows}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true",
                        help="read-only full planning matrix")
    args = parser.parse_args()
    report = summary()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("[PASS] 45 unique WSLPE IDs: foundation=20 advanced=15 expert=10")
        print("[SCOPE] WSLPE-WS01 only; frozen NORTH catalog unchanged")
        print("[STATE] 20 lifecycle-qualified, 25 planned, 0 new fixtures deployed")
        print("[BLOCKED] Live batch requires fixtures, source tests and safe recovery")
    return 0
