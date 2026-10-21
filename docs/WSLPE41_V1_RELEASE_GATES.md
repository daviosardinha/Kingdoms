# WSLPE41 v1.0 — Fresh-install and release gates

**Status:** PLANNED, NOT RELEASED  
**Fresh-install integration branch:** `feature/wslpe41-fresh-full-installer` (draft PR #44; existing golden-master evidence remains on `feature/wslpe45-single-candidate-pilot`)  
**Scope:** One standalone Windows LPE installation containing **41 scenarios**. Existing historical source roles are reused internally, never deployed as separate 20/21 campaigns. Original numeric identifiers retained. Excluded: #25, #36, #38 and #40.  
**Proposed course release tag:** `windows-lpe-v1.0.0` (Kingdoms platform already has `v1.0.0`, `v1.1.0` and `v1.1.1`).  
**Owner:** Kingdoms operator.

## Confirmed baseline, not fresh-build proof

- `WSLPE-WS01` is a domain-free Windows 10 VM.
- The 20 original standalone scenarios have previously passed operator-side six-stage lifecycle qualification, but not 20 independently proven learner exploit paths.
- The selected 21 additional scenarios passed installation/configuration validation on the original pilot, recorded in private journal `wslpe45-resume-registered27-77c4f73d6782a328.json` (source `6b612e9abf2547dc76e4d4a89f4df1be6137f6e6`). These are **not** learner-exploitation proofs or a clean install.
- Master snapshot `KINGDOMS-WSLPE41-CONFIG-VALIDATED` and frozen-master receipt exist; the separate test clone passed isolation and #21 learner/operator read-only checks.
- The native `windows-lpe` course installer currently supports Stage 1 guest creation only. The existing `ansible/wslpe-foundation.yml` and `ansible/wslpe-operator-foundation.yml` are reusable but **not yet wired into the one-shot installer**; the complete 41-scenario lab is not installed. Existing #30 JEA registration and recovery procedures are sensitive to Windows PowerShell 5.1 WinRM restarts. Do not replay the old pilot's recovery commands to approximate a fresh install.

## Gate A — From-scratch build on a new native WSLPE instance

- [ ] Create a fresh, independent Kingdoms WSLPE instance via the existing course selector/VMware provider, automatically selecting a collision-free private subnet after checking host routes, VMware networks and registered instances, and creating a new workspace. No cloning or importing the existing golden master; do not contact or modify NORTH.
- [ ] Provision `WSLPE-WS01` as a workgroup guest with local non-admin `lpe.trainee`, intact UAC, Defender and Windows Firewall, fresh operator-only credentials, independent TLS trust/pins and management isolation.
- [x] Integrate the complete **41-ID manifest into one ordered installer transaction**, with a single journal, per-scenario apply/validate evidence, first-failure stop and no silent replay. This is source-tested integration only.
- [ ] From one fresh native guest, run the **single 41-scenario installation** in one operator action. Each scenario must be installed and configuration-validated in that same transaction; no separate baseline/additions commands, no old pilot journal, and no inherited master fixture. Preserve NORTH's shared-role source and exclude 25,36,38,40.
- [ ] Provide a safe fresh-instance setup for #30 JEA with independent out-of-band WinRM recovery; never assume existing registration on the old guest.
- [x] Implement the unified **source-tested 41/41 transaction engine** with a new-instance attestation interface, owner-only per-instance journal, exact stage proofs, JEA guest-console channel and recovery sentinel. Production guest execution is still disabled.
- [ ] Wire and host-validate the engine's fresh-native adapter: automatic collision-free network selection, exact native inventory/VMX identity, independent guest creation, foundation and operator management, per-stage execution and out-of-band JEA activation. Never inherit a development snapshot, private journal, sentinel or pinned source TLS certificate. **Source integration now exists for learner/operator foundation playbooks and for the 83-stage runner bridge; it is NOT wired to a production command or backed by real creation/console evidence.**
- [ ] Verify `41/41` configuration acceptance on the genuinely fresh guest. No unresolved install or preservation failures.
- [ ] Repeat the same clean install independently on **another new instance** to prove reproducibility. A single successful reused developer VM is insufficient.

**Current source checkpoint:** `scripts/wslpe41-install.py --plan` displays all 41 scenarios as one installation; `--execute` intentionally fails closed until the new VMware/Windows runtime adapter is proven. The single installation engine now maps **83 internal runtime stages** across the 41 scenarios: each scenario is applied and validated, while JEA #30 additionally requires source staging through Ansible **before** independent guest-console activation and fresh learner endpoint validation. All 20 original scenarios now have a WSLPE41-only post-role Windows identity check and an exact stage marker, gated to the new instance ID, its HTTPS/5986 management address and validated server certificate. The result-verifier source additionally binds the expected marker to the new VMX/instance, return code and transport, requiring an independent local WinRM recovery marker for JEA. The new `kingdoms/wslpe41_stage_executor.py` implements a bounded **single-stage Ansible execution adapter**: it checks the exact running native VMX, owner-only instance fixture file, private credentials, resolved single-guest HTTPS/5986 inventory, exact stage invocation and real Ansible exit/Windows marker before returning proof. It allows unrelated NORTH guests to remain running. **This adapter is not connected to a production installer yet; it cannot attest new-VM creation, provision Windows/TLS or activate JEA #30.** These source checks are not substitutes for native creation provenance, TLS trust provisioning, the complete fresh-install runner or live Windows evidence. These are internal steps of **one installation**, not 20+21 separate campaigns. Passing CI does not mean a new Windows guest was installed.

## Native foundation and one-shot runner integration (source-only)

- `kingdoms/wslpe41_foundation_executor.py` now invokes the **existing** `ansible/wslpe-foundation.yml` and `ansible/wslpe-operator-foundation.yml` with the same instance-bound native VMX, private inventory, TLS/5986 hostvars and private operator environment checks as the per-scenario adapter. It requires the actual Windows foundation markers and zero Ansible exit code. No secret-bearing transcript is stored in proof.
- The operator-account stage refuses to run without explicit handoff authorization and a **separately implemented, live VMware-console recovery callback**. Its Windows marker states `CREATED_NOT_AUTHENTICATED` on purpose. Authentication, vagrant retirement, independent TLS trust and management separation remain unproven.
- `kingdoms/wslpe41_native_stage_runner.py` implements the existing `FreshGuestRunner` interface for the 41-scenario journal. The 82 Ansible stages use the exact stage executor; JEA #30 activation can only use an independently implemented guest-console callback with the local WinRM recovery marker. Fresh-guest attestation is an injected **required** provider capability; the module does not invent it from a registration, callback stub or old VM.
- Both adapters have mocked negative-path regressions. **Neither module is a new CLI entry point.** `--execute` remains fail-closed. Native creation provenance, management NIC isolation, fresh TLS trust, operator authenticated handoff, real JEA console activation and two full clean builds must be completed before enabling it.

## October 21 partial VMware Stage 1 recovery integration

- The KINGDOMS fresh Windows guest `bf5369-wslpe-vmware` was successfully
  created and authenticated over NAT-side WinRM, but the initial Vagrant
  guest-communication/network step failed. Windows had no working `VMTools`
  core service, the exercise NIC was APIPA instead of `172.28.232.31`, and
  the VMware Tools MSI failed at `VM_SecureVGAuthDirs` with error 1603 after
  a VGAuth logfile sharing violation `0x80070020`.
- The existing provider now selects a WSLPE-only Tools installation script
  that temporarily stops/restores `VGAuthService` while preserving the native
  mount/WinRM/reboot handling. **Live WSLPE recovery later passed** for the
  same partial guest. This does not yet establish a repeatable clean-VM MSI
  install or rule out a different Tools failure on a second guest.
- The existing KINGDOMS operator console now supports exact-local-instance
  `load` and explicitly confirmed `repair_stage1`. Recovery reuses the
  existing Tools provider and `vagrant up WSLPE-WS01 --provision` containing
  `vagrant/fix_ip.ps1`, with independent running VMX, authenticated Windows,
  NAT MAC, Tools and expected exercise IP proof. Fails closed without a silent
  second retry. No alternate instance, vmnet manager, NORTH route, learner
  or attack fixture.
- **Live Stage 1 recovery completed on 2026-10-21** for the existing
  `bf5369-wslpe-vmware` guest. Operator evidence shows the provider's VMware
  Tools bootstrap completed, native `vagrant up WSLPE-WS01 --provision`
  successfully ran the WinRM and existing `fix_ip.ps1` provisioners, and the
  instance-bound recovery accepted VMware Tools, NAT and the exercise IP
  `172.28.232.31/24`. A separate read-only
  `scripts/wslpe41-install.py --native-status` returned
  `[NATIVE PROVIDED] bf5369-wslpe-vmware` with subnet
  `172.28.232.0/24` and guest address `172.28.232.31`.
  This closes the **existing guest's Stage 1 operational recovery** but is
  **not** an independent zero-state clean build or a complete 41/41 run.
- The `--execute` production installer, private management/TLS,
  out-of-band JEA #30 recovery and two clean-build reproduction gates remain
  blocked. The learner/operator foundation and 41 vulnerabilities were not
  deployed by this Stage 1 repair. See
  [native Stage 1 recovery](WSLPE41_NATIVE_STAGE1_RECOVERY.md).

## October 21 read-only foundation reuse checkpoint

- The existing WSLPE HTTPS certificate/WinRM/account audit is now also usable
  **before** learner/operator creation through
  `scripts/wslpe-account-audit.py --pre-foundation --expected-thumbprint <fresh-pin>`.
  It preserves strict default learner-required release checks and does not
  provision any Windows account. A new VM's HTTPS certificate thumbprint must
  be collected independently from the new VM console; the old WSLPE master's
  pin must never be reused. See
  [native foundation reuse](WSLPE41_NATIVE_FOUNDATION_REUSE.md).
- **Read-only source integration only:** the actual fresh guest's HTTPS trust,
  management-network isolation, WinRM-free recovery, learner account creation,
  dedicated operator authentication and credential handoff remain unproven.
  No WSLPE41 foundation playbook, scenario or JEA #30 operation has yet run on
  `bf5369-wslpe-vmware`.

## October 21 native creation and orchestrator source checkpoint

- `kingdoms/wslpe41_native_stage1_bridge.py` now also exposes a **private
  guarded native-creation entry point**. It checks the exact source HEAD and
  clean tracked checkout, reruns the live host subnet audit, rejects a stale
  operator-approved prefix, and compares instance/VMware VMX inventories before
  and after calling the existing Stage 1 provider exactly once. No alternate
  Vagrant project, VMnet creator, Windows bootstrap or second lab manager.
  It also inspects the registered VMX and VMware networking metadata after
  bootstrap to prove exactly two active adapters and one non-NORTH, non-shared
  vmnet owning the selected exercise /24. Failures leave the guest for
  operator investigation without automatic retry. The result is **VMX and
  vmnet creation provenance, not guest freshness**.
- `kingdoms/wslpe41_native_orchestrator.py` now composes guarded creation,
  the existing learner/operator handoff, and the existing `install_41` journal
  and 83-stage runner, all for the same native instance. Its runtime
  capabilities must be provided by independently reviewed management/TLS,
  guest-console recovery, fresh attestation and JEA activation implementations.
  **Those live capability implementations are still missing.** The module is
  private and is **not wired to `scripts/wslpe41-install.py --execute`**.
- New mock-only regressions reject stale prefix, changed co-tenant inventory,
  mismatched source or workspace, missing runtime capability, nonmatching
  management context and failed console handoff before 41-stage execution.
  Source CI passing is not live Windows or console recovery evidence.
- The earlier WSLPE pilot's authenticated Vagrant bootstrap over the corrected
  NAT address and the owner-scoped VMware recovery *rehearsal* are useful
  engineering evidence, but are **not** a separate fresh Windows 10 install or
  independent WinRM-free guest console proof.

## Current operator commands (read-only)

Use a **separate checkout** for this development branch. These checks do not stop NORTH, alter VMware networks, or create a guest:

```bash
git clone --branch feature/wslpe41-fresh-full-installer --single-branch \
  https://github.com/daviosardinha/Kingdoms.git \
  "$HOME/kingdoms-wslpe41-fresh"
cd "$HOME/kingdoms-wslpe41-fresh"
"$HOME/.goad/.venv/bin/python" scripts/wslpe41-install.py --plan
"$HOME/.goad/.venv/bin/python" scripts/wslpe41-install.py --host-plan \
  --workspace "$HOME/kingdoms-rebuild/workspace"
```

The additional workspace must exist. Supply **every other known Kingdoms workspace** (including the old WSLPE master workspace) with further `--workspace` arguments. The host-plan checks live Linux addresses, all IPv4 route tables, VMware vmnet metadata, `vmrun`'s running guest inventory and the instance manifests in the provided workspaces. It reports a **candidate**, not global registration coverage, an actual dedicated VMnet, or permission to boot a guest. No Vagrant, Ansible, Windows or host network mutations occur. It is safe to run while NORTH is active.

After a future native guest is created through the verified native provider, read-only registration inspection is available:

```bash
"$HOME/.goad/.venv/bin/python" scripts/wslpe41-install.py --native-status \
  --instance-dir /absolute/path/to/new/kingdoms/workspace/instance-id
```

This proves only the exact provided WSLPE VMX registration and VMware running state, **not** that it was created by the current install or that the 41 scenarios are installed. Production `--execute` remains disabled until the creation-provenance, fresh TLS/management and guest runner gates are implemented and tested.

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

**Release status as of 2026-10-21:** independent fresh installation NOT PROVEN; official v1.0 NOT RELEASED.
