"""Read-only, evidence-honest WSLPE 45 completion dashboard.

Derived from the frozen 45-ID catalog and the current 25-fixture source index.
This module intentionally never contacts VMware, WinRM, Ansible, or NORTH.
A source candidate or green CI run is NOT a learner exploit or live qualification.
"""
from __future__ import annotations

import json
from collections import Counter

from kingdoms.wslpe_batch_catalog import catalog
from kingdoms import wslpe45_batch_operator as batch

RELEASE_GATES = (
    "new_25_six_stage_windows_lifecycle",
    "all_45_real_nonadmin_exploit_proofs",
    "negative_authorization_and_owned_reset",
    "local_learner_rdp_nla",
    "dedicated_operator_handoff_and_bootstrap_retirement",
    "guest_to_north_host_hypervisor_isolation",
    "clean_install_and_restore_reproducibility",
    "per_instance_secrets_and_licensing",
    "course_walkthrough_acceptance",
)


def report() -> dict:
    catalog_rows = catalog()
    extension = batch.index_rows()
    _, source_blockers = batch.source_readiness()
    if len(catalog_rows) != 45 or len(extension) != 25:
        raise ValueError("Unexpected standalone course cardinality")

    blockers_by_number: dict[int, list[str]] = {}
    for message in source_blockers:
        if not message.startswith("#") or len(message) < 4:
            raise ValueError("Unexpected batch source blocker format")
        number = int(message[1:3])
        if number < 21 or number > 45:
            raise ValueError("Out-of-range batch source blocker")
        blockers_by_number.setdefault(number, []).append(message[4:])
    source_rows = {entry["number"]: entry for entry in extension}
    result = []

    for item in catalog_rows:
        number = item["number"]
        if number <= 20:
            result.append({
                "number": number,
                "id": item["id"],
                "group": "foundation",
                "source": "existing_verified_foundation",
                "six_stage_lifecycle": "accepted_prior_standalone_evidence",
                "learner_exploit": "not_verified",
                "source_blockers": [],
            })
            continue

        entry = source_rows[number]
        if entry["id"] != item["id"]:
            raise ValueError("Source index disagrees with frozen 45-technique catalog")
        blockers = blockers_by_number.get(number, [])
        source = (
            "candidate_source_ready" if (
                entry["status"] == "candidate" and
                entry["source_ci"] == "passed" and not blockers
            ) else "source_incomplete"
        )
        result.append({
            "number": number,
            "id": item["id"],
            "group": item["stage"],
            "source": source,
            "six_stage_lifecycle": "not_verified",
            "learner_exploit": "not_verified",
            "source_blockers": blockers,
        })

    new = result[20:]
    source_complete = sum(row["source"] == "candidate_source_ready" for row in new)
    lifecycle_accepted = sum(
        row["six_stage_lifecycle"] == "accepted_prior_standalone_evidence"
        for row in result
    )
    current = {
        "schema": "kingdoms.wslpe45.closeout.v1",
        "scope": "standalone-wslpe-only",
        "machine": "WSLPE-WS01",
        "north_frozen": True,
        "no_guest_contact": True,
        "counts": {
            "target": 45,
            "foundation_lifecycle_evidence": lifecycle_accepted,
            "additional_source_candidates": source_complete,
            "additional_source_incomplete": 25 - source_complete,
            "additional_six_stage_qualified": 0,
            "independent_learner_exploit_accepted": 0,
        },
        "release_gates": {name: "not_verified" for name in RELEASE_GATES},
        "ready_for_batch_execution": False,
        "ready_for_learner_release": False,
        "techniques": result,
    }
    return current


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true",
                        help="show all 45 rows with separate source/runtime/proof states")
    args = parser.parse_args(argv)
    current = report()
    if args.json:
        print(json.dumps(current, indent=2))
        return 0
    c = current["counts"]
    print("[SCOPE] Standalone WSLPE-WS01 only; frozen NORTH")
    print(f"[FOUNDATION] {c['foundation_lifecycle_evidence']}/20 provision/reset lifecycle accepted")
    print(f"[NEW SOURCE] {c['additional_source_candidates']}/25 candidates, "
          f"{c['additional_source_incomplete']} unfinished")
    print("[NEW RUNTIME] 0/25 six-stage qualifications accepted")
    print("[LEARNER] 0/45 independent exploit proofs accepted")
    print("[RELEASE] BLOCKED: source CI alone cannot authorize an LPE course")
    for row in current["techniques"][20:]:
        if row["source"] != "candidate_source_ready":
            reason = "; ".join(row["source_blockers"]) or "source incomplete"
            print(f"[SOURCE BLOCKED] #{row['number']:02d} {row['id']}: {reason}")
    print("[NEXT] Finish missing source mechanisms as a batch; then reviewed live qualification")
    print("[NO VM CHANGES] No guest, VMware, NORTH, Ansible or WinRM interaction")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
