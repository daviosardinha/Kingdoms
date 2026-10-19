# Standalone WSLPE: selected 21 deployment

This is an install-and-validate operation, not the six-stage qualification
runner. It uses the existing implementation index, scenario playbooks,
batch command builder, native inventory registration, VMware snapshot guard,
pinned management TLS and private journal components.

## Scope and existing-state contract

Selected in order: 21, 22, 23, 24, 26, 27, 28, 29, 30, 31, 32, 33, 34,
35, 37, 39, 41, 42, 43, 44, 45.
Explicitly excluded: 25 MSI repair, 36 WMI provider authorization, 38 DCOM,
40 custom RPC. No excluded install/reset/remove operation is dispatched.

#30 already has a console-activated fixture according to
WSLPE_JEA_ACTIVATION_RECOVERY_GATE.md. It is preserved. Its installation
result is PASS_EXISTING only after actual owned configuration validation and
a fresh lpe.trainee JEA Status session. It is validated again in its next
step. An absent, partial or inactive JEA endpoint fails closed; this runner
does not register it remotely or bypass the existing PS5.1 console guard.
Status proves activation, not exploitation. No Proof operation is invoked.

All other selected fixtures are applied then immediately validated, stopping
at the first failure. Existing collisions are not adopted or reset.
The report distinguishes NOT_ATTEMPTED, FAIL, PASS and PASS_EXISTING.
An interrupted stage is recorded as inflight; it must not be inferred failed
cleanly or retried automatically.

## Reconciliation of 6043850

That commit conditionally suppressed the shared ACL update, but did not add
a selected deployment coordinator or suppress common-module writes in every
candidate. The dedicated runner now verifies the existing protected root,
library and common-module hash, checks the interrupted #25 marker without
writing it, and sets the shared-preservation option for every selected
playbook. Directory creation and WslpeFixture.psm1 copying are skipped.
The common module itself and the index qualification claims remain unchanged.
Shared ACL/hash, #25 marker and existing JEA file fingerprints are checked
before and after every operation. An existing #40 server may coexist only
when its exact protected image path, sole --serve-local-only argument,
administrator/SYSTEM process owner, owned fixture and absence of TCP/UDP
endpoints are verified. Multiple or unidentifiable hosts fail closed.
Its existing fixture, staged binaries and operator module are inspected and
fingerprinted, never modified, invoked or killed. Their contents and ACLs
must remain unchanged throughout the batch; natural process exit is allowed.
Existing shared source destinations must not be linked or writable by
non-administrators.

#22 remains a deliberately machine-wide SCM CREATE_SERVICE grant. It is not
fixture-local. Its validation now requires the exact original descriptor
plus precisely one intended learner ACE, with the original snapshot retained.
The user-authorized --execute batch includes this global guest-local change.
Exact host/snapshot guards do not establish post-exploitation network
isolation or student-release readiness.

#24 now resolves the opened update handle and copies locked bytes into the
protected fixture root before starting that copy, closing the lexical
check/reopen gap. It still intentionally trusts an unsigned learner update.
Native compile/parse checks are not adversarial Windows runtime proof.
#34 already contains exact-target nonrecursive junction removal before the
generic reset guard; this deployment never invokes reset. Full rollback and
junction-race qualification remain separate.
#35 already uses canonical ../files/wslpe45 sources, verified by dependency
checks and Ansible syntax CI.
#43 retains its catalog ID but demonstrates manifest-based plugin trust,
not a cryptographic signature bypass.

## Operator command

After GitHub source checks pass for the current branch commit:

```bash
cd /home/stark/kingdoms-wslpe45-pilot &&
git pull --ff-only origin feature/wslpe45-single-candidate-pilot &&
"$HOME/.goad/.venv/bin/python" scripts/wslpe45-deploy21.py --execute
```

The checkout must already be on that exact branch and clean. The command
never stashes, switches branches, resets source or installs dependencies.
The existing runtime must supply ansible.windows with win_powershell
sensitive_parameters support, pywinrm, PyYAML, and the existing private
learner credential. Missing dependencies/credentials fail without prompting.
If native registration is ambiguous, supply --workspace with the verified
original native workspace, not a newly created workspace.

No argument selects just #28. The selection is fixed at all 21.
The pre-existing KINGDOMS-WSLPE-PRE-LPE40-20261018 snapshot is checked,
never created, restored or deleted.
The fixed state directory is ~/.local/state/kingdoms-wslpe45-live (0700).
Journals/logs are 0600; no alternate report directory bypass is exposed.

## Recovery and report

On failure, keep the JSON, logs, sentinel and guest state. Do not delete
.wslpe45-recovery-required and do not rerun blindly. The journal names the
commit, exact VMX/address/inventory/snapshot, UTC timestamps, every scenario,
installation result, configuration result, private evidence paths and failure
stage. Later scenarios remain NOT_ATTEMPTED; successful earlier ones remain
installed. Recovery is a separate reviewed operation after inspecting the
failed fixture and outstanding processes. There is no automatic rollback.

The 20-scenario baseline is operator-reported; this operation does not
reapply, reset or recount it. Twenty baseline plus 21 distinct selected
configurations is the desired 41/45 state, not a source-CI result.
Do not double-count pre-existing #30 as a newly installed scenario.

Evidence categories:
- Source implemented: committed code and successful GitHub source checks.
- Installed on Windows: actual apply or verified existing-state result.
- Configuration validated: immediate Windows validation passed.
- Exploitation proven: independent learner boundary-crossing evidence.

This change supplies no new Windows runtime or exploitation evidence.

## Correction for the observed initial preflight failure

The operator's bcc4000 transcript stopped at the blanket active-#40 check,
with changed=0 and no selected scenario application. This was an overly broad
coexistence gate. The reviewed server uses the dedicated ncalrpc endpoint
KingdomsWSLPE40 and its own fixture; selected playbooks and their copied
sources do not address those resources. CI checks that separation and runs
positive/negative identity decisions under native Windows PowerShell 5.1.

The replacement gate preserves the existing host and records its protected
files in the batch preservation fingerprint. Those recorded hashes establish
unchanged existing bytes, not independent original-build attestation.
No excluded #40 implementation is changed. No RPC operation is called.
Concurrent #40 fixture writes cause preservation validation to stop the batch.

After pulling the tested correction, repeat the operator command above.
The observed initial read-only failure occurs before creation of a new
recovery sentinel. If a sentinel from another attempt exists, it still blocks;
do not delete it. Preflight failures now print a bounded reason as well as the
private evidence path. This source correction supplies no guest installation,
configuration-validation or learner-exploitation result.

## Recorded #27 partial application, 2026-10-19

Journal wslpe45-deploy21-8e5b1f7c2a08b2d5.json records a3cbd7d on
WSLPE-WS01 (172.28.231.31). #21,22,23,24,26 passed installation and configuration
validation. At 08:39:24 UTC, #27 apply failed on RegAsm warning RA0000 emitted
to stderr through PS5.1's native pipeline. The log does not prove whether
registration completed. The fixture and DLLs had already been created.
The subsequent 15 selected scenarios were not attempted.

The RegAsm wrapper now captures native stdout/stderr separately, checks the
actual exit code, keeps warnings, and retains the post-registration checks.
It does not change global error handling or automatically repair a partial
registration. The remaining-source review also found and corrected #29's
unsupported PipeStream.ReadTimeout setter. Native CI exercises denial and
idle timeout against a CI-only pipe, without services or Proof operations.

The next operator operation is read-only inspection through the existing
runner, with the same provenance, inventory, snapshot, TLS and host gates:

```bash
cd /home/stark/kingdoms-wslpe45-pilot &&
git pull --ff-only origin feature/wslpe45-single-candidate-pilot &&
"$HOME/.goad/.venv/bin/python" scripts/wslpe45-deploy21.py --inspect-failure "$HOME/.local/state/kingdoms-wslpe45-live/wslpe45-deploy21-8e5b1f7c2a08b2d5.json"
```

This mode requires the matching owner-only journal and recovery sentinel,
compares preserved state with the failed run before and after inspection,
and records file hashes/ACLs, DLL metadata, exact CLSID/ProgID registrations,
consumer task XML and any outstanding RegAsm processes in private logs.
It neither updates guest source nor installs, resets, activates COM, kills
processes or clears recovery state. Share the new inspect27-state log and
inspection JSON to select the repair for the actual observed state.

Count remains 20 operator-reported baseline + 5 runtime-validated additions.
No learner exploitation is proven by this run. The target remains 41/45,
not 45/45. Exclusions and all earlier successful installations are retained.

## #27 inspection verdict and guarded recovery contract, 2026-10-19

The operator completed read-only inspection on WSLPE-WS01 at source commit
`61f83a943d45405191d8303e8ca6efa54ee355f5`. Private report:
`wslpe45-inspect27-f0a42380da6f77f4.json` (parent:
`wslpe45-deploy21-8e5b1f7c2a08b2d5.json`).

- Preflight before and after: PASS. Both preservation digests matched
  `9AB97BF7EB5D424B87F2893D41816BE78683F7BAC407C68B4ADAC2E5BB724D26`.
- Read-only state inspection: PASS; `guest_mutations=false`.
- Dedicated #27 ownership marker identifies the intended guest, scenario and
  existing learner SID. The fixture root, inbox and both COM assembly files
  exist; only the inbox/its DLL have the observed learner Modify permission.
- The inspected CLSID and ProgID registration trees are absent. No dedicated
  COM consumer scheduled task and no outstanding RegAsm process were detected.
- Assessment stays `RECOVERY_REVIEW_REQUIRED`. Inspection PASS is **not**
  installation or vulnerable-configuration PASS.

This is an owned partial **pre-registration** fixture, not a completed COM
scenario. The corrected RegAsm handling is committed, but the current deploy
runner deliberately will not retry while the partial directory and its
recovery sentinel exist.

A future explicit recovery implementation must fail closed unless it confirms
the original private journal and sentinel, exact guest/inventory/snapshot and
unchanged preservation fingerprint. Reinspect immediately before any mutation
and compare exact marker, SHA-256, ACL, directory entries, COM registration,
task and process state with the recorded inspection. A mismatch requires a
fresh review. Never adopt foreign registry entries or kill a running process.

If cleanup is authorized, constrain it to these specifically enumerated
#27-owned files/directories. The learner-writable inbox makes recursive
deletion or path-following cleanup a poor default: reject links and unexpected
entries, unlink only verified files, and remove empty directories without
traversing into foreign paths. No reset/reapply of #21–26, baseline20, #25,
#36, #38, #40 or unrelated services. Record intent before mutation, preserve
the original journal/sentinel and stop on any uncertain state.

After a successful clean #27 boundary, restart **at #27** with the committed
RegAsm wrapper, validate #27 on Windows, and only then attempt remaining
selected scenarios #28–45 in order, subject to exclusions and fresh
per-scenario preservation checks. Existing #30 JEA is validation-only.
Do not issue the original `--execute` command from a fresh batch, delete
`.wslpe45-recovery-required`, or claim 41/45 until a reviewed resume path
and real guest evidence exist.

This paragraph records the reviewed evidence and intended recovery criteria;
**no recovery code or guest mutation is claimed by this documentation change**.


## Exact journal-linked recovery and continuation (source-ready 2026-10-19)

The uploaded original #27 apply log proves the PowerShell 5.1 RegAsm
\`RA0000\` warning was promoted to \`NativeCommandError\`. The existing
read-only inspection proves the distinct pre-registration partial state.
The correction to capture stderr without changing global error handling was
already committed. The new explicit recovery mode is intentionally separate
from the normal \`--execute\` batch, which still refuses an outstanding
sentinel.

GitHub source CI validates the explicit recovery CLI, the exact private
inspection/journal binding, nonrecursive #27-only cleanup, no previously
successful replay, native PowerShell 5.1 syntax and Ansible syntax. It is not
Windows guest execution or learner exploitation qualification.

On the **original Kali machine** with the original owner-only evidence files,
after confirming branch CI passes, execute:

\`\`\`bash
cd /home/stark/kingdoms-wslpe45-pilot &&
git pull --ff-only origin feature/wslpe45-single-candidate-pilot &&
"$HOME/.goad/.venv/bin/python" scripts/wslpe45-deploy21.py \
  --execute \
  --recover-failure "$HOME/.local/state/kingdoms-wslpe45-live/wslpe45-deploy21-8e5b1f7c2a08b2d5.json" \
  --inspection-report "$HOME/.local/state/kingdoms-wslpe45-live/wslpe45-inspect27-f0a42380da6f77f4.json"
\`\`\`

This operation requires the original fail-closed recovery sentinel, original
journal digest, matching completed inspection and exact standalone guest,
inventory, VMware snapshot, authenticated management certificate and learner
identity. It re-inspects #27, compares all recorded ownership/file hashes,
ACLs, registry, tasks and RegAsm state, and requires preservation checks
before and after cleanup. It removes only enumerated owned #27 partial files
and verified empty directories, never recursive fixture trees or excluded
objects. It then verifies the clean #27 boundary and attempts #27–45 in the
original selection order (excluding #36/#38/#40; #25 was previously excluded).
Previously validated #21/#22/#23/#24/#26 are not installed again.

A new private \`wslpe45-recovery27-*.json\` journal records recovery and each
later installation/configuration result; the original failed deployment
journal and earlier read-only inspection remain unchanged. The recovery
sentinel is not cleared until all remaining selected configurations validate.
Any mismatch, timeout, uncertain partial state or failed validation stops
immediately and retains the sentinel and the recorded guest state. Do not
manually remove it, restore snapshots, rerun the original full batch or claim
learner exploitation. Report the new recovery journal and failed-stage
private log if anything stops.

The expected successful end state is the operator-reported baseline20 plus
21 configuration-validated selected scenarios, not proof of exploitability.
