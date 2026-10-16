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

Both commands demand the exact interactive approval. The bootstrap route
does the native WSLPE inventory safety check **before** applying the
foundation and then runs the existing local/domain-free `status`
acceptance before any LPE vulnerability scenario.

The runner:

1. Requires interactive exact confirmation: \`QUALIFY WSLPE 20\`.
2. Reads the local learner password securely if not supplied via a
   private environment variable; never commits it.
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
