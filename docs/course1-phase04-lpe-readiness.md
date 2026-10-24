# Course 1 NORTH — Module 04 LPE readiness audit

**Audit date:** 2026-10-12
**Scope:** current Course 1 NORTH rebuild, instance `ac9fda-north-vmware`.
**Source verdict:** LPE provisioning is included and backed by the original
20-scenario WS01 implementation. **Live NORTH LPE acceptance is not yet proven.**
This audit does not modify guest systems, reset scenarios or change Notion.

## Source configuration confirmed

- The `NORTH` entry in `playbooks.yml` explicitly installs
  `ws01.yml`, then proceeds through vulnerability provisioning and
  `ws01-lpe-install.yml` before `kingdoms-health-final.yml`.
- `ansible/ws01-lpe-install.yml` applies
  `windows_lpe_profile: full-lpe` on `ws01`.
- The Windows LPE role has **20 Implemented / zero Candidate / zero Planned**
  techniques. Its role files and selectors are retained from the validated
  original Kingdoms configuration.
- `docs/WINDOWS_LPE_CATALOG.md` records a full apply → validate vulnerable →
  reset → validate clean → reapply → validate vulnerable sequence passing on
  **2026-09-03**, leaving the original WS01 in training-vulnerable state.
  Historical success is NOT proof the replacement VM still has every fixture.
- WS01 foundation expects `NORTH\\rickon.stark` as the sole RDP foothold
  and not a local Administrator; domain secure channel, UAC, Firewall and
  Defender are separately checked.

## Technique families available

Service abuse: unquoted paths, weak service DACL, weak service executables,
service registry permissions, DLL search paths, PATH hijacking, writable
Program Files and service-controlled registry execution paths.

Scheduled execution: weak scheduled-task binaries, replaceable executable
directories, writable Common Startup and registry Run keys.

Credential exposure: unattended answer files, PowerShell history,
application configuration, stored RunAs and Winlogon credentials.

User rights and installation policy: SeBackupPrivilege,
SeImpersonatePrivilege and AlwaysInstallElevated.

All twenty scenarios have role-level lifecycle implementation. The Notion
page `04 - Climb the Keep` currently contains an outline, starting position
and exit condition, NOT a written 20-technique walkthrough.

## Critical GOAD-to-NORTH validation mismatch

Do NOT run the legacy scripts below blindly against the current NORTH instance:

- `scripts/validate-windows-lpe-full-runtime.sh` — hardcoded
  `ad/GOAD/data/inventory`, performs RESET and REAPPLY of all 20 scenarios.
- `scripts/validate-windows-lpe-promoted-runtime.sh` — hardcoded
  `ad/GOAD/data/inventory`.
- `scripts/validate-ws01-runtime.sh` — hardcoded GOAD data and provider
  inventory paths, even if a NORTH provider directory is selected.

The full-profile Ansible `validate` role is also not strictly read-only:
`stored_runas_credentials.yml` temporarily grants and restores Rickon's
`SeBatchLogonRight` to exercise the stored-credential validation. Therefore,
don't run it concurrently with Phase 03 attacks or describe it as a passive
inspection.

## Dedicated NORTH acceptance (implemented, not yet executed)

`scripts/course1-phase04-acceptance.sh` now provides two modes. The
`--plan` path prints the exact target and remains source-only/inert.
The `--validate --confirm-transient-right` path is **not for use during
Phase 03**: it locks against other Phase 03 acceptance runs, requires
the installed NORTH exercise instance, checks current GitHub/source and
VMware ownership, verifies Rickon is the only WS01 RDP member and not a
local Administrator (with secure channel/UAC/Firewall/Defender checks),
then validates the seeded `full-lpe` profile using the **NORTH and exact
instance inventories**. It requires all 20 per-technique VULNERABLE
markers before accepting. It never calls LPE apply/reset or VM snapshots.

The source and playbooks are staged for Kali regression and live runtime
validation; there is **no live NORTH LPE acceptance evidence yet**.
Because RunAs validation temporarily alters SeBatchLogonRight before
restoring it, use the live mode only once Phase 03 is neutral and there
are no conflicting Rickon or WS01 activities.

Source-only operator check (safe to execute alongside guide authoring):

```bash
cd "$HOME/kingdoms-rebuild" && git pull --ff-only
python3 -m unittest tests.test_course1_phase04_source tests.test_course1_phase04_acceptance
bash scripts/course1-phase04-acceptance.sh ac9fda-north-vmware --plan
```

**Save for after Phase 03:** `sudo -v`, then
`bash scripts/course1-phase04-acceptance.sh ac9fda-north-vmware --validate --confirm-transient-right`.
This is a live validation, not a passive inspection, and it is not a
replacement for a real Rickon interactive privilege escalation.

## Release gate for Module 04

**Source:** `python3 -m unittest tests.test_course1_phase04_source` checks
the explicit NORTH manifest, 20 technique fixtures, promotion status and
these unsafe legacy validation boundaries. This test does not contact guests.

**Runtime, after Module 03 has finished and the lab is neutral:** run
the new NORTH-specific acceptance described above with exact NORTH/instance
inventories and an explicit transient-right confirmation. It preserves the
20 seeded vulnerable fixtures and does not reset/reapply. Do not call the
old full reset/reapply runner without separate approval for the recovery
point.

To certify LPE as ready for teaching, obtain fresh NORTH evidence that all
20 seeded scenarios validate as vulnerable, Rickon can start a fresh
low-privilege interactive RDP session, and at least one controlled LPE
scenario reaches elevated WS01 context with scoped cleanup. No
kernel/build-dependent CVE is required for this course.

**Current operator decision:** Continue Phase 03. No NORTH reprovisioning,
manual seeding, snapshot restore or changes to Notion are justified by the
source audit. Keep Module 04 active runtime acceptance PENDING until the
new NORTH-specific gate completes.
