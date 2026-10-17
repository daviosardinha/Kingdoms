# WSLPE45 — 21-candidate source audit and operator recovery review

**Audit date:** 2026-10-17  
**Read-only baseline:** `feature/windows-lpe-45-batch` @ `859b4244c6cb537ad00584b1c5a41f621814cfa5`  
**Scope:** 21 candidate playbooks, their common PowerShell/C# modules and existing source tests, implementation index, and batch operator. **No guest, VMware, or NORTH runtime test was performed.**

## Executive decision

**Do not promote or execute the 25-addition batch yet.** The repository correctly records **21 source candidates / 4 planned** and **0 new six-stage Windows qualifications / 0 learner exploit proofs**. Preserve the current `batch_execution_authorized: false` and the frozen NORTH role. Source-CI passing is a *build/syntax contract*, not a Windows exploitability claim.

The 21 candidate playbooks generally have exact-inventory, exact workgroup-host, local-learner, and action/stage guards; several share capable lab-only ownership and rollback code. Nevertheless, there are high-priority source defects and unproven lifecycle assumptions. **21/21 reviewed here is not 21/21 approved**.

## Prioritized findings

### F-01 — High — The development/source gate does not check material implementation dependencies (confirmed source)

**File:** `kingdoms/wslpe45_batch_operator.py`, `source_readiness()` (approximately lines 91–124). The gate verifies the index, candidate flags, playbook existence/YAML with two plays, disallowed literal strings, and presence of a lifecycle marker. It does **not** resolve `win_copy.src` against controller-side files, inspect per-scenario lifecycle action correctness, verify source revision/compiled artifact provenance, or prove that the Windows operation took place. The present source tests mostly check static string presence and Python/YAML shapes. An incorrect source path or inert privileged consumer can therefore remain `source_ci: passed`.

**Action:** Add controller-only dependency-resolution tests, source-to-artifact build assertions, scenario-owned resource manifests, and negative tests for missing modules, stale registration, and unexpected dependency reuse. Keep Windows exploitation a separate gate.

### F-02 — High — JEA endpoint registered without service restart; activation is unproven (confirmed source, live effect pending)

**Files:** `ansible/files/wslpe45/WslpeJea.psm1` lines 49–55, 76–83; `ansible/wslpe45/jea_role_capability_misconfig.yml`. The code calls `Register-PSSessionConfiguration -NoServiceRestart` and explicitly reports configuration presence rather than execution. Registration without WinRM restart does **not** establish that the new session configuration is active/reachable. Vulnerable-state validation checks source artifacts rather than a fresh low-privilege JEA session.

**Action:** Keep JEA source status distinct from *activated endpoint*. Design a separately authorized activation/recovery window with independent operator management, and test a new local learner session. Do not restart shared WinRM automatically or call this exploitable.

### F-03 — High — NTFS link exploitation conflicts with the shared rollback guard (confirmed source)

**Files:** `ansible/files/wslpe45/KingdomBoundaryService.cs` lines 214–247; `WslpeBoundary.psm1` lines 84–102; `WslpeFixture.psm1` lines 52–79, 127–164. Technique #34 explicitly relies on a learner-created junction under `inbox/link`. However, `Assert-Wslpe45OwnedFixture` refuses **any** reparse point beneath the fixture; `reset` calls that assertion before removing the fixture. Thus a normally exploited fixture containing its intended link will enter fail-closed/manual-recovery state rather than complete the promised six-stage reset.

**Action:** Add a separate, tightly scoped, exact-target *owned-junction removal/verification contract* before invoking the general no-reparse recursive cleanup. Never weaken the common guard or follow arbitrary junction targets.

### F-04 — High — Updater path containment is purely lexical (confirmed source)

**Files:** `ansible/files/wslpe45/KingdomServiceConsumer.cs` lines 40–51; `WslpeServiceConsumer.psm1` lines 43–56. The updater derives a path by `Path.GetFullPath(Path.Combine(inbox, supplied))` and checks a string prefix and `.exe` extension before privileged execution. `GetFullPath` canonicalizes path syntax but does **not** resolve filesystem reparse-point destinations. The learner has `Modify` access to the inbox, so the code does not establish that the executable's **resolved final destination** remains under the owned fixture.

**Action:** Review reparse-point handling and final opened-object identity. Demonstrate containment with deliberately adversarial reparse tests in a disposable Windows guest before any release; fail closed if ambiguous.

### F-05 — High — #35 controller-side source-copy paths are inconsistent with peer playbooks (confirmed path discrepancy; deployment failure untested)

**File:** `ansible/wslpe45/traversal.yml` lines 86–96. Uses `win_copy.src: files/wslpe45/WslpeFixture.psm1` and `files/wslpe45/KingdomTraversalService.cs`; actual files are under `ansible/files/wslpe45/`. Other `ansible/wslpe45/*.yml` playbooks use `../files/wslpe45/...`. No existing #35 source test resolves Ansible's source search path. This is a concrete inconsistency and likely runtime copy failure, **not yet proven** without an Ansible path-resolution check.

**Action:** Add a static Ansible-controller source lookup test and align the playbook with verified peer paths. Do not update qualification status based only on string checks.

### F-06 — Medium — Source verification reports 'vulnerable' without authentic learner interaction (confirmed across candidates)

**Files:** `WslpeServiceConsumer.psm1` lines 105–137; `WslpeBoundary.psm1` lines 110–143; `WslpeLsaRights.psm1` lines 223–240; `WslpeWmiConsumer.psm1` lines 104–129; `WslpeComRegistration.psm1` lines 115–143. These validate ownership, service/registry/ACL state, input presence or account rights. They **do not invoke** each scenario under the actual `lpe.trainee` token and validate a separately protected proof outcome. This is an evidence gap, not falsification: the index correctly sets `learner_proof: pending`.

**Action:** For each scenario, maintain separate provisioned, effective learner access, boundary-crossing evidence, reset and post-reset denial outcomes; never infer those from a stage marker.

### F-07 — Medium — #43 signature-bypass label exceeds demonstrated source mechanism (confirmed semantic mismatch)

**Files:** `WslpeBoundary.psm1` lines 54–60; `KingdomBoundaryService.cs` lines 249–277. The loader checks whether a learner-writable manifest contains the literal `trusted=true` before loading a local .NET DLL. No cryptographic signature is checked, and no signature verification is bypassed. This is an insecure manifest-trust decision, not a demonstrated cryptographic signature bypass.

**Action:** Either describe it accurately as manifest-based plugin trust or independently justify and validate the intended signed-plugin verification failure. Do not teach it as a proven signature bypass.

### F-08 — Medium — #22 deliberately delegates a machine-wide SCM privilege (design risk, not undisclosed defect)

**File:** `ansible/wslpe45/scm_create_service_acl.yml`. Adds a direct learner `SC_MANAGER_CREATE_SERVICE` ACE to the global SCM DACL; does snapshot and verify SDDL restoration. That is broader than a lab-owned fixture. A SYSTEM-capable learner may create unrelated privileged services if the guest is not sufficiently isolated.

**Action:** Require explicit risk acceptance and verified isolation/recovery before exercising #22; add test-only negative constraints and independent rollback review. Do not silently describe it as scoped to one service.

### F-09 — Medium — One-shot privileged consumers and runtime triggers require separate proof (runtime risks, source-based)

**Files:** `KingdomServiceConsumer.cs` lines 20–31, 79–83; `KingdomBoundaryService.cs` lines 66–80, 214–277; `WslpeWmiConsumer.psm1` lines 60–79. #23/#24/#41/#42 actions are evaluated on service start; #34/#43 proof attempts occur on service worker start; #37 relies on a permanent WMI process-start event. A 'Running' service or registered WMI binding proves neither the learner's ability to trigger it nor a successful privileged output. Service restart, WMI event delivery, and clean handle release need end-to-end acceptance.

### F-10 — Medium — No automatic per-scenario recovery or resumption after partially applied guest state (confirmed operator behavior)

**File:** `kingdoms/wslpe45_batch_operator.py` approximately lines 240–300. Good controls exist: exact guest lookup, private atomic journals, exclusive lock, timeout handling, recovery-required sentinel, immediate stop after a failed stage. The sentinel intentionally blocks blind reruns. However, there is **no automatic rollback or reviewed per-scenario recovery path**, no stage-specific resume, and no isolated diagnostic selector in the current CLI (`--execute` runs the full batch).

**Action:** Preserve the journal and stop-on-failure behavior. Add an operator-only, non-bypassing diagnostic plan and separate reviewed recovery workflow that can inspect owned artifacts and safely resume after validation. **Do not** replace the coordinator or clear the sentinel automatically.

### F-11 — Medium — Release/network prerequisites remain independent (previous project acceptance evidence, not re-tested)

The last recorded standalone audit does not establish actual `lpe.trainee` RDP logon, trusted WinRM HTTPS management, post-escalation host/NORTH isolation, or commercial Windows licensing. None is fixed by source compilation. See `docs/WSLPE_LIVE_SECURITY_AUDIT_2026-10-15.md`; treat its results as point-in-time evidence, not current runtime status.

## 21-candidate mechanism matrix

**Legend:** S = source mechanism located, C = specific concern described above, R = runtime learner proof / cleanup not established. Every row remains **candidate**, and no row is accepted for release.

| # | Actual technique | Source evidence / relevant mechanism | Source audit conclusion |
|---|---|---|---|
| 21 | `scheduled_task_definition_acl` | Dedicated SYSTEM task; task-object ACL via Task Scheduler COM; separate binary | S; need real learner task-edit/trigger proof (R) |
| 22 | `scm_create_service_acl` | Global SCM descriptor snapshot, learner CREATE_SERVICE ACE, restoration | S; machine-wide privilege/isolation risk (F-08), R |
| 23 | `privileged_service_config_injection` | Privileged service consumes learner request in command-interpreter arguments | S; one-shot trigger, actual token/proof required (F-06/F-09), R |
| 24 | `privileged_updater_hijack` | SYSTEM service trusts learner inbox executable path | S; lexical-path containment gap (F-04), R |
| 26 | `ifeo_debugger_acl_hijack` | Dedicated HKLM IFEO key with learner registry SetValue and SYSTEM task consumer | S; confirm IFEO debugger invocation and protected proof from learner, R |
| 27 | `com_clsid_registration_hijack` | Dedicated COM assembly via RegAsm, learner-editable per-version CodeBase, SYSTEM task | S; exact CLSID registration and re-registration cleanup require live proof, R |
| 28 | `app_paths_registry_hijack` | Dedicated App Paths key, ShellExecute consumer and SYSTEM task | S; ShellExecute resolution and learner-edited registry value need proof, R |
| 29 | `named_pipe_authorization` | SYSTEM named-pipe server grants Users read/write and handles PROOF request | S; actual local caller access/response and service teardown, R |
| 30 | `jea_role_capability_misconfig` | Native JEA role/endpoint, virtual account, no WinRM restart | S; endpoint not proven active (F-02), R |
| 31 | `setakeownership_privilege` | Direct LSA local learner-right assignment | S; new logon token, scoped object effect and revocation, R |
| 32 | `serestore_privilege` | Direct LSA learner-right assignment with owned evidence | S; actual privileged restore operation not established, R |
| 33 | `sedebug_privilege` | LSA right plus dedicated non-PPL SYSTEM service | S; actual effective privilege and debug access after fresh logon, R |
| 34 | `ntfs_link_redirection` | SYSTEM service follows learner junction, final file-handle path checked | S; intentional link blocks common owned reset (F-03), R |
| 35 | `privileged_path_traversal_write` | SYSTEM service with exact bounded protected-file destination | S; likely controller-side copy path mismatch (F-05), R |
| 37 | `wmi_permanent_consumer_hijack` | Owned permanent WMI filter/consumer/binding; learner-writable script | S; WMI event delivery and complete binding rollback, R |
| 39 | `privileged_loopback_http_authz` | SYSTEM HTTP listener bound to 127.0.0.1; anonymous POST proof | S; actual non-admin loopback request and listener termination, R |
| 41 | `privileged_argument_injection` | SYSTEM service builds command-interpreter arguments from learner input | S; actual input parsing/trust boundary, R |
| 42 | `privileged_child_environment_trust` | SYSTEM service forwards learner input via environment to fixed child | S; actual child execution and protected result, R |
| 43 | `elevated_plugin_signature_bypass` | Local .NET plugin loaded following writable manifest approval | S; semantic mismatch with cryptographic signature bypass (F-07), R |
| 44 | `privileged_file_toctou` | Privileged service double-reads request across a deliberate timing window | S; actual race reproducibility, cleanup and timing, R |
| 45 | `privileged_backup_restore_api` | SYSTEM service trusts learner snapshot/request; writes owned protected file | S; distinguish unauthorized restore from independent user-writable output, R |

**Unimplemented #25/#36/#38/#40 are outside the 21-candidate audit and remain `planned/source_ci: pending`.**

## Targeted operator review

**Retain:** fail-closed source-index check, frozen NORTH references, exact WSLPE instance/inventory checks, `--limit ws01,localhost`, per-stage unique marker, timeout, private atomic JSON, flock, durable recovery sentinel.

**Improve before executing:** (1) controller source/dependency checking; (2) reviewed per-technique diagnostic/repair path that never bypasses global guest-authorization and exact instance safeguards; (3) journal contextual ownership/artefact-version IDs and potentially explicit cleanup outcomes; (4) evidence of a true low-privilege trigger and protected proof separate from each `WSLPE45_BATCH_STAGE` marker; (5) Windows-native regression for failed/partially applied scenarios.

**Do not adopt Gemini's proposal to move the 21–45 fixtures into the frozen NORTH role or discard the 150-stage batch.** The one-shot batch is a valid release-level orchestration requirement; development diagnosis and failure recovery may be per-scenario without removing that contract.

## Fix order

1. **Source-only hardening first:** F-01 + F-05. Add playbook dependency-resolution tests and review source-artifact references; preserve the 21/25 source count as historical CI only, not runtime readiness.
2. **Safety / rollback:** F-03 and F-04; prove junction handling with explicitly owned targets, containment, safe cleanup in disposable environment.
3. **Native activation and pedagogical correctness:** F-02 and F-07. Do not restart WinRM or weaken signing controls as a shortcut.
4. **Runtime proof and isolation:** F-06, F-08, F-09; verify exact learner token, privileged effect, cleanup and post-reset denial; prioritize high-blast-radius #22.
5. **Operator recovery:** F-10; add reviewed diagnostic/partial-recovery plan, preserve the fail-closed sentinel.
6. **Complete four pending native mechanisms** only under approved source/build workflows; keep NORTH and the shared role untouched.
7. **One consolidated 25-addition six-stage qualification** after independent execution approval, followed by separate 25 learner proofs and all-course release gates.

## What this audit does not claim

No guest connection, exploit, six-step runtime run, effective user-token inspection, post-reboot recovery, TLS/RDP verification, or successful Windows install was performed. Some path resolution and WMI/COM/JEA operational conclusions require the actual pinned Windows/Ansible environment. Severity indicates **priority for engineering validation**, not a verified vulnerability on a production host.
