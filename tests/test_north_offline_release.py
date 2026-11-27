"""NORTH-only offline owner release: synthetic tests, no VMware host writes."""
from contextlib import contextmanager
from collections import Counter
import json
import os
from pathlib import Path

import pytest

from goad import course1_offline_release as release
from goad import course1_vmnet_journal as journals


FOREIGN = (
    b"answer VNET_1_DHCP no\n"
    b"answer VNET_8_HOSTONLY_SUBNET 192.168.213.0\n"
    b"answer VNET_30_DHCP no\n"
    b"answer VNET_100_DHCP yes\n"
    b"add_nat_portfwd 8 tcp 39001 192.168.213.188 22\n"
)
FOREIGN_NAT = b"add_nat_portfwd 8 tcp 39001 192.168.213.188 22\n"


def configuration():
    baseline = FOREIGN
    north_lines = b"".join((x + "\n").encode() for x in release.NORTH_DECLS)
    forward_lines = b"".join((x + "\n").encode() for x in release.NORTH_NAT)
    labels = b"".join((x + "\n").encode() for x in release.OWNED_LABELS)
    return baseline, FOREIGN + labels + north_lines + forward_lines


def test_exact_13_nat_and_15_declarations_preserve_every_foreign_byte():
    original, installed = configuration()
    assert len(release.NORTH_NAT) == 13
    assert len(set(release.NORTH_NAT)) == 13
    assert len(release.NORTH_DECLS) == 15
    assert release.release_candidate(installed, original) == original
    assert release.nat_lines(original) == Counter([FOREIGN_NAT.decode().strip()])


def test_missing_or_duplicate_nat_rule_blocks_without_write():
    original, installed = configuration()
    nat = (release.NORTH_NAT[0] + "\n").encode()
    for changed in (installed.replace(nat, b""), installed + nat):
        with pytest.raises(release.NorthReleaseError, match="NAT delta"):
            release.release_candidate(changed, original)


def test_foreign_nat_removal_and_unknown_nat_addition_block():
    original, installed = configuration()
    with pytest.raises(release.NorthReleaseError, match="pre-NORTH NAT"):
        release.release_candidate(installed.replace(FOREIGN_NAT, b""), original)
    with pytest.raises(release.NorthReleaseError, match="NAT delta"):
        release.release_candidate(
            installed + b"add_nat_portfwd 8 tcp 55999 192.168.213.99 22\n",
            original,
        )


def test_missing_duplicate_and_unknown_vmnet_declarations_block():
    original, installed = configuration()
    line = (release.NORTH_DECLS[0] + "\n").encode()
    for changed in (installed.replace(line, b""), installed + line):
        with pytest.raises(release.NorthReleaseError, match="declarations"):
            release.release_candidate(changed, original)
    with pytest.raises(release.NorthReleaseError, match="Unknown"):
        release.release_candidate(
            installed + b"answer VNET_10_HOSTONLY_HOSTADDR 10.4.10.254\n",
            original,
        )


def test_north_release_never_matches_vmnet100_as_vmnet10():
    original, installed = configuration()
    assert b"VNET_100_" in release.release_candidate(installed, original)


def test_baseline_nat_is_not_deleted_even_if_current_NORTH_identical():
    original, installed = configuration()
    nat = (release.NORTH_NAT[0] + "\n").encode()
    with pytest.raises(release.NorthReleaseError, match="NAT delta"):
        release.release_candidate(installed, original + nat)


def test_manifest_checksum_independent_of_library_registration(tmp_path, monkeypatch):
    original, installed = configuration()
    network = tmp_path / "networking"
    network.write_bytes(installed)
    baseline = tmp_path / "baseline"
    baseline.write_bytes(original)
    provider = tmp_path / "provider"
    provider.mkdir()
    owner = tmp_path / "owner.json"
    owner.write_text(json.dumps({"backup": str(baseline)}))
    states = []
    def fake_plan(p, inv, expect):
        states.append(expect)
        return {
            "provider": str(p), "vm_count": 5,
            "inventory_reference_count": 10 if expect == "registered" else 0,
            "vmx": {"VM" + str(i): str(tmp_path / (str(i) + ".vmx"))
                    for i in range(5)},
        }
    monkeypatch.setattr(release, "plan", fake_plan)
    monkeypatch.setattr(release, "verify_vagrant_ports", lambda provider: {})
    monkeypatch.setattr(release, "_read_assets",
                        lambda *args: {"helper": b"h", "service": b"s", "timer": b"t"})
    a = release.manifest(provider, tmp_path / "inventory", network, owner, "registered")
    b = release.manifest(provider, tmp_path / "inventory", network, owner, "unregistered")
    assert a["reviewed_sha256"] == b["reviewed_sha256"]
    assert a["inventory_references"] == 10
    assert b["inventory_references"] == 0
    assert a["release_authorized"] is False
    assert states == ["registered", "unregistered"]


def test_manifest_hash_changes_when_reviewed_config_drifts(tmp_path, monkeypatch):
    original, installed = configuration()
    network = tmp_path / "networking"
    network.write_bytes(installed)
    baseline = tmp_path / "baseline"
    baseline.write_bytes(original)
    provider = tmp_path / "provider"
    provider.mkdir()
    owner = tmp_path / "owner.json"
    owner.write_text(json.dumps({"backup": str(baseline)}))
    monkeypatch.setattr(release, "plan", lambda p, i, e:
                        {"provider": str(p), "vm_count": 5,
                         "inventory_reference_count": 10, "vmx": {"x": "y"}})
    monkeypatch.setattr(release, "verify_vagrant_ports", lambda provider: {})
    monkeypatch.setattr(release, "_read_assets",
                        lambda *args: {"helper": b"h", "service": b"s", "timer": b"t"})
    initial = release.manifest(provider, tmp_path / "inventory", network, owner)
    network.write_bytes(installed.replace(b"answer VNET_1_DHCP no",
                                          b"answer VNET_1_DHCP yes"))
    changed = release.manifest(provider, tmp_path / "inventory", network, owner)
    assert changed["reviewed_sha256"] != initial["reviewed_sha256"]


def test_new_release_journal_safely_blocks_incomplete_runs(tmp_path):
    root = tmp_path / "backup"
    root.mkdir(mode=0o700)
    folder = root / "release-mock"
    folder.mkdir(mode=0o700)
    data = {
        "schema": "kingdoms.north.offline-release.v1",
        "state": "PREPARED",
        "backup_folder": str(folder),
        "provider": "/fake/north/provider",
        "reviewed_sha256": "a" * 64,
    }
    (folder / "release.json").write_text(json.dumps(data))
    with pytest.raises(journals.VmnetJournalError, match="unfinished NORTH"):
        journals.require_reconciled(root)
    data["state"] = "COMMITTED_RELEASE"
    (folder / "release.json").write_text(json.dumps(data))
    journals.require_reconciled(root)


def test_journal_rejects_stranded_release_without_journal(tmp_path):
    folder = tmp_path / "release-stranded"
    folder.mkdir(mode=0o700)
    with pytest.raises(journals.VmnetJournalError, match="lacks a journal"):
        journals.require_reconciled(tmp_path)


def synthetic_transaction(tmp_path, monkeypatch, failure=None):
    original, installed = configuration()
    provider = tmp_path / "provider"
    provider.mkdir()
    vmx = {}
    for i in range(5):
        path = provider / (f"old-{i}.vmx")
        path.write_text("vmx remains untouched")
        vmx[str(i)] = path
    networking = tmp_path / "networking"
    networking.write_bytes(installed)
    owner = tmp_path / "owner.json"
    immutable_backup = tmp_path / "baseline"
    immutable_backup.write_bytes(original)
    owner.write_text(json.dumps({"backup": str(immutable_backup)}))
    inventory = tmp_path / "inventory"
    inventory.write_text("foreign vm registrations only")
    backup_root = tmp_path / "backups"
    backup_root.mkdir(mode=0o700)
    tools = tmp_path / "vmware-networks"
    tools.write_text("#!/bin/sh\nexit 0\n")
    tools.chmod(0o755)
    paths = {}
    for kind in ("helper", "service", "timer"):
        path = tmp_path / (kind + ".north")
        path.write_bytes(kind.encode())
        paths[kind] = path

    events = []
    monkeypatch.setattr(release, "require_explicit_root", lambda: None)
    monkeypatch.setattr(release, "_verify_no_running_vmware",
                        lambda: events.append("no-running-vms"))
    monkeypatch.setattr(release, "require_reconciled", lambda _: None)
    monkeypatch.setattr(release, "manifest", lambda *args, **kwargs:
                        {"reviewed_sha256": "a" * 64})
    monkeypatch.setattr(release, "asset_paths", lambda: paths)
    monkeypatch.setattr(release, "_read_assets",
                        lambda *args: {k: k.encode() for k in paths})
    monkeypatch.setattr(release, "_disable_timer",
                        lambda: events.append("disable-timer"))
    monkeypatch.setattr(release, "systemd_reload",
                        lambda: events.append("daemon-reload"))
    monkeypatch.setattr(release, "systemd_activate",
                        lambda: events.append("activate-timer"))
    monkeypatch.setattr(release, "inspect_clean_host",
                        lambda **kwargs: events.append("clean-host-check"))

    @contextmanager
    def lock(_):
        events.append("lock-acquired")
        yield
    monkeypatch.setattr(release, "exclusive_vmnet_lock", lock)

    class Restart:
        def __init__(self, *args):
            self.calls = 0

        def __call__(self):
            self.calls += 1
            events.append("restart")
            if failure == "restart" and self.calls == 1:
                raise RuntimeError("Injected VMware restart failure")
            if failure == "concurrent" and self.calls == 1:
                networking.write_bytes(networking.read_bytes() + b"# foreign edit\n")
                raise RuntimeError("Injected third-party edit")

    monkeypatch.setattr(release, "VMwareNetworkRestart", Restart)
    return (provider, inventory, networking, owner, backup_root, tools,
            original, installed, paths, events, vmx)


def test_release_success_owner_last_and_foreign_bytes_unchanged(tmp_path, monkeypatch):
    env = synthetic_transaction(tmp_path, monkeypatch)
    provider, inv, net, owner, backups, tools, original, installed, paths, events, vmx = env
    result = release.release(provider, inv, "a" * 64, net, owner, backups,
                             tmp_path / "no-netmap", tools)
    assert result["result"] == "COMMITTED_RELEASE"
    assert net.read_bytes() == original
    assert not owner.exists()
    assert not any(path.exists() for path in paths.values())
    assert all(path.read_text() == "vmx remains untouched" for path in vmx.values())
    assert events.index("disable-timer") < events.index("restart")
    folder = Path(result["release_backup"])
    assert json.loads((folder / "release.json").read_text())["state"] == "COMMITTED_RELEASE"
    assert (folder / "owner.retired").exists()


def test_release_restart_failure_restores_network_owner_assets(tmp_path, monkeypatch):
    env = synthetic_transaction(tmp_path, monkeypatch, failure="restart")
    provider, inv, net, owner, backups, tools, original, installed, paths, events, vmx = env
    with pytest.raises(release.NorthReleaseError, match="rolled back"):
        release.release(provider, inv, "a" * 64, net, owner, backups,
                        tmp_path / "no-netmap", tools)
    assert net.read_bytes() == installed
    assert owner.exists()
    assert all(p.exists() for p in paths.values())
    assert "activate-timer" in events
    state = json.loads(next(backups.glob("release-*/release.json")).read_text())["state"]
    assert state == "ROLLED_BACK"


def test_concurrent_foreign_edit_is_never_overwritten(tmp_path, monkeypatch):
    env = synthetic_transaction(tmp_path, monkeypatch, failure="concurrent")
    provider, inv, net, owner, backups, tools, original, installed, paths, events, vmx = env
    with pytest.raises(release.NorthReleaseError, match="manual reconciliation"):
        release.release(provider, inv, "a" * 64, net, owner, backups,
                        tmp_path / "no-netmap", tools)
    assert net.read_bytes().endswith(b"# foreign edit\n")
    assert owner.exists()
    state = json.loads(next(backups.glob("release-*/release.json")).read_text())["state"]
    assert state == "MANUAL_RECONCILIATION"


def test_stale_review_refuses_all_mutations(tmp_path, monkeypatch):
    env = synthetic_transaction(tmp_path, monkeypatch)
    provider, inv, net, owner, backups, tools, original, installed, paths, events, vmx = env
    before = installed
    with pytest.raises(release.NorthReleaseError, match="Manifest is stale"):
        release.release(provider, inv, "b" * 64, net, owner, backups,
                        tmp_path / "no-netmap", tools)
    assert net.read_bytes() == before
    assert owner.exists()
    assert not list(backups.glob("release-*"))
    assert "disable-timer" not in events
    assert "restart" not in events


def test_release_source_does_not_destroy_old_vms():
    code = (Path(__file__).resolve().parents[1]
            / "goad/course1_offline_release.py").read_text()
    for disallowed in ("vagrant destroy", "deleteVM", "rmtree(",
                       "shutil.rmtree(", "vmrun -T ws deleteVM"):
        assert disallowed not in code


def test_vagrant_port_proof_requires_exact_five_guest_maps(monkeypatch, tmp_path):
    import subprocess
    import pwd
    class Result:
        def __init__(self, value):
            self.returncode = 0
            self.stdout = value
    monkeypatch.setenv("SUDO_USER", "fictional")
    monkeypatch.setattr(pwd, "getpwnam", lambda user: object())

    def fake_run(command, **kwargs):
        vm = command[-1]
        pairs = release.EXPECTED_PORTS[vm]
        return Result("\n".join(f"{guest} (guest) => {host} (host)"
                                for guest, host in sorted(pairs)))
    monkeypatch.setattr(subprocess, "run", fake_run)
    actual = release.verify_vagrant_ports(tmp_path)
    assert len(actual) == 5
    assert sum(map(len, actual.values())) == 13
    assert actual["GOAD-ROUTER"] == [(22, 2222)]


def test_vagrant_port_proof_rejects_unexpected_forward(monkeypatch, tmp_path):
    import subprocess
    import pwd
    class Result:
        returncode = 0
        stdout = "22 (guest) => 2222 (host)\n"
    monkeypatch.setenv("SUDO_USER", "fictional")
    monkeypatch.setattr(pwd, "getpwnam", lambda user: object())
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Result())
    with pytest.raises(release.NorthReleaseError, match="Unexpected/duplicate"):
        release.verify_vagrant_ports(tmp_path)


def test_foreign_vm_started_mid_release_blocks_global_restart(tmp_path, monkeypatch):
    env = synthetic_transaction(tmp_path, monkeypatch)
    provider, inv, net, owner, backups, tools, original, installed, paths, events, vmx = env
    calls = {"count": 0}
    def changing_vm_state():
        calls["count"] += 1
        if calls["count"] >= 4:
            raise release.NorthReleaseError("A foreign VMware VM started")
    monkeypatch.setattr(release, "_verify_no_running_vmware", changing_vm_state)
    with pytest.raises(release.NorthReleaseError, match="manual reconciliation"):
        release.release(provider, inv, "a" * 64, net, owner, backups,
                        tmp_path / "no-netmap", tools)
    # Fail closed: never restart the networking service underneath any guest.
    assert "restart" not in events
    assert owner.exists()
    assert net.read_bytes() != installed
    assert json.loads(next(backups.glob("release-*/release.json")).read_text())["state"] == "MANUAL_RECONCILIATION"
