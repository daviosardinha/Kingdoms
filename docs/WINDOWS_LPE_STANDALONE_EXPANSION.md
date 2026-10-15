# Module 04 Engineering Plan: Fifteen Standalone Windows LPE Additions

Status: **DESIGN ONLY**. No additions are implemented, validated, or promoted by this document.

## Non-negotiable scope

Build fifteen additional, independently reversible Windows privilege-escalation scenarios for **one WS01 Windows VM**. Each lab must be reproducible in two deployment modes using the same underlying Ansible role and technique ID:

- **Kingdoms AD mode**: preserve the current NORTH-joined WS01 and Rickon's low-privileged interactive foothold; introduce no new AD, DNS, GPO, DC, or second-host configuration dependencies.
- **Standalone Windows LPE mode**: one **non-domain-joined** Windows VM with a local, non-administrator trainee account and local administrator/SYSTEM fixture principals. Once provisioned, the student can complete every scenario with no network, DC, secondary Windows host, external authentication, callback listener, internet service, or external application server.

The lab author can provision the VM from an administrative controller beforehand, but **the exploit path and evidence must be workstation-local**. Do not break or weaken the existing 20-scenario Kingdoms course, Phase 03 runtime, Rickon's RDP foothold, UAC, Windows Defender, Firewall, or general code-integrity protections.

The existing source contains `NORTH\rickon.stark` and domain-specific credential/profile assumptions. Introduce an actor name and SID abstraction, local trainee provisioning, and per-profile account selection **before** calling this framework standalone-compatible. Avoid duplicating technique implementations. Keep local administrator and SYSTEM fixtures distinct from the actor.

## Scope inventory and local-only feasibility

| # | Proposed technique ID | Local-only fixture and required proof | Design / safety risk |
| --- | --- | --- | --- |
| 21 | `se_restore_privilege` | Grant scoped SeRestorePrivilege to the local actor. Prove an unauthorized local file/restore write has a security consequence. | A right displayed in `whoami /priv` is not by itself exploitation; privilege may require a new logon token. |
| 22 | `se_take_ownership_privilege` | Grant scoped right; attacker changes a protected lab-owned object's owner/ACL and demonstrates a meaningful local consequence. | Use dedicated object only; reset exact owner/DACL. |
| 23 | `se_debug_privilege` | Scoped right and dedicated, non-protected privileged local process; prove an actual process-access consequence. | Do not globally disable PPL, Credential Guard, driver or kernel protections; privilege existence alone is insufficient. |
| 24 | `weak_scheduled_task_dacl` | Dedicated local SYSTEM task with weak **task-object** DACL; prove task alteration and privileged execution. | Must differ from the existing task executable/directory permission scenarios. |
| 25 | `scheduled_task_script_hijacking` | Dedicated local SYSTEM task executes a user-writable script; validate actual SYSTEM result. | Distinct task and script, no privileged interactive logon dependency. |
| 26 | `privileged_startup_script_hijacking` | Lab-owned SYSTEM service or boot-time component executes a writable local script. | **Conditional**: ordinary Startup and user logon scripts are not inherently SYSTEM; reject or redesign if indistinguishable from #25. |
| 27 | `insecure_local_updater` | Privileged local updater consumes an attacker-editable offline package/payload and executes it. | No internet/update server, scheduled remote push, or third-party infrastructure. |
| 28 | `msi_repair_abuse` | Locally installed managed MSI with intentionally unsafe privileged repair/custom-action path. | **Conditional**: confirm actual Windows version/update/UAC behavior; must differ from existing AlwaysInstallElevated. |
| 29 | `writable_privileged_app_config` | Privileged lab application consumes editable local command/argument config; prove elevated action. | Distinct from existing registry HelperPath and weak-service-binary fixtures. |
| 30 | `privileged_plugin_module_hijacking` | Local privileged app loads explicitly configured plugin/module from a writable location. | Distinct from existing missing-DLL search-order scenario. |
| 31 | `ifeo_debugger_hijacking` | Lab-owned executable with narrowly permissioned IFEO `Debugger` registration and local SYSTEM trigger. | **Conditional**: IFEO HKLM keys ordinarily require administrator rights. Never change a broadly used Windows binary's IFEO entry. |
| 32 | `insecure_named_pipe_ipc` | Dedicated local SYSTEM named-pipe server trusts an unauthorized caller's request. | Local IPC only. Validate endpoint ACL and missing per-message authorization independently. |
| 33 | `insecure_localhost_management_api` | Dedicated loopback-only SYSTEM management agent authorizes an unsafe local operation. | No outside listener or network service, use loopback only and prove caller access. |
| 34 | `dpapi_local_credential_exposure` | Trainee-readable secret containing a local admin credential encrypted using a deliberately recoverable local DPAPI context. | User-scope DPAPI is not automatically decryptable by another user; demonstrate machine scope/actual decryptability, no domain backup key. |
| 35 | `third_party_local_credential_exposure` | Offline-installed pinned local app contains a recoverable **local admin** credential; prove a local elevated logon. | **Conditional**: remote FTP/SSH credentials alone are not Windows LPE. No internet app sign-in or external server. |

These are **proposed topics**, not verified exploits. Any technique that cannot independently prove a local privilege/security-context change is rewritten as a prerequisite/concept lesson or rejected rather than advertised as a successful LPE.

## Build phases and gates

1. **Baseline and actor abstraction**
   - Pin the exact Git branch, commit, WS01 edition/build, existing 20-source/runtime results, and local-group/privilege baseline.
   - Parameterize all workstation actor assumptions (`windows_lpe_actor`, SID, home, user vault, profile, any credentials), and distinguish `kingdoms-ad` vs `windows-lpe-standalone` configuration.
   - Build a standalone VM provisioning entrypoint that does **not** import domain-join playbooks, change any DC setting, or require another Windows host. Create the local non-admin actor and all fixture principals locally.
   - Freeze smoke tests for 20 existing techniques and verify no Phase 03/WS01 RDP regression.
2. **First proof: 21**
   - Implement `se_restore_privilege` end-to-end before parallel work: `apply -> validate vulnerable -> exploit interactively as non-admin -> capture high-privileged outcome -> reset -> validate clean -> reapply`.
   - Include an offline single-VM execution test with all external network access disconnected after provisioning.
3. **Small batches**: 22–25, 26–30, 31–35. For conditional scenarios (26, 28, 31, 35), confirm differentiation and build compatibility **before** creating or advertising the fixture.
4. **Each scenario has six proofs**: pre-attack normal behavior; local misconfiguration; nonadmin access to that weakness; controlled elevated consequence; targeted cleanup; independent clean-state check. Save exactly matched screenshots/output for later Notion chapters.
5. **Regression and promotion**: all new fixtures isolated and reversible individually, combinations validated, original 20 still pass. Mark `Implemented` only when real live source/runtime and attacker-side proof succeed. No new module guide or marketing claim ahead of that gate.

## References and current baseline

- `docs/WINDOWS_LPE_CATALOG.md`: 20 Implemented scenarios with September 3, 2026 full reversible promotion checkpoint.
- `ansible/roles/windows_lpe/defaults/main.yml`: current catalog, named profiles, and hard-coded NORTH/Rickon assumptions.
- `ansible/ws01-lpe-install.yml`: currently provisions `full-lpe` on WS01 after existing setup.
- `ansible/ws01.yml`: imports Kingdoms domain-join flow. **This must not be the standalone entrypoint.**
- `scripts/validate-windows-lpe-framework-source.sh` and `scripts/validate-windows-lpe-full-runtime.sh`: source/runtime gates to preserve and extend.

Do not modify Notion Module 04 until new scenarios and their actual evidence have been proved and reviewed.
