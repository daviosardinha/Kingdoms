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

## 2026-10-23 WS01 Windows evaluation shutdown maintenance

Windows 10 evaluation guest `mayfly/windows10` is used for `GOAD-WS01`. Historical 2026-10-15 / Oct 21 WSLPE instances using this image showed `TIMEBASED_EVAL`, `GracePeriodRemaining=0` and Winlogon/License Monitoring (`wlms.exe`) shutdowns; an idempotent existing `ansible/roles/settings/eval_rearm/tasks/main.yml` fixed those by using supported `slmgr.vbs /rearm` **only when expired**, rebooting and verifying grace.

The currently installed NORTH guest `93fd1b-north-vmware` has twice powered off unexpectedly during build, while its vmnet10 NIC config, host vmnet10 routing and NAT owner remained correct. This is **consistent with** the prior WLMS behavior, but this guest's specific Event 1074 license-shutdown evidence is not yet collected. Never claim a confirmed current-guest root cause solely from VMware power state.

NORTH's existing `ansible/ws01.yml` already imported `settings/eval_rearm`, but this happens **after** `build.yml`, much too late for an expired WS01 that powers off in the meantime. Fix:

- `ansible/north-ws01-eval-maintenance.yml` imports **the same role** before initial AD configuration, via an isolated, runtime-generated one-guest WinRM inventory. If the role needs `/rearm`, its `win_reboot` and post-reboot verification execute before proceeding. The maintenance play also requires at least 24h of valid evaluation grace when `TIMEBASED_EVAL` is present.
- `scripts/north-ws01-eval-maintenance.py` validates native NORTH network owner and exact original GOAD-WS01 VMX/vmnet10/MAC, discovers only this guest's forwarded TCP/5985 port, then runs the existing Ansible role. Never disables WLMS/Windows Defender/firewall, never changes VMware network state, and does not create or alter other VMs. Its `--start-existing` operator flag starts only that WS01 VMX if it is powered off.
- `GoadKingdomsVmwareProvider.install` invokes the same helper on NORTH WS01 immediately after first Vagrant/VMware guest bring-up and recovery, before any of the 21 long AD playbooks. This is not inserted into the immutable 21-play manifest; it is a bounded pre-AD guest-readiness operation. Full KINGDOMS install is untouched.
- The original `ansible/ws01.yml` later calls the same role idempotently for future grace maintenance.

### Recovery of the Oct 23 interrupted instance

From the clean source checkout `~/kingdoms-north-fresh-test`, with other NORTH VMs and network ownership preserved:

```bash
sudo -v
python3 scripts/north-ws01-eval-maintenance.py \
  --provider-dir "$HOME/kingdoms-north-fresh-test/workspace/93fd1b-north-vmware/provider" \
  --start-existing
```

If the guest has expired licensing and can establish authenticated NAT WinRM, expect `WINDOWS_EVAL=REARMED`, a normal guest reboot and `WINDOWS_EVAL_READY=PASS` followed by `NORTH_WS01_LICENSE_READY=PASS`. If healthy already, the role is read-only/idempotent except for its verification tasks. If the role fails or the VM cannot remain on long enough for WinRM, **stop** and inspect Windows shutdown Event 1074 or the VMware power-off logs before attempting anything else. No automatic retries, no bypass of Windows licensing, and no attempt to rearm beyond Microsoft's allowed count.

After the role passes, operator must check all five VMs still running and `10.4.10.31:5986` reachable/authenticated, then use native existing-instance `resume-north -i 93fd1b-north-vmware -r build.yml` to finish *development recovery only*. A truly fresh uninterrupted one-command install remains mandatory before release/merge.

## 2026-10-24 snapshot pop restore failure and offline NORTH exact-generation fix

Operator validated **two Vagrant `snapshot push` operations across all five NORTH VMs (10 VMware snapshots)** on instance `93fd1b-north-vmware`, then invoked native `./goad.sh -t reset -l NORTH -p vmware -i 93fd1b-north-vmware`. The restore **failed with exit code 1** after Vagrant had started and reconfigured guest NIC/host NAT management forwards despite `--no-start`, ending in `GOAD-WS01 Guest-specific operations were attempted on a machine that is not ready for guest communication`. Log: `~/north-reset-20261024T101515Z.log`.

A second, more serious problem was visible: `vagrant snapshot pop` chose the **older/first** WS01 `push_1792834953_621` while the expected latest was `push_1792835377_3829`. This corresponds to Vagrant `pop` matching only *bare* `push_TIMESTAMP_RANDOM` names in a VMware provider snapshot list where the newest child is nested as `first/second`. Vagrant may restore the wrong generation. The existing native code only normalized exercise NICs *after* successful Vagrant pop and thus could not recover when Vagrant had already failed mid-restore. **Do not rerun legacy reset, start VMs or destroy any snapshots while the instance is potentially partially restored.**

Code fix (NORTH only, leaving full KINGDOMS behavior unchanged):
- New `goad/course1_snapshot_restore.py` verifies exact instance/Vagrant-registered VMX for all five guests, requires all five guests offline, reads each VM's `vmrun -T ws listSnapshots`, chooses the newest `push_timestamp_random`, and verifies equal generations with timestamp cohesion across all five **before reverting any VM**. No Vagrant boot, provisioning, network rewrites or pop stack ambiguity.
- NORTH `GoadKingdomsVmwareProvider.reset` uses `vmrun -T ws revertToSnapshot` for the five exact snapshot IDs. Each revert is checked for unauthorized VM auto-start, and the established offline management-NIC normalization path then executes. Errors fail closed without automatically starting anything. Partial revert can still occur if vmrun fails after another VM was restored: it logs the failure and needs operator review.
- Full KINGDOMS still uses original Vagrant pop path; its regression compatibility is preserved.
- `tests/test_course1_snapshot_restore.py` covers newest-vs-parent selection, wrong/missing generation, running guest, foreign VMX, failures midway and no Vagrant or boot calls.
- Dedicated NORTH + KINGDOMS alias CI on `0434920` passed. Runtime reset with this new helper has not yet been performed.

**Recovery boundary:** first inspect the five VMX running states, VMware and Vagrant snapshot inventories, current vmnet owner verification, and persistent Windows NAT adapter settings. The failed restore may have changed NAT forwarded-port rules. Do not trigger a second reset until exact host/guest status is recorded and safe; no lossless rollback is guaranteed when snapshots have already changed guest disk state. After recovery, check AD domain identity, RBCD, shadow baseline, LPE fixture count and exercise isolation, then fresh one-command installation release gate.
