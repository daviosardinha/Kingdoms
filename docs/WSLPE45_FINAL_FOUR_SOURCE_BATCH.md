# WSLPE45 — final four native-source batch (prototypes only)

**State: SOURCE RESEARCH / NOT DEPLOYABLE / NOT QUALIFIED.** This checkpoint is in
`feature/windows-lpe-45-batch`; no Windows guest, NORTH, VMware, or shared
Ansible role was changed. The machine remains 21/25 candidate sources and
0/25 formal new-batch six-stage qualifications.

The source files below are deliberately incomplete, isolated **native
interface prototypes**. Building or parsing a file does not prove that an
attack path exists. The four implementation-index records must remain
`status: planned`, `source_ci: pending`, `learner_proof: pending`,
`six_stage_qualification: pending`. The global `batch_execution_authorized`
flag must remain false. None of the four scenario playbooks is present.

| # | Mechanism | Preliminary source | Native-build gate | Critical missing lifecycle |
|---|---|---|---|---|
| 25 | Windows Installer repair custom action | `Kingdom25Repair.cpp` | MSVC DLL export, link against `msi.lib` | Genuine per-machine MSI authoring and repair trigger, verified CustomActionData, protected marker ACL, owned uninstall/rollback, real learner test without AlwaysInstallElevated |
| 36 | Managed WMI provider authorization | `Kingdom36WmiProvider.cs` | .NET Framework compile against WMI instrumentation assemblies | Dedicated namespace, schema/provider registration, method authorization, exact provider identity, owned namespace/provider cleanup; preserve root namespace ACLs |
| 38 | DCOM launch permissions | **No accepted source** | Review-approved local-server native build, CLSID/AppID contract | Owned CLSID/AppID per-application security descriptor, local non-admin activation evidence and controlled unregistration; no machine-wide DCOM changes |
| 40 | Local RPC authorization | `Kingdom40LocalRpc.idl` | MIDL-generated local client/server stubs | `ncalrpc`-only implementation, explicit bounded authorization decision, authenticated standard user test, owned endpoint shutdown and cleanup |

## Coordinated native source round — all four prototypes, not deployment

Windows native CI now builds #25's MSI with its bounded repair-request nonce,
#36's LocalSystem-scoped WMI provider with time-bounded revocation, #38's
bounded LocalService COM host and fixed-local IDispatch learner verifier, and
#40's native local RPC server/client and a compiled source-only atomic operator
refresh bridge. #38 was newly implemented as a *source prototype*; it is not
an approved DCOM activation/registration lifecycle.

#25 still requires a standard user's actual ability to trigger privileged
repair. #36 requires owned namespace/registration permissions and cleanup.
#38 requires unique owned CLSID/AppID and per-AppID launch rights, not global
DCOM changes. #40 still has the original guest operator installed, with no
approved host/learner proof. No source-only build promotes any of these to
accepted candidates.

## 2026-10-18 coordinated implementation wave — #25 / #36 / #40

This checkpoint changes the previous one-technique-at-a-time workflow.
Code for **three independent candidates** is developed and source-gated on
the same feature branch; routine GitHub/CI diagnosis no longer requires
repeated Kali pulls. These changes are **unqualified source**, not release.

- **#25 MSI**: the partial-install recovery ledger parser regression has
  been corrected; original native Windows PowerShell syntax failure was
  caused by a truncated SHA-256 expression. Exact guest recovery execution
  and actual learner-controlled repair exploitation remain unproven.
- **#36 WMI**: the native managed provider now accepts a limited learner
  nonce for an exclusive create operation under the exact owned fixture,
  illustrating the *method authorization* boundary. A separate exact-local
  WMI verifier source can request Status or Proof, without remote targets.
  Provider registration/namespace ACLs, authorized host identity and
  uninstall are **not implemented/approved**, and the new verifier's native
  compile and live operation still need independent qualification.
- **#40 local RPC**: a concrete `ncalrpc`-only server and client are present.
  The server authenticates/im-personates the exact local learner before
  performing a deliberately under-authorized, bounded protected marker
  write. The client is fixed to local RPC with Windows authentication.
  Windows CI is configured to link actual MIDL-generated client and server
  executables; no listener is started by CI. Protected fixture preparation,
  runtime token evidence, negative tests and reset still remain.
- **#38 DCOM**: source is **review blocked**. No workaround for the earlier
  rejected implementation and no substitution with #27 COM hijacking.
  Consider another genuinely distinct candidate from the original 45
  only through an explicit engineering decision.

**Acceptance remains unchanged**: all four index entries stay
`planned / source_ci: pending`, `batch_execution_authorized: false`,
21/25 source-qualified, 0/25 new formal six-stage learner proofs. Native
Windows CI and any source tests added in this wave must pass before making
a new source-readiness claim. A native build does not establish real LPE.

## 2026-10-18 #40 owned fixture + native artifact gate

The `Wslpe40RpcOperator.psm1` module adds a **standalone, opt-in**
Prepare/Inspect/Reset lifecycle for the dedicated local RPC proof fixture.
It requires the exact Windows 10 workgroup guest, protected source library,
an elevated interactive console and explicit operator approval for any
mutation. Inspection requires exact learner-selected nonce bytes. Reset
refuses unrecognized/linked objects or a still-running native RPC server.

CI now parses the module on Windows PowerShell 5.1 and retains the native
server and client EXEs as a two-day **source-review-only** artifact. Nothing
is executed, registered, installed or staged on the existing guest.

**Still missing:** an approved, privileged native host launch/identity
contract, independent authentication and negative-authorization runtime
checks, guest-owned artifact staging and reset/reapply proof. A proof file
containing a learner nonce is evidence of a bounded privileged operation,
**not automatically evidence of arbitrary code execution or SYSTEM takeover**.
Do not label #40 fully qualified until the actual intended escalation
boundary is demonstrated.

## 2026-10-18 native packaging and metadata checkpoint

An isolated WiX 6.0.2 XML package source
ansible/files/wslpe45/Kingdom25RepairPackage.wxs and dedicated payload
were added. GitHub Windows CI **builds** a real x64 per-machine MSI using the
previously compiled #25 custom action DLL, then opens its Windows Installer
database **read-only** and verifies that the repair entry is deferred,
no-impersonation and wired to the expected DLL export.

The package is repair-scheduled via the REINSTALL property; it is **not
installed, repaired or uninstalled** in CI. This is stronger than DLL-only
compilation but does not demonstrate a learner privilege boundary. Native
MSI repair authorization, fixture ACL/reparse safety, independently verified
proof, per-instance installation and rollback remain outstanding.

Windows CI also checks the #36 compiled WMI assembly's management-method
attributes and compiles the generated #40 MIDL client and server C stubs,
without installing WMI or registering an RPC endpoint. These changes are
offline checks only and do not promote either scenario to a candidate.

**Commercial licensing note:** WiX v6 introduced an Open Source Maintenance
Fee for some commercial uses. Nomad Kingdom must review applicable WiX
licensing before using these build outputs in a paid course or release.
A passing open-source CI job does not grant distribution rights.

## 2026-10-18 #25 non-clobbering source checkpoint

The MSI custom action now uses `CREATE_NEW` rather than `CREATE_ALWAYS`
for its fixed proof marker, refusing an existing file/link instead of
overwriting it. A source regression test enforces the non-clobbering
contract; the native Windows build remains the compile gate. This does
**not** make a writable or reparse-point parent safe, implement owned
fixture provisioning, authorize a non-admin MSI repair, or provide
uninstall/reset proof. The repair can only be repeated after a reviewed
owned reset removes its old marker. No MSI was installed or run.

## 2026-10-18 #25 owned read-only inspection checkpoint

Added `ansible/files/wslpe45/Wslpe25RepairInspection.psm1`, a source-only
Windows PowerShell inspection function. It reuses the existing exact-guest
and ownership helpers (fixture #25), requires privileged ownership and
non-writable ACLs along the owned fixture ancestors, refuses reparse points,
and checks the proof-file absence before repair or exact marker after repair.
It does not create directories, change ACLs, invoke MSI, or delete anything.
The new offline regression check verifies these source invariants only.

**Not yet qualified:** this gate has not been parsed/executed on Windows
PowerShell 5.1; no Windows ACL evidence has been collected and no independent
race-resistant native path/open review has occurred. A passing inspection
alone does not establish atomic filesystem safety. No install/repair/reset
lifecycle or low-privilege authorization proof exists. All four index rows
remain planned and execution authorization remains false.

## 2026-10-18 #25 explicit fixture preparation source checkpoint

Added `ansible/files/wslpe45/Wslpe25RepairPreparation.psm1`. A trusted
local operator can explicitly request an `Inspect` or `Prepare` action
only on the exact standalone WSLPE-WS01 machine. The preparation function
requires an elevated local Administrator, the original protected operator
library, protected non-writable fixture ancestor ACLs, no reparse-point
ancestors, and a completely absent #25 fixture entry before using
`New-Wslpe45OwnedFixture -Number 25`. It then runs the independent
pre-repair inspection. A failed post-creation verification preserves state
for investigation instead of attempting blind cleanup.

**Source only:** importing the module has no side effects. GitHub Windows
CI parses (but does not import or execute) both PowerShell modules, and
the offline test suite enforces their API/guard contracts. This is not
an approved deployment command, an installer, a non-admin repair trigger,
or a complete teardown. The #25 package is still uninstalled; MSI product
identity, owned uninstall/reset, negative authorization behavior, and
learner-side six-stage qualification remain open. Do not use
`-Action Prepare` on the existing guest without separate operator
authorization and a reviewed recovery plan.

## 2026-10-18 #25 MSI product identity and provenance gate

The native Windows CI now inspects the built MSI database's ProductCode,
ProductName, Manufacturer, ProductVersion and ALLUSERS values **read-only**,
requires a GUID ProductCode, and records the MSI/DLL SHA-256 digests alongside
the source commit and pinned WiX version. The build log reports the ProductCode
and MSI digest. This prepares an explicit identity to match during later
owned product installation/repair/uninstall, rather than guessing which
installed package should be modified.

This remains a **build-only** check. It neither invokes msiexec nor
registers the MSI, and it does not persist or distribute an MSI artifact to
learners. The exact installed product identity, Windows Installer privilege
behavior under the learner account, rollback and uninstall must still be
demonstrated on the separately approved standalone guest. No promotion of
the four incomplete candidates or batch execution is authorized.

## 2026-10-18 #25 native MSI property reader regression

The initial MSI metadata provenance CI failed in the native Windows job while
source-only and syntax jobs passed. The Windows logs showed each property
value bracketed by spaces, consistently across ProductName, Manufacturer,
ProductVersion, and ALLUSERS. Source review identified two COM method calls
(`View.Execute()` and `View.Close()`) whose return values were not suppressed
inside a PowerShell function. PowerShell can emit these values into the
function result alongside the actual MSI record string.

The reader now assigns both COM call results to `$null`, preserving strict
per-property comparisons without trimming or weakening the expected MSI
identity. The existing regression test asserts both suppressions.
**Native CI confirmation passed** in GitHub Actions run 39119544326
(three jobs successful at source commit b8d6b88); no installer or
Windows guest execution has occurred. The later review-artifact archiving
change requires its own new CI confirmation.

## 2026-10-18 #25 opt-in local MSI product lifecycle source

The feature branch now contains `Wslpe25MsiOperator.psm1`, a standalone
Windows PowerShell 5.1 module with separate **Inspect**, **Install**, and
**Uninstall** operations. Import has no side effects. Actual mutating
operations require WSLPE-WS01 identity, existing #25-owned fixture, a
protected module directory, elevated local Administrator, interactive
VMware console session, and an action-specific approval phrase.

Install reads the fixed protected `Kingdom25Repair.msi` using the native
Windows Installer database API, requires exact package metadata and an
operator-approved SHA-256 digest, refuses any registered product/foreign
Program Files folder, and writes an owned recovery ledger **before**
invoking native `msiexec`. A failed installation leaves the ledger and
guest state intact for manual review. No automatic retry.

Uninstall requires the same staged MSI digest, exact owned ledger,
registered ProductCode, and installed state. It invokes the native
uninstaller only for that ProductCode, verifies no registration and no
Program Files payload remain, checks the bounded proof if present, and
removes only the verified dedicated fixture. Foreign files, reparse
points, unexpected product states, or changed metadata cause refusal.

**This is a code-ready operator prototype, NOT deployment approval.**
No MSI is staged in the existing guest, no real install/repair/uninstall
has been executed, and there is no non-admin learner repair proof or
approved rollback rehearsal. Windows CI parses the module without
importing or executing it; a regression test enforces source contracts.
The operator is intentionally not wired into the batch playbooks.
A separate artifact trust review and snapshot-backed WSLPE-WS01
maintenance authorization are required before any mutating command.

The non-admin **repair trigger** remains an independent learner-side
exercise: the operator module installs and uninstalls only. No source
candidate is promoted; the count remains **21/25** and
`batch_execution_authorized: false`.

## 2026-10-18 #25 short-lived MSI artifact handoff (source review only)

The Windows native-build job now archives the actual compiled
`Kingdom25Repair.msi`, custom-action `Kingdom25Repair.dll`, and
`Kingdom25Repair.provenance.txt` as a two-day GitHub Actions artifact on
pushes to the exact WSLPE feature branch. Missing files fail the job.
The archive is **not a release, not approved for learner distribution,
not guest staging, and not an installation authorization**.

This closes the previous CI-to-operator provenance gap for review:
an operator can obtain the exact package plus its ProductCode and hashes
from the same build and independently compare the manifest to the files
before considering a separate guest staging decision. No workflow step
installs the MSI or invokes the local MSI operator.

Still required before a live run: review the pinned WiX v6 commercial
licensing implications, independently verify the artifact and package
semantics, approve a trustworthy transfer into the WSLPE-only protected
library, capture the guest snapshot and recovery path, and review
the initial install, learner repair behavior, and uninstall/reset
failure modes. The existing JEA #30 and NORTH remain untouched.
All four source index rows remain planned/pending.

## Four technique-specific acceptance boundaries

### #25 — Installer

The custom-action export writes only a marker beneath its hardcoded fixture
directory. It accepts only a fixed installer-supplied `CustomActionData`
value. The native source must not be mistaken for a Windows Installer
package. Source qualification requires a **built MSI** whose install/repair
sequencing and rollback are independently inspected on Windows. The MSI
must not relax system-wide installer policies or accept arbitrary file paths.

### #36 — WMI

The managed prototype exposes two explicit management methods: a harmless
status result and a bounded marker. Its decoupled hosting model does NOT
by itself establish privileged execution. The model requires a supported
provider registration flow, the exact process token, safe namespace
permissions, and a separate cleanup path. Microsoft notes the older
System.Management.Instrumentation libraries are in final state; confirm
compatibility before selecting a release implementation.

### #38 — DCOM

A prior write of an executable COM local-server fixture was rejected by
platform safety checks. Do not encode, fragment, rename, or otherwise
repackage the rejected content. Keep #38 pending a reviewed implementation.
An in-process COM registration hijack from #27 is NOT a substitute for
a genuine **out-of-process** DCOM launch-ACL boundary.

### #40 — RPC

The MIDL interface file is an interface definition only. The eventual
service must be restricted to local RPC transport and never expose a TCP,
named-pipe, or remote network listener. A generated stub is not an
authorization test, nor proof of privilege. Use only dedicated fixture
objects and lab-owned proof markers.

## Build/qualification progression

1. Offline/native CI may compile the three accepted prototypes, if their
   toolchains are present. This is an artifact syntax/build check ONLY.
2. Independently review and finish each native lifecycle and negative path.
3. Build/test a complete owned local deployment and reset implementation
   and re-run the native-build checks.
4. Only then move the relevant index row from planned to source candidate
   after committed sources and CI evidence. No row is promoted here.
5. A later separately authorized exact-WSLPE run must perform
   apply → vulnerable → reset → clean → reapply → vulnerable and prove the
   learner context; first run must stop on errors, with owned rollback.
6. Fresh-install, account hardening, guest isolation and commercial
   student-ready gates remain separate.

## References

- Windows Installer deferred action context:
  https://learn.microsoft.com/en-us/windows/win32/msi/obtaining-context-information-for-deferred-execution-custom-actions
- .NET Framework WMI managed instrumentation:
  https://learn.microsoft.com/en-us/dotnet/api/system.management.instrumentation.instrumentation?view=netframework-4.8.1
- WMI provider hosting and security:
  https://learn.microsoft.com/en-us/windows/win32/wmisdk/provider-hosting-and-security
- MIDL interface definition:
  https://learn.microsoft.com/en-us/windows/win32/rpc/using-midl

**Unchanged:** NORTH domain/WS01 and the frozen 20-technique role. No VM
write, installer invocation, provider registration, DCOM registration,
RPC listener or scenario activation is performed by this source batch.
