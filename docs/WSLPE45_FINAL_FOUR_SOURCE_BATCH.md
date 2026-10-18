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
