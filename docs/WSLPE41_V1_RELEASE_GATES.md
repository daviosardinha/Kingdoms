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


## 2026-10-21: live learner and host recovery checkpoint

- Operator live evidence: `repair_license` returned
  `WSLPE_LICENSE_READY=PASS` on native `bf5369-wslpe-vmware` without manual
  Windows scripting. Pinned HTTPS/5986 account audit succeeded and observed
  the absent learner/operator accounts before foundation.
- Operator live evidence: `foundation_learner` completed with
  `WSLPE_LEARNER_FOUNDATION=PASS`; nonadmin membership and Remote Desktop
  Users were proven on that exact native VM. Actual learner RDP logon has
  **not** been proven.
- Dedicated per-instance `kingdom.operator` secret was prepared locally,
  **not applied**. The host recovery rehearsal subsequently passed owner
  systemd timer, VMware VMX inventory and byte-exact scratch VMX restoration.
  It did **not** test true WinRM-independent console recovery, actual
  stop/start, network cutover or rollback.
- The existing management vmnet planner now recognizes new native WSLPE41
  instance networks instead of assuming old WSLPE vmnet2/172.28.231. The
  planned management subnet and VMnet remain **not allocated**, and current
  running VMs prohibit modifying shared VMware networking. New operator
  account creation/authenticated handoff, isolation, 41/41 installation and
  two clean builds are still release-blocking.


## 2026-10-22 live host-network checkpoint

The guarded root-only management vmnet4 transaction **committed** on the
existing Kali VMware Workstation host, with interface
`172.28.233.254/24`, connected `172.28.233.0/24` link route,
source SHA256 `9717eecc5c8f05f4d214018a7da280c4484dc3d2e9a26a33902a9efe3e89f990`
and root journal status `committed`. The network configuration before
the additive operation had SHA256
`538955e59ce433b3764e19e5d46073f2b476af54c15d5260465867d87ca15bff`.

Only the **initial host allocation gate** is closed. VMware service
restart/reboot persistence, fresh Windows management NIC, isolated
operator HTTPS/WinRM, independent console recovery, real 41/41 scenario
deployment and a second clean build remain open. Do not interpret the
host network commit as course completion or readiness to merge.


## 2026-10-22 host-network persistence acceptance blocked

Initial vmnet4 allocation was committed successfully at .254, but an
explicit guest-free VMware network restart regenerated vmnet4 at
172.28.233.1/24 and temporarily reset NORTH vmnet10/vmnet99 to .1.
Host address persistence is therefore **NOT YET ACCEPTED**. A distinct
root-installed, vmnet4-only repair service/timer has been implemented
in the feature branch, source-tested, but is not yet installed on
the operator's Kali host. The existing NORTH address repair timer
remains independent and unchanged. Confirm host address and NORTH
recovery before attaching the Windows operator NIC.


## 2026-10-22: WSLPE vmnet4 keeper live PASS

Operator installed the root-owned vmnet4-only address keeper and active
15-second timer on Kali. Live output demonstrated
`VMNET4_HOSTADDR_PERSISTENCE=PASS` (twice, across timer interval) and
`VMNET4_HOSTADDR_PERSISTENCE_INSTALLED`. WSLPE `vmnet4`
was `172.28.233.254/24`; independent NORTH `vmnet10` and
`vmnet99` were `10.4.10.254/24` and `10.4.99.254/24`.
All guests were kept off and no shared network restart was used.

This **supersedes** the earlier "keeper not installed" status.
It closes local keeper installation and immediate host address acceptance,
not reboot persistence, Windows operator NIC, authentication or 41/41.

Next: provider-compatible third NIC on the fresh registered guest ONLY;
MAC-pinned Windows management IP, TLS-pinned operator HTTPS, console
recovery, learner isolation, existing 41-stage runtime and independent
clean-build validation.


## 2026-10-22: offline vmnet4 management NIC integration ready for operator acceptance

Source now includes a dedicated, journaled offline VMX third-NIC attachment
for the **existing fresh** `bf5369-wslpe-vmware`, preserving the provider's
NAT and vmnet3 exercise NIC. It refuses a guest start, foreign VMX,
other Workstation registrations, a stale source hash, an unhealthy
root-installed vmnet4 keeper, or an already present transaction journal.
A passing `--plan` is not a NIC installation; `--apply` requires explicit
owner approval and an exact pinned original VMX checksum.

This is NOT evidence of Windows NIC enumeration, a guest-side static
management address, operator HTTPS authentication, independent recovery
or any of the 41 scenarios. It is a bounded single-VM integration stage.
A separate Windows MAC-bound IP and operator handoff remain necessary
before any scenario execution or release claim.


## 2026-10-22: exact live management-NIC attachment committed

Kali operator evidence for existing native fresh `bf5369-wslpe-vmware`:
- One-time owner VMX permissions normalized from 0771 to 0600 with
  `[VMX SHA256 UNCHANGED]`, private receipt and exact original contents
  preserved.
- `scripts/wslpe41-attach-management-nic.py --plan` passed with original
  native registered VMX checksum
  `4674db8143136629f41c71e80626d3d370e4fe90a537e0d178668abd6aef51`.
- After separate exact operator approval, `--apply` reported
  `[COMMITTED] Third NIC added to exact offline native WSLPE VMX`.
  A private transaction journal exists at
  `~/.local/state/kingdoms-wslpe41-mgmt-nic/bf5369-wslpe-vmware/journal.json`.
- `ethernet0` provider NAT and `ethernet1` learner `vmnet3` preserved.
  New `ethernet2` is dedicated custom `vmnet4`, backed by the already
  proven host `172.28.233.254/24`.
- `[PASS] FRESH_WSLPE_MANAGEMENT_NIC_COMMITTED`.

**Host-side VMX guest adapter integration: PASS.** Do not repeat the one-time
permission or NIC transaction, clear its journal or attach an additional NIC.
The Windows VM was **not** booted by this command; no Windows management IP,
adapter MAC matching, TLS pin, operator account, independent console recovery,
learner isolation or 41/41 scenario execution is yet proven.

Next stage: boot **only** the exact fresh VMX, confirm Windows license
readiness and VMware Tools, obtain `ethernet2` generated MAC from the running
VMX and match exactly one enabled Windows network adapter in the local guest
console before applying `172.28.233.31/24` with no default gateway.
Preserve native Vagrant NAT bootstrap until pinned operator management,
WinRM-free recovery and learner separation are independently accepted.


## 2026-10-22: Windows detected uninitialized management virtual hardware

The fresh guest successfully booted and Windows licensing was active
(EnterpriseEval, LicenseStatus=1). Windows PowerShell displayed only
two operational network adapters:
- vmnet3 learner `00-0C-29-2F-D7-65`, `172.28.232.31/24`
- NAT bootstrap `00-0C-29-2F-D7-5B`, `192.168.213.249/24`

Kali VMX inspection independently proved the third adapter is present,
enabled and assigned to vmnet4, with generated MAC
`00:0c:29:2f:d7:6f`. The Windows PnP inventory also shows an Unknown
Intel(R) PRO/1000 MT Network Connection (`PCI\\VEN_8086&DEV_100F`),
while the two working devices are Intel(R) 82574L
(`PCI\\VEN_8086&DEV_10D3`).

The offline NIC append implementation omitted
`ethernet2.virtualDev`; VMware thus exposed its legacy E1000 model
rather than the working E1000e virtual device. This is the likely
explanation for Windows's uninitialized adapter; the PCI evidence is
strong but an exact management MAC match in Windows remains pending.

The future fresh-NIC template now pins `ethernet2.virtualDev="e1000e"`.
For the existing **committed** fresh guest, a distinct
`scripts/wslpe41-fix-management-nic-model.py` maintenance tool has been
added. It verifies exact registration, the committed *original* NIC
attachment journal, unchanged NIC0/NIC1, old management MAC, healthy
vmnet4 host-only network, and a pinned VMX hash. It changes only an
absent or exactly `e1000` third-adapter virtual device model to
`e1000e`, while offline under explicit authorization. It writes a
private second recovery journal and preserves the first NIC-attachment
journal; it performs no Windows driver installation, no VMware network
restart and no other VM modification.

**Status:** source fix implemented, live pending. Shut down only the
fresh WSLPE guest normally, establish zero running VMware guests before
applying, and boot only that guest afterwards to prove exact MAC
`00-0C-29-2F-D7-6F` becomes a working Windows adapter. Then apply
`172.28.233.31/24` on the **MAC-matched adapter only**, with no gateway.
The Windows operator/WinRM, negative learner/NORTH isolation and 41/41
fresh scenario acceptance remain open.


## 2026-10-22: live Windows E1000e management NIC enumeration PASS

Operator's Windows PowerShell screenshot confirms the fresh WSLPE guest
now enumerates and reports **Up** the third physical VMware NIC:
`Ethernet2`, InterfaceIndex `15`, MAC `00-0C-29-2F-D7-6F`,
Intel(R) 82574L Gigabit Network Connection. The independent
exact-instance model-repair transaction committed
`ethernet2.virtualDev=e1000e` while the VM was offline.
The pre-existing NAT and vmnet3 learner NICs still report Up:
`00-0C-29-2F-D7-5B` and `00-0C-29-2F-D7-65`.

**Windows hardware/driver enumeration gate: PASS.**
This supersedes the previous uninitialized PRO/1000 MT device finding.
Do not rerun either VMX attachment or model-repair journal transaction.

**Still pending:** apply/verify guest-only static
`172.28.233.31/24` on the unique MAC-matched management adapter,
with **no IPv4 default gateway or DNS** on vmnet4. Prove host/guest
reachability and negative management access from learner and NORTH,
then configure pinned operator HTTPS/5986, `kingdom.operator`
identity, console recovery, and complete 41/41 scenario execution.
No other lab or VMware networking service mutation is necessary.
