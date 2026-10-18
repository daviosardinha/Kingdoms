# WSLPE-WS01 — 45-technique completion contract

**Owner:** Kingdoms standalone Windows LPE. **Target:** WSLPE-WS01 only.
**NORTH:** permanently frozen at its already established 20 techniques.
**Date:** 2026-10-18. **Status:** NOT RELEASE READY.

This is the engineering closeout path, not a list of completed vulnerabilities.
The source of truth for current states is the checked-in machine-readable
`kingdoms/wslpe45_implementation_index.yml`, interpreted by
`scripts/wslpe45-closeout.py`. No second, manually maintained success
counter is allowed.

## Coordinated native source wave (2026-10-18)

- #25: exact-path learner-writable request file, bounded 1–6 digit nonce,
  elevated repair custom-action proof and independent source checks. The
  non-admin MSI repair trigger and owned runtime cycle remain **unverified**.
  Windows installer execution and guest fixture setup have not occurred.
- #36: prototype host now refuses non-WSLPE machine and any identity other
  than LocalSystem before WMI registration; the native runner verifies the
  wrong-host negative case. Dedicated provider installation, namespace
  permissions, service lifecycle and reset still need real source/runtime.
- #38: remains **review-blocked**. Do not reproduce the previously rejected
  DCOM local-server path or substitute COM hijacking for launch-ACL abuse.
- #40: source refresh uses a narrowly scoped same-volume Win32 atomic rename
  after old/new hash verification, with a Windows-native compilation gate.
  **Not applied to the guest.** The independent last guest hash still matches
  the original module and the local RPC host remains stopped.

This wave does **not** change the official 21/25 source-candidate status, the
25 unqualified new lifecycles or the learner proof tally. It establishes real
source improvements on three mechanisms while keeping the deployment disabled.

## Proven checkpoint

- Foundation #1–20: previous standalone six-stage *provisioning lifecycle*
  accepted, distinct learner exploit proofs still unverified.
- Additions #21–45: 21 source candidates and four unfinished native mechanisms,
  **zero** new formally qualified guest six-stage lifecycles and **zero**
  independent `lpe.trainee` exploit proofs.
- #25 MSI repair: built prototype and source-controlled recovery, missing
  learner-controlled repair primitive and approved end-to-end ownership/recovery.
- #36 WMI provider: source-verifiable native provider prototype, missing owned
  registration, method authorization and bounded cleanup/retest.
- #38 DCOM: distinct approved out-of-process implementation still missing;
  review-blocked. Do not pass by relabeling an unsafe previous prototype.
- #40 native ncalrpc: exact server/client and operator assets staged, SHA-256
  checked, listener stopped, original operator still installed according to
  the last independent guest SHA-256 comparison. Corrected source operator is
  **not** yet installed. No learner proof or lifecycle has been accepted.
- Older source audit F-03 (#34 exact owned junction reset) and F-05 (#35
  controller copy source) have code/test implementations now. This clears
  their *source discrepancies*, not guest six-stage or learner validation.
- This snapshot is read from project evidence; do not infer current guest
  correctness from CI alone.

## Change execution strategy — batch engineering, not 25 micro-pilots

### Wave A: finish source mechanisms and safety reviews

1. Implement **real, distinct** #25/#36/#38/#40 mechanisms in the standalone
   package. Source may advance independently: one blocked mechanism does not
   prevent engineering/review of the others. Each must have an actual
   learner-influenced Windows trust boundary, not merely a privileged marker.
2. Review existing 21 candidates together, prioritizing concrete privileged
   consumer boundaries, #22 machine-wide SCM effect, #24 reparse containment,
   #43 mislabeled cryptographic signature claim, source dependencies and exact
   owned cleanup. Preserve every existing validated foundation scenario.
3. Native Windows CI must parse, compile or build the actual candidate and
   its positive/negative contracts. An API-presence check or green build is
   **not** an exploit proof. Do not promote index fields prematurely.

### Wave B: one coordinated Windows qualification

4. Use a **separate snapshot-backed disposable WSLPE clone** for risky new
   scenario tests. Confirm exact workgroup identity, private management
   connectivity and snapshot before guest mutation.
5. Once all 25 sources and rollback mechanisms are independently approved,
   unlock the guarded `scripts/wslpe-45-qualify.py` runner through the
   reviewed, standalone-only batch execution flag. Execute exactly
   `apply -> vulnerable validation -> reset -> clean validation -> reapply
   -> revulnerable validation` for each of 25 additions (150 stages).
   Journal stages privately; stop at an ambiguous partial state.
6. Provide approved per-scenario, owned-object recovery/resume rather than
   wiping the entire VM or rerunning completed candidates blindly. Never
   bypass the fail-closed sentinel just to get a green screen.

### Wave C: learner evidence, security and release

7. Exercise **all 45** from actual standard `WSLPE-WS01\\lpe.trainee`
   context. Independently verify the intended privileged effect, negative
   boundary and reset. Distinguish a deliberately bounded privileged write
   from arbitrary SYSTEM execution when teaching.
8. Prove RDP/NLA login, isolated student traffic, operator-only HTTPS/5986,
   protected per-instance secrets, default `vagrant` retirement after a
   confirmed new operator handoff, clean restore/start/reinstall, Windows
   licensing, and 45 walkthroughs. Only then capture the distribution image.

## Engineering guardrails

- Stop adding prompt phrases. A deliberate CLI flag authorizes a *specific*
  bounded operation; programmatic safety checks and provenance are mandatory.
- Never use `exit 1`, `set -e` or `exec` in copy/paste Kali snippets
  that could terminate the operator's interactive session.
- Never change shared NORTH role/source/VM/network/AD to make standalone pass.
- A failed write means fresh read-only inventory before a new controlled
  attempt. No speculative retry loops or disabling certificate checks.
- CI must remain completely source-only, even after future
  `batch_execution_authorized` becomes true. Live execution belongs to an
  explicitly reviewed operator workflow, never to a GitHub runner.

## One report command (no guest contact)

```bash
(
  repo="$HOME/kingdoms-lpe-standalone"
  if [ -n "$(git -C "$repo" status --porcelain)" ]; then
    echo "[BLOCKED] Review local changes before updating"
  elif git -C "$repo" pull --ff-only; then
    "$HOME/.goad/.venv/bin/python" "$repo/scripts/wslpe45-closeout.py"
  else
    echo "[BLOCKED] Source update failed"
  fi
)
```

`--json` emits all 45 row states and release gates. Neither mode runs
Ansible, WinRM, VMware, a native host or a learner exploit. A report saying
21/25 source is a **blocker report**, not permission to seed those 21.

**Definition of done:** 45 distinct bounded techniques, native artifact
provenance, 25 new clean six-stage lifecycles, 45 independently executed
learner proofs, explicit negative tests and reset, student isolation,
per-instance credentials, reproducible licensed deployment and accurate
teaching material. A green CI build is never a substitute.
