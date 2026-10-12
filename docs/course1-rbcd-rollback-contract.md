# NORTH Phase 03 — RBCD exact-object rollback contract

**Status: source implementation pending live acceptance.** Does not enable
`--run-rbcd`, start listeners, modify AD, or change the existing snapshot.
The legacy `scripts/phase03/rollback-rbcd.sh` remains unchanged for GOAD
compatibility. Do not call it for NORTH: it can remove a candidate by name
alone and uses generic GOAD inventory defaults.

## Safety boundaries and evidence

1. Obtain a **fresh clean** NORTH WS01$ baseline after any VM snapshot
   restoration. The baseline is a private `rbcd-baseline.json` with
   `CapturedAtUtc`, original target DN, exact RBCD descriptor presence and
   `CandidateExisted=False`. `rbcd-baseline.sha256` accompanies it.
2. After the controlled Stage 1 relay creates `PHASE03RBCD$`, but **before**
   any delegation change, run the separate Stage 1 ownership registrar.
   It reads live AD on WINTERFELL through the NORTH inventories. It checks
   that the account was created *after* the baseline, its DN is in NORTH,
   WS01 still has no RBCD entry, and the target DN matches the baseline.
   It writes `rbcd-ownership.json` containing candidate **SID, GUID, DN,
   created time**, target DN, and baseline SHA-256. This is evidence tied
   to the exact run. It is not cryptographic proof of who created the AD
   object; the active Stage 1 acceptance must separately prove creation
   through the expected relay.
3. The NORTH rollback accepts only the selected baseline and matching
   ownership receipt. Before ANY AD mutation, it validates the candidate's
   live SID, GUID, DN and creation time; ensures the target is WS01 in NORTH,
   the original state was clean, and the current RBCD descriptor is either
   absent or contains exactly one ACE identifying the recorded candidate
   SID. Unexpected delegation entries, replaced computer objects, or an
   invalid receipt block rollback without deleting anything.
4. Only after those checks does it clear the WS01 RBCD attribute (if set)
   and delete the *exact* matching candidate (if present). The action is
   safely re-runnable after a partial failure where either change completed,
   as long as the remaining state still matches the ownership evidence.
   No generic name-based deletion, snapshot revert, broad process kill,
   or password change is allowed.
5. The rollback must be followed by the existing **independent** read-only
   `phase03-rbcd-verify-neutral.yml`. PASS means WS01's RBCD descriptor
   and PHASE03RBCD$ candidate state match the recorded original baseline.
   The mutation playbook's own "complete" marker is insufficient.

The Bash wrapper holds the existing Phase 03 lock, requires explicit
`--apply --confirm`, checks owner-only 0700/0600 evidence and both hashes,
checks that no NTLM relay/mitm6 session remains, and validates the installed
GitHub source and live VMnet owner before modifying AD. It writes all
rollback and independent verification output to a new private evidence
directory. The baseline and ownership receipt remain intact for audit.

A failed rollback is a **stop condition**: no automatic reset or destructive
retry, and no new RBCD/Shadow Credentials scenario until reviewed. If the
Stage 1 registration is interrupted before writing the SID/GUID receipt,
the automated NORTH rollback **must refuse deletion**. Investigate and
establish object provenance first; do not bypass the guard.

## Operator validation — before any attack

```bash
cd "$HOME/kingdoms-rebuild" && git pull --ff-only
python3 -m unittest tests.test_course1_rbcd_rollback_contract \
  tests.test_course1_rbcd_baseline_paths \
  tests.test_course1_rbcd_neutral tests.test_phase03_overlay_source
sudo -v
bash scripts/course1-phase03-acceptance.sh \
  ac9fda-north-vmware --prepare-rbcd --confirm
```

The last command is **read-only against AD** and prints the new baseline
path. Keep that exact path; do not select the old pre-restore baseline.

After Stage 1 creation is proven in the active acceptance and BEFORE Stage 2
writes any delegation, register exact ownership:

```bash
bash scripts/course1-phase03-rbcd-register.sh \
  ac9fda-north-vmware "$BASELINE" --register --confirm
```

After Stage 2, S4U, and access proof, stop the relay listener(s).
Preview rollback:

```bash
bash scripts/course1-phase03-rbcd-rollback.sh \
  ac9fda-north-vmware "$BASELINE" --plan
```

Explicit instructor-controlled directory cleanup:

```bash
bash scripts/course1-phase03-rbcd-rollback.sh \
  ac9fda-north-vmware "$BASELINE" --apply --confirm
```

**Do not execute the cleanup commands until Stage 1 ownership registration
and controlled Stage 2 proof are operationally validated.** Success criteria:

```text
PHASE03_RBCD_STAGE1_OWNERSHIP_CAPTURE=PASS
PHASE03_RBCD_ROLLBACK_ACCEPTANCE=PASS
PHASE03_RBCD_NEUTRAL_ACCEPTANCE=PASS
PHASE03_RBCD_ACTIVE_ACCEPTANCE=NOT_TESTED
```

Active RBCD can only be marked PASS after the separate execution runner
proves the Stage 1 computer account, Stage 2 descriptor, S4U ticket,
authorized CIFS consequence, and clean rollback.

Removing a delegation relationship prevents *new* delegation requests
through it; it does **not** retroactively revoke already-issued service
tickets. Clear the specific local S4U/Kerberos cache and account for ticket
lifetimes before declaring credentials invalid. The rollback does not
blindly remove arbitrary local ticket directories or instructor files.

## Notion alignment

The published Attack 14 guide currently says `PHASE03RBCD$` remains
for later housekeeping. Once this NORTH rollback is live-accepted, update
that passage: the instructor-side fixture is removed under exact-object
provenance checks, while the learner sees the attribute-level cleanup and
the independent return to baseline. Avoid exposing protected instructor
provisioning credentials or suggesting an attacker can delete arbitrary
AD objects without the required privileges.
