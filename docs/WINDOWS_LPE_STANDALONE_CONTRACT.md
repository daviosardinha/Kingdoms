# Windows LPE standalone contract (design gate)

Status: **FOUNDATION / NOT DEPLOYED**. This document defines acceptance criteria. It does not claim a standalone VM has been created or that the 20 existing Kingdoms exercises work outside NORTH.

## Objective and deployment split

Maintain **one** reusable Windows local privilege escalation scenario role with two independently provisioned consumers:

- **Kingdoms**: existing, domain-joined GOAD-WS01. Its current `NORTH\rickon.stark` foothold, network identity, security controls, Phase 00-03 fixtures, and runtime remain untouched.
- **Standalone Windows LPE**: a separate VM with the **same pinned Windows edition/build** and a **local standard user**, no domain join, no DC, no second Windows host, and no training dependency on AD, LDAP, Kerberos, DNS provided by a DC, domain GPO, or remote shares.

Neither consumer should modify the other. The management workstation or hypervisor may provision/start the VM, but **a learner must be able to enumerate, exploit, verify, and restore every local exercise using only the target machine**. Offline practice is an acceptance test. Local loopback services and target-local administrative fixtures are allowed.

The current `ansible/ws01.yml` remains the Kingdoms-only baseline because it deliberately performs a NORTH domain join. Standalone needs its own provisioning entrypoint; do not simply run `ansible/ws01.yml` without a reachable DC. The existing `ansible/ws01-lpe-install.yml` seeds the original full-lpe profile and is **not** the standalone installer.

## Acceptance gates

1. **Separate instance, no regression**: snapshot or clone the pinned image for development. Never change the existing NORTH WS01, domain controllers, networks, user assignments, or baseline security settings to create the standalone candidate.
2. **Identity isolation**: replace hard-coded `NORTH\rickon.stark` references in the **shared** LPE role with an explicit learner identity input. The standalone adapter supplies a local, non-admin identity; the Kingdoms adapter continues to supply Rickon. Credential Manager and PowerShell history artifacts must be planted in the selected learner's actual security/profile context.
3. **Trust boundaries**: privileged services and scheduled tasks execute on WS01 itself. All privileged target identities are local principals or SYSTEM, and no vulnerability depends on domain-controller permissions, a reachable file share, a second victim, a cloud API, or a domain-authenticated user.
4. **OS and security invariants**: pin the guest OS/build and relevant tool versions. Do not disable UAC, Windows Defender, Windows Firewall, protected-process controls, or endpoint protections globally to force an exploit. If a narrowly scoped scenario requires an exception, justify, validate, and restore it explicitly.
5. **Real exploitation proof**: for each scenario, demonstrate the starting low-privilege token, the vulnerable object or behavior, the actual exploit precondition, the resulting *local* privilege/identity, and the local-only rollback. An administrator-side Ansible `APPLIED` marker alone does not prove exploitation.
6. **Reversibility**: repeat `apply -> validate vulnerable -> learner-side exploit -> reset -> validate clean -> reapply -> validate vulnerable` for each scenario, then run the whole set together. Check collision behavior, repeated runs, offline usability and compatibility with the existing 20.
7. **Promotion**: a new scenario starts **Planned**. Move it to **Candidate** only after source apply/validate/reset exists. Move it to **Implemented** only after a successful pinned-build, low-privileged, **DC-free** end-to-end test. Do not include unverified additions in the existing `full-lpe` profile.

## Current inventory

- **20 existing scenarios**: Implemented and lifecycle-tested in the *Kingdoms domain-joined environment*, per `docs/WINDOWS_LPE_CATALOG.md`. Standalone compatibility is **unverified**.
- **15 new scenarios**: Planned for engineering, not yet provisioned or validated.
- **Standalone environment**: Not created in this foundation PR.
- **Kingdoms environment**: Preserve existing behavior, profiles, scripts and source gates until an independently proven adapter can replace them.

## New local-only scenario backlog

| ID | Scenario | Required WS01-local fixture / condition |
| --- | --- | --- |
| 21 | `se_restore_privilege` | Scoped local user-right assignment and protected target-local filesystem operation |
| 22 | `se_take_ownership_privilege` | Scoped local user-right assignment and protected object with demonstrable ownership/ACL consequence |
| 23 | `se_debug_privilege` | Scoped local right and suitable target-local privileged process; do not claim PPL bypass |
| 24 | `weak_scheduled_task_dacl` | Task-object permissions, independently of executable/file ACLs |
| 25 | `scheduled_task_script_hijacking` | SYSTEM task that executes a script writable by learner |
| 26 | `privileged_local_startup_script` | Target-local startup mechanism with explicit privileged context; **no domain GPO** |
| 27 | `insecure_local_updater` | Local privileged updater that trusts a learner-controlled update input |
| 28 | `msi_repair_abuse` | Vulnerable elevated repair operation proved on the pinned build; not merely AlwaysInstallElevated |
| 29 | `writable_privileged_app_config` | SYSTEM application consuming attacker-writable configuration in an execution-sensitive way |
| 30 | `privileged_plugin_hijacking` | Local elevated application that loads a plugin from a controllable path |
| 31 | `ifeo_debugger_hijacking` | Precisely scoped IFEO modification affecting a demonstrably privileged executable launch |
| 32 | `insecure_named_pipe_ipc` | Target-local privileged pipe server with insufficient authorization |
| 33 | `insecure_loopback_management_api` | Target-local privileged management service restricted to loopback with missing/weak authorization |
| 34 | `dpapi_vault_credential_exposure` | Credible local secret-handling error and usable *local* privileged credential, not a generic DPAPI bypass |
| 35 | `local_third_party_credential_exposure` | Locally installed application leaking a credential valid for a *local* privileged account |

Names above are **design identifiers**, not entries in the production Ansible catalogue. Each scenario must have a distinct exploitation mechanism. If two proposals only demonstrate the same writable-file execution primitive, merge or replace them rather than inflating the practical count.

## Source-only dependency inventory

Run the non-mutating diagnostic:

```bash
python3 scripts/windows-lpe-standalone-audit.py --json
```

Add `--strict` to fail when direct domain/network references remain in the shared role. The initial audit identified 10 indicators, all from 5 learner-identity settings. The shared role now uses `windows_lpe_learner_account` and `windows_lpe_learner_password`, while both existing Kingdoms entrypoints explicitly retain Rickon's original values. A clean strict scan only proves those **source indicators** are absent from the shared role. It does not prove standalone readiness. It scans the shared role only. Later runtime tests must also inspect provisioning playbooks, Ansible inventory, any local account creation, session context, OS/build, outbound traffic and every new fixture.

## Standalone guest preflight (read-only)

After independently provisioning a separate Windows VM and creating a local standard learner, run the preflight using an inventory group named `windows_lpe_standalone`:

```bash
ansible-playbook -i <standalone-inventory> \
  ansible/windows-lpe-standalone-preflight.yml \
  -e windows_lpe_standalone_expected_build=<pinned-windows-build>
```

This task checks the guest is a Windows client on the explicitly pinned build, is **not domain joined**, has an enabled local learner who is not a *direct* member of local Administrators, and retains UAC, Windows Firewall and Microsoft Defender. It is read-only, and it does not seed any exploit or create any account. A later interactive learner-token test remains mandatory to rule out indirect group privileges. If the inventory group is empty, the playbook may skip all target tasks: **a skipped play is not a pass**. Prove a target was reached and the `WINDOWS_LPE_STANDALONE_PREFLIGHT=PASS` marker was emitted.

## First implementation sequence

1. Create a **standalone-specific Windows base provisioner** with a pinned image, local administrator for provisioning, and local non-administrator learner. Do not import the Kingdoms domain-join playbook.
2. Validate the initial parameterization: shared role identity bindings and NORTH adapters are in this PR. Run `python3 -m unittest discover -s tests -p 'test_windows_lpe_*adapter*.py' -v` and the domain-dependency audit. Verify the existing 20-scenario runtime on a safe test clone before claiming this refactor is behavior-preserving.
3. Validate each original scenario on the separate, disconnected standalone VM and ensure exact resets. Leave the domain-joined original untouched.
4. Implement scenario 21 (`se_restore_privilege`) as the first new Candidate, validate learner-side exploitation and local-only rollback, then repeat for the remainder of the approved 15.
5. Only after successful standalone promotion, run a controlled compatibility/regression pass on Kingdoms WS01. Do not silently promote changes into Kingdoms or modify its deployed guest during standalone development.

**Stop condition:** Any need for DC authentication, cross-machine credential handling, weakened global defenses, failure to restore state, or an unproven privilege transition blocks promotion.
