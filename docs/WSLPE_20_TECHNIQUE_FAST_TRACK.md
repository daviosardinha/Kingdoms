# Windows LPE — Today’s fast-track from NORTH WS01 to standalone WSLPE

**Source of truth:** Existing \`ansible/roles/windows_lpe\` in this repo.
**Scope:** Standalone WSLPE development only; NORTH is read-only/frozen.
**Status:** Fast-track operator runner committed, first Kali qualification pending.

## What is already done and should NOT be recreated

\`ansible/roles/windows_lpe/defaults/main.yml\` contains 20 implemented
techniques and **zero candidates**, with documented full reversible
runtime validation on NORTH WS01 (2026-09-03). Those 20 tasks are already
included in \`ansible/roles/windows_lpe/tasks/main.yml\` and operate
through the shared \`apply\`, \`validate\` and \`reset\` actions.
WSLPE \`ansible/wslpe-lpe-test.yml\` already imports that *same* role.
**DO NOT copy or fork the role.** Reuse it; fix any standalone
incompatibility at the WSLPE adapter or in reusable identity parameters.

Domain-specific \`ansible/ws01.yml\` / \`commonwkstn\`, NORTH learner
\`NORTH\\rickon.stark\`, DCs, routes and NORTH VMnets are out of scope.
The intended WSLPE identity is \`WSLPE-WS01\\lpe.trainee\`; the guest
must have \`PartOfDomain=False\`.

## Why 42 source tests did not mean the course was ready

The P1-C source tests prove pieces of VMware/WinRM/network recovery.
They do NOT prove that the 20 exercises work with **local accounts**
on WSLPE; nor do they prove local learner RDP, stable scenario resets,
real exploitation under a non-admin identity, safe learner isolation,
or course materials. Do not block trusted developer-side scenario
qualification on the learner-only network topology.

## Immediate accelerated workflow

First, once per checkout, run the source tests and the **non-mutating**
exact-WSLPE catalog/target plan:

~~~bash
# Run in an isolated subshell. Any failure returns to the Kali prompt.
if (
cd "$HOME/kingdoms-lpe-standalone" || exit 1
git pull --ff-only || exit 1
"$HOME/.goad/.venv/bin/python" -m unittest -v tests.test_wslpe_fast_track_20
"$HOME/.goad/.venv/bin/python" scripts/wslpe-fast-track-20.py
); then
  printf '[PASS] WSLPE command completed; operator shell remains open\n'
else
  printf '[BLOCKED] Check output above; operator shell remains open\n' >&2
fi
~~~

The script loads the 20 techniques from the current shared role,
finds the existing WSLPE-only instance/VMX/inventory, and enumerates
all 20. It does not write to Windows, NORTH, VMware or the firewall.

### Prerequisite: the local learner foundation must exist

\`ansible/wslpe-foundation.yml\` defines local \`lpe.trainee\`, asserts
the guest is not domain-joined, and maintains the Windows evaluation
baseline. **It is NOT the same as the already proven read-only Stage 2
baseline**; no live foundation acceptance has been recorded yet.
Its installation may modify Windows and reboot for license rearm.
Run it separately under explicit operator approval when necessary,
against ONLY the WSLPE inventory. Do not automatically provision NORTH.
Keep \`KINGDOMS_WSLPE_LEARNER_PASSWORD\` private (at least 12 chars).

### One explicit batch qualification — WSLPE DEVELOPMENT ONLY

If the learner foundation has NOT already been applied, use the
**one-shot bootstrap + qualification** route. Bootstrap reuses the
existing WSLPE-only foundation playbook and may perform a controlled
Windows evaluation-rearm reboot. It never invokes NORTH:

~~~bash
# Run in an isolated subshell. Any failure returns to the Kali prompt.
if (
cd "$HOME/kingdoms-lpe-standalone" || exit 1
"$HOME/.goad/.venv/bin/python" scripts/wslpe-fast-track-20.py --execute --bootstrap-learner
); then
  printf '[PASS] WSLPE command completed; operator shell remains open\n'
else
  printf '[BLOCKED] Check output above; operator shell remains open\n' >&2
fi
~~~

If `lpe.trainee` already exists, avoid unnecessary provisioning and run
only the qualification:

~~~bash
# Run in an isolated subshell. Any failure returns to the Kali prompt.
if (
cd "$HOME/kingdoms-lpe-standalone" || exit 1
"$HOME/.goad/.venv/bin/python" scripts/wslpe-fast-track-20.py --execute
); then
  printf '[PASS] WSLPE command completed; operator shell remains open\n'
else
  printf '[BLOCKED] Check output above; operator shell remains open\n' >&2
fi
~~~

Both commands are noninteractive: \`--execute\` authorizes the requested WSLPE-only changes. The bootstrap route
does the native WSLPE inventory safety check **before** applying the
foundation and then runs the existing local/domain-free `status`
acceptance before any LPE vulnerability scenario.

The runner:

1. Uses \`--execute\` as explicit authorization; no phrase or terminal interaction.
2. Creates one strong, unique local Windows learner password on the first \`--bootstrap-learner\`, saves it in an operator-owned \`0700\` directory as a \`0600\` file outside Git, then reuses it automatically. An existing private environment credential is also supported.
3. Verifies the dynamic WSLPE-only instance/inventory and host IP.
4. Runs the existing WSLPE playbook \`status\` to prove exact hostname,
   domain-free machine and existing local \`lpe.trainee\` before changes.
   The Ansible limit includes both \`ws01\` and \`localhost\`; otherwise
   the adapter's first authorization play would be silently skipped.
5. Executes each existing technique one at a time:
   \`apply → validate vulnerable → reset → validate clean →
   reapply → validate vulnerable\`. Stops at the **first** error.
6. Writes a private 0600 JSON acceptance report containing status codes,
   not learner passwords or raw Ansible outputs.
7. If all 20 pass, leaves the **intentionally vulnerable** scenarios
   in place and reports \`WSLPE_STANDALONE_20_TECHNIQUES_ACCEPTED=TRUE\`.

This is a potentially lengthy, **mutating** test on WSLPE ONLY; do not
run on an unisolated machine with untrusted learners attached.
If the foundation is absent, status preflight fails closed before
any technique can be applied. Repair just that prerequisite once,
then rerun; do not repeat VMware audit loops.

## Acceptance still required after 20/20

The batch proves Ansible scenario seeding and reversal under the
operator context, NOT a learner's real non-admin → SYSTEM exploitation.
Follow it with effective local RDP/NLA access checks, evidence of
successful technique exploitation from a non-admin session, reset
reproducibility, course walkthroughs/screenshots and the commercial
learner infrastructure rollout. That last gate requires host-L2
isolation, scoped persistent firewall, independent recovery,
appropriate Windows licensing and tenant separation.

### Today’s decisions

- **Reuse, never rewrite** the 20 shared technique implementations.
- **One batch, one report**, not 20 manual command threads.
- When a scenario fails, fix only the local-account/standalone
  assumption it exposes; keep NORTH unchanged.
- Treat local developer qualification and commercial learner release
  as separate milestones. Do not pretend 20 tests alone finish the
  entire course.


## Fast-track Python syntax hotfix (2026-10-16)

The first Kali fast-track invocation stopped **before tests, PLAN or
Windows changes** with `IndentationError: unexpected indent` at
`scripts/wslpe-fast-track-20.py` line 108. A source-edit operation had
inserted literal `\\n` tokens between a two-line comment and
`return`, leaving the `return` misparsed. The feature-branch hotfix
replaces those tokens with real newlines, without changing the WSLPE
target, Ansible invocation, or scenario lifecycle.

**Next run compiles BEFORE importing tests or executing any guest action:**

~~~bash
# Run in an isolated subshell. Any failure returns to the Kali prompt.
if (
cd "$HOME/kingdoms-lpe-standalone" || exit 1
git pull --ff-only || exit 1
PY="$HOME/.goad/.venv/bin/python"
"$PY" -m py_compile scripts/wslpe-fast-track-20.py tests/test_wslpe_fast_track_20.py &&
"$PY" -m unittest -v tests.test_wslpe_fast_track_20 &&
"$PY" scripts/wslpe-fast-track-20.py
); then
  printf '[PASS] WSLPE command completed; operator shell remains open\n'
else
  printf '[BLOCKED] Check output above; operator shell remains open\n' >&2
fi
~~~

This hotfix has not yet been validated on Kali. Do not run the
`--execute --bootstrap-learner` branch until compile, unit tests and
the exact WSLPE-only plan have all passed.

## What the learner actually uses

The Windows account is **WSLPE-WS01\lpe.trainee** (or **.\lpe.trainee**
inside the guest). This is a *standard local Users member*, never a
local administrator and never an Active Directory identity.

The existing \`ansible/wslpe-foundation.yml\` creates/enables this
account with the generated password and checks that it does not belong
to local Administrators. The **vagrant** credentials are provisioning
credentials, not learner credentials.

When you need the local development login details, explicitly run:

~~~bash
"$HOME/.goad/.venv/bin/python" scripts/wslpe-fast-track-20.py --show-learner-access
~~~

That displays the account/password **only on explicit operator request**.
Normal commands never print them. The local private store lives under
\`~/.local/state/kingdoms-wslpe-learner/credential\`, outside the Git
checkout. Never commit or post that password into Discord.

**RDP is not yet proven**: local account creation does not automatically
grant Remote Desktop Users group membership or ensure RDP/NLA logon
rights. The course must validate actual non-administrator login before
student release. Production multi-tenant course deployments must
generate independent credentials per learner instance and deliver them
via the authenticated platform or Discord entitlement workflow, not
share the developer VM credential.

### No more redundant confirmations

The first fast-track execution exposed an unintended
\`sys.stdin.isatty()\`/confirmation gate. This has been removed.
\`--execute --bootstrap-learner\` now handles credential generation
and WSLPE-only provisioning directly; \`--show-learner-access\` remains
a separate read-only operator operation. Actual infrastructure and
learner-release safety preconditions still apply.



## Inventory export-mode regression (2026-10-16)

On Kali the refreshed fast-track passed **12/12 source tests** and
catalog discovery (20/20), then stopped *before credential creation
or Windows modification* at:
`[BLOCKED] WSLPE qualification: Inventory does not target exact WSLPE management address`.
The user also attempted `--show-learner-access`, which appropriately
failed because no credential had been created.

The runner had invoked `ansible-inventory --list --export` but
assumed `_meta.hostvars.ws01` held the fully merged connection
variables. Export mode optimizes the format for inventory export and
may leave `[all:vars]` connection properties separate from hostvars.
This is not the correct representation for strict effective
connection checks.

**Fix:** `resolved_inventory_command()` now runs
`ansible-inventory -i <native_instance> -i <WSLPE_only_vars> --list`
(without `--export`), preserving the exact registered WSLPE
instance/IP, the resolved WinRM transport, one standalone host,
`domain_name=WSLPE`, and denial of NORTH/DC hosts. The negative
regression covers export-style layout, wrong transport and NORTH IP.
On a real mismatch the runner displays only expected/actual IP and
transport, never passwords.

A missing `--show-learner-access` credential now explains that
`--bootstrap-learner` must first pass inventory. No account, secret
or vulnerability changes were made by the failed run.

**Next combined local execution:**

~~~bash
# Run in an isolated subshell. Any failure returns to the Kali prompt.
if (
cd "$HOME/kingdoms-lpe-standalone" || exit 1
git pull --ff-only || exit 1
PY="$HOME/.goad/.venv/bin/python"
"$PY" -m py_compile scripts/wslpe-fast-track-20.py kingdoms/wslpe_learner_credentials.py &&
"$PY" -m unittest -v tests.test_wslpe_fast_track_20 tests.test_wslpe_learner_credentials &&
"$PY" scripts/wslpe-fast-track-20.py --execute --bootstrap-learner
); then
  printf '[PASS] WSLPE command completed; operator shell remains open\n'
else
  printf '[BLOCKED] Check output above; operator shell remains open\n' >&2
fi
~~~

The newly added tests are **not yet validated on Kali**. Explicit
`--execute` remains sufficient authorization; no terminal confirmation
phrases or manual password prompts. If WSLPE provisioning fails, the
script stops and supplies a private diagnostic log path. Never share
an unredacted log containing Ansible credentials.


## Local learner Administrators/RDP SID hotfix (2026-10-16)

Kali source batch **14/14 PASS**; exact native WSLPE inventory
verified, and a private non-admin learner credential was generated
and reused. The first real `ansible/wslpe-foundation.yml` run returned
exit=2 after completing the baseline/license checks and creating the
local `lpe.trainee` account. The failure was specifically:

`Get-LocalGroupMember -Group BUILTIN\\Administrators` could not locate
the group. `Get-LocalGroupMember -Group` needs the local group name;
the previous code translated builtin Administrators SID to the
domain-qualified `BUILTIN\\Administrators` string.

The WSLPE-only foundation now uses
`Get-LocalGroup -SID S-1-5-32-544` and passes `$admins.Name`
into `Get-LocalGroupMember`, then checks learner SID equality.
It also adds the **standard non-admin learner** to the built-in
Remote Desktop Users group by SID `S-1-5-32-555`, with idempotent
membership verification and no AD membership changes. These source
changes do **not** prove actual learner RDP/NLA logon: that requires
separate runtime acceptance.

The existing VM, workgroup, generated password and user are preserved.
The same `--execute --bootstrap-learner` operation safely reruns the
idempotent foundation, then resumes the 20 existing shared-role
qualification cycles. No NORTH files or guest were changed. New
source regression is awaiting its first Kali run. The result is
not yet 20/20; previous attempt stopped **before any LPE scenario**.


## First live 20-scenario qualification: 6 accepted, 7th apply blocked

Kali source validation passed **12/12** and the WSLPE-only local
learner foundation returned PASS with the reusable private credential.
The first six shared-role techniques completed all six lifecycle
steps: apply, validate vulnerable, reset, validate clean, reapply and
validate vulnerable (**36 successful actions**).

`always_install_elevated` failed on its **first apply** (Ansible exit
code 2). All subsequent techniques were untouched. The run stopped
cleanly and wrote the operator-only files:

- `~/.local/state/kingdoms-wslpe-qualification/wslpe-qualification-20261016T153256Z.json`
- `~/.local/state/kingdoms-wslpe-qualification/wslpe-scenario-8e06d146092c.log`

The JSON proves the six completed cycles and the failed seventh apply,
but **does not contain the Ansible/PowerShell failure cause**. Inspect
the private log's actual failure before changing the shared
`ansible/roles/windows_lpe` role. The AlwaysInstallElevated task
requires the local learner Windows profile/NTUSER.DAT, which was
previously created using an authenticated Start-Process path for the
NORTH domain learner; profile setup incompatibility is only a
hypothesis pending the log. NORTH remains frozen.

A new `--resume-report` mode reads an owner-only, exact-format,
sequential qualification report with a **failed first apply only**.
The current WSLPE native inventory and standalone identity gates
still run. Before skipping any previously accepted technique, the
runner rechecks it with `validate/vulnerable` against the actual
guest; any drift aborts. It never repeats the passed six apply/reset
cycles. Do **not** run mutating resume until the seventh scenario's
error and potential partial apply state have been investigated.

After a specific fix and state review, the controlled resume workflow
will be:

~~~bash
# Run in an isolated subshell. Any failure returns to the Kali prompt.
if (
cd "$HOME/kingdoms-lpe-standalone" || exit 1
git pull --ff-only || exit 1
PY="$HOME/.goad/.venv/bin/python"
"$PY" -m unittest -v tests.test_wslpe_fast_track_resume tests.test_wslpe_fast_track_20
"$PY" scripts/wslpe-fast-track-20.py \
  --resume-report "$HOME/.local/state/kingdoms-wslpe-qualification/wslpe-qualification-20261016T153256Z.json"
# After diagnosis/repair only: append --execute to the exact command.
); then
  printf '[PASS] WSLPE command completed; operator shell remains open\n'
else
  printf '[BLOCKED] Check output above; operator shell remains open\n' >&2
fi
~~~

No learner, VM, firewall, NAT or NORTH changes were made by
adding the resume parser. The new resume source tests have not yet
run on Kali.

## Operator terminal safety standard

Previous copy/paste commands used top-level `|| exit 1` and could
terminate an interactive Kali shell whenever a source test or preview
failed. All multi-command examples in this document now wrap their work
inside `if ( ... ); then ... else ... fi`. Failure only exits the
**child subshell**; the parent terminal remains usable. A failed step
still stops the child workflow before later, potentially mutating commands.
Do not source Bash wrappers or use top-level `exit` in operator snippets.
Python `--execute` remains explicit WSLPE-only mutation authorization.

The actual seventh-technique PowerShell/Ansible failure is still unknown;
the private `wslpe-scenario-8e06d146092c.log` must be inspected before
running mutating resume. Source review and simulated shell safety do not
prove the live guest state or preclude all future errors.


## Fast-track regression test contract hardened (2026-10-16)

Operator source checks failed with `AttributeError: 'types.SimpleNamespace'
object has no attribute 'resume_report'`. The resume feature had added
a mandatory `args.resume_report` read to the non-mutating path, but
the preexisting `test_default_mode_does_not_invoke_ansible_or_modify_vm`
test still constructed `SimpleNamespace(execute=False)`. No guest
modifications occurred; the parent Kali terminal correctly remained
open with a `[BLOCKED]` status.

**Durable fix:** `build_parser()` is now shared by runtime and the
source tests. Default plan and checkpoint-resume plan tests use
`build_parser().parse_args(...)`, not hand-created namespace mocks.
A test matrix covers all CLI option defaults. WSLPE-only
`.github/workflows/wslpe-fast-track-source.yml` now runs syntax
compilation and source/negative-path tests on branch updates, without
any VMware, Windows, firewall, Vagrant or NORTH calls.

**GitHub Actions source validation:** run 38946855211 completed
SUCCESS, **22/22 tests**, `python -m py_compile` PASS. Source checks
are real, but guest-side scenario 7 `always_install_elevated` is
still blocked pending its private Ansible error inspection. Do not
confuse green source CI with 20/20 Windows scenario acceptance.

Next operator action: pull the feature branch; inspect
`~/.local/state/kingdoms-wslpe-qualification/wslpe-scenario-8e06d146092c.log`
with password redaction. Do not run `--execute --resume-report` until
technique-7 failed APPLY's exact cause and baseline are established.
