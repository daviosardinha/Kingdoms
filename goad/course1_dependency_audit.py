"""Read-only inventory of source files still coupled to full Kingdoms topology.

Only source file paths and reference counts are emitted: never excerpts, hashes,
secret-bearing inventory rows, connection strings, or fixture credentials.
The report is a work planning signal, not proof a file is broken.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPES = ("goad", "scripts", "ansible", "ad/GOAD")
SOURCE_EXT = {".py", ".sh", ".ps1", ".yml", ".yaml", ".json", ".ini",
              ".j2", ".j2s", ".txt", ".rb", ".cfg", ".nft"}
MARKERS = {
    "reference_ipv4": re.compile(r"(?<!\d)10\.4\.(?:10|20|30|99)\.\d{1,3}\b"),
    "reference_vmnet": re.compile(r"\bvmnet(?:10|20|30|99)\b", re.I),
    "essos_domain": re.compile(r"\bessos\.local\b", re.I),
    "essos_guests": re.compile(r"\bGOAD-(?:DC03|SRV03)\b", re.I),
    "hardcoded_six_guest_roster": re.compile(r"goa[dD]_nomad_windows|FULL_WINDOWS"),
}
IGNORED = {"__pycache__", ".git", ".venv", "node_modules", "vendor", ".vagrant",
           "tests", "docs"}

PRIORITY = {
    "goad/provider/vagrant/vmware_kingdoms.py": "P0_VMWARE_LIFECYCLE",
    "goad/provider/vagrant/vmware.py": "P0_VMWARE_LIFECYCLE",
    "goad/instance.py": "P0_INSTALLER_BINDING",
    "goad/lab_manager.py": "P0_INSTALLER_BINDING",
    "goad/goadpath.py": "P0_INSTALLER_BINDING",
    "scripts/lab-mode.sh": "P0_MODE_AND_ROUTER",
    "scripts/router-ssh.sh": "P0_MODE_AND_ROUTER",
}


def classify(path: str) -> str:
    if path in PRIORITY:
        return PRIORITY[path]
    if path.startswith(("goad/course1_", "scripts/course1/")):
        return "SOURCE_REFERENCE_ONLY"
    if path.startswith("ad/GOAD/data/"):
        return "REFERENCE_RECIPE"
    if path.startswith("ad/GOAD/providers/vmware/"):
        return "REFERENCE_VMWARE_CONFIG"
    if path.startswith("ansible/"):
        return "ANSIBLE_PLAYBOOK_DEPENDENCIES"
    if path.startswith("scripts/"):
        return "OTHER_RUNTIME_SCRIPTS"
    if path.startswith("goad/"):
        return "OTHER_RUNTIME_PYTHON"
    return "OTHER_SOURCE"


def collect(root: Path = ROOT) -> list[dict]:
    results: list[dict] = []
    for scope in SCOPES:
        folder = root / scope
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(root)
            if any(part in IGNORED for part in rel.parts):
                continue
            if path.suffix.lower() not in SOURCE_EXT:
                continue
            try:
                if path.stat().st_size > 1_000_000:
                    continue
                contents = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            hits = {key: len(rx.findall(contents))
                    for key, rx in MARKERS.items()}
            hits = {k: v for k, v in hits.items() if v}
            if hits:
                results.append({
                    "path": rel.as_posix(),
                    "workstream": classify(rel.as_posix()),
                    "references": hits,
                    "total": sum(hits.values()),
                })
    return sorted(results, key=lambda x: (
        0 if x["workstream"].startswith("P0_") else 1,
        -x["total"], x["path"],
    ))


def report(root: Path = ROOT, limit: int = 30) -> dict:
    records = collect(root)
    counts: dict[str, int] = {}
    for entry in records:
        counts[entry["workstream"]] = counts.get(entry["workstream"], 0) + 1
    return {
        "kind": "KINGDOMS_COURSE1_REFERENCE_DEPENDENCY_AUDIT",
        "status": "READ_ONLY_PLANNING",
        "files_with_topology_references": len(records),
        "workstream_file_counts": dict(sorted(counts.items())),
        "high_priority_paths": [x for x in records
                                if x["workstream"].startswith("P0_")],
        "top_referenced_paths": records[:limit],
        "reference_matches_are_not_automatically_bugs": True,
        "deployment_authorized": False,
        "files_modified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True,
                        help="read repository source text only")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("--limit must be between 1 and 100")
    print(json.dumps(report(limit=args.limit), indent=2))
    print("[BLOCKED] Dependency audit does not make Course 1 deployable")


if __name__ == "__main__":
    main()
