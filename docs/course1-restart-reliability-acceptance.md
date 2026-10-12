# NORTH — Repeated cold-start and snapshot-restore acceptance

The retained NORTH profile consists of KINGSLANDING, WINTERFELL,
CASTELBLACK, WS01 and GOAD-ROUTER. The previous 1m41s successful restart
did not prove repeatability. The earlier CASTELBLACK/NT5DS cold-start
stall remains an open reliability regression pending live repeat acceptance.

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

## Course compatibility review

The current Notion Modules 00, 01 and 02 were reviewed: their actual
targets and teaching scope are WINTERFELL, CASTELBLACK, WS01 and NORTH.
They contain no Essos, DC03/SRV03 or 10.4.30.x exercise targets.
No substantive rewrite is required: preserve commands, lessons and
screenshots. Update only the introductory five-VM topology and any
environment-specific references that differ. New Phase 03 content should
use current NORTH runtime evidence before publication.
