# NORTH — Repeated cold-start and snapshot-restore acceptance

The retained NORTH profile consists of KINGSLANDING, WINTERFELL,
CASTELBLACK, WS01 and GOAD-ROUTER. The previous 1m41s successful restart
did not prove repeatability. The earlier CASTELBLACK/NT5DS cold-start
stall is now **closed for recovery reliability**, based on two passing cold-start
cycles and independently reconciled post-snapshot readiness (2026-10-12).
Startup-duration optimization remains separate: cold-start 1 required 351s,
whereas cold-start 2 required 54s. Neither duration should be misrepresented
as a guaranteed cold-start SLA.

## Source-controlled gates

scripts/course1-restart-preflight.sh performs only read-only checks:
the installed owner/source contract, exercise mode, Phase 03 lock, five
registered VMX identities, VMware snapshot inventory, persistent NAT
isolation, and current router/host routing state. Logs are private.

scripts/course1-restart-acceptance.sh is a separate deliberate operator
action. It requires an explicit data-loss acknowledgement, one unambiguous
snapshot per VM, and clean read-only Phase 03 prerequisites before power
operations. It performs two native stop/start cycles, validating AD and
isolation after each, followed by ONE native reset. The existing
Goad.do_reset already runs stop, provider snapshot restore, and start.
A separate start must not be appended.

The reset permanently discards guest changes made after each stored snapshot.
The scripts do not create snapshots, change AD trusts, weaken time checks,
repair the domain or automatically retry on failure. Native lifecycle
start/stop/reset operations are deliberately NOT wrapped in an external GNU
timeout: process-group termination could unintentionally signal VMware guest
monitors. The provider's existing bounded operations and PID-safe cleanup
remain authoritative. Any failure blocks release acceptance and retains exact
stage logs. An operator must review the selected snapshots before
authorizing the destructive stage.

## Read-only operator command

    cd "$HOME/kingdoms-rebuild" && git pull --ff-only
    python3 -m unittest tests.test_course1_restart_preflight tests.test_course1_restart_acceptance
    sudo -v
    bash scripts/course1-restart-preflight.sh ac9fda-north-vmware

A successful audit reports NORTH_RESTART_PREFLIGHT=PASS, but both live
runtime gates remain NOT_TESTED. This does not close the defect.

## Deliberate live repeat acceptance — after operator reviews snapshots

    cd "$HOME/kingdoms-rebuild"
    sudo -v
    bash scripts/course1-restart-acceptance.sh ac9fda-north-vmware --run --confirm-restore-data-loss

Only accept release closure after seeing the following three markers:

    NORTH_REPEATED_COLD_START=PASS
    NORTH_SNAPSHOT_RESTORE=PASS
    RESTART_RESTORE_RELIABILITY=PASS

Logs and wall-clock timings remain in the private evidence directory.
Also verify AD dependency order, NT5DS synchronization, members' secure
channels and router/NAT exercise isolation. Do not merge the rebuild
branch before runtime acceptance.

## 2026-10-12 — Restored NORTH runtime evidence and DNS false-negative

The operator completed the explicitly authorized recovery run on the existing
`ac9fda-north-vmware` instance:

- Initial source/owner gate PASS and read-only prerequisites PASS (69 seconds).
- Cold 1 stop PASS (36s), start PASS (351s), prerequisites PASS (72s).
- Cold 2 stop PASS (50s), start PASS (54s), prerequisites PASS (72s).
- Native snapshot restore PASS (1005s).
- Immediate post-restore read-only prerequisite **STOPPED at owner gate**:
  `git fetch` could not resolve `github.com`. Its other prerequisite
  gates were not attempted. The original runner correctly recorded
  `RESTART_RESTORE_RELIABILITY=NOT_CERTIFIED`.

A separate read-only verification after external DNS recovered passed the
same installed NORTH owner gate and all **11 required** Phase 03 prerequisite
checks (1 optional Rickon Explorer-session warning, 0 failures).
Evidence: `~/Kingdoms-evidence/phase03-batch-20261012-190138/`.
This establishes restored infrastructure readiness without repeating
destructive VM restoration; it does **not** prove the optional Rickon
interactive victim-session state or active attack chains.

### Preventing external DNS false-negative on future recovery runs

The strict online source/upstream validation remains mandatory **before**
any VM lifecycle action. The runner now records that verified Git HEAD and
uses a narrowly scoped offline pinned-source gate for subsequent readiness
checks. That gate still verifies the exact HEAD SHA, branch, local upstream
ref, clean worktree/index, and **live** installed VMware host ownership.
Any source drift or owner mismatch still blocks acceptance, but transient
GitHub DNS loss no longer masks the restored AD state.

The original failed summary is never rewritten. An independent, read-only
reconciler accepts the previous run only when all two-cycle start and
snapshot-restore markers exist, the failure was specifically GitHub DNS,
and a later owner-verified Phase 03 run has exactly 11 required PASS
markers and zero failures. It writes a separate owner-only reconciliation
record, not a forged original PASS.

Operator after pulling the new GitHub branch:

    cd "$HOME/kingdoms-rebuild"
    git pull --ff-only
    python3 -m unittest tests.test_course1_restart_preflight tests.test_course1_restart_acceptance tests.test_course1_restart_pinned_source tests.test_course1_restart_finalize
    RUN="$(find "$HOME/Kingdoms-evidence" -maxdepth 1 -type d \
      -name 'north-restart-acceptance-*' -printf '%T@ %p\n' \
      | sort -nr | head -1 | cut -d' ' -f2-)"
    echo "Selected original run: $RUN"
    POST="$HOME/Kingdoms-evidence/phase03-batch-20261012-190138"
    bash scripts/course1-restart-finalize.sh "$RUN" "$POST"

If the actual RUN path differs, use the one printed by the initial runner;
never guess or silently select unrelated evidence. A successful reconciler
prints `NORTH_REPEATED_COLD_START=PASS`,
`NORTH_SNAPSHOT_RESTORE=PASS`,
`NORTH_POST_RESTORE_READINESS=PASS`, and
`RECOVERY_EVIDENCE_RECONCILIATION=PASS`. Only then mark the
restart/restore release acceptance formally closed. No new reset is needed.

## 2026-10-12 — FINAL RECOVERY ACCEPTANCE: CLOSED

**Status: ACCEPTED / CLOSED** for existing instance `ac9fda-north-vmware`
on `rebuild/course1-from-kingdoms`.

The operator performed the final, non-mutating reconciliation after
correcting the post-restore Phase 03 evidence timestamp. The prior
source regression run passed **19/19 tests**, and the reconciler emitted:

```text
instance=ac9fda-north-vmware
original_run=/home/stark/Kingdoms-evidence/north-restart-acceptance-HG00FGjo
successful_post_restore_batch=/home/stark/Kingdoms-evidence/phase03-batch-20261012-190138
original_failure=external_github_dns_during_repeated_online_source_fetch
NORTH_REPEATED_COLD_START=PASS
NORTH_SNAPSHOT_RESTORE=PASS
NORTH_POST_RESTORE_READINESS=PASS
RESTART_RESTORE_RELIABILITY=PASS
RECOVERY_EVIDENCE_RECONCILIATION=PASS
```

**Evidence artifact on operator Kali:**
`/home/stark/Kingdoms-evidence/north-restart-acceptance-HG00FGjo/reconciled-recovery-acceptance.txt`.
This artifact references the original cold-start/snapshot logs and the later
11-PASS/0-FAIL read-only Phase 03 post-restore audit (one optional Rickon
interactive Explorer warning).

The original acceptance run's `NOT_CERTIFIED` marker is intentionally
preserved, because it reflects its initial GitHub DNS-source-gate failure.
The independent reconciler establishes the full recovery acceptance without
rewriting or falsifying the original logs.

**Scope of closure:** repeat cold-start health, native snapshot restoration,
post-restore AD/Phase 03 prerequisites, and recovery network ownership/isolation
for this NORTH instance. **Not included:** full Phase 03 active attack-chain
acceptance, Rickon interactive WebDAV proof, startup speed optimization, or
course publication readiness.

No additional VM reset, reprovision, snapshot creation or repair is required
for this checkpoint. Future changes to VMware/AD lifecycle may require rerunning
relevant acceptance evidence; do not merge the broader rebuild merely on this
single checkpoint.

## Course compatibility review

The current Notion Modules 00, 01 and 02 were reviewed: their actual
targets and teaching scope are WINTERFELL, CASTELBLACK, WS01 and NORTH.
They contain no Essos, DC03/SRV03 or 10.4.30.x exercise targets.
No substantive rewrite is required: preserve commands, lessons and
screenshots. Update only the introductory five-VM topology and any
environment-specific references that differ. New Phase 03 content should
use current NORTH runtime evidence before publication.
