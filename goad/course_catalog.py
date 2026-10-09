"""Native Kingdoms course registry layered on the existing ad/<LAB>/providers tree.

Course metadata is discovery-only: it never authorizes a provider or writes an
instance. Until its provider implementation passes full runtime acceptance,
a course with a manifest is strictly non-installable.
"""
from __future__ import annotations

import json
from pathlib import Path

from goad.goadpath import GoadPath


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


def refuse_course_mutation(lab_name: str, action: str) -> bool:
    """True means caller MUST refuse the action; no artifact may be written."""
    if is_course_lab(lab_name):
        course_manifest(lab_name)  # malformed manifests fail closed
        return True
    return False
