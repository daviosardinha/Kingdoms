"""Immutable 41-scenario scope for an independent *fresh* WSLPE build.

This is an installer's source contract, not a Windows deployment runner.
Never infer a fresh 41/41 installation from the old golden-master journal.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kingdoms.wslpe_batch_catalog import FROZEN_FOUNDATION, catalog

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {
    25: "msi_repair_custom_action",
    36: "wmi_privileged_provider_authorization",
    38: "dcom_server_launch_acl",
    40: "custom_rpc_authorization",
}
SELECTED_ADDITIONS = tuple(n for n in range(21, 46) if n not in EXCLUDED)
EXPECTED_NUMBERS = tuple(range(1, 21)) + SELECTED_ADDITIONS


class FreshInstallContractError(ValueError):
    """Refuse any unexpected scope or missing scenario source."""


@dataclass(frozen=True)
class FreshScenario:
    number: int
    identifier: str
    playbook: str
    execution_channel: str


def fresh_scenario_manifest() -> tuple[FreshScenario, ...]:
    """Resolve real source definitions, never hardcode a substitute 41-ID list."""
    rows = catalog()
    if len(rows) != 45 or tuple(r["number"] for r in rows) != tuple(range(1, 46)):
        raise FreshInstallContractError("Original 45-ID catalog changed")
    if tuple(r["id"] for r in rows[:20]) != tuple(FROZEN_FOUNDATION):
        raise FreshInstallContractError("Shared NORTH/WSLPE foundation drift")
    if {r["number"]: r["id"] for r in rows if r["number"] in EXCLUDED} != EXCLUDED:
        raise FreshInstallContractError("Four explicit exclusions changed")

    result: list[FreshScenario] = []
    for row in rows:
        number = row["number"]
        if number not in EXPECTED_NUMBERS:
            continue
        identifier = row["id"]
        if number <= 20:
            path = "ansible/wslpe-lpe-test.yml"
            channel = "standalone_ansible"
        elif number == 30:
            # Windows PowerShell 5.1 can stop WinRM during JEA registration.
            # It must be installed through independently recovered guest console,
            # not by reusing the existing golden master's JEA registration.
            path = "ansible/wslpe45/jea_local_stage.yml"
            channel = "out_of_band_jea_activation"
        else:
            path = (
                "ansible/wslpe45/traversal.yml" if number == 35
                else f"ansible/wslpe45/{identifier}.yml"
            )
            channel = "standalone_ansible"
        source = ROOT / path
        if source.is_symlink() or not source.is_file():
            raise FreshInstallContractError(f"Missing or unsafe scenario source: #{number}")
        result.append(FreshScenario(number, identifier, path, channel))

    if (len(result) != 41 or tuple(r.number for r in result) != EXPECTED_NUMBERS
            or len({r.identifier for r in result}) != 41):
        raise FreshInstallContractError("Fresh WSLPE scope must be exactly 41 unique IDs")
    if len([r for r in result if r.execution_channel == "out_of_band_jea_activation"]) != 1:
        raise FreshInstallContractError("JEA #30 independent activation is mandatory")
    return tuple(result)
