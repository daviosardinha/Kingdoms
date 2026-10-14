# Course 1 NORTH — Attack 15 Shadow Credentials baseline contract

**Status:** Attack 15 manual exploitation PASS; independent post-cleanup NORTH Shadow neutral verification PASS on 2026-10-14. The old mutating apply task failed an internal readback after attempting the attribute clear; its corrected readback has not been retested via a second mutation.

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

## Live capture evidence — 2026-10-14

The operator pulled source checkpoint `15ab136`, passed **4 source tests** and
parsed the capture YAML. Live NORTH baseline capture then returned:

```text
PHASE03_SHADOW_BASELINE_NEUTRAL=True
PHASE03_SHADOW_BASELINE_TARGET=WS01$
PHASE03_SHADOW_BASELINE_KCL_COUNT=0
PHASE03_SHADOW_BASELINE_CAPTURE=PASS
PHASE03_SHADOW_ACTIVE_ACCEPTANCE=NOT_TESTED
```

**Exact private baseline:**
`/home/stark/Kingdoms-evidence/phase03-shadow-baseline-y9Z23fYy/shadow-baseline.json`

Only one previously empty `msDS-KeyCredentialLink` attribute was captured.
The old September 25 baseline remains untouched.

## NORTH rollback design (staged, not live-accepted)

The new wrapper `scripts/course1-phase03-shadow-rollback.sh` is scoped
to exactly one current NORTH instance and one owner-only per-run baseline.
It validates the JSON contents and SHA-256, locks against other Phase 03
acceptance operations, requires an installed network owner/source check,
and never touches the original September baseline.

- `--plan` is read-only. It checks the live WS01 DN/SID against the
  selected baseline, rejects **more than one KeyCredential entry**, and
  prints the SHA-256 fingerprint of the *single* present value without
  exporting raw key material. When no KCL exists it reports
  `PHASE03_SHADOW_ROLLBACK_PLAN=ALREADY_NEUTRAL`.
- `--apply --confirm <64hex-fingerprint>` is a **mutating operator
  action** that requires the fingerprint from the reviewed plan. It
  refuses any extra KCL values, changed fingerprint, unexpected WS01
  identity, active relay or poisoning process, invalid baseline or
  owner mismatch. It clears the *sole* matching KCL entry, and reads
  back immediately. Only under these exact checks is clearing the
  whole attribute safe: the baseline was empty and there is exactly
  one expected newly introduced value.
- After mutation, the wrapper runs a *different*, read-only playbook,
  `ansible/phase03-shadow-verify-neutral-north.yml`, comparing
  WS01's exact SID/DN and empty KCL against the baseline.
  `PHASE03_SHADOW_ROLLBACK_ACCEPTANCE=PASS` requires this verifier.
- `--verify` runs that independent read-only verification alone.
  The runner never automatically erases PFX/private key artifacts or
  performs snapshot restore. Locally generated secrets must be
  handled as separate exercise-owned evidence.
- `tests/test_course1_shadow_rollback_contract.py` checks syntax,
  exact NORTH scoping and the explicit authorization and fail-closed
  boundaries; **these tests and the Ansible YAML parser have not yet
  run on Kali for the new rollback implementation.**

Operator source-only check and safe plan **before any attack**:

```bash
cd "$HOME/kingdoms-rebuild" && git pull --ff-only
python3 -m unittest tests.test_course1_shadow_baseline_contract tests.test_course1_shadow_rollback_contract
"$HOME/.goad/.venv/bin/python" -c "import yaml; [yaml.safe_load(open('ansible/' + n)) for n in ('phase03-shadow-rollback-north.yml','phase03-shadow-verify-neutral-north.yml')]"
sudo -v
bash scripts/course1-phase03-shadow-rollback.sh ac9fda-north-vmware \
  "$HOME/Kingdoms-evidence/phase03-shadow-baseline-y9Z23fYy/shadow-baseline.json" --plan
```

This initial plan should report `ALREADY_NEUTRAL` and leave the lab
unchanged. Before later applying rollback, repeat `--plan` **after**
the controlled Shadow attack, review its exact single-value fingerprint,
then explicitly authorize the exact plan. Never reuse a stale fingerprint
or select the GOAD baseline. If plan finds two or more values, stop.

**Pre-attack status superseded by the dated live evidence below.** The source test suite does not establish acceptance of a second mutating apply. A coordinated restore of the five consistent VMware
snapshots remains fallback if the target has unexplained changes.

## Legacy GOAD boundaries

The legacy `scripts/phase03/rollback-shadow.sh` and
`ansible/phase03-shadow-rollback.yml` still default to the original
GOAD inventories and the September global baseline. Do **not** use
them directly on NORTH.

## 2026-10-14 — Independent Shadow neutral verification PASS

The operator fast-forwarded the NORTH branch to `8977a11`, ran five rollback unit tests (OK), parsed the rollback YAML and executed the existing read-only independent verifier against the exact private pre-attack NORTH Shadow baseline.

Observed output:

```text
[RUN] Independent read-only neutral verification
PHASE03_SHADOW_NEUTRAL_ACCEPTANCE=PASS
PHASE03_SHADOW_ACTIVE_ACCEPTANCE=NOT_TESTED
```

Evidence: `/home/stark/Kingdoms-evidence/phase03-shadow-rollback-cDcoIZJ2`.

**Interpretation:** WS01's exact DN/SID and now-empty `msDS-KeyCredentialLink` match the original clean baseline. The earlier authorized apply attempted the AD clear, then failed an unreliable internal null-based readback. The independent verifier confirms **AD recovery is complete without a VM reset or second apply**. Do not rerun `--apply`.

**Status distinction:** Manual NTLM-to-LDAPS relay, KCL injection, independent KCL verification and certificate PKINIT TGT proof: PASS. Independent neutral state: PASS. Original mutating wrapper completion marker: FAILED. Corrected readback source exists but **has not been retested through an additional mutation**. Automated active attack acceptance remains NOT_TESTED.

**Remaining hygiene:** Private exercise-owned PFX and password artifacts remain under `phase03-shadow-attack-AhK4e7Ut`; preserve privately or remove only those artifacts after saving redacted documentation. WS01 WebClient was temporarily changed from Stopped/Manual to Running/Manual; restore runtime state before the next attack if no longer needed. Do not publish the generated PFX password.

## 2026-10-14 — First live rollback readback failure

Attack 15's first LDAPS relay inserted one KCL value on WS01$, independently
verified as the single entry with SHA-256
`37d6f52a023e988df4f5d57c3ef975ae91dc36a51709a76c130fabd12bbc04e0`.
Certipy authenticated as `WS01$` through PKINIT and reported a TGT, without
requesting an NT hash or persisting the ticket cache. The SHA-matched
`--plan` passed and `--apply --confirm` was explicitly requested.

The Ansible rollback task **failed after attempting the AD clear**:
`KeyCredentialLink rollback failed internal readback; independent verifier required`.
The log shows the expected plan/identity/fingerprint evidence but task error
`changed: true`. The prior post-write readback used
`$null -ne $after.'msDS-KeyCredentialLink'`; this is not a reliable presence
test for an AD multi-valued property because PowerShell can return an
empty `ADPropertyValueCollection` rather than `$null`. A source fix
replaced that check with `$afterValues.Count -ne 0` and added explicit
readback identity/count diagnostic markers and a regression source test.

**Current live cleanup status is UNKNOWN until independent verification.**
The first `--apply` must **not** be rerun. Obtain a fresh exact-state
reading using:
```bash
cd "$HOME/kingdoms-rebuild" && git pull --ff-only
python3 -m unittest tests.test_course1_shadow_rollback_contract
"$HOME/.goad/.venv/bin/python" -c "import yaml; yaml.safe_load(open('ansible/phase03-shadow-rollback-north.yml'))"
sudo -v
bash scripts/course1-phase03-shadow-rollback.sh \
  ac9fda-north-vmware \
  "$HOME/Kingdoms-evidence/phase03-shadow-baseline-y9Z23fYy/shadow-baseline.json" \
  --verify
```

If `PHASE03_SHADOW_NEUTRAL_ACCEPTANCE=PASS`, the directory has already
returned to its original empty KCL state and no further mutation is needed;
record this as an independent recovery acceptance (not a successful original
apply task). If verification fails, preserve logs and inspect the current
read-only `--plan` output before any further decision. Do not reset the
lab or retry apply simply because the initial task returned an error.

The existing protected exercise baseline and original private PFX evidence
must remain intact while recovery status is being resolved.
