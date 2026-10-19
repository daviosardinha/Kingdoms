# Windows LPE — 41-scenario deployment closeout

**Decision:** 2026-10-19  
**Status:** **DEPLOYMENT COMPLETE / SCOPE FROZEN AT 41**  
**Release status:** NOT STUDENT-RELEASE ACCEPTED  
**Scope:** standalone `WSLPE-WS01` (Windows 10 workgroup), not the NORTH domain workstation.  
**Engineering branch:** `feature/wslpe45-single-candidate-pilot`  
**Guest-validated source:** `6b612e9abf2547dc76e4d4a89f4df1be6137f6e6`

## Final curriculum scope

**41 active scenarios**, not the earlier proposed 45:

- **20 original scenarios:** operator-reported standalone baseline, not recounted by the final deployment journal. The original NORTH 20-technique milestone is a distinct, previously released environment and is not silently relabeled as standalone runtime proof.
- **21 additional scenarios, IDs 21–45 excluding 25, 36, 38 and 40:** installation or retained-owned installation and vulnerable-configuration validation PASS on the exact standalone guest.
- **Four explicitly out of scope for this course:** #25 `msi_repair_custom_action`, #36 `wmi_privileged_provider_authorization`, #38 `dcom_server_launch_acl`, #40 `custom_rpc_authorization`. Their existing source/prototypes remain archived in Git for provenance; they are **not** advertised as four missing exercises and are **not** reopened merely to reach the old 45 target.

**Retain the original scenario numbers, implementation-index records, code filenames, journal names and CI filenames containing `45`.** They are historical/technical identifiers. Do not mass-renumber or rename them solely to change the marketed scenario count. All future course-facing counts say **41** and explicitly exclude the four IDs.

## Runtime evidence and acceptance boundary

Operator-uploaded final private journal (not stored in Git):

`~/.local/state/kingdoms-wslpe45-live/wslpe45-resume-registered27-77c4f73d6782a328.json`

Recorded source SHA: `6b612e9abf2547dc76e4d4a89f4df1be6137f6e6`

- `schema=kingdoms.wslpe45.resume_registered27.v1`, `completed=true`, `failure=null`, `inflight=null`.
- `runtime_configuration_pass_count=21`; each of the 21 selected records has `configuration_validation=PASS`.
- #21–24 and #26 were installed/validated in the earlier run and revalidated without reinstalling.
- #27's previously registered COM fixture was completed in place, then independently configuration-validated: `installation=PASS_EXISTING`, `configuration_validation=PASS`. Earlier failed attempts remain visible in its journal events.
- #30 retained the existing JEA installation and passed its configuration check: `installation=PASS_EXISTING`.
- Other selected scenarios #28, #29, #31–35, #37, #39 and #41–45 were installed and configuration-validated sequentially.
- The final journal records preservation checks as PASS; excluded IDs are absent from the 21 selected deployment operations.
- Protected-state fingerprint recorded by the final journal: `9AB97BF7EB5D424B87F2893D41816BE78683F7BAC407C68B4ADAC2E5BB724D26`.
- All 21 added scenarios still carry `exploitation=NOT_TESTED`. The final journal **does not establish 21 learner privilege escalations** or recount the baseline 20.

**What is closed:** sourcing, installing and configuration-validating the selected 21 additions, with the declared course scope reduced to 41.

**What is not claimed:** 41 independent learner exploit proofs; full six-stage reversible qualification for all additions; immutable reproduction from a distribution image; security/release acceptance; or integration into `main`.

The original `kingdoms/wslpe45_implementation_index.yml` continues to track source candidates, six-stage qualification and learner proof, not this 21-scenario install/validate checkpoint. Do **not** rewrite candidate entries to `implemented` merely because the deployment journal passed.

## Freeze and acceptance automation — next phase

The operator-only freeze controller, `scripts/wslpe41-freeze.py`, verifies the exact final private journal and native VMware instance before creating a unique snapshot with `--execute`. Without this explicit flag it is read-only and only plans the snapshot. The source-only `scripts/wslpe41-learner-acceptance.py` creates the precise 41-ID acceptance matrix; no learner proofs are executed or claimed yet. See [WSLPE41 learner acceptance plan](./WSLPE41_LEARNER_ACCEPTANCE_PLAN.md) for strict cloned-lab proof and evidence requirements. A **freeze PASS receipt must exist before live acceptance execution is authorized**.

## Freeze / transition

1. **Stop the installation campaign.** No replay of `--execute`, `--recover-failure`, `--complete-registered27`, fixture cleanup or excluded-scenario deployment is part of this closeout.
2. Preserve the final journal and its referenced private stage logs outside Git, including original failure/recovery/inspection evidence for #27. Never commit local-state paths' contents, secrets, guest certificates or learner credentials.
3. Take an operator-controlled **post-deployment VMware snapshot** only after guest/runtime identity and snapshot semantics have been checked; suggested descriptive name `KINGDOMS-WSLPE41-CONFIG-VALIDATED`. **No snapshot is claimed to have been created by this document.**
4. Begin the **next phase as separate work**, without reopening the completed install wave:
   - learner-facing walkthroughs, ordered by concept → normal behavior → weakness → attacker reasoning → interaction → output → interpretation → consequence;
   - scenario-level `lpe.trainee` acceptance/proof and reset testing, explicitly independent of deployment closure;
   - guest isolation, access, management, reproducibility, licensing and student-distribution readiness checks before any course release.
5. Keep the NORTH AD course and original 20-technique released milestone untouched.

## Repository integration

The closing decision and runtime evidence are recorded in this feature branch. `main` is not modified by documenting this checkpoint. Integration/merge requires an independently reviewed branch/PR; the feature branch contains historical work beyond this single closeout.

Earlier `WSLPE45_*` planning and engineering contracts preserve their historical 45-scenario goal for audit, but **this closeout supersedes that goal for active scope**.
