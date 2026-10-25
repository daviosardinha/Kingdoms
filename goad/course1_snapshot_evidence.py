"""Read-only, fail-closed NORTH five-VM snapshot generation evidence checks.

This module performs no VMware operations, guest changes, or network writes.
"""
import json
from pathlib import Path
import re

GUESTS = frozenset((
    "GOAD-ROUTER", "GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01"
))
NAME = re.compile(r"push_([0-9]{10,})_([0-9]+)\Z")


class SnapshotEvidenceError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise SnapshotEvidenceError(reason)


def read_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    require(isinstance(value, dict), "Snapshot inventory must be a JSON object")
    return value


def prove_generation(before, after):
    """Return the five newly created snapshots; refuse any ambiguous inventory."""
    require(isinstance(before, dict) and isinstance(after, dict) and
            set(before) == GUESTS and set(after) == GUESTS,
            "Five-VM NORTH snapshot roster is missing or changed")
    selected = {}
    timestamps = []
    for machine in sorted(GUESTS):
        old, new = before[machine], after[machine]
        require(isinstance(old, list) and isinstance(new, list) and
                all(isinstance(s, str) and NAME.fullmatch(s) for s in old + new),
                "Invalid push snapshot inventory: " + machine)
        require(len(old) == len(set(old)) and len(new) == len(set(new)),
                "Duplicate snapshot name: " + machine)
        added = set(new) - set(old)
        require(len(new) == len(old) + 1 and
                set(old).issubset(set(new)) and len(added) == 1,
                "Expected exactly one new snapshot: " + machine)
        name = added.pop()
        # The restore helper chooses the newest by push timestamp.
        old_stamps = [int(NAME.fullmatch(x).group(1)) for x in old]
        stamp = int(NAME.fullmatch(name).group(1))
        require(not old_stamps or stamp > max(old_stamps),
                "New snapshot is not the latest generation: " + machine)
        selected[machine] = name
        timestamps.append(stamp)
    require(max(timestamps) - min(timestamps) <= 900,
            "Five NORTH snapshots are not a common timed generation")
    return selected


def verify_restored_generation(selected, restore_log):
    """Verify each original guest selected and reverted the proven new snapshot."""
    log = Path(restore_log).read_text(encoding="utf-8")
    for guest, name in selected.items():
        for prefix in (
            "NORTH snapshot target: ", "NORTH offline snapshot restore verified: "
        ):
            marker = prefix + guest + " -> " + name
            require(log.count(marker) == 1,
                    "Missing or repeated exact restore marker: " + marker)
    # Do not accept extraneous snapshot targets from a different VM or generation.
    targets = re.findall(r"NORTH snapshot target: (GOAD-[A-Z0-9]+) -> (push_[0-9]+_[0-9]+)", log)
    restored = re.findall(r"NORTH offline snapshot restore verified: (GOAD-[A-Z0-9]+) -> (push_[0-9]+_[0-9]+)", log)
    expected = {(guest, name) for guest, name in selected.items()}
    require(set(targets) == expected and len(targets) == 5 and
            set(restored) == expected and len(restored) == 5,
            "Restore log targets or completed original VM snapshot generations differ")
    require("snapshot restored and offline exercise NIC" in log and
            "mode: exercise" in log,
            "Exercise isolation was not confirmed after offline restoration")


def audit_evidence(evidence_dir):
    """Retrospective certification of the captured snapshot/restore steps only."""
    folder = Path(evidence_dir)
    require(folder.is_dir() and not folder.is_symlink(), "Evidence directory invalid")
    before = read_json(folder / "snapshots-before.json")
    after = read_json(folder / "snapshots-after.json")
    selected = prove_generation(before, after)
    verify_restored_generation(selected, folder / "05-snapshot-restore.log")
    for name in ("04-post-snapshot-health.log", "06-post-restore-health.log"):
        log = (folder / name).read_text(encoding="utf-8")
        require("[PASS] NORTH_RUNTIME_ACCEPTANCE=PASS" in log and
                "instance status is installed" in log and
                "[PASS] NORTH_EXERCISE_MODE_PRESERVED" in log,
                "NORTH authenticated runtime acceptance absent: " + name)
    owner = (folder / "07-owner-final.log").read_text(encoding="utf-8")
    require("[PASS] NORTH immutable owner" in owner and
            "[PASS] NORTH live vmnets" in owner,
            "Final NORTH host network ownership was not proven")
    summary = (folder / "summary.txt").read_text(encoding="utf-8")
    require("instance=8aafc9-north-vmware" in summary and
            "PASS | 03-snapshot-create" in summary and
            "PASS | 05-snapshot-restore" in summary and
            "PASS | 06-post-restore-health" in summary,
            "Snapshot lifecycle stage receipts are missing")
    return selected


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Evidence folder, or before/after JSON for --generation-only")
    parser.add_argument("--generation-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.generation_only:
            require(len(args.paths) == 2, "Generation check requires before and after inventory")
            selection = prove_generation(read_json(args.paths[0]), read_json(args.paths[1]))
        else:
            require(len(args.paths) == 1, "Evidence audit requires one evidence folder")
            selection = audit_evidence(args.paths[0])
    except (SnapshotEvidenceError, OSError, ValueError) as error:
        parser.exit(1, "[FAIL] NORTH_SNAPSHOT_EVIDENCE_AUDIT: " + str(error) + "\n")
    for machine, snapshot in sorted(selection.items()):
        print("[PASS] NORTH_SNAPSHOT_GENERATION=" + machine + " " + snapshot)
    if args.generation_only:
        print("[PASS] NORTH_FIVE_VM_SNAPSHOT_GENERATION=PASS")
    else:
        print("[PASS] NORTH_SNAPSHOT_EVIDENCE_AUDIT=PASS")
