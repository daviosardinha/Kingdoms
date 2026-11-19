# NORTH Climb the Keep | Full 20-topic outcome audit

Status: source and Notion walkthrough inspection on 2026-11-19. This is not a fresh-install exploit report. GitHub is the lab implementation source of truth. Do not copy development internals into the student lessons.

## Acceptance policy

A CONFIGURATION PASS means the expected lab object, permissions, trigger or Windows policy are present. It does not mean a student obtained SYSTEM. For any lesson advertised as an interactive SYSTEM privilege escalation, require a NEW visible SYSTEM process in Rickon's RDP session plus cleanup. A service-start message, successful file copy, old log entry, or assigned privilege is insufficient.

## Findings

| Topics | Current technique | Interactive SYSTEM requirement and gaps |
| --- | --- | --- |
| 01–05 | Credential exposure / alternate identity | Recovered credentials or administrator token do not automatically give SYSTEM. Validate actual identity and elevation chain, especially UAC and saved RunAs. |
| 06 | Weak service DACL | Check effective SCM rights, execution trigger, resulting token and cleanup. |
| 07–11 | Service executable / path / Registry abuse | Interactive SYSTEM evidence is present in student lessons; require fresh-install independent replay and rollback gates. |
| 12 | Missing native DLL | NORTH WS01 configuration and recurring SYSTEM trigger passed, but PR #107 currently provides a proof log, not an interactive SYSTEM shell. |
| 13 | PATH helper search | Lesson currently relies on a proof file and conditional execution; new interactive SYSTEM session is not verified. |
| 14–15 | SYSTEM scheduled task file / directory | Prove task trigger, effective replacement rights and actual new process identity; source configuration alone insufficient. |
| 16 | Common Startup folder | Normally executes with the signing-in user, not SYSTEM. A SYSTEM claim requires a separate real privilege boundary. |
| 17 | HKLM Run entry | Runs with the signing-in user, not automatically SYSTEM. Document a real validated elevation chain or teach the actual autorun impact. |
| 18 | AlwaysInstallElevated | Both policy values can be present without any MSI running as SYSTEM. Needs tested controlled MSI and token proof. |
| 19 | SeBackupPrivilege | An assigned backup right is not a SYSTEM token. Demonstrate backup-aware protected-file access, then separately validate any escalation. |
| 20 | SeImpersonatePrivilege | The privilege alone cannot impersonate SYSTEM. Need an actual privileged token source and independently verified result. |

## Important implementation distinctions

1. The role has 20 source validations. Most check vulnerable configuration, not exploitation or a new token.
2. Topic 05's validation temporarily changes the owner account's SeBatchLogonRight. Topic 18 may temporarily mount and unmount the target user's Registry hive. Topics 19–20 export security policy into temporary files. Therefore the full remote check must require explicit acknowledgement of these guest changes.
3. Topic 12's existing PR #107 remains a DLL placement and log-proof pilot, not the requested interactive SYSTEM shell implementation.
4. Topics 13–20 currently have no student screenshots in the Notion chapter. These lessons have not been independently proven as complete hands-on exercises.
5. Cred recovery, autostart-on-logon, policy misconfiguration and token privileges are real security topics, but they do not independently guarantee SYSTEM. Either teach their authentic result or supply a real, verified follow-on escalation chain. Do not equate admin sign-in with SYSTEM.

## New one-command configuration validator

Default source-only mode (does not contact WS01):

    python3 scripts/validate-north-climb-the-keep.py --mode source

Disposable NORTH WS01 configuration mode (per-topic checks, may make temporary changes and requires explicit approval):

    GOAD_PROVIDER_DIR="$HOME/kingdoms-north-fresh-test/workspace/0da0a9-north-vmware/provider" python3 scripts/validate-north-climb-the-keep.py --mode configuration --acknowledge-temporary-guest-changes

It produces a JSON report under ~/Kingdoms-evidence/north-climb-the-keep/ and independently reports SOURCE, CONFIGURATION and INTERACTIVE_SYSTEM. The last field remains NOT_RUN. The script never executes exploits, changes scenario setup, or reports a SYSTEM shell.

## Next release gates

- Run 20 source checks and the opt-in per-technique WS01 configuration checks.
- Identify each lesson's precise outcome contract, not a generic promise of SYSTEM.
- In a disposable snapshot, test one authorized attack path per lesson and observe actual token/process identity.
- Prove teardown and reapplication preserve other NORTH scenarios.
- Keep PR #107 unmerged until the interactive DLL requirement and real Windows validation are resolved.
