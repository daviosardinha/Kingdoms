"""NORTH source-only offline release review tests. No host operations."""
import hashlib
from pathlib import Path

import pytest

from goad import course1_offline_release_review as review


OWNED = b"""answer VNET_10_DHCP no
answer VNET_10_HOSTONLY_SUBNET 10.4.10.0
answer VNET_20_DHCP no
answer VNET_20_HOSTONLY_SUBNET 10.4.20.0
answer VNET_99_DHCP no
answer VNET_99_HOSTONLY_SUBNET 10.4.99.0
"""
FOREIGN = b"""answer VNET_1_DHCP no
answer VNET_8_HOSTONLY_SUBNET 192.168.213.0
add_nat_portfwd 8 tcp 5985 192.168.213.134 5985
"""


def test_preserves_foreign_lines_and_reports_three_removed_vmnets():
    current = FOREIGN + OWNED
    proposed, removed = review.propose_removed_north_vmnets(
        current, frozenset((10, 20, 99))
    )
    assert proposed == FOREIGN
    assert len(removed) == 6
    assert current == FOREIGN + OWNED
    assert b"VNET_10_" not in proposed


def test_rejects_missing_or_unknown_owned_vmnet_directives():
    with pytest.raises(review.HandoffPlanError, match="missing"):
        review.propose_removed_north_vmnets(
            OWNED.replace(b"answer VNET_99_DHCP no\n", b"").replace(
                b"answer VNET_99_HOSTONLY_SUBNET 10.4.99.0\n", b""
            ), frozenset((10, 20, 99))
        )
    with pytest.raises(review.HandoffPlanError, match="Unrecognized"):
        review.propose_removed_north_vmnets(
            OWNED + b"mystery VNET_10_UNEXPECTED x\n", frozenset((10, 20, 99))
        )


def test_does_not_remove_vmnet100_when_vmnet10_owned():
    proposal, _ = review.propose_removed_north_vmnets(
        OWNED + b"answer VNET_100_DHCP yes\n", frozenset((10, 20, 99))
    )
    assert proposal == b"answer VNET_100_DHCP yes\n"


def test_preview_is_read_only_and_treats_unreviewed_nat_rules_as_blockers(
    tmp_path, monkeypatch
):
    current = FOREIGN + OWNED
    config = tmp_path / "networking"
    config.write_bytes(current)
    monkeypatch.setattr(
        review, "plan",
        lambda provider, inventory, state: {
            "provider": str(provider),
            "vm_count": 5,
            "inventory_reference_count": 10,
            "network_ownership": ["owner and journal verified"],
        },
    )
    result = review.preview(tmp_path, tmp_path / "inventory", config)
    assert result["vm_count"] == 5
    assert result["nat_forward_count"] == 1
    assert result["fresh_install_blocked_by_forward_rules"] is True
    assert result["release_authorized"] is False
    assert result["vmnets_proposed_for_removal"] == [10, 20, 99]
    assert result["networking_before_sha256"] == hashlib.sha256(current).hexdigest()
    assert config.read_bytes() == current


def test_preview_without_nat_reports_no_nat_blocker(tmp_path, monkeypatch):
    config = tmp_path / "networking"
    config.write_bytes(OWNED)
    monkeypatch.setattr(
        review, "plan",
        lambda provider, inventory, state: {
            "provider": str(provider),
            "vm_count": 5,
            "inventory_reference_count": 10,
            "network_ownership": [],
        },
    )
    outcome = review.preview(tmp_path, tmp_path / "inventory", config)
    assert outcome["fresh_install_blocked_by_forward_rules"] is False
    assert outcome["release_authorized"] is False


def test_no_mutating_entrypoint_in_release_review():
    source = (Path(__file__).resolve().parents[1]
              / "goad/course1_offline_release_review.py").read_text()
    for forbidden in (
        "unlink(", "rmtree(", "os.replace(", "shutil.move(",
        "subprocess.run(", "systemctl stop", "vmware-networks --stop", "vmrun -T ws",
    ):
        assert forbidden not in source
