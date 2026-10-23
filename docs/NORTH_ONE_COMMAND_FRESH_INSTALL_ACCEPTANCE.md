# NORTH — one-command fresh-install acceptance gate

**Scope:** KINGDOMS Course 1 `NORTH`, not the full KINGDOMS lab or standalone WSLPE. **Status: SOURCE CANDIDATE — NO FRESH RUNTIME ACCEPTANCE YET.**

## Release contract

The exact user invocation for a **new, empty** NORTH instance is:

```bash
./goad.sh -t install -l NORTH -p vmware
```

It must bootstrap host networking through the existing owned VMware transaction, create and provision **five** machines (GOAD-ROUTER, GOAD-DC01/KINGSLANDING, GOAD-DC02/WINTERFELL, GOAD-SRV02/CASTELBLACK, GOAD-WS01), execute the current NORTH **21-play** Ansible manifest, finalize exercise-mode isolation and return success only if the instance is READY. Manual `prepare-north`, manual network apply, manual Ansible `resume-north`, or a preexisting provisioned guest do **not** qualify as fresh-install proof.

The new native clean-host bootstrap captures the current VMware configuration SHA-256 as a concurrency guard. This automatic hash is **not** a prior human-reviewed baseline; the underlying transactional apply still checks the original bytes under lock, no running VMware guests, unallocated vmnet IDs, CIDR/IP/route/registered-VMX collisions, owned backup, rollback and verified persistent `.254` host interfaces before any Windows VM starts.

## Hard safety gates

- Execute only on an **isolated disposable VMware test host** with no running guests, no existing NORTH owner, and no conflicting vmnets or IP routes. Do not run the first acceptance on the existing Kali workstation carrying `ac9fda-north-vmware`, full KINGDOMS or WSLPE.
- If the original command fails, **stop and retain logs**. A partial instance/owner is not an invitation to rerun with `--start`, `resume-north`, reinstall, delete VMs or change the owner SHA.
- Existing-instance operations remain strict, read-only-ownership guarded; no silent adoption/repair. The source-only `course1-rollout.sh --source` and `--deploy` guard do not authorize guest operations.
- No schema, trust, RDP or vulnerability modifications are justified to make the installer return `0`. Fix source and repeat on a newly reset **disposable** test host after reviewing the previous failure.

## Acceptance evidence to retain (fresh instance only)

1. Exact branch/commit and clean working tree, full unit/source regressions on that commit, full KINGDOMS alias/source compatibility.
2. Full command invocation, exit status `0`, new instance ID, all five exact Vagrant VMX registrations and Ansible 21-play completion. No manual intervention besides ordinary sudo authentication.
3. Parent/child DC, DNS, trust, secure channels, W32Time NT5DS and authoritative service identities proven independently.
4. NORTH WS01 RDP foothold, CASTELBLACK SQL/HTTP, Phase 01/02 scenarios, Phase 03 read-only prerequisites; separate active attack consequence and rollback are their own gates.
5. All 20 NORTH WS01 LPE vulnerable-state markers after a neutral Phase 03; `course1-phase04-acceptance.sh` uses an explicit transient-right confirmation.
6. Exercise mode router drop policy, absent protected-network host routes, disconnected persistent Windows NAT NICs, owned vmnet10/20/99 and `.254` host persistence.
7. Two independently observed native cold-start cycles and snapshot restore on the fresh test instance (only after reviewing data-loss consequences). No unowned VMware guest affected.
8. A second clean fresh-install acceptance after any source revision, and explicit PR #35 review; do not conflate tests on the existing recovered `ac9fda-north-vmware` instance with a fresh installation.

## Candidate source tests

On a **reviewed clean checkout** of the candidate branch:

```bash
python3 -m unittest tests.test_course1_one_command_bootstrap tests.test_install_noninteractive tests.test_course1_provider_guard tests.test_course1_native_lifecycle
bash scripts/course1-rollout.sh --source
```

The above commands do not bootstrap networking or launch VMware guests. The command under test remains `./goad.sh -t install -l NORTH -p vmware`; do not replace it with `scripts/course1-rollout.sh --deploy` (currently deliberately blocked).

## Merge decision

Until the clean-host end-to-end evidence and regressions are accepted, keep this bootstrap change as a draft PR against `rebuild/course1-from-kingdoms`, and keep NORTH integration PR #35 draft against `main`. Standalone WSLPE deployment is expressly out of scope.
