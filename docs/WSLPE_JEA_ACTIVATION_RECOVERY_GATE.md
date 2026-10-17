# WSLPE #30 — JEA PS5.1 WinRM lifecycle incident and safe release gate

**2026-10-17 status: JEA FUNCTIONAL ON EXISTING WSLPE-WS01; REMOTE APPLY/RESET BLOCKED.**
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
| Safe independent JEA apply/reset/reapply lifecycle | BLOCKED, NOT IMPLEMENTED |
| WinRM automatic restart/resilience after future registrations | BLOCKED |
| Full six-stage technique qualification | PENDING |
| Student-ready Windows 45-exercise image and vagrant retirement | PENDING |

The original snapshot is a developer recovery point, not a final student
image. No change to NORTH/shared role, no VM/snapshot mutation, and no
automatic Vagrant account retirement is part of this source-only safety fix.
