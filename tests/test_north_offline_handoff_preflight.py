"""Fixture-only tests for safe, read-only NORTH handoff planning."""
from pathlib import Path

import pytest

from goad import course1_offline_handoff as handoff


def fixture(tmp_path):
    provider = tmp_path / "workspace" / "123abc-north-vmware" / "provider"
    provider.mkdir(parents=True)
    found = {}
    for vm in handoff.GUESTS:
        root = provider / ".vagrant" / "machines" / vm / "vmware_desktop"
        guest = root / ("unique-" + vm)
        guest.mkdir(parents=True)
        vmx = guest / "Windows.vmx"
        vmx.write_text('displayName = "' + vm + '"\n')
        (root / "id").write_text(str(vmx) + "\n")
        found[vm] = str(vmx)
    inventory = tmp_path / "inventory.vmls"
    lines = []
    for i, vm in enumerate(handoff.GUESTS):
        lines.extend((
            'vmlist' + str(i) + '.config = "' + found[vm] + '"',
            'index' + str(i) + '.id = "' + found[vm] + '"',
        ))
    # A foreign VM in the library should be unaffected.
    lines.append('vmlist77.config = "/other/vms/other.vmx"')
    inventory.write_text("\n".join(lines) + "\n")
    return provider, found, inventory


def test_exact_five_preserved_vms_and_ten_inventory_references(tmp_path, monkeypatch):
    provider, found, inventory = fixture(tmp_path)
    monkeypatch.setattr(handoff, "inspect_installed_north",
                        lambda _: ("owner+journal OK", "vmnet OK"))
    result = handoff.plan(provider, inventory, "registered")
    assert result["vm_count"] == 5
    assert result["vmx"] == found
    assert result["inventory_reference_count"] == 10
    assert result["network_ownership"] == ["owner+journal OK", "vmnet OK"]
    assert result["network_release_authorized"] is False
    assert "READ_ONLY" in result["mode"]


def test_no_registered_vm_after_manual_library_removal_preserves_disks(tmp_path, monkeypatch):
    provider, found, inventory = fixture(tmp_path)
    inventory.write_text('vmlist77.config = "/other/vms/other.vmx"\n')
    monkeypatch.setattr(handoff, "inspect_installed_north", lambda _: ("OK",))
    result = handoff.plan(provider, inventory, "unregistered")
    assert result["inventory_state"] == "unregistered"
    assert result["inventory_reference_count"] == 0
    assert all(Path(path).is_file() for path in found.values())


def test_refuse_registered_old_vm_when_unregistered_required(tmp_path, monkeypatch):
    provider, _, inventory = fixture(tmp_path)
    monkeypatch.setattr(handoff, "inspect_installed_north", lambda _: ("OK",))
    with pytest.raises(handoff.HandoffPlanError, match="Expected VMware library state"):
        handoff.plan(provider, inventory, "unregistered")


def test_partial_or_extra_provider_registrations_fail_closed(tmp_path):
    provider, found, inventory = fixture(tmp_path)
    inv = inventory.read_text()
    inventory.write_text(inv.replace('index0.id = "' + found["GOAD-DC01"] + '"', ""))
    with pytest.raises(handoff.HandoffPlanError, match="Incomplete/foreign"):
        handoff.inventory_state(provider, found, inventory)
    inventory.write_text(inv + 'vmlist88.config = "' + str(provider / "foreign.vmx") + '"\n')
    with pytest.raises(handoff.HandoffPlanError, match="Incomplete/foreign"):
        handoff.inventory_state(provider, found, inventory)


def test_missing_vmx_or_symlinked_marker_is_rejected(tmp_path):
    provider, found, _ = fixture(tmp_path)
    victim = Path(found["GOAD-DC01"])
    victim.unlink()
    with pytest.raises(handoff.HandoffPlanError, match="VMX identity"):
        handoff.expected_guest_vmx(provider)
    victim.write_text("exists\n")
    marker = provider / ".vagrant/machines/GOAD-DC01/vmware_desktop/id"
    marker.unlink()
    marker.symlink_to(tmp_path / "foreign")
    with pytest.raises(handoff.HandoffPlanError, match="symlinked"):
        handoff.expected_guest_vmx(provider)


def test_refuses_duplicate_vagrant_guest_identity(tmp_path):
    provider, found, _ = fixture(tmp_path)
    marker = provider / ".vagrant/machines/GOAD-DC02/vmware_desktop/id"
    marker.write_text(found["GOAD-DC01"] + "\n")
    with pytest.raises(handoff.HandoffPlanError, match="VMX identity"):
        handoff.expected_guest_vmx(provider)


def test_read_only_design_contains_no_host_mutation_actions():
    source = (Path(__file__).resolve().parents[1]
              / "goad/course1_offline_handoff.py").read_text()
    for forbidden in ("unlink(", "rmtree(", "os.replace(", "shutil.move(",
                      "vmrun -T ws deleteVM", "vmrun -T ws unregister",
                      "subprocess.run(", "systemctl stop", "vmware-networks --stop"):
        assert forbidden not in source


def test_public_north_wrapper_exposes_only_read_only_plan():
    source = (Path(__file__).resolve().parents[1]
              / "scripts/setup-vmware-networks.sh").read_text()
    assert 'if [[ "${1:-}" == "handoff-plan" ]]; then' in source
    assert "python3 -m goad.course1_offline_handoff" in source
