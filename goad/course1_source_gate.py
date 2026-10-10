"""Fail-closed inspection of a private Kingdoms Course 1 source preview.

This deliberately does NOT register a lab, create a workspace, install a guest,
resolve the preview via GoadPath, or confer any lifecycle authorization. It
validates a separately generated preview against the current canonical sources.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import stat
from dataclasses import dataclass
from pathlib import Path

from goad.course1_instance_binding import parse_instance_vagrant_roster
from goad.course1_runtime_contract import COURSE1, ROUTER, ProfileNotReady

PROJECT = Path(__file__).resolve().parents[1]
GENERATOR = PROJECT / "scripts/course1/generate-profile.py"


@dataclass(frozen=True)
class SourcePreview:
    root: Path
    profile: str
    windows: tuple[str, ...]
    router: str
    file_count: int
    state: str = "PREVIEW_ONLY_NOT_INSTALLABLE"

    def summary(self) -> dict:
        return {
            "profile": self.profile,
            "state": self.state,
            "windows_machines": list(self.windows),
            "router": self.router,
            "verified_files": self.file_count,
            "deployment_authorized": False,
        }


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ProfileNotReady(reason)


def _safe_directory(path: Path) -> None:
    _require(not path.is_symlink() and path.is_dir(),
             "preview directory missing or symlinked")
    _require(stat.S_IMODE(path.stat().st_mode) & 0o077 == 0,
             "preview directory exposes confidential lab fixtures")


def _validate_location(directory: Path) -> Path:
    """Reject Git checkouts and all paths that resemble installed workspaces."""
    _require(directory.is_absolute(), "provide an absolute private preview path")
    _require(not directory.is_symlink(), "preview root may not be a symlink")
    for ancestor in (directory, *directory.parents):
        _require(not ancestor.is_symlink(), "private preview path traverses a symlink")
    try:
        candidate = directory.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ProfileNotReady("cannot resolve private preview directory") from exc
    _safe_directory(candidate)
    _require(not candidate.is_relative_to(PROJECT),
             "private preview cannot be inside the Kingdoms Git checkout")
    for ancestor in (candidate, *candidate.parents):
        _require(ancestor.name != "workspace",
                 "preview may not be placed inside an installed workspace tree")
        _require(not (ancestor / "instance.json").exists()
                 and not (ancestor / ".vagrant").exists()
                 and not (ancestor / ".goad-nomad-mode").exists(),
                 "preview path overlaps an installed instance or Vagrant state")
    return candidate


def _generator_render() -> dict[str, str]:
    # Load the existing verified generator, not a candidate-controlled script.
    spec = importlib.util.spec_from_file_location("kingdoms_course1_preview", GENERATOR)
    _require(spec is not None and spec.loader is not None,
             "cannot load canonical Course 1 source generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.render()


def inspect_source_preview(directory: str | Path) -> SourcePreview:
    """Read and compare every preview artifact, without writing or executing it.

    Paths and file contents are checked against the current source generator.
    A matching preview is still NOT an installable instance or activation token.
    """
    root = _validate_location(Path(directory).expanduser())
    expected = _generator_render()
    _require(len(expected) == 7, "unexpected canonical Course 1 artifact set")

    for relpath, content in expected.items():
        target = root / relpath
        _require(not target.is_symlink() and target.is_file(),
                 "missing or symlinked Course 1 artifact: " + relpath)
        _require(target.resolve(strict=True).is_relative_to(root),
                 "Course 1 artifact escapes private preview: " + relpath)
        _require(stat.S_IMODE(target.stat().st_mode) & 0o077 == 0,
                 "Course 1 artifact permissions are unsafe: " + relpath)
        parent = target.parent
        while parent != root:
            _safe_directory(parent)
            parent = parent.parent
        # Constant-size digests avoid exposing fixture passwords or file contents
        # in diagnostics while proving byte-for-byte agreement.
        observed = hashlib.sha256(target.read_bytes()).digest()
        canonical = hashlib.sha256(content.encode("utf-8")).digest()
        _require(observed == canonical,
                 "Course 1 artifact differs from canonical source: " + relpath)

    discovered = set()
    for item in root.rglob("*"):
        _require(not item.is_symlink(), "symlink inside private Course 1 preview")
        if item.is_file():
            discovered.add(item.relative_to(root).as_posix())
        else:
            _require(item.is_dir(), "unsupported object in Course 1 preview")
            _safe_directory(item)
    _require(discovered == set(expected),
             "private preview has missing or unexpected files")

    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    _require(manifest.get("profile") == COURSE1.name,
             "unexpected Course 1 profile")
    _require(manifest.get("state") == "PREVIEW_ONLY_NOT_INSTALLABLE",
             "Course 1 preview must never claim activation")
    _require(tuple(manifest.get("windows_machines", [])) == COURSE1.windows,
             "Course 1 manifest guest roster mismatch")
    _require(manifest.get("router") == ROUTER, "Course 1 router mismatch")

    vm_names = parse_instance_vagrant_roster(
        (root / "instance-preview/Vagrantfile").read_text(encoding="utf-8")
    )
    _require(set(vm_names) == set(COURSE1.windows) | {ROUTER}
             and len(vm_names) == 5,
             "Course 1 rendered Vagrant roster mismatch")
    return SourcePreview(root, COURSE1.name, COURSE1.windows, ROUTER, len(expected))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-preview", required=True,
                        help="absolute path to separately generated private preview")
    args = parser.parse_args()
    try:
        selected = inspect_source_preview(args.check_preview)
    except (ProfileNotReady, OSError, ValueError, UnicodeError) as exc:
        parser.exit(1, "[BLOCK] " + str(exc) + "\n")
    print("[PASS] Private Kingdoms Course 1 preview matches current source")
    print(json.dumps(selected.summary(), indent=2))
    print("[BLOCKED] Course 1 has no install/start/stop/reset authorization")


if __name__ == "__main__":
    main()
