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
cd "$HOME/kingdoms-lpe-standalone" || exit 1
git pull --ff-only || exit 1
"$HOME/.goad/.venv/bin/python" -m unittest -v tests.test_wslpe_fast_track_20
"$HOME/.goad/.venv/bin/python" scripts/wslpe-fast-track-20.py
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
cd "$HOME/kingdoms-lpe-standalone" || exit 1
"$HOME/.goad/.venv/bin/python" scripts/wslpe-fast-track-20.py --execute --bootstrap-learner
~~~

If `lpe.trainee` already exists, avoid unnecessary provisioning and run
only the qualification:

~~~bash
cd "$HOME/kingdoms-lpe-standalone" || exit 1
"$HOME/.goad/.venv/bin/python" scripts/wslpe-fast-track-20.py --execute
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
cd "$HOME/kingdoms-lpe-standalone" || exit 1
git pull --ff-only || exit 1
PY="$HOME/.goad/.venv/bin/python"
"$PY" -m py_compile scripts/wslpe-fast-track-20.py tests/test_wslpe_fast_track_20.py &&
"$PY" -m unittest -v tests.test_wslpe_fast_track_20 &&
"$PY" scripts/wslpe-fast-track-20.py
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
cd "$HOME/kingdoms-lpe-standalone" || exit 1
git pull --ff-only || exit 1
PY="$HOME/.goad/.venv/bin/python"
"$PY" -m py_compile scripts/wslpe-fast-track-20.py kingdoms/wslpe_learner_credentials.py &&
"$PY" -m unittest -v tests.test_wslpe_fast_track_20 tests.test_wslpe_learner_credentials &&
"$PY" scripts/wslpe-fast-track-20.py --execute --bootstrap-learner
~~~

The newly added tests are **not yet validated on Kali**. Explicit
`--execute` remains sufficient authorization; no terminal confirmation
phrases or manual password prompts. If WSLPE provisioning fails, the
script stops and supplies a private diagnostic log path. Never share
an unredacted log containing Ansible credentials.
