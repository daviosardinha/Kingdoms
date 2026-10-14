# Course 1 NORTH — Attack 15 Shadow Credentials baseline contract

**Status:** source staged, Kali unit test and live capture pending.

## Why this is necessary

The previous `$HOME/.config/kingdoms/phase03-shadow-baseline.json`
belongs to the original Kingdoms environment (2026-09-25); it cannot be
used to authorize recovery of the current NORTH exercise instance
`ac9fda-north-vmware`. Attack 14 has been recovered by a coordinated
five-VM snapshot restore; independent RBCD neutral verification passed,
and the Phase 03 baseline most recently passed 11 mandatory checks,
one optional interactive Rickon warning and zero failures.

Before any Shadow Credentials modification, capture the exact current
WS01 `msDS-KeyCredentialLink` state. The NORTH preflight requires the
attribute to be empty, SELF validated-write rights present, and a KDC
certificate on WINTERFELL. This only proves readiness, **not** a PKINIT
attack or a completed rollback.

## Source design

- `ansible/phase03-shadow-baseline.yml` accepts the explicit
  `KINGDOMS_PHASE03_SHADOW_BASELINE` output path. Its original legacy
  default remains unchanged for compatibility, but the NORTH wrapper
  always selects a newly created evidence directory.
- `scripts/course1-phase03-shadow-baseline.sh` requires the installed
  NORTH instance in exercise mode, serializes against other Phase 03
  acceptance operations with the shared lock, refuses active
  poisoning/relay processes, verifies source + installed VMware network
  ownership, checks the Shadow prerequisites, and captures the baseline
  using **NORTH and the selected instance inventories only**.
- Exact per-run evidence is private (directory 0700, JSON 0600,
  SHA-256 checksum 0600), and the JSON must identify WS01$ in NORTH with
  an empty `msDS-KeyCredentialLink` attribute.
- The existing September 25 baseline is left untouched. None of the
  new code writes to Active Directory, runs PKINIT, starts a relay,
  changes networks or resets a VM.
- `tests/test_course1_shadow_baseline_contract.py` checks the source
  boundary and command-line safety on Kali.

## Operator command (baseline capture only)

```bash
cd "$HOME/kingdoms-rebuild" && git pull --ff-only
python3 -m unittest tests.test_course1_shadow_baseline_contract
"$HOME/.goad/.venv/bin/python" -c "import yaml; yaml.safe_load(open('ansible/phase03-shadow-baseline.yml'))"
sudo -v
bash scripts/course1-phase03-shadow-baseline.sh ac9fda-north-vmware --capture --confirm
```

Require `PHASE03_SHADOW_BASELINE_NEUTRAL=True` and
`PHASE03_SHADOW_BASELINE_CAPTURE=PASS` with a new absolute JSON path.
**Retain that exact path** for this exercise; no blanket use of
`~/.config/kingdoms/phase03-shadow-baseline.json`.

## Recovery boundary

The legacy `scripts/phase03/rollback-shadow.sh` and
`ansible/phase03-shadow-rollback.yml` still default to the original
GOAD inventories and legacy global baseline. They must **not** be run
unchanged on the current NORTH instance. Before the first Shadow
Credentials write, stage and source-test a NORTH-specific, exact-baseline
recovery that independently compares WS01's DN/SID, original KCL
values and only the attack-owned addition. Reject concurrent or
unexpected KCL changes; never wipe the attribute simply because a
generic helper reports success. Independently verify restored state and
clean up only exercise-owned local key/certificate artifacts.

If recovery cannot be proven safely, a separately approved coordinated
VMware snapshot restore is the fallback, with the known consequences
for all guest changes since the snapshot.
