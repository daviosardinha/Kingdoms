"""Fail-closed binding of an installed VMware instance to a Kingdoms profile.

This is a legacy compatibility and PREVIEW rejection gate. It cannot authorize
a four-guest deployment. A preview manifest is NOT an activation token.

The sidecar file, when present, is stored next to the generated provider
Vagrantfile: provider/.kingdoms-profile.json. No caller may infer a profile
from a repository branch or environment variable.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from goad.course1_runtime_contract import FULL, ROUTER, ProfileNotReady, examine_profile_manifest

PROFILE_FILENAME = ".kingdoms-profile.json"
_GUEST_NAME = re.compile(r"""(?m)^\s*:name\s*=>\s*["'](GOAD-[A-Z0-9]+)["']""")
_M1_WINDOWS = frozenset(FULL.windows) - {"GOAD-WS01"}
_EXPECTED_FULL = frozenset(FULL.windows) | {ROUTER}
_EXPECTED_M1 = _M1_WINDOWS | {ROUTER}


def parse_instance_vagrant_roster(text: str) -> tuple[str, ...]:
    """Read concrete GOAD machine declarations, not the Ruby box loop."""
    names = tuple(_GUEST_NAME.findall(text))
    if len(names) != len(set(names)):
        raise ProfileNotReady("duplicate GOAD machine declarations in instance Vagrantfile")
    if not names:
        raise ProfileNotReady("instance Vagrantfile has no GOAD machine declarations")
    return names


def inspect_instance_binding(provider_path: str | Path):
    """Return FULL only for known legacy layouts; otherwise reject.

    No files are written, and this function never runs a guest operation.
    Historical five-guest source layouts are permitted ONLY so the existing
    GOAD WS01 compatibility migration can add the missing workstation.
    """
    directory = Path(provider_path)
    if not directory.is_dir():
        raise ProfileNotReady("VMware instance provider directory does not exist")
    vagrantfile = directory / "Vagrantfile"
    if vagrantfile.is_symlink() or not vagrantfile.is_file():
        raise ProfileNotReady("instance Vagrantfile missing or a symlink")
    names = parse_instance_vagrant_roster(vagrantfile.read_text(encoding="utf-8"))
    observed = frozenset(names)
    if observed not in (_EXPECTED_FULL, _EXPECTED_M1):
        raise ProfileNotReady(
            "VMware instance machine roster is neither six-guest legacy GOAD "
            "nor recognized pre-WS01 GOAD; reduced profile activation is blocked"
        )

    marker = directory / PROFILE_FILENAME
    if marker.is_symlink():
        raise ProfileNotReady("instance profile sidecar must not be a symlink")
    if marker.exists():
        if not marker.is_file():
            raise ProfileNotReady("instance profile sidecar is not a regular file")
        try:
            manifest = json.loads(marker.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError, OSError) as exc:
            raise ProfileNotReady("invalid instance profile sidecar") from exc
        roster = examine_profile_manifest(manifest)
        if observed != _EXPECTED_FULL:
            raise ProfileNotReady("explicit full profile requires all six Windows guests")
        return roster

    # Backwards compatibility: pre-profile six-/five-guest Vagrant instances
    # remain full GOAD. An implicit reduced deployment is never accepted.
    return FULL


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect read-only GOAD VMware instance profile binding")
    parser.add_argument("--check-provider", required=True,
                        help="Existing instance provider directory containing Vagrantfile")
    args = parser.parse_args()
    try:
        roster = inspect_instance_binding(args.check_provider)
    except (ProfileNotReady, OSError) as exc:
        parser.exit(1, "[BLOCK] " + str(exc) + "\n")
    print("[PASS] Legacy full-GOAD instance binding verified: " + roster.name)


if __name__ == "__main__":
    main()
