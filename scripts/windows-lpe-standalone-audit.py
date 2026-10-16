#!/usr/bin/env python3
"""Read-only source inventory of domain dependencies in the shared Windows LPE role.

This is NOT a VM readiness test. In the initial state it is expected to report
blockers. It does not modify roles, VM configuration, accounts, or credentials.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SCANNED_SUFFIXES = frozenset({".yml", ".yaml", ".ps1", ".py", ".sh"})
RULES = (
    ("domain_principal", re.compile(r"\b(?:NORTH|SEVENKINGDOMS)\\", re.IGNORECASE)),
    ("domain_learner", re.compile(r"\brickon\.stark\b", re.IGNORECASE)),
    ("ad_dns_name", re.compile(r"\b(?:north\.)?sevenkingdoms\.local\b", re.IGNORECASE)),
    ("north_network", re.compile(r"\b10\.4\.10\.\d{1,3}\b")),
    (
        "domain_configuration",
        re.compile(
            r"\blab\.domains\b|\b(?:domain_username|domain_password|member_domain|"
            r"win_domain_membership)\b",
            re.IGNORECASE,
        ),
    ),
)


def scan_role(root: Path) -> tuple[list[dict[str, object]], int]:
    """Return line-level indicators without echoing possible credential values."""
    role = root / "ansible" / "roles" / "windows_lpe"
    if not role.is_dir():
        raise FileNotFoundError(f"Windows LPE role missing: {role}")

    findings: list[dict[str, object]] = []
    files_scanned = 0
    for path in sorted(role.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SCANNED_SUFFIXES:
            continue
        files_scanned += 1
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except UnicodeError as exc:
            raise ValueError(f"cannot decode {path.relative_to(root)}") from exc
        for line_number, line in enumerate(lines, start=1):
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#"):
                continue
            for rule_name, expression in RULES:
                if expression.search(line):
                    findings.append(
                        {
                            "path": str(path.relative_to(root)),
                            "line": line_number,
                            "rule": rule_name,
                        }
                    )
    return findings, files_scanned


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only audit of domain dependencies in the shared Windows LPE role."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (default: directory above scripts/)",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 2 if source dependency indicators remain.",
    )
    args = parser.parse_args()
    root = args.root.resolve()

    try:
        findings, files_scanned = scan_role(root)
    except (FileNotFoundError, OSError, ValueError) as exc:
        parser.exit(1, f"[ERROR] {exc}\n")

    report = {
        "status": "source_dependencies_found" if findings else "source_scan_clean",
        "scope": "shared_role_source_only",
        "root": str(root),
        "files_scanned": files_scanned,
        "findings_count": len(findings),
        "findings": findings,
        "note": (
            "A clean role source scan is not proof of standalone runtime readiness. "
            "Standalone VM provisioning, account context, offline exercise, "
            "exploit outcomes, and per-scenario reversibility require separate tests."
        ),
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"[{'BLOCKED' if findings else 'SCAN CLEAN'}] "
            f"Windows LPE role source: {len(findings)} indicators "
            f"in {files_scanned} scanned files"
        )
        for item in findings:
            print(f"  {item['path']}:{item['line']} [{item['rule']}]")
        print(report["note"])

    return 2 if args.strict and findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
