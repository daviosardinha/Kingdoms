# WSLPE41 — Freeze and learner acceptance handoff

**Engineering branch:** `feature/wslpe45-single-candidate-pilot`  
**Active lab:** standalone workgroup `WSLPE-WS01`; **NORTH is permanently out of scope**.  
**Target:** **41 Windows LPE scenarios**, retaining original technique IDs and excluding #25/#36/#38/#40.  
**Deployment acceptance:** selected 21/21 additional configurations PASS at guest-validated source `6b612e9abf2547dc76e4d4a89f4df1be6137f6e6`; baseline 20 operator-reported.  
**Learner exploitation:** none of the additional 21 independently proven by the deployment run.

## Phase A — freeze the validated master, not an exploitation test

From an origin-synchronized, clean checkout on the original operator's Kali host:

```bash
cd "$HOME/kingdoms-wslpe45-pilot" &&
git pull --ff-only origin feature/wslpe45-single-candidate-pilot &&
"$HOME/.goad/.venv/bin/python" scripts/wslpe41-freeze.py
```

The default command is inspection/plan only. After confirming that it identifies exactly the intended running standalone workgroup VM, the pinned original recovery snapshot and 21/21 private final-journal proof, authorize **one VMware Workstation snapshot**:

```bash
cd "$HOME/kingdoms-wslpe45-pilot" &&
"$HOME/.goad/.venv/bin/python" scripts/wslpe41-freeze.py --execute
```

Proposed snapshot name: `KINGDOMS-WSLPE41-CONFIG-VALIDATED`.

The controller requires the original protected 21/21 journal and SHA of the validated deployment source, exact unique registered VMX, original snapshot and snapshot-name noncollision. It writes an owner-only `wslpe41-freeze-*.json` receipt before snapshot creation. Successful completion requires independent VMware snapshot inventory confirmation. An interrupted VMware operation leaves `STARTED` evidence; inspect manually, never automatically retry. It does **not** deploy fixtures, run learner proof, stop/start the VM, reset/revert/delete snapshots or alter NORTH. This operation is invoked on the real operator host only, never by GitHub Actions.

**Important:** A VMware snapshot is a recoverable checkpoint, not physically immutable or a substitute for a verified backup. Do not overwrite it; consider an independent encrypted copy of the VM/snapshot storage before distribution. No snapshot is claimed until the operator supplies a verified PASS receipt.


## Current operator checkpoint — frozen master PASS (2026-10-19)

The operator provided the private frozen-master receipt:
`wslpe41-freeze-3c465ceba8b31352.json` — `schema=kingdoms.wslpe41.freeze.v1`,
`status=PASS`, source `9efc85796aa9e1b60017cadd1d90f72a97d9823c`,
deployed source `6b612e9abf2547dc76e4d4a89f4df1be6137f6e6`,
snapshot `KINGDOMS-WSLPE41-CONFIG-VALIDATED`, completed
`2026-10-19T19:22:24.329527+00:00`. The receipt was read from the user-provided
local file; its source fingerprint matches the final deployment journal.
This verifies that the freeze workflow reported a snapshot PASS and supplied a
VMware inventory check; it does not independently demonstrate student proofs
or clone readiness. Do **not** execute another freeze.

Verify the receipt with the existing source-only acceptance planner:

```bash
cd "$HOME/kingdoms-wslpe45-pilot" &&
git pull --ff-only origin feature/wslpe45-single-candidate-pilot &&
"$HOME/.goad/.venv/bin/python" scripts/wslpe41-learner-acceptance.py   --freeze-receipt "$HOME/.local/state/kingdoms-wslpe45-live/wslpe41-freeze-3c465ceba8b31352.json"
```

Expected next evidence is `[FREEZE] RECEIPT_VERIFIED: KINGDOMS-WSLPE41-CONFIG-VALIDATED`.
This is source-only and records **zero** new learner proof.

### Disposable clone requirement (read-only audit)

Create a **full working clone** in VMware Workstation from the named
`KINGDOMS-WSLPE41-CONFIG-VALIDATED` snapshot. Do **not** use a linked
clone. Keep the candidate powered off with **every NIC explicitly
disconnected**. Keep the frozen master unchanged. Do not boot two VMs
with the same computer name/IP/MAC on an attached student/lab network.
Record the candidate VMX path from VMware rather than guessing it.

Run the new **read-only** clone check on Kali, substituting the actual
created clone VMX path:

```bash
cd "$HOME/kingdoms-wslpe45-pilot" &&
"$HOME/.goad/.venv/bin/python" scripts/wslpe41-clone-audit.py   --freeze-receipt "$HOME/.local/state/kingdoms-wslpe45-live/wslpe41-freeze-3c465ceba8b31352.json"   --clone-vmx "/absolute/path/to/working-clone.vmx"
```

The audit rejects the original guest, a running candidate, connected NICs,
external disk references, linked/differencing disk descriptors and a missing
frozen-master snapshot. It performs **no VM mutation**. Even PASS cannot prove
that the clone was actually made from the selected snapshot or that the
Windows guest and isolation controls are valid; the operator must confirm
snapshot ancestry in VMware and then review any isolated-guest boot,
networking and learner identity before running a proof.

### First learner-console evidence — scenario #21

The operator's isolated working clone has passed its offline VMX audit and,
from a normal PowerShell session as `WSLPE-WS01\lpe.trainee`, produced:

- `WSLPE41_LEARNER_IDENTITY=PASS`
- `WSLPE41_LOCAL_NONADMIN=PASS`
- `WSLPE41_NETWORK_DISCONNECTED=PASS`

These are user-supplied console observations, **not** elevated evidence. Do
not increment the 41-scenario learner acceptance count.

The first candidate is **#21 — Scheduled Task Definition ACL**. GitHub source
`scripts/wslpe41-learner-pilot21-readonly.ps1` is read-only and must run in
that same learner console on the disconnected disposable clone. It verifies
exact guest and learner identity, the owned #21 marker, its dedicated SYSTEM
task action, and the learner's task object ACE. It never modifies a task,
launches an elevated program, runs an exploit or returns learner exploitation
PASS. Native Windows PowerShell 5.1 CI parses it; source-only tests reject
known mutating task APIs.

On Kali, inspect/copy the script:

```bash
cd "$HOME/kingdoms-wslpe45-pilot" &&
git pull --ff-only origin feature/wslpe45-single-candidate-pilot &&
cat scripts/wslpe41-learner-pilot21-readonly.ps1
```

Paste its contents into ordinary PowerShell in the offline learner VM. Confirm
`WSLPE41_21_READONLY_PREFLIGHT=PASS` and
`WSLPE41_21_LEARNER_EXPLOITATION=NOT_TESTED` or capture its precise
`BLOCKED` output. Do not boot or reconfigure the original master.
Only after this precondition do we separately engineer an owned-canary learner
proof, with explicit rollback in the clone and independent privileged evidence.

### First pilot, then automation for all 41

The learner-acceptance planner is not an exploit runner. After clone
identity/isolation is independently verified, implement **one**
learner-initiated test for a selected technique on that disposable clone.
Keep precondition, trigger, elevated evidence, expected negative behavior,
post-test contamination and restore checks separate. A manually observed
configuration remains `LEARNER_PENDING` until a real learner-originated
privileged effect is independently evidenced. Generalize only after the
pilot passes; retain exact scenario IDs and explicit four exclusions.

## Phase B — learner acceptance automation: architecture

Build a **local, operator-controlled test orchestrator**, not a scheduled job and not a GitHub-hosted remote exploitation workflow.

- **One manifest of 41 active scenario IDs**, preserving original IDs #1–20 and selected #21–45 without renumbering; exact four exclusions reject any adapter/test attempt.
- **Separate proof adapter for each scenario** (or common adapter only if its behavior is demonstrably identical), because credential disclosures, task ACLs, services, COM, token privileges, path traversal and races do not share a valid generic exploitation action.
- The **test initiator must be the actual non-admin** `WSLPE-WS01\lpe.trainee`. Confirm token identity, groups, effective permissions and non-administrator state in its real session. A SYSTEM/admin operator calling its own helper does **not** prove local privilege escalation.
- Tests use an **owned canary marker** and bounded expected behavior. Require a before-state demonstrating learner cannot perform the privileged action, a learner-originated trigger, and independent privileged context/owned marker validation. Record the precise privileged effect achieved, not automatically 'SYSTEM' if the outcome is a weaker capability.
- **Negative tests are first-class**: wrong principal, unintended path, insufficient token rights, disallowed parameter or invalid input as applicable. Never write evidence into an arbitrary system path or run an unknown payload.
- **No destructive proof on the frozen master.** Create a disposable working clone from the frozen snapshot for mutable/race/credential/ACL demonstrations. For destructive scenarios, fresh clone per scenario or group with proven isolation. Reset/clean/reapply checks are separate and cannot silently modify the frozen reference.
- **Stop on the first ambiguous state** and retain the per-scenario private log. Explicit IDs and a reviewed retry/resume permit controlled continuation; no automatic cleanup/retry of partially exploited state.
- **Never merge deployment PASS with learner PASS.** Fields: `CONFIG_VALIDATED`, `LEARNER_PENDING`, `LEARNER_PASS`, `LEARNER_FAIL`, `BLOCKED`, `RESET_VERIFIED`. Evidence and counts are generated from the manifest and runtime logs, not entered optimistically.
- Private JSON + stdout/PowerShell evidence lives outside Git with owner-only permissions; Git stores only source/tests and safe, redacted summary. Prevent logging passwords, fixture secrets or privileged command contents.
- CI tests adapters with fixtures and mocks, checks native PowerShell compatibility, pinning, duplicate IDs, excluded scenarios and fail-closed behavior. **CI never contacts Windows, VMware, a hypervisor or a learner VM.**

## Phase C — qualification and course release (separate)

After learner proofs, test reversible lifecycle in disposable clones, release-day guest isolation, RDP/NLA access, management credential handoff, fixture secret rotation, WinRM exposure, reproducibility, Windows licensing and per-learner distribution. A passed exploit proof alone does not pass release acceptance.

## Immediate stop/go

- **GO for freeze:** only after local source gate and exact private-journal/VM identity checks; operator manually performs `--execute`.
- **GO for learner acceptance automation engineering:** create scenario manifests/adapters/source-only CI now, with no guest actions.
- **NO GO for live learner exploitation:** until the post-deployment snapshot PASS receipt exists and a disposable test clone has been verified. The original source-only index deliberately leaves learner proof and six-stage qualification pending.

The frozen master should never be used for blind, bulk exploit replay or automatically reverted by a test runner.
