# WSLPE41 v1.0 — Fresh-install and release gates

**Status:** PLANNED, NOT RELEASED  
**Branch:** `feature/wslpe45-single-candidate-pilot`  
**Scope:** 41 standalone Windows LPE scenarios (20 foundation + 21 additional); original numeric identifiers retained. Excluded: #25, #36, #38 and #40.  
**Proposed course release tag:** `windows-lpe-v1.0.0` (Kingdoms platform already has `v1.0.0`, `v1.1.0` and `v1.1.1`).  
**Owner:** Kingdoms operator.

## Confirmed baseline, not fresh-build proof

- `WSLPE-WS01` is a domain-free Windows 10 VM.
- The 20 original standalone scenarios have previously passed operator-side six-stage lifecycle qualification, but not 20 independently proven learner exploit paths.
- The selected 21 additional scenarios passed installation/configuration validation on the original pilot, recorded in private journal `wslpe45-resume-registered27-77c4f73d6782a328.json` (source `6b612e9abf2547dc76e4d4a89f4df1be6137f6e6`). These are **not** learner-exploitation proofs or a clean install.
- Master snapshot `KINGDOMS-WSLPE41-CONFIG-VALIDATED` and frozen-master receipt exist; the separate test clone passed isolation and #21 learner/operator read-only checks.
- The native `windows-lpe` course installer currently creates the WSLPE guest and foundation, **not the complete 41-scenario lab**. Existing #30 JEA registration and recovery procedures are sensitive to Windows PowerShell 5.1 WinRM restarts. Do not replay the old pilot's recovery commands to approximate a fresh install.

## Gate A — From-scratch build on a new native WSLPE instance

- [ ] Create a fresh, independent Kingdoms WSLPE instance via the existing course selector/VMware provider, choosing an unused private subnet and a new workspace. No cloning or importing the existing golden master; do not contact or modify NORTH.
- [ ] Provision `WSLPE-WS01` as a workgroup guest with local non-admin `lpe.trainee`, intact UAC, Defender and Windows Firewall, fresh operator-only credentials, independent TLS trust/pins and management isolation.
- [ ] Install and independently validate all 20 shared foundation scenarios without affecting the NORTH shared-role contract.
- [ ] Install and independently validate exactly these 21 additions: 21,22,23,24,26,27,28,29,30,31,32,33,34,35,37,39,41,42,43,44,45. Never deploy excluded 25,36,38,40.
- [ ] Provide a safe fresh-instance setup for #30 JEA with independent out-of-band WinRM recovery; never assume existing registration on the old guest.
- [ ] Create a unified, fail-closed installer/controller using exact inventory, VMX and native guest identity; keep private per-stage evidence and stop on partial, ambiguous or drifted state. No inherited development snapshot, private journal, sentinel or pinned source TLS certificate may be used to bypass a failed stage.
- [ ] Verify `41/41` configuration acceptance on the genuinely fresh guest. No unresolved install or preservation failures.
- [ ] Repeat the same clean install independently on **another new instance** to prove reproducibility. A single successful reused developer VM is insufficient.

## Gate B — Merge into `main` (engineering acceptance)

- [ ] Source CI and native Windows PowerShell 5.1 tests pass.
- [ ] Review **the entire feature-branch integration diff**: initial GitHub comparison found 808 commits ahead of `main` and at least 300 file entries (compare response was capped). In particular review modifications to shared `ansible/roles/windows_lpe`, core installer, course registry and VMware networking; prohibit NORTH regression.
- [ ] Source and installed artifacts must contain no learner secrets, operator credentials, management TLS material or private runtime evidence.
- [ ] Run the relevant existing NORTH/GOAD regression checks with no mutation to the deployed NORTH lab.
- [ ] Raise and review a PR with both fresh-build reports. Merge only after gates above pass; not simply because historical deployment logs or CI are green.
- [ ] Do not label the course released merely by merging installer source into `main`.

## Gate C — Official Windows LPE v1.0 course release

- [ ] From the genuine local non-admin learner session, prove each advertised scenario's intended privilege boundary, consequence, negative control and reset/restore. Distinguish bounded privileged actions from arbitrary SYSTEM execution. #21 has completed read-only learner/operator preflights only, **not exploitation**.
- [ ] Validate offline learner usability and distribution isolation (RDP/NLA or intended console path; no learner access to installer/hypervisor/WinRM operator controls), per-instance credential rotation and licensing.
- [ ] Validate release artifact or reproducible installer, initial start/stop, operator restore, teardown, course documentation and per-learner distribution.
- [ ] Publish release notes and an explicit 41-ID manifest. Mark course released in registry/README and tag the relevant accepted `main` commit as `windows-lpe-v1.0.0`.

## VM cleanup — only after release gates

**Retain until fresh-install and recoverability are proven:** the WSLPE golden reference, its snapshot, original private evidence and at least one separately recoverable backup. Do not delete or revert the master yet.

After two clean builds, approved release image and validated backup, delete disposable learner test clones and superseded temporary VMs **one exact VMX at a time**, after explicit operator review. Do not delete NORTH or operator evidence and do not auto-clean by prefix.

## Canonical supporting records

- [41-scenario deployment closeout](WSLPE41_DEPLOYMENT_CLOSEOUT_2026-10-19.md)
- [Learner acceptance](WSLPE41_LEARNER_ACCEPTANCE_PLAN.md)
- [Core integration plan](WSLPE_CORE_INTEGRATION_PLAN.md)
- [Standalone 20 foundation qualification](WSLPE_20_TECHNIQUE_FAST_TRACK.md)
- [JEA lifecycle recovery risk](WSLPE_JEA_ACTIVATION_RECOVERY_GATE.md)

**Release status as of 2026-10-20:** independent fresh installation NOT PROVEN; official v1.0 NOT RELEASED.
