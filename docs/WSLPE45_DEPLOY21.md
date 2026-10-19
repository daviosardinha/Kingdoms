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
