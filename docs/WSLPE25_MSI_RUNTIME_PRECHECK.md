# WSLPE #25 — MSI runtime precheck and recovery blockers

**Status: REVIEW REQUIRED / NO GUEST DEPLOYMENT / NOT AN LPE PROOF.**
Tracked exclusively in `feature/windows-lpe-45-batch`, against standalone
Windows 10 workgroup `WSLPE-WS01`. Do not touch NORTH, shared AD Ansible roles,
or the existing JEA #30 session. This document does not authorize execution.

## Established evidence (18 October 2026)

- Source baseline: 21 of 25 source-qualified candidates; #25, #36, #38 and
  #40 remain planned and `batch_execution_authorized: false`.
- GitHub Actions run `39120048388` passed all three jobs for commit
  `6e74eb5815c7b831117392d2322ed643e4d9d796`.
- Exact native MSI archive artifact: `12134076564`, short-lived, source
  review only; expires 2026-10-20. A separate Kali check confirmed the exact
  three files, manifest, product identity and both file hashes.
- Package ProductCode:
  `{8A053A14-F10D-44E4-A871-1BD618677455}`.
- MSI SHA-256:
  `E74EFC2B16D325C44B8CEBB9360127CBE9C5F5DD70154D819DB36FD6A742B2E6`.
- No MSI was staged, installed, repaired or uninstalled on the existing
  Windows guest. No non-admin learner proof has been executed.

## Source update — dedicated learner-controlled repair nonce

The custom action now reads only `repair-request.txt` from its fixed owned
#25 directory, accepts strictly 1–6 ASCII digits with a value from 1 through
999999, and writes that nonce into one non-overwriting protected proof file.
The preparation module creates that *one file* with a narrowly scoped
`lpe.trainee` data-write ACE; the fixture directory and proof remain
administrator-owned and protected. Inspection validates the request-file
type, reparse state, learner ACE and bounded proof, optionally against an
independently selected `ExpectedNonce`. No caller-selected path, command
or executable is accepted. Native CI compiles the source.

**This resolves only the proposed learner-controlled input path at source
level.** It does NOT establish that `lpe.trainee` can trigger Windows
Installer to execute the deferred no-impersonation repair custom action in
a privileged context. That exact trigger, file ACLs on the Windows guest,
negative inputs, installer permissions and complete recovery still require
independent Windows acceptance. #25 remains planned and unqualified.

## Blocker A — identify a genuine attacker-controlled LPE mechanism

`Kingdom25Repair.cpp` accepts fixed `CustomActionData`, writes a fixed
`repair-proof.txt` marker under an administrator-owned fixture root, and
refuses preexisting proof files. `Kingdom25RepairPackage.wxs` schedules this
deferred, no-impersonation action on repair. This establishes a reproducible
privileged *behavior* candidate, **not by itself privilege escalation**.
Neither the repair input nor the binary path is currently controlled by
`WSLPE-WS01\lpe.trainee`.

A candidate must specify the precise non-admin-controlled resource,
the misconfiguration that allows that control, the native Windows Installer
repair boundary, and the attacker-selected effect in a dedicated lab-owned
destination. Record what the learner could change **before** repair, the
installer's actual context, the resulting bounded proof, and why that proves
a security boundary crossed. A SYSTEM-owned fixed marker alone is
insufficient. Preserve a negative test where unauthorized/unchanged input
cannot cause an unintended action. Do not loosen global
`AlwaysInstallElevated` policies.

**Decision gate:** approve a real, distinct #25 exploitation mechanism or
keep #25 planned; do not mistake packaging, native CI or logged-on repair
for learner exploit proof.

## Blocker B — installation ownership and failure recovery

`Wslpe25MsiOperator.psm1` requires exact local administrator console
approval, an exact staged MSI hash/ProductCode, and a protected #25 fixture.
Before `msiexec /i`, it creates `msi-product-ownership.json` with
`status=install-attempted`. Only after installer success and a registered
product state does it change the status to `installed`.

Its `Uninstall` operation currently accepts only `status=installed`.
If the native installer completes but the PowerShell verification or ledger
update fails, the product can remain registered while the ledger still
says `install-attempted`. The normal uninstall then correctly **refuses**
to adopt or delete it, but there is no reviewed owned recovery action.
Repeated installs, blind ledger edits and arbitrary MSI uninstalls are
not acceptable solutions.

| Owned ledger | Product state | Current safe response |
| --- | --- | --- |
| Absent | Not registered | Baseline only if the owned fixture and Program Files destination are also absent |
| `install-attempted` | Not registered | Block live changes; offline Recover prototype requires proving exact absence and ownership |
| `install-attempted` | Registered | Block live changes; prototype Recover can target only the exact approved ProductCode after separate authorization |
| `installed` | Registered | Standard owned uninstall may be considered only after snapshot/review authorization |
| `installed` | Not registered | Block; inspect partial cleanup without deleting unrelated resources |
| Any | Foreign ProductCode, missing MSI, ACL anomaly or reparse point | Refuse mutation and preserve evidence |

Do not automatically remove or rewrite the ledger on failure. A recovery
path must verify **all** recorded ownership fields, the exact Windows
Installer ProductCode, native installation state, protected directories,
unexpected files and cleanup state, then positively prove restoration.
The currently compiled package produces a new ProductCode for each build;
pin the chosen build, manifest and SHA-256 through an entire lifecycle.

## Recovery implementation checkpoint (18 October 2026)

An explicit, **still unqualified** `Recover` action is now present in
`Wslpe25MsiOperator.psm1`, independent of the standard `Uninstall`.
This is **source only; no Windows guest has run it**. The new action requires
the same exact WSLPE machine, elevated interactive local console, owned
#25 fixture, native ProductCode and staged MSI digest checks as the standard
operator, plus an action-specific recovery approval phrase and an explicitly
supplied SHA-256 digest.

Recovery only accepts a matching `install-attempted` ownership ledger.
Registered product state `5` is handled by bounded native uninstall of
the exact ProductCode; unregistered state `-1` is handled only by verifying
the dedicated Program Files path is absent and cleaning the owned fixture.
Other states, `installed` ledgers, ownership mismatch, unexpected fixture
entries, unknown product state, or altered package digest **fail closed**.
The owned ledger is preserved on any unsuccessful attempt. It never adopts
a foreign MSI or edits a ledger to bypass state checks.

A separate **pure, no-I/O Windows CI recovery decision matrix** covers
registered/unregistered, foreign ownership, unexpected content, and unknown
states. CI also parses the operator. This does not constitute a real MSI
rollback rehearsal. Registration and filesystem state can change between
checks, so the recovery path still needs a native security/race review and
a separately authorized, snapshot-backed runtime test.

**Blocker A is unchanged:** the fixed repair marker is not a learner-chosen
privilege-escalation effect. No deployment or source candidate promotion is
authorized.

## Blocker C — staging and independent operational acceptance

The successful Windows CI artifact is available for *review*, not deployment.
Staging into `C:\ProgramData\KingdomsWSLPE45\lib\Kingdom25Repair.msi`
is an explicit future operator change, not part of the batch and not yet
approved. A separate review must resolve protected-path transfer,
artifact signature/provenance, snapshot restoration, WinRM/RDP continuity,
per-machine registration and non-admin repair authorization.

Acceptance sequence after a separately approved maintenance window:
`apply -> vulnerable validation -> reset -> clean validation -> reapply
-> revulnerable validation`; independently prove the learner-side attack
and negative cases. If the first mutation fails, stop and use the
pre-agreed recovery method. CI does not execute any of these stages.

## Current engineering decision

1. Define and independently review the missing attacker-control primitive
   before promoting or deploying #25.
2. Independently review the committed `Recover` operator, including the
   native product-state assumptions and failure/cleanup edge cases;
   Windows CI evidence alone cannot qualify live rollback.
3. Only after both reviews, authorize a pinned-artifact staging plan and
   a snapshot-backed WSLPE-WS01 test.
4. Keep #25 `planned` and the official tally **21/25** until complete
   source and evidence satisfy their distinct gates.

**Do not run `Invoke-Wslpe25FixturePreparation -Action Prepare`,
`Invoke-Wslpe25MsiOperator -Action Install`, repair, or uninstall on the
existing WSLPE guest from this checkpoint.**
