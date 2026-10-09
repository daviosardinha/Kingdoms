"""Kingdoms-patched foundation contract for NORTH and all future courses.

Historical names such as ad/GOAD, GOAD-WS01 and goad.sh are compatibility
names, NOT permission to reload upstream GOAD defaults. The authoritative
baseline is the patched source in THIS Kingdoms repository.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

FOUNDATION_ID = "kingdoms-foundation-v1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
KINGDOMS_REFERENCE_RECIPE = Path("ad/GOAD")

# Contract sentinels for hard-won Kingdoms fixes. This does not replace
# their existing behavior/regression tests: it prevents silently choosing
# an upstream provider/template or deleting an established safety layer.
# Each tuple is (named protection, source evidence).
PROTECTIONS = {
    "goad/provider/vagrant/vmware.py": (
        ("stable_winrm", "def _wait_winrm_ready("),
        ("vmware_tools_recovery", "def _ensure_vmware_tools("),
        ("vmware_guest_ip_readiness", "def _wait_guest_ip("),
        ("isolated_inventory_repair", "def _sync_goad_nomad_inventories("),
    ),
    "goad/provider/vagrant/vmware_nomad.py": (
        ("segmented_router_provisioning", "def _bootstrap_provisioning_plane("),
        ("provisioning_finalization", "def finalize_install("),
        ("lab_mode_binding", "def is_goad_nomad_segmented("),
    ),
    "goad/provider/vagrant/vmware_kingdoms.py": (
        ("noninteractive_privilege_gate", "def _require_cached_sudo("),
        ("instance_collision_preflight", "def _check_segmented_instance_conflicts("),
        ("preserve_guest_processes_on_timeout", "def _vagrant_cleanup_targets("),
        ("bounded_vagrant_execution", "def _run_vagrant_bounded("),
        ("validated_kingdoms_router_start", "def _bring_up_router("),
    ),
    "goad/provider/vagrant/vmware_kingdoms_profile.py": (
        ("install_phase_profiling", "def _profile_call("),
        ("timed_inventory_sync", "def _sync_goad_nomad_inventories("),
    ),
    "scripts/lab-mode.sh": (
        ("exercise_isolation_mode", "enter_exercise_mode()"),
        ("temporary_provisioning_mode", "enter_provisioning_mode()"),
        ("router_policy_application", "apply_router_policy()"),
        ("parent_child_ad_readiness", "wait_domain_controller_ready()"),
        ("domain_member_readiness", "wait_domain_member_ready()"),
        ("child_time_authority", "ensure_child_dc_time_ready()"),
        ("isolated_guest_checks", "prove_isolated_guest_ready()"),
    ),
    "scripts/verify-test-source.sh": (
        ("clean_tree_gate", "working tree is not clean"),
        ("pinned_git_upstream_gate", "git fetch --all --prune --quiet"),
    ),
    "template/provider/vmware/Vagrantfile": (
        ("offline_box_metadata_gate", "config.vm.box_check_update = false"),
        ("vmware_winrm_ip_lookup_fix", "v.enable_vmrun_ip_lookup = false"),
    ),
    "vagrant/fix_ip.ps1": (
        ("windows_multizone_route", "10.4.0.0"),
        ("windows_segmented_nic", "GOAD_NOMAD"),
    ),
    "ad/GOAD/providers/vmware/Vagrantfile": (
        ("reference_vmnet_north", 'vmnet10'),
        ("reference_vmnet_parent", 'vmnet20'),
        ("reference_vmnet_essos", 'vmnet30'),
        ("reference_vmnet_management", 'vmnet99'),
        ("reference_windows_workstation", 'GOAD-WS01'),
        ("reference_router_guest", 'GOAD-ROUTER'),
    ),
    "ad/GOAD/providers/vmware/router/provision.sh": (
        ("router_mac_bound_nics", "find_iface_by_mac()"),
        ("router_static_gateways", "configure_lab_interface()"),
        ("router_nftables", "table inet goad_nomad"),
    ),
    "scripts/router-ssh.sh": (
        ("instance_bound_router_ssh", "GOAD_PROVIDER_DIR"),
        ("router_address_collision_preflight", "Host owns router address"),
    ),
    "scripts/provisioning-routes.sh": (
        ("temporary_host_routes_only", "enable_routes()"),
        ("route_cleanup", "disable_routes()"),
    ),
}


class KingdomsFoundationError(ValueError):
    """The patched Kingdoms base has changed: block derived course output."""


def reference_recipe(root: Path = PROJECT_ROOT) -> Path:
    """Return the patched reference recipe IN Kingdoms, not an upstream checkout."""
    return root / KINGDOMS_REFERENCE_RECIPE


def validate_foundation(
    root: Path = PROJECT_ROOT,
    reader: Callable[[str], str] | None = None,
) -> dict:
    """Fail closed when a named Kingdoms protection or file goes missing.

    This verifies source structure only. The full Python, Ansible, shell,
    networking and runtime regressions remain mandatory for deployment.
    """
    if reader is None:
        def reader(relative_path: str) -> str:
            path = root / relative_path
            if path.is_symlink() or not path.is_file():
                raise KingdomsFoundationError(
                    f"missing/unsafe Kingdoms foundation source: {relative_path}"
                )
            try:
                return path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise KingdomsFoundationError(
                    f"unreadable Kingdoms foundation source: {relative_path}"
                ) from exc

    capabilities = []
    for relpath, checks in PROTECTIONS.items():
        content = reader(relpath)
        if not isinstance(content, str):
            raise KingdomsFoundationError(
                f"invalid Kingdoms foundation source: {relpath}"
            )
        for label, marker in checks:
            if marker not in content:
                raise KingdomsFoundationError(
                    f"Kingdoms foundation regression: {label} in {relpath}"
                )
            capabilities.append(label)

    return {
        "foundation": FOUNDATION_ID,
        "authority": "kingdoms-patched-repository",
        "reference_recipe": KINGDOMS_REFERENCE_RECIPE.as_posix(),
        "verified_files": len(PROTECTIONS),
        "verified_protections": len(capabilities),
        "upstream_goad_configuration_allowed": False,
        "course_install_authorized": False,
    }
