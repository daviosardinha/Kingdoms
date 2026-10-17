# WSLPE #30 — JEA PS5.1 WinRM lifecycle incident and safe release gate

**2026-10-17 update: JEA #30 local-console reset/clean/reapply and post-reapply learner proof were observed successfully on WSLPE-WS01; automated batch qualification and effective administrator-token proof remain pending.**
This is a verified user-observed Windows runtime incident, not just source inference.
Scope is the exact standalone WSLPE-WS01 workgroup guest. NORTH/GOAD VMs and
the shared 20-technique role remain untouched. Vagrant bootstrap stays enabled
until the *entire* machine is student-ready.

## Confirmed evidence

1. A genuine real-VM restoration of KINGDOMS-WSLPE-PRE-JEA was exercised,
   followed by VMware-console learner sign-in and successful WinRM HTTPS/5986
   authenticated checks. Recovery from a deliberately disrupted WinRM service
   was accomplished manually at the VMware console, using an elevated vagrant
   session and Start-Service WinRM. Host-level automatic recovery remains unproven.
2. Windows showed one Kingdoms45JEA registration, a dedicated
   Kingdoms45JEA module and a dedicated lab fixture. The module owner marker
   matched WSLPE45:30:jea_role_capability_misconfig.
3. The learner WSLPE-WS01\lpe.trainee (Medium integrity, nonadmin) successfully
   invoked Invoke-Kingdoms45Maintenance -Operation Status using the dedicated
   JEA endpoint and received WSLPE45_JEA_STATUS.
4. The same learner invoked the deliberately scoped Proof operation and received
   WSLPE45_JEA_PROOF_WRITTEN. The lab-owned proof.txt showed a dedicated
   "WinRM Virtual Users\WinRM VA ..." execution identity, not the learner.
   This proves distinct privileged-context execution, not by itself SYSTEM
   identity or complete exploitability of any arbitrary command.
5. Get-LocalUser sent through the endpoint was rejected as not recognized:
   the intended restricted command surface is enforced.
6. WinRM Operational log at 12:21:40 PM (local guest time) showed successful
   WSMan Config/Plugin Put operations (Event IDs 145/132), service stopping
   (211), and at 12:21:42 PM service stopped successfully (212).
   The dedicated JEA module/file timestamps were approximately 12:21:38 PM.
   The Windows System event 10149 corroborated that WinRM was no longer
   listening. WinRM was Auto start and exited with code 0. Exact caller PID
   for the service stop has not been independently established.
7. After WinRM was manually started from the guest's elevated local console,
   the normal pinned TLS HTTPS management worked again, and the JEA endpoint
   remained functionally accessible to the learner.

### Root cause: Windows PowerShell 5.1 NoServiceRestart is NOT implemented

Official Microsoft Windows PowerShell 5.1 reference:
https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/register-pssessionconfiguration?view=powershell-5.1

Microsoft explicitly states that the -NoServiceRestart functionality on
Register-PSSessionConfiguration is NOT implemented in Windows PowerShell 5.1,
and won't be backported. The feature was implemented in a PowerShell 7.5
preview. Therefore this source statement **cannot** be interpreted as a
no-stop/no-restart guarantee in the target OS:

    Register-PSSessionConfiguration -Name $name -Path $config -NoServiceRestart -Force

The guest WinRM stop during Config/Plugin registration is consistent with
this documented behavior. Until separately reproduced with full process
attribution, label the component cause "strongly supported", not as an
independently identified service-control caller.

PowerShell 5.1 Unregister-PSSessionConfiguration has different documented
behavior, but removal still changes the remoting plug-in. Treat BOTH
registration and removal as potentially disruptive; schedule via a local
independent operator channel.

## Immediate source safety correction

- ansible/wslpe45/jea_role_capability_misconfig.yml now explicitly rejects
  apply and reset in the WSLPE pre_tasks using the controller-side Ansible
  fail action. The guard runs before any Windows guest change, even when a
  caller limits execution to the WSLPE group.
- scripts/wslpe-jea-single.py is now PLAN ONLY, and refuses --apply even
  with --recovery-rehearsed. No broad batch or automatic restart.
- Native JEA source and the current functioning endpoint are preserved.
  No destructive guest action is authorized by this change.

## Next engineering step: independent JEA endpoint lifecycle

Implement a separate, narrowly scoped, auditable local-console or
out-of-band guest-management stage **after** fixture file preparation, not
within a WinRM-hosted Ansible execution. Verify exact registered WSLPE
guest and WORKGROUP, snapshot backup and ownership, and an authenticated
management session BEFORE endpoint registration. Accept that WinRM may
stop and arrange a controlled service recovery *from outside WinRM*.
After it returns, prove both existing HTTPS management and learner JEA
Status again. On failures, stop; don't silently retry, clean up unrelated
plugins, disable vagrant, touch NORTH, or run the other scenarios.

Do NOT try to fix this by merely increasing timeouts, blindly restarting
WinRM inside the same remote session, ignoring TLS errors, or using a
different public credential.

## Qualification status

| Gate | State |
| --- | --- |
| Pre-JEA snapshot exists; real restoration exercised | PASS |
| Learner VMware console access and nonadmin security token | PASS |
| Pinned HTTPS/5986 management after recovery | PASS |
| JEA registration/owner evidence | PASS |
| Learner Status and bounded Proof operations | PASS |
| JEA virtual account context and restricted command surface | PASS |
| Effective local Administrators token membership | NOT YET PROVEN |
| Safe independent JEA reset/clean/reapply lifecycle on existing guest | PASS — witnessed local console + Kali checks (2026-10-17) |
| WinRM recovery from local reset/reapply, plus authenticated HTTPS after each | PASS — observed (2026-10-17) |
| Manual JEA six-stage demonstration | PASS — initial functional test, reset, clean, reapply, final functional test |
| Automated 25-technique six-stage qualification | PENDING |
| Student-ready Windows 45-exercise image and vagrant retirement | PENDING |

The original snapshot is a developer recovery point, not a final student
image. No change to NORTH/shared role, no VM/snapshot mutation, and no
automatic Vagrant account retirement is part of this source-only safety fix.


## JEA #30 — independent local-console lifecycle (LIVE TESTED ON EXISTING GUEST)

The remote Ansible JEA scenario remains deliberately blocked for apply/reset.
On Windows PowerShell 5.1, the previously used -NoServiceRestart was
ineffective; our guest WinRM actually stopped during endpoint registration.
The repository now provides two separate phases:

1. **Stage** exact owned PowerShell modules through existing pinned WSLPE
   HTTPS/5986, without registering or removing JEA. The new
   ansible/wslpe45/jea_local_stage.yml is scoped to WSLPE-WS01 and rejects
   unexpected inventory, domain membership, symlinks and missing approval.
2. **Run** endpoint Inspect, Reset or Apply from a high-integrity administrator
   in the interactive VMware Windows guest console. The new
   WslpeJeaLocal.psm1 validates the local console/identity and JEA ownership,
   then performs an isolated fixture operation. Whether it succeeds or fails,
   it checks WinRM service status, starts that service if it stopped, and
   verifies that HTTPS/5986 listens. It never changes the TLS certificate,
   global listener settings, firewall, NAT or any other guest.

**Source-only verification from Kali:**

    cd "$HOME/kingdoms-lpe-standalone"
    git pull --ff-only
    "$HOME/.goad/.venv/bin/python" -m unittest -v \
      tests.test_wslpe_jea_single tests.test_wslpe45_jea_candidate
    "$HOME/.goad/.venv/bin/python" scripts/wslpe-jea-single.py

To explicitly stage source only, after inspecting the tests:

    "$HOME/.goad/.venv/bin/python" scripts/wslpe-jea-single.py --stage

This requires a clean feature/windows-lpe-45-batch checkout, the exact
running WSLPE VM, the PRE-JEA snapshot, authenticated certificate-pinned HTTPS,
an independently resolved WSLPE-only inventory, and human confirmation
with the exact phrase STAGE WSLPE JEA 30.

**Read-only verification in the existing elevated VMware Windows console:**

    Import-Module 'C:\ProgramData\KingdomsWSLPE45\lib\WslpeJeaLocal.psm1' -Force
    Invoke-Wslpe45JeaLocal -Action Inspect

The current guest ALREADY contains a functioning JEA endpoint. Do not run
Apply on it. Only in a separately approved, snapshot-backed maintenance
window, after inspecting the current state, run exactly one of:

    Invoke-Wslpe45JeaLocal -Action Reset
    Invoke-Wslpe45JeaLocal -Action Apply

Between Reset and Apply, verify JEA is actually clean using the existing
certificate-pinned Kali inspection. After Apply, verify management HTTPS and
learner Status/Proof/negative-command behavior independently again.

**Limit:** local WinRM Running/listener checks alone do not prove authenticated
management, but the pinned Kali HTTPS audit was independently repeated and
passed after both reset and reapply. A future partial failure can still leave
partial state; do not retry automatically or delete unknown files. Manual
six-stage evidence has passed; automated qualification and release gates are
pending. NORTH, Vagrant bootstrap, and frozen shared role remain unchanged.

For unattended commercial cloud image creation, an independently running
SYSTEM task or equivalent guest-local stage is still required; that future
integration is NOT authorized by the developer-local console implementation.


### 2026-10-17 local console detector correction

Observed on the real VMware guest after successful WSLPE JEA source staging:
the elevated vagrant PowerShell shows SESSIONNAME=[] and SessionId=1
with PSSenderInfo=False, while quser reports lpe.trainee console 1 Active.
The original local runner incorrectly rejected this legitimate console
because it treated the inherited SESSIONNAME environment variable as
the primary proof of interactive access.

Correction: the local runner now uses the documented Win32
WTSGetActiveConsoleSessionId API from kernel32.dll to identify the
console session, then requires the current process SessionId to be
nonzero and equal to that returned console ID. Reject 0xFFFFFFFF
(no attached console), mismatched RDP/other sessions, any PowerShell
remoting PSSenderInfo, non-admin tokens, and incorrect guest identity.
The underlying JEA fixture invokes the SAME exported local guard for
direct apply/reset attempts, avoiding duplicate inconsistent checks.

Official API documentation:
https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-wtsgetactiveconsolesessionid

The corrected guard was re-staged and verified in the existing elevated
console. The operator subsequently completed a separately authorized local
Reset and local Apply successfully. See the dated evidence summary below.


## 2026-10-17 witnessed live JEA #30 lifecycle checkpoint

These are operator-observed terminal and screenshot results for the
standalone WSLPE-WS01 VM, not claims of automated batch execution.

| Step | Observed evidence | Result |
| --- | --- | --- |
| Initial learner access | Standard WSLPE-WS01\lpe.trainee invoked JEA Status and Proof; Get-LocalUser was rejected by the restricted endpoint. | PASS |
| Console inspection | WSLPE45_JEA_ENDPOINT_COUNT=1, correct owner marker, WSLPE45_JEA_LOCAL_INSPECTION=PASS. | PASS |
| Reset | WSLPE45_JEA_WINRM_LOCAL_RECOVERY=PASS; WSLPE45_JEA_LOCAL_RESET=PASS. | PASS |
| Independent clean-state proof | Kali pinned HTTPS passed; JEA registrations=0, module=False, fixture=False; WSLPE_JEA_CLEAN_PREEXISTING_STATE=TRUE. | PASS |
| Reapply | WSLPE45_JEA_WINRM_LOCAL_RECOVERY=PASS; WSLPE45_JEA_LOCAL_APPLY=PASS. | PASS |
| Post-reapply management | Kali certificate-pinned authenticated HTTPS returned WSLPE_AUTHENTICATED_HTTPS=TRUE and WSLPE_DOMAIN_FREE=TRUE. | PASS |
| Post-reapply learner check | JEA Status returned WSLPE45_JEA_STATUS; Proof returned WSLPE45_JEA_PROOF_WRITTEN; unapproved Get-LocalUser rejected. | PASS |
| Reinstalled proof identity | New proof.txt contained WSLPE45_JEA_PROOF=WinRM Virtual Users\WinRM VA_2_WSLPE-WS01_lpe.trainee. | PASS — distinct virtual-account identity |

The manual developer-local lifecycle is working on the existing Windows 10
workgroup guest without another snapshot restore. The proof identity is a
WinRM virtual account, not NT AUTHORITY\SYSTEM. Effective local Administrators
membership and a full administrator token inside that virtual account were
NOT VERIFIED by this screenshot. The learner_proof and six_stage_qualification
fields in kingdoms/wslpe45_implementation_index.yml remain pending because
those fields cover the broader learner privilege and formal automated
qualification contract.

Next: independently prove the virtual account's effective administrative
boundary with a lab-owned bounded proof, incorporate the local-console
lifecycle into the formal qualification framework, and later validate a
fresh WSLPE install. The 24 other new candidates, cloud student instantiation,
Vagrant retirement, persistent NAT/network isolation and release approval are
not granted by this #30 manual proof. NORTH and the shared role remain frozen.
