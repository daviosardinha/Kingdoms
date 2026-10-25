"""Read-only one-instance proof for recovering NORTH's installed metadata.

The native runtime acceptance script remains fully authoritative: this gate
ONLY permits its strict read-only live checks to run before status is installed.
The standard controller writes 'installed' iff the entire validator passes.
"""
from __future__ import annotations

import json
from pathlib import Path

INSTANCE = "8aafc9-north-vmware"
ATTEMPT = "20261024T231210Z-e678c23cc64a"
PRE_AD_MARKER = ".north-ws01-repaired-pre-ad-resume-used"
SRV02_MARKER = ".north-srv02-vmtools-repair-attempted"


class RecoveredRuntimeBlocked(ValueError):
    pass


def require(value, message):
    if not value:
        raise RecoveredRuntimeBlocked(message)


def prove_recovered_north_metadata(instance: Path, provider: Path, metadata: dict):
    """Validate source state + one-off operator recovery markers without writes."""
    require(instance.name == INSTANCE and provider == instance / "provider"
            and instance.is_dir() and not instance.is_symlink()
            and provider.is_dir() and not provider.is_symlink()
            and instance.resolve(strict=True) == instance
            and provider.resolve(strict=True) == provider,
            "Not the exact repaired NORTH instance")
    require(isinstance(metadata, dict)
            and (metadata.get("id"), metadata.get("lab"),
                 metadata.get("provider"), metadata.get("status")) ==
            (INSTANCE, "NORTH", "vmware", "not provided"),
            "Original instance metadata differs")
    mode = provider / ".goad-nomad-mode"
    require(mode.is_file() and not mode.is_symlink()
            and mode.read_text(encoding="utf-8").strip() == "exercise",
            "Recovered instance is not recorded in exercise mode")
    resume = instance / PRE_AD_MARKER
    repair = instance / SRV02_MARKER
    for marker in (resume, repair):
        require(marker.is_file() and not marker.is_symlink()
                and marker.stat().st_size <= 4096
                and marker.stat().st_mode & 0o077 == 0,
                "Recovered-instance repair marker missing or unsafe")
    require(resume.read_text(encoding="utf-8") ==
            ("NORTH repaired provider resume for " + INSTANCE +
             "\nAttempt " + ATTEMPT + "\nAuthorized first playbook: build.yml\n"),
            "Original one-shot pre-AD resume marker differs")
    require(repair.read_text(encoding="utf-8") ==
            ("One repair attempt for " + INSTANCE + "/GOAD-SRV02\n"),
            "Original CASTELBLACK repair marker differs")

    timing = instance / "install-timings"
    require(timing.is_dir() and not timing.is_symlink(),
            "Original NORTH installation receipt directory missing")
    receipts = sorted(timing.glob("*.json"))
    require(len(receipts) == 1 and receipts[0].is_file()
            and not receipts[0].is_symlink()
            and receipts[0].stat().st_size <= 1048576,
            "Expected one canonical original failed provider-install receipt")
    try:
        record = json.loads(receipts[0].read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise RecoveredRuntimeBlocked("Original receipt cannot be read") from exc
    require(isinstance(record, dict)
            and record.get("instance_id") == INSTANCE
            and record.get("attempt_id") == ATTEMPT
            and record.get("status") == "failed"
            and record.get("provider_success") is False
            and record.get("ansible_phases") == [],
            "Not the original failed-before-Ansible installation receipt")
    # The original receipt cannot prove the later 21-play recovery. Its job is
    # only to bind the exception to the exact failed VM generation. The
    # existing validator must still establish actual AD, trust, host network,
    # VMX, router-policy and exercise-state health independently.
    return True
