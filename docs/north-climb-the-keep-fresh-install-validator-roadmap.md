# NORTH Climb the Keep | Fresh-install vulnerability validator roadmap

## Status

**Deferred until course completion.** Preserve this requirement in `main` so it is not lost between development sessions. The validator has not been implemented, and the merged code is not itself a substitute for fresh-install regression testing.

## Goal

After every Climb the Keep lesson is complete, provision a disposable **fresh NORTH installation** and independently verify that each intended vulnerability is configured, reachable from the expected learner privileges, and capable of producing the intended lab outcome. Record failures and recover the lab safely.

The target is **NORTH only**, using its own VMware provider and WS01. Never reuse the full KINGDOMS or WSLPE inventory.

## Current merged foundation

- [PR #98](https://github.com/daviosardinha/Kingdoms/pull/98): Topic 07 scheduled service-start maintenance.
- [PR #99](https://github.com/daviosardinha/Kingdoms/pull/99): interactive SYSTEM shell helper for Topics 07–09, with **opt-in staging only** as currently implemented.
- [PR #100](https://github.com/daviosardinha/Kingdoms/pull/100): Topic 10 service Registry redirection and interactive SYSTEM helper.
- [PR #101](https://github.com/daviosardinha/Kingdoms/pull/101): Topic 11 application `HelperPath`, standalone helper and `HKLM\SOFTWARE\Kingdoms\KingdomConfigSvc` migration.

All four PRs are merged into `main` as of **2026-11-13**. Some attack and cleanup runtime gates remain unverified; do not equate source merge with a validated fresh installation.

## Required capabilities

1. **Inventory isolation**: refuse to run if the provider, guest or target does not match the selected NORTH instance and approved disposable workstation.
2. **Baseline checks**: service identities, startup modes, Registry locations, value types, ACLs, executable paths, source hashes, domain/user permissions and triggers must match the course contract.
3. **Attack-surface checks**: verify specific writable rights and their absence on protected objects, not just service or file existence. Detect vulnerability collisions between topics.
4. **Exploitability checks**: distinguish a Registry/file write from actual privileged execution. In interactive service topics, verify a *new* SYSTEM process while the original Rickon token remains unprivileged. For non-execution topics, prove the actual technique-specific outcome.
5. **Trigger checks**: service `DEMAND_START`, scheduled task and `AUTO_START`/reboot paths must be tested separately. Verify the direct start/stop rights promised by each exercise.
6. **Repeatability and cleanup**: retain the original Registry value and type, executable hash and service metadata, restore them after testing and verify reset and reapply idempotence. Include post-reboot service reload checks when necessary.
7. **Evidence and reporting**: per-topic PASS/FAIL/BLOCKED/SKIPPED, reason, collected outputs and artifacts, plus human-readable and machine-readable summary. Do not claim an interactive SYSTEM shell solely from a successful Ansible apply or SCM start.
8. **Safety**: read-only baseline mode by default. Explicit operator approval and a disposable snapshot are required for active exploit checks. Never test against running learner instances.

## Milestones

- [ ] Finish course definitions and map every final topic (currently 01–20) to exact configuration and expected result.
- [ ] Build a source-of-truth manifest for the independent topic tests.
- [ ] Ensure fresh installation provisions every essential helper and trigger. Specifically address opt-in `KingdomShell.exe` staging for Topics 07–09 before claiming default fresh-install readiness.
- [ ] Implement read-only configuration validator and per-topic diagnostic outputs.
- [ ] Implement snapshot-gated, controlled exploitation checks for approved disposable NORTH instances.
- [ ] Implement cleanup verification, rerun and regression suite.
- [ ] Pass the full suite on a truly fresh NORTH installation and again after all topic tests have run.

## Acceptance gate

The validator is complete only when the entire final course passes in a fresh NORTH installation, all claimed privilege-escalation outcomes are independently verified in isolated test runs, and cleanup/reapply returns the lab to its expected state without breaking other topics.
