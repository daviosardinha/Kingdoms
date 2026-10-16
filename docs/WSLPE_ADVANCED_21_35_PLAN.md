# Kingdoms — Advanced standalone Windows LPE (techniques 21–35)

**Status:** 15 planned candidates, 0 newly implemented and 0 accepted on the WSLPE guest.

**Scope contract:** `docs/WSLPE_45_TECHNIQUE_ROADMAP.md`. NORTH retains its own original 20 techniques and never receives this catalog. The existing WSLPE foundation has qualified 20/20 reversible vulnerability deployments. The new 15 must remain in dedicated standalone files and are **not part of the existing 20-technique qualification runner**.

## Planned catalog

| # | ID | Vulnerability / attack surface | Boundary versus existing 20 |
| --- | --- | --- | --- |
| 21 | `scheduled_task_definition_acl` | Scheduled Task Definition ACL Abuse | Modify **task action and definition** through task-object security; NOT the scheduled task binary/directory |
| 22 | `scm_create_service_acl` | Service Control Manager ACL Abuse | `SC_MANAGER_CREATE_SERVICE` on SCM itself; NOT an existing service DACL |
| 23 | `privileged_service_config_injection` | Service Configuration File Injection | Service interprets writable *data* as privileged actions; NOT just writable service binary/registry |
| 24 | `privileged_updater_hijack` | Privileged Software Updater Hijacking | Writable manifest or update package consumed by elevated updater; NOT PATH/unquoted-service trick |
| 25 | `msi_repair_custom_action` | Windows Installer Repair Abuse | Unsafe elevated repair action; NOT AlwaysInstallElevated global policy |
| 26 | `ifeo_debugger_acl_hijack` | IFEO Debugger Hijacking | Dedicated executable's IFEO launch redirection; NOT Run key persistence |
| 27 | `com_clsid_registration_hijack` | COM CLSID Registration Hijacking | Writable registration used by dedicated elevated COM client; NOT classic DLL search order |
| 28 | `app_paths_registry_hijack` | App Paths Registry Hijacking | Trusted ShellExecute resolution of writable App Paths registration; NOT PATH environment variable |
| 29 | `named_pipe_authorization` | Insecure Named Pipe Authorization | Privileged IPC trusts unauthorized user-controlled request; NOT service access permissions |
| 30 | `jea_role_capability_misconfig` | PowerShell JEA Endpoint Misconfiguration | Excessive delegated endpoint command scope; NOT impersonation token privileges |
| 31 | `setakeownership_privilege` | SeTakeOwnershipPrivilege Abuse | Misassigned ownership right against an isolated protected object |
| 32 | `serestore_privilege` | SeRestorePrivilege Abuse | Restore right allows protected test-object replacement |
| 33 | `sedebug_privilege` | SeDebugPrivilege Abuse | Misassigned debugging right against a *non-PPL, dedicated* elevated test process |
| 34 | `ntfs_link_redirection` | NTFS Junction / Hardlink Redirection | Privileged file handling follows a user-controlled reparse/link destination |
| 35 | `privileged_path_traversal_write` | Privileged File-Write Path Traversal | Custom elevated writer improperly constrains destination path |

The machine-readable list and feasibility conditions are in `kingdoms/wslpe_advanced_catalog.yml`. All 15 are **planned**, not registered in NORTH's shared `windows_lpe_catalog`. There are no student-facing claims, live deployment results or added vulnerabilities yet.

## First engineering wave: 21–25

Start with **#21, Task Definition ACL Abuse**. Existing foundation techniques `scheduled_task_binary_permissions` and `scheduled_task_directory_permissions` make a natural comparison: the new task must keep its executable and directory unwritable while granting the local learner the specific task-definition permissions needed to alter a dedicated SYSTEM task action. Validate access through Task Scheduler's security descriptor API, and prove the actual unprivileged edit in a separate live gate.

`ansible/wslpe-advanced21-probe.yml` is deliberately **read-only**. It checks that the target is the exact workgroup Windows 10 `WSLPE-WS01`, that `lpe.trainee` is enabled and non-admin, and that COM Task Scheduler returns a parseable DACL for the previously validated `KingdomTaskBinary` fixture. It neither registers nor edits tasks and does not touch NORTH. CI must verify YAML, Ansible syntax, PowerShell parsing and a Windows-native read-only COM connection before anybody runs this probe on the WSLPE guest.

After probe acceptance, build the actual **standalone-only #21 fixture**: unique task name, inert SYSTEM action by default, task-definition write grant to the exact local learner SID, protected service executable and directory, reversible original state, and an offline test proving only the intended task was modified. Do not silently modify a pre-existing task or blanket-change the Task Scheduler folder. Use an exact, deterministic six-stage apply/vulnerable/reset/clean/reapply/vulnerable check, followed by non-admin login/execution evidence.

Design reviews for #22–25 must specifically test machine-wide SCM ACL restore (#22), privileged fixture containment (#23–24), and MSI repair elevation requirements without global AlwaysInstallElevated (#25).

## Feasibility risks to resolve before implementation

- **#22:** SCM security-descriptor changes are machine-wide; require a verified exact original-SDDL snapshot and a rollback escape hatch before deployment.
- **#25:** MSI repair privilege context differs by Windows build/install policy; must prove this is not simply AlwaysInstallElevated again.
- **#26–28:** use dedicated, non-system file names, CLSIDs and registry keys only. An elevated consumer must actually resolve the attacker-controlled registration.
- **#30:** JEA can affect WinRM and provisioner availability; require independently verified management recovery before changing any endpoint.
- **#31–33:** privilege assignment alone does not demonstrate escalation. The low-privilege user must obtain a token with the intended right; avoid LSASS, PPL bypass, EDR tampering or Windows system-object corruption.
- **#34–35:** enforce a hard ceiling on target directories and reject symlinks/reparse points outside the dedicated Kingdoms fixture. Exploit proof must stay inside the isolated lab-owned tree.

## Promotion gates

`planned → feasibility-proven → implemented/candidate → 6-step-qualified → learner-exploitable → release-accepted`

For **each** of the 15, capture exact prerequisites, attacker-controlled entry, elevated consumer, proof observable in the learner session, apply/validate/reset functions, negative-path tests and private acceptance logs. Configuration-state validation does not substitute for exploitation from `WSLPE-WS01\lpe.trainee`.

Retain separation between the local developer VM and learner release: RDP/NLA, domain-free status, isolated networking, independent instance lifecycle, credential uniqueness, build licensing and course materials remain pending gates, regardless of the number of implemented techniques.

**Next action:** run source/Windows CI for the catalog and read-only #21 feasibility probe; then accept #21 from the exact WSLPE guest before building its intentionally vulnerable fixture. Do not touch NORTH.
