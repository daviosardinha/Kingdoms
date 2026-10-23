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

## 2026-10-23 NAT lifecycle failure and guarded remediation

Actual instance `93fd1b-north-vmware` booted all five VMware VMs (32m25s) but stopped **before** any Ansible play because VMware replaced three NAT8 TCP mappings that had existed in the original host baseline. The deleted mappings were `2200 -> 192.168.213.249:5985`, `2201 -> .249:5986`, and `2202 -> .249:22`. The replacements point to the new NORTH VM addresses (`.251`, `.252`, `.253`, `.132`, `.250`) and are limited to guest management ports.

**Historical ownership discovered (October 21–22):** the earlier fresh WSLPE instance `bf5369-wslpe-vmware` was explicitly observed using VMware NAT guest IP `192.168.213.249/24`. WinRM to that guest over `127.0.0.1:2200 -> 192.168.213.249:5985` succeeded with identity `wslpe-ws01\\vagrant`. Therefore the former `2200 -> .249:5985` mapping was WSLPE's, not the old NORTH installation. **Limit:** the available earlier evidence does not independently reproduce the exact old `2201 -> .249:5986` and `2202 -> .249:22` Vagrant forwarding declarations, even though they share the same destination IP. Do not authorize all three retirements without independently checking their full mapping history. No current running VM means decommissioning may have occurred, but cached Vagrant registrations alone are not deletion proof. NEVER authorize retirement solely because the old target IP is no longer currently used.

### Fix and trust boundary

- `native-bootstrap` now **refuses all pre-existing NAT port-forward entries** before creating a VM; if another lab has any, this is not a clean-host acceptance run. Inspect and explicitly retire only evidence-backed old entries through a separate reviewed VMware/Vagrant decommission before starting a new attempt. This prevents this 32-minute late failure on hosts with pre-existing forwarding rules.
- The installed-owner verifier still blocks all removed vmnet declarations, all unexpected changes to NORTH or foreign networks, altered protected isolation, invalid NAT/IP/port values, and unauthorized additions. For recorded NAT forwards, only an **explicit root-owned, mode-0600 attestation of exact removed rules**, bound to the provider and original baseline SHA, can authorize a narrow removal. Each allowed removal must have exactly one same-host-port new mapping to the pinned vmnet8 NAT subnet on management guest ports 22, 5985 or 5986.
- The optional retirement record is `/etc/vmware/kingdoms-course1-retired-nat.json`. Schema `kingdoms.north.retired-nat.v1`; fields: `schema`, `provider` (exact new instance provider path), `baseline_sha256` (immutable owner backup hash), `reviewed_prior_owner` (validated previous NORTH or WSLPE instance-ID format), `removed_rules` (list of exact lines approved). The code DOES NOT create this record or infer prior ownership. For this specific original `.249` guest, the candidate reviewed prior owner is `bf5369-wslpe-vmware`, not `ac9fda-north-vmware`. A reviewer must first independently identify who owned the previous mappings, verify the old guest is decommissioned, and approve the three exact retirements. `reviewed_prior_owner` is an operator assertion, not independent cryptographic proof. If provenance cannot be verified, DO NOT install the record. No owner hash or journal is rebased.
- Do not hand-edit `/etc/vmware/networking` to bypass verification and do not modify existing NAT policy mid-install. Preserve the failed instance and log while investigating.

### Source and evidence gates

```bash
python3 -m unittest -v \
  tests.test_course1_vmnet_config \
  tests.test_course1_retired_nat_attestation \
  tests.test_course1_host_network_apply \
  tests.test_course1_one_command_bootstrap
bash scripts/course1-rollout.sh --source
```

The dedicated GitHub Actions job `NORTH native bootstrap NAT lifecycle regression` runs the dependency-free NAT, attestation and existing host transaction tests, independent of local VMware. The original CLI bootstrap tests remain in the local source suite.

The actual merge test still requires a **newly clean VMware host** with no pre-existing NAT forwards, a fresh five-VM installation via exactly `./goad.sh -t install -l NORTH -p vmware`, all 21 Ansible plays, exercise isolation, Phase 01-04 acceptance and lifecycle. Completing provisioning on the interrupted VM may aid development; it is NOT a fresh-install release PASS.

## 2026-10-23 interruption recovery: first playbook, pre-AD only

The first exact CLI fresh installation `93fd1b-north-vmware` completed all five VMware VM materializations, but failed in the **first and only** recorded Ansible phase `Provisioning management-plane preparation` before even `build.yml`. Operator verified `provider_success=True`, `status=failed`, `.goad-nomad-mode=unknown`, and manually restored the identical original GOAD-WS01 VMX. Owner + all five running VMX now pass independent read-only inspection.

Normal `resume-north` calls the AD-aware mode transition; it cannot be used *as-is* before AD exists. The candidate patch introduces an **extremely narrow one-call exception** for `resume-north -i 93fd1b-north-vmware -r build.yml`, gated by:

- Exact current NORTH+VMware provider and valid native owner verification.
- `build.yml` is first in the actual NORTH manifest; the requested start is exactly that file.
- Provider mode still `unknown`; instance status is `ready for provisioning`, never READY.
- Exactly **one** unambiguous, non-symlinked install receipt with `provider_success=true`, `status=failed`, and **one failed** `Provisioning management-plane preparation` phase; no Ansible playbook success or attempt.
- All five expected Vagrant registration files and original VMX files under that provider, and the five original VMX guests running. No absent WS01 and no newly provisioned VM substituted.
- Pre-AD authorization exists only during the single provisioner `run_from(build.yml)` call and is revoked in `finally`, including Ansible failure.

The existing original pre-AD router provisioning policy, parent route and authenticated management readiness are reused (without AD-readiness preconditions). After the 21 playbooks complete, original finalization restores exercise isolation. An incomplete Ansible run remains incomplete; never mark READY on failure.

**Operator steps:** pull candidate commit `e1d94a8` or later, run `python3 -m unittest -v tests.test_course1_pre_ad_resume tests.test_install_noninteractive` and `bash scripts/course1-rollout.sh --source`, then issue the verified native `./goad.sh -t resume-north -l NORTH -p vmware -i 93fd1b-north-vmware -r build.yml`. Capture pipeline `PIPESTATUS` in Bash. Do not use native `install -i`, `vagrant up`, `--ansible_only`, or `-t start` in this unusual pre-AD state.

**Release boundary:** This is **development recovery only**. The user explicitly requires a wholly fresh `./goad.sh -t install -l NORTH -p vmware` from zero (and complete AD/SQL/Phase03/LPE/isolation/lifecycle checks) before merging PR #45 and parent PR #35.
