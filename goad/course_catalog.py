"""Native Kingdoms course registry layered on the existing ad/<LAB>/providers tree.

Course metadata is discovery-only: it never authorizes a provider or writes an
instance. Until its provider implementation passes full runtime acceptance,
a course with a manifest is strictly non-installable.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from goad.goadpath import GoadPath
from goad.kingdoms_foundation import FOUNDATION_ID


class CourseCatalogError(ValueError):
    pass


def manifest_path(lab_name: str) -> Path:
    if not isinstance(lab_name, str) or not lab_name or "/" in lab_name or "\\" in lab_name or lab_name in (".", ".."):
        raise CourseCatalogError("invalid lab identifier")
    return Path(GoadPath.get_lab_path(lab_name)) / "course.json"


def is_course_lab(lab_name: str) -> bool:
    path = manifest_path(lab_name)
    return path.exists() or path.is_symlink()


def course_manifest(lab_name: str) -> dict | None:
    path = manifest_path(lab_name)
    if not (path.exists() or path.is_symlink()):
        return None
    if path.is_symlink() or not path.is_file():
        raise CourseCatalogError("course manifest must be a regular file")
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CourseCatalogError("course manifest is unreadable or invalid") from exc
    if not isinstance(info, dict) or info.get("lab") != lab_name:
        raise CourseCatalogError("course manifest lab identity mismatch")
    if not isinstance(info.get("title"), str) or not info["title"].strip():
        raise CourseCatalogError("course title missing")
    if not isinstance(info.get("runtime_profile"), str) or not info["runtime_profile"].strip():
        raise CourseCatalogError("runtime profile missing")
    if info.get("kingdoms_foundation") != FOUNDATION_ID:
        raise CourseCatalogError(
            "course must declare the current patched Kingdoms foundation"
        )
    if info.get("state") != "PREVIEW_ONLY_NOT_INSTALLABLE":
        raise CourseCatalogError("course release state not explicitly approved")
    providers = info.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise CourseCatalogError("course providers missing")
    for provider, status in providers.items():
        if not isinstance(provider, str) or not provider or status != "preview":
            raise CourseCatalogError("course provider readiness must be preview")
        if not (path.parent / "providers" / provider).is_dir():
            raise CourseCatalogError("course provider directory missing")
    return info


# An explicit disposable-first-install exception, not a general course release.
# The source-controlled manifest, narrow action allowlist, and operator
# acknowledgement must all agree. No env variable alone can authorize NORTH.
NORTH_PILOT_ID = "NORTH_VMWARE_DISPOSABLE_FIRST_INSTALL_20261010"
NORTH_PILOT_ENV = "KINGDOMS_NORTH_FIRST_INSTALL_PILOT"
NORTH_PILOT_ACTIONS = frozenset({
    "install/create", "install", "create_instance",
    "create_instance_folder", "install_instance",
    "provide", "provision_lab",
})


def north_first_install_pilot_authorized() -> bool:
    """Require committed NORTH identity AND an exact operator opt-in."""
    if os.environ.get(NORTH_PILOT_ENV) != NORTH_PILOT_ID:
        return False
    info = course_manifest("NORTH")
    return bool(
        info
        and info.get("lab") == "NORTH"
        and info.get("runtime_profile") == "course1-fall-of-the-north"
        and info.get("state") == "PREVIEW_ONLY_NOT_INSTALLABLE"
        and info.get("providers") == {"vmware": "preview"}
        and info.get("first_install_pilot") == NORTH_PILOT_ID
    )


def refuse_course_mutation(lab_name: str, action: str) -> bool:
    """True means caller MUST refuse the action; no artifact may be written."""
    if is_course_lab(lab_name):
        course_manifest(lab_name)  # malformed manifests fail closed
        if (lab_name == "NORTH"
                and action in NORTH_PILOT_ACTIONS
                and north_first_install_pilot_authorized()):
            return False
        return True
    return False
