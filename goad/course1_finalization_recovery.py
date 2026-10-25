"""Read-only, single-attempt NORTH final-isolation metadata recovery gate.

This does NOT mark any instance installed. It allows the existing strict native
runtime validator to run against the precise sixth clean install whose 21
playbooks passed but whose final mode-record guard failed. The normal
GOAD_NOMAD validate command alone promotes status after live checks pass.
"""
from __future__ import annotations

import json
from pathlib import Path

INSTANCE = "0da0a9-north-vmware"
ATTEMPT = "20261025T185129Z-e9bb62a88403"
PLAYBOOKS = (
    "build.yml", "ad-servers.yml", "ad-parent_domain.yml",
    "ad-child_domain.yml", "wait5m.yml", "ad-members.yml",
    "kingdoms-time-backoff.yml", "ad-data.yml", "ws01.yml",
    "ad-gmsa.yml", "laps.yml", "ad-relations.yml", "adcs.yml",
    "ad-acl.yml", "servers.yml", "security.yml", "kingdoms-health.yml",
    "vulnerabilities.yml", "phase01.yml", "ws01-lpe-install.yml",
    "kingdoms-health-final.yml",
)


class NorthFinalizationRecoveryBlocked(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise NorthFinalizationRecoveryBlocked(message)


def prove_north_finalization_recovery(instance: Path, provider: Path,
                                     metadata: dict) -> bool:
    """Prove the exact successful-provisioning/failed-isolation receipt.

    All checks are read-only. The installer status must remain unmodified until
    validate-north-runtime.sh independently proves every live acceptance gate.
    """
    require(
        instance.name == INSTANCE
        and provider == instance / "provider"
        and instance.is_dir() and not instance.is_symlink()
        and provider.is_dir() and not provider.is_symlink()
        and instance.resolve(strict=True) == instance
        and provider.resolve(strict=True) == provider,
        "Not the exact recovered sixth NORTH instance",
    )
    require(
        isinstance(metadata, dict)
        and (metadata.get("id"), metadata.get("lab"),
             metadata.get("provider"), metadata.get("status"))
        == (INSTANCE, "NORTH", "vmware", "ready for provisioning"),
        "Instance metadata is not the original pending NORTH installation",
    )
    mode = provider / ".goad-nomad-mode"
    require(
        mode.is_file() and not mode.is_symlink()
        and mode.read_text(encoding="utf-8").strip() == "exercise",
        "Exact instance is not recorded in exercise mode",
    )
    timing = instance / "install-timings"
    require(timing.is_dir() and not timing.is_symlink(),
            "NORTH installation evidence directory absent or unsafe")
    receipt = timing / (ATTEMPT + ".json")
    require(
        receipt.is_file() and not receipt.is_symlink()
        and receipt.stat().st_size <= 1048576,
        "Exact failed-finalization receipt absent or unsafe",
    )
    try:
        data = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise NorthFinalizationRecoveryBlocked(
            "Exact installation receipt is not readable JSON"
        ) from exc
    require(
        isinstance(data, dict)
        and (data.get("instance_id"), data.get("attempt_id"),
             data.get("status"), data.get("provider_success"))
        == (INSTANCE, ATTEMPT, "failed", True)
        and data.get("partial") is False,
        "Receipt is not the exact failed-after-provisioning attempt",
    )
    phases = data.get("ansible_phases")
    require(isinstance(phases, list) and bool(phases),
            "Missing recorded Ansible phase outcomes")
    require(all(isinstance(row, dict)
                and isinstance(row.get("label"), str)
                and row.get("outcome") in ("succeeded", "failed")
                for row in phases),
            "Invalid Ansible phase evidence")
    normal = [
        (row["label"], row["outcome"])
        for row in phases if row.get("kind") != "playbook_attempt"
    ]
    expected = [
        ("Provisioning management-plane preparation", "succeeded"),
        *((f"Playbook {name}", "succeeded") for name in PLAYBOOKS),
        ("Final exercise-mode transition", "failed"),
    ]
    require(normal == expected,
            "Receipt does not prove all 21 NORTH playbooks passed before final isolation")
    require(all(row["outcome"] == "succeeded"
                for row in phases if row.get("kind") == "playbook_attempt"),
            "Receipt contains an unsuccessful playbook attempt")
    return True
