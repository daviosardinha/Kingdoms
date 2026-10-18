# WSLPE45 — final four native-source and acceptance gates

**State: INCOMPLETE — do not deploy or release.**

Repository source of truth: `feature/windows-lpe-45-batch`.
Verified source checkpoint: 21/25 accepted *source candidates*; four still planned.
New live six-stage qualifications: 0/25. New independent learner-side exploit proofs: 0/25.

## 2026-10-18 #40 review artifact → guest copy-only staging

The `scripts/wslpe40-stage.py` handoff is now available for **opt-in
copy-only staging**. It verifies the exact clean feature checkout, a
successful matching native GitHub run, short-lived artifact source commit,
three-file inventory, native server/client SHA-256 values against both
manifest and independent CI log, unique running VMware WSLPE-WS01 VM,
the named current-state pre-#40 snapshot, the existing certificate-pinned
HTTPS/5986 management identity and no #40 artifacts/host in Windows.

An explicit interactive `--stage` plus approval phrase are mandatory for
copying `Wslpe40RpcOperator.psm1` and native server/client executables into
the existing protected WSLPE library. The transfer uses the previously
verified TLS-pinned WinRM channel and exact final paths, sends fixed-size
chunks, checks final digests and rejects preexisting destinations. An
interrupted copy leaves evidence for manual inspection; it does **not**
automatically overwrite or delete files. The learner client is intended
to run locally as standard `lpe.trainee`, never inside the privileged host.
No RPC listener, service, fixture, Windows Installer, account or JEA endpoint
is started or changed by this staging command.

The server's source previously used synchronous
`RpcServerListen(..., TRUE)`, which prevented the bounded 12-minute
shutdown from being reached. The fixed native code uses
`RpcServerListen(..., FALSE)` and checks listener stop/unregistration.
New regression tests require this bounded lifetime. Both executables must
come from a **new** green build after the fix, not an earlier archived binary.

**Copying is not qualification or deployment approval of a privileged
listener.** Before execution, independently review the host token,
endpoint security, learner negative cases, proof location and exact reset.
Keep #40 planned, 21/25 source qualified, and the batch disabled.
Preserve JEA #30 and NORTH.

## 2026-10-18 runtime preflight — authenticated but not deployed

The running standalone VMware WSLPE-WS01 has a second snapshot:
`KINGDOMS-WSLPE-PRE-LPE40-20261018`. Its prior `PRE-JEA` snapshot
remains available. The host reports 460 GiB free.

A direct, TLS-pinned authenticated HTTPS/5986 audit succeeded using the
existing `~/.goad/.venv/bin/python` interpreter. The system Python lacks
`pywinrm`; no dependency installation was needed. Windows confirmed an
enabled **non-administrator** `lpe.trainee`, exact workgroup host and
running management endpoint.

Existing account inventory also reported `vagrant` still active and
`kingdom.operator` absent. These are **release blockers** but not grounds
to rotate credentials during this isolated test; none were modified.

The new `scripts/wslpe40-runtime-preflight.py` reuses that certificate-pinned
WinRM path for a **read-only** snapshot of #40 fixture/library/proof and
host-process presence, plus existing JEA #30 registration/module state.
Offline evidence-contract tests and PS5.1 parse are required in CI. Do not
stage or run native binaries based on this source addition alone.

## 2026-10-18 accelerated engineering checkpoint (latest)

The current green native/source CI run is
[39124084759](https://github.com/daviosardinha/Kingdoms/actions/runs/39124084759)
on commit `55a64181bbddf84f77b81a2c7c83c94c7596dd15`.
All three GitHub Actions jobs passed. This builds real #40 local RPC
server/client binaries and archives them as a two-day unqualified source
review artifact, alongside the independent #25 MSI review archive.
The new `Wslpe40RpcOperator.psm1` parses with Windows PowerShell 5.1;
its explicit Prepare/Inspect/Reset only operates on a dedicated owned
fixture and is **not deployed or executed by CI**.

**Do not promote based on these builds.** #40 still needs a privileged
local host identity, exact learner authentication/authorization runtime
proof, negative cases and six-stage owned lifecycle. #36 still needs
native verifier acceptance, owned provider registration/namespace ACL
review and cleanup. #25 still lacks a real attacker-controlled repair
primitive and approved recovery rehearsal. #38 remains reviewed/blocked,
with no workaround to the previously rejected COM local-server source.

### Finish gates (no guest execution yet)

- [ ] #25 — show learner-controlled MSI repair trust boundary and exact
  registered ProductCode / owned uninstall / rollback / negative cases
- [ ] #36 — prove exact local WMI provider registration, identity, method
  access by `lpe.trainee`, safe negative cases and exact teardown
- [ ] #38 — secure independent implementation review or explicitly
  approve a genuinely distinct replacement; never repackage the
  rejected out-of-process DCOM fixture
- [ ] #40 — approved local privileged host, bounded native RPC learner
  proof, negative authorization and exact owned reset/reapply
- [ ] Record separately for **every** candidate: apply, vulnerable
  validation, reset, clean validation, reapply and revulnerable validation,
  with independent learner-side proof and a verified guest snapshot
- [ ] Keep `batch_execution_authorized: false` and all four planned
  until source acceptance and actual Windows qualification are complete

GitHub Issues are disabled for this repository (API 410), so this tracked
document holds the completion checklist. The standalone guest, existing
JEA #30, NORTH and shared AD role remain untouched. Never use `exit 1`,
`set -e` or `exec` in user copy/paste terminal commands.

## 2026-10-18 #25 security-boundary and recovery review

The native MSI artifact and its build provenance passed independent Kali
hash/manifest checks, and run 39120048388 passed all three GitHub jobs.
That closes **artifact integrity**, not the exploitation boundary.

The current fixed Windows Installer repair custom action writes an owned
proof marker but has no identified `lpe.trainee`-controlled primitive.
It cannot yet count as an actual Windows LPE route. In addition, the
operator's `install-attempted` ledger can survive a partial install
while the normal owned uninstall path requires `installed`, leaving
a recovery gap that must be designed before guest mutation.

See [#25 MSI runtime precheck and recovery blockers](./WSLPE25_MSI_RUNTIME_PRECHECK.md) for the exact evidence, failure-state
matrix, distinct-attack acceptance criteria and release blockers.
**Do not stage or execute #25 on WSLPE-WS01 at this checkpoint.**
The source-qualified count remains 21/25.

## 2026-10-18 offline MSI/RPC/WMI checkpoint

GitHub Windows native CI on this branch now passes all three jobs, including:
- #25: WiX 6.0.2 compiles an actual x64 per-machine MSI and read-only
  Windows Installer database inspection confirms a repair-scheduled, deferred,
  no-impersonation bounded custom action. **No install or repair was run.**
- #36: The managed .NET Framework WMI provider binary compiles, and reflection
  validates its dedicated class and two attributed management methods. **No
  provider or WMI namespace was installed.**
- #40: The MIDL interface generates real client/server C stubs; MSVC compiles
  both into object files. **No RPC server, listener, or client was executed.**
- #38: Out-of-process DCOM local-server source remains review-blocked.

These are **native artifact build milestones**, NOT learner-side proof,
runtime privilege-escalation validation, rollback acceptance, or candidate
promotion. All four index entries remain planned/pending and execution
authorization remains false.

WiX v6 introduces an Open Source Maintenance Fee for certain commercial uses.
Review the licensing implications before distributing Kingdoms course images.

## 2026-10-17 native prototype checkpoint

The coordinated source-only preliminary batch is tracked in
[WSLPE45 final-four source batch](./WSLPE45_FINAL_FOUR_SOURCE_BATCH.md).
Source CI now compiles the #25 native MSI custom-action **DLL** (not an MSI
installer), the #36 managed WMI provider **prototype** (not registered on
Windows), and the #40 local RPC **MIDL interface** (no server/client).
The #38 out-of-process DCOM local-server source remains absent because its
prior write was blocked by platform safety checks. Nothing from this
checkpoint is deployed to the guest, and it is not a qualification claim.

All four implementation-index rows stay planned/source_ci pending, and
batch_execution_authorized remains false. The original 21/25 source
candidates, 0/25 formal new six-stage qualification and learner-proof
counts remain unchanged.

## What remains

| Number | Distinct Windows-native mechanism | Source acceptance |
| --- | --- | --- |
| 25 | MSI repair custom action | Build genuine per-machine MSI; verify elevated repair boundary for a non-admin learner; uninstall and rollback. No `AlwaysInstallElevated` policy changes. |
| 36 | WMI privileged provider authorization | Register a dedicated managed/native provider and unique namespace; verify intended provider token, method-access permissions, and targeted removal. Never relax WMI root namespace ACLs. |
| 38 | DCOM server launch ACL | Build a dedicated out-of-process COM server; create task-owned CLSID/AppID and per-AppID permissions, prove non-admin activation, restore only owned registration. No global DCOM settings. |
| 40 | Custom Windows RPC authorization | Build MIDL interface and local-only RPC client/server; prove a local standard-user caller can reach the bounded lab operation and verify exact endpoint cleanup. No remote transport. |

## Batch-wide non-negotiable rules

- Target **WSLPE-WS01** only: Windows 10 workgroup and local non-admin `WSLPE-WS01\lpe.trainee`. The original **NORTH WS01** and the AD shared Ansible role remain frozen and untargeted.
- Use dedicated fixture directories, registry keys, service and interface names; disallow adoption of existing foreign objects.
- Each mechanism must use its authentic Windows primitive; a generic privileged script/service is not equivalent.
- Native CI must compile/build the actual artifacts and preserve their reproducible source/version provenance. CI parsing is not a runtime vulnerability proof.
- Keep `kingdoms/wslpe45_implementation_index.yml` truthful: these four remain `planned`/`source_ci: pending` until committed complete source plus CI evidence exists.
- `batch_execution_authorized: false` must stay disabled until an independent human review of exact-guest scope, artifact trust, and rollback.
- One consolidated operator run must cover all 25 additions: apply → vulnerable validation → reset → clean validation → reapply → revulnerable validation. Independent `lpe.trainee` proofs and clean RDP/WinRM access are separate release gates.

## Current blocker and safe resolution

The GitHub connection and branch writes work, but selected offensive native-source and build-workflow write attempts have been blocked by platform safety checks. Do not route identical rejected content through an alternative method. Redesign or review the flagged material and pursue an approved implementation path.

A GitHub Issue could not be created because **Issues are disabled on this repository (HTTP 410)**, so this branch document tracks the release gate.

**Do not claim 25/25 source complete or deploy the consolidated operator while any of these gates remain open.**
