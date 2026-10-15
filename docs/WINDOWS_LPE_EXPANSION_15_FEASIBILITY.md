# Phase 04: WS01 LPE Expansion, 15-Candidate Compatibility Gate

**Status:** planning / read-only feasibility, not approved for guest mutation.  
**Base:** `rebuild/course1-from-kingdoms`  
**Host:** GOAD-WS01 (`10.4.10.31`), Windows 10 Enterprise Evaluation image, NORTH domain member.  
**Foothold:** `NORTH\rickon.stark`, low-privileged interactive RDP session.

## Existing contract
The initial 20 techniques are Implemented in `docs/WINDOWS_LPE_CATALOG.md` and passed the reversible runtime gate on 2026-09-03. This checkpoint is **historical** and does not independently prove the currently running VM is unchanged. The new 15 are **proposals**, with no current WS01 compatibility or exploitation evidence.

**Preserve:** Rickon's low-privileged RDP foothold, the domain secure channel, RDP and WinRM reachability, UAC, Defender, Windows Firewall, evaluation grace, Phase 03 behavior, and the original 20 LPE scenarios.

**Core isolation rule:** Vulnerability fixtures may be selectable on WS01, but they must **not all be active simultaneously by default** if one grants broad filesystem/process rights or invalidates the intended proof of another. `SeRestorePrivilege`, `SeTakeOwnershipPrivilege` and `SeDebugPrivilege` are especially cross-cutting rights. Use isolated selectable profiles, a fresh Rickon logon after rights changes, and full rollback. Do not globally weaken security settings.

## Candidate compatibility register

Every row is **not yet verified on the current VM**. "Provisional fit" means the scenario is technically designable for the pinned Windows 10 lab with a controlled fixture, not that exploitation has been demonstrated.

| ID | Proposed scenario | Provisional disposition | Main proof / risk |
| --- | --- | --- | --- |
| 21 | `se_restore_privilege` | Conditional, isolated profile | Assign right, fresh token, narrowly scoped protected-write consequence; remove right and restore object. Global grant undermines other ACL labs. |
| 22 | `se_take_ownership_privilege` | Conditional, isolated profile | Distinguish ownership acquisition, DACL edit and impact; capture and restore original owner and security descriptor. |
| 23 | `se_debug_privilege` | Conditional, isolated profile | Use non-PPL controlled privileged process; do not disable Defender/PPL; demonstrate privileges distinct from existing token topics. |
| 24 | `weak_scheduled_task_dacl` | Strong fixture candidate | Explicit task-object security descriptor and authenticated non-admin change; do not confuse with writable action binary. |
| 25 | `scheduled_task_script_hijacking` | Strong fixture candidate, overlap review | Privileged task must execute writable script, not just a writable task executable; reset task, script and ACL. |
| 26 | `privileged_startup_script_hijacking` | Conditional, boot-risk review | Controlled privileged startup/logon script; prove **actual** elevated execution, not ordinary Common Startup; avoid unbounded reboot requirements. |
| 27 | `insecure_software_updater` | Conditional, distinct trust primitive required | Dedicated safe mock updater; prove which less-trusted artifact/update data the privileged updater executes; avoid duplicate writable-service-binary lesson. |
| 28 | `unsafe_msi_repair` | Conditional, tooling/build check | Real elevated repair/custom-action path, distinct from `always_install_elevated`; preserve Windows Installer settings. |
| 29 | `writable_privileged_app_config` | Strong fixture candidate, overlap review | User-writeable **file configuration** controls privileged program behavior; avoid duplicate registry-based `insecure_service_registry`. |
| 30 | `privileged_plugin_module_hijacking` | Conditional, overlap review | Actual privileged plugin/module-loading boundary, not a renamed missing-DLL hijack. |
| 31 | `insecure_ifeo_debugger` | Conditional, narrow ACL fixture | Restrict writable permissions to dedicated IFEO subkey and controlled privileged process trigger; never weaken whole IFEO tree. |
| 32 | `insecure_named_pipe_ipc` | Conditional, custom fixture | SYSTEM service incorrectly trusts named-pipe client; explicit access-control and request authorization evidence, protected listener scope. |
| 33 | `insecure_localhost_management_api` | Conditional, custom fixture | Localhost-only privileged endpoint lacking correct caller authorization; prohibit externally accessible listener and persistent exposure. |
| 34 | `dpapi_vault_credential_exposure` | Conditional, distinct credential fixture | Rickon must legitimately be able to decrypt/read target artifact and reuse credential for *local* elevation; never claim DPAPI crypto bypass. |
| 35 | `third_party_stored_credentials` | Redesign/de-dup check | Pin supported tool/profile and show consequence distinct from hardcoded application credentials, PowerShell history and stored RunAs; otherwise consolidate rather than add filler. |

## Phase A: no-change proof of compatibility
- [ ] Record branch, upstream and exact SHA for the deployed lab checkout, then run `bash scripts/verify-test-source.sh`.
- [ ] Run `bash scripts/validate-ws01-runtime.sh` **only** if WS01 is already running and the environment is in exercise mode. This performs baseline checks and must not apply or reset LPE fixtures.
- [ ] From Rickon's RDP session, collect OS edition/build, architecture, domain membership, `whoami /all`, integrity level, privileges, UAC, Defender, Firewall, current services/task inventory, installed tools, relevant app runtimes and permissions. Avoid secrets and unnecessary host exports.
- [ ] Confirm LPE fixtures/source status using read-only `windows_lpe_action=status` or source inspection, not the mutating full runtime cycle.
- [ ] Record each proposed fixture's caller, privileged principal, trigger, controlled resource, ACL/privilege prerequisites, expected low-to-high evidence, conflicts with old 20, reset strategy, and whether a logoff/reboot is necessary.
- [ ] Grade each entry `fit`, `needs fixture`, `redesign`, or `reject`. A scenario is not promoted because it can be planted; require an attacker-side demonstrated consequence.

## Phase B: implementation and acceptance
- [ ] Open one dedicated branch and PR per approved scenario. Issues are disabled in this repository.
- [ ] Keep new techniques Candidate until exact committed-source validation passes.
- [ ] Each candidate: apply -> validate vulnerable -> demonstrate from Rickon -> targeted reset -> validate clean -> reapply -> validate vulnerable -> verify WS01 foundation/Phase 03 and old 20 remain unchanged.
- [ ] Keep broad-right scenarios **out of** the permanent `full-lpe` install until cross-scenario isolation is proven; prefer individually activatable profiles.
- [ ] Validate source and failure paths; do not run `scripts/validate-windows-lpe-full-runtime.sh` for discovery because it **resets and reapplies** all 20.
- [ ] Write the course walkthrough in Notion only after actual outputs, commands and screenshot evidence exist.

## First operator check
From the existing Kingdoms checkout on Kali, while leaving the VM untouched:

```bash
cd "$HOME/Documents/GOAD_NOMAD" || exit 1
git status -sb
git branch --show-current
git rev-parse HEAD
bash scripts/verify-test-source.sh
```

If the lab is currently running in exercise mode and unchanged, perform the already-available read-only foundation audit:

```bash
bash scripts/validate-ws01-runtime.sh
```

From **Rickon's** PowerShell session, collect a minimal non-mutating guest fingerprint:

```powershell
Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,OSArchitecture
Get-CimInstance Win32_ComputerSystem | Select-Object Name,Domain,PartOfDomain
whoami /all
Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' | Select-Object EnableLUA,ConsentPromptBehaviorAdmin
Get-NetFirewallProfile | Select-Object Name,Enabled
Get-MpComputerStatus | Select-Object AntivirusEnabled,RealTimeProtectionEnabled
```

Do **not** paste passwords, private key files, hashes or machine secrets into the planning record. If the existing checkout has moved, locate it first instead of assuming the sample path.

## Completion criteria
An evidence-backed feasibility decision for all 15, a dependency-aware implementation order, and a tested isolation strategy. Only then expand the implemented catalogue from 20 toward 35.
