# Course 1 — One-command rollout contract

## Accepted baseline

At commit `ecb2584`, the Kali operator validated the original unified source and clean-host command: **19/19 stages PASS, 477 tests PASS, 13 seconds**. This is a *read-only* milestone and is **not** installation authorization.

The full Kingdoms scenario (`GOAD`) is the implementation baseline. Course 1 (`NORTH`) removes Essos only, retaining KINGSLANDING, WINTERFELL, CASTELBLACK, WS01 and GOAD-ROUTER. The discarded experimental NORTH installer and its branch must not return.

## One operator entrypoint

```bash
cd "$HOME/kingdoms-rebuild"
git pull --ff-only
bash scripts/course1-rollout.sh
```

The default `--all` action runs the established `scripts/validate-course1.sh` suite, including dynamic discovery of every `tests/test_*.py`, both 10.4/10.5 topology variants, the original Kingdoms compatibility gate, and clean-host read-only checks. Then it reports *all five* release-engineering gates in one output. An unimplemented runtime gate produces a **nonzero exit status** by design; do not mistake 19/19 source validation for a deployable NORTH instance.

Other modes: `--source` runs the full source suite without live host inspection; `--plan` prints the five current engineering readiness states quickly without running the regression; `--prepare` runs the complete read-only validation and then uses the existing `./goad.sh -t prepare-north -l NORTH -p vmware` CLI task to generate and register a single genuine NORTH instance **without starting guests or applying VMware networking**; `--deploy` is deliberately **blocked** pending runtime adapter and acceptance evidence. `--prepare` refuses a duplicate registered NORTH instance.

## Host integration now committed (not live-proven)

The reduced host setup is connected through the **existing** `scripts/setup-vmware-networks.sh --north apply` dispatcher. Its privileged adapter calls the existing file transaction and creates the exact NORTH helper/service/timer using exclusive ownership checks. The adapter requires an existing instance-provider directory and a manually reviewed baseline SHA-256, rechecks VM/route/VMX collisions under the vmnet transaction lock, writes durable VMware netmap recovery evidence, and fails closed on interrupted restarts or unowned assets.

The Python unit tests now inject VMware restart, partial systemd activation, failed commit, and foreign file edits entirely in temporary directories. `scripts/course1-rollout.sh --all` automatically discovers those tests. **No live VMware apply, systemd activation, first NORTH VM launch, or AD acceptance has been performed.** The current NORTH lifecycle guard remains in place.

When future live acceptance is authorized, its reviewed `--north apply` workflow must be performed on the intended clean Kali host with explicit privilege and reconciled instance identity. It is **not** automatically invoked by `--all`, and it must not be confused with `--deploy`, which is still blocked.

### VMware Workstation netmap compatibility

The original GOAD host setup handles `/etc/vmware/netmap.conf` as **optional**. NORTH's native apply adapter must do the same. An absent file is not a host failure and must never be manufactured just to satisfy an installer prerequisite. If present, it must be a safe regular file and its bytes are backed up; if absent, rollback tracks VMware-created netmap state and refuses unknown or externally modified state. Offline regression tests explicitly cover absent netmap, failed restart, generated-file rollback, foreign changes and symlinks. The host apply remains a separate, explicitly privileged action—never part of `--all` or `--prepare`.

## Installed NORTH post-network gate

After a successful privileged NORTH vmnet apply, use **one read-only command**
that deliberately replaces the clean-host preflight (which must fail once the
owned vmnets exist):

```bash
sudo -v
bash scripts/course1-rollout.sh --installed "$PWD/workspace/<existing-instance>/provider"
```

It discovers all existing Python unit tests and the NORTH/GOAD source checks,
then calls the root-owned committed transaction verifier through the **same
Kingdoms VMware setup script**. The verifier refuses another instance ID, a
modified or unowned VMware configuration, missing baseline backups, unresolved
journals, invalid .254 interfaces, or disabled/mismatched systemd assets. It
does not apply networking or start Vagrant. The original provider's NORTH
guard calls this same verifier using non-interactive `sudo -n` before any
Vagrant launch; operator sudo credentials must be primed. Full GOAD continues
through the existing native lifecycle unchanged.

This is a host setup acceptance check, **not** proof of AD, child trust,
MSSQL, or Phase 03 readiness. Start the **existing** prepared instance only
after the installed check returns green; do not create a second NORTH instance.

### Resolution: reuse full Kingdoms runtime checks without losing NORTH ownership

The first installed-NORTH diagnostic confirmed **[TOPOLOGY] PASS**: VMware
reordered the VNET declarations, removed optional .254 metadata, rotated
the existing vmnet1/vmnet8 DHCP_CFG_HASH tokens, and appended vmnet8 NAT
forwards to generated guest addresses. A strict full-file SHA check mistakenly
treated those normal runtime operations as an ownership violation.

The immutable owner record, original baseline backup and committed transaction
journal remain mandatory and are **never rewritten**. Verification reconstructs
the original installed bytes and checks their saved hash, then uses the
validated full-Kingdoms semantic vmnet policy with a strict NORTH allowlist:
declaration ordering, correct optional .254 metadata, and already-present
foreign DHCP hash rotation.

New Vagrant NAT forwarding is allowed only on baseline vmnet8, via TCP,
to guests inside vmnet8's original NAT subnet on ports 22, 5985 or 5986.
Every other added, deleted or modified directive, including isolation changes,
foreign subnet drift, unexpected NAT forwards, and duplicate host ports,
is rejected. Live .254 addresses and systemd repair assets must also pass.

Use the source-and-live-owner **--installed** gate for the existing provider
before retrying Ansible provisioning. The separate **--north diagnose** command
shows raw byte drift and can still exit 2 even when expected VMware changes
pass the installed semantic verification.
### First live NORTH bring-up: VMware configuration drift

On the first official NORTH install, the original Kingdoms provider successfully
created all five guests (including WS01) in approximately 25 minutes, then
stopped before Ansible provisioning because the root-owned network config SHA
no longer matched the hash recorded during host-network installation.

This is a **post-VM-start ownership attestation**, not evidence of failed guest
creation or an AD provisioning failure. Do not destroy the prepared NORTH
instance, rerun host-network apply, overwrite the owner record or skip the
guard. The network layer needs an actual byte-level diagnosis before deciding
whether VMware performed an expected normalization or introduced an unsafe
change.

A guarded read-only diagnostic is available through the *existing* setup
entrypoint:

```bash
sudo bash scripts/setup-vmware-networks.sh --north diagnose \
  --provider-dir "$PWD/workspace/ac9fda-north-vmware/provider"
```

It reconstructs the original committed config from the owned baseline backup,
compares the present bytes, prints the SHA-256 values, topology check and a
bounded diff. Exit 2 means drift was found and is **expected diagnostic output,
not authorization for reinstallation**. The fix must be implemented and tested
against those exact differences before resuming the existing instance's
provisioning.

### NORTH provisioning-route protocol alias after first VM bring-up

The first real NORTH retry brought all five previously-created VMs back
without duplication, then stopped on the single, **already-owned**
parent-domain route to 10.4.20.0/24 via 10.4.10.1 on vmnet10.
Read-only diagnostics showed ownership matched the selected instance,
but Linux route JSON presented protocol 186 as its registered name **bgp**.
The NORTH verifier compared that name directly to the string 186 and
mistook its own existing route for a foreign/overlapping route.

The same route source now uses **ip -j -N -4 route show table all**.
The iproute2 -N presentation flag requests numeric protocol IDs;
it performs no host writes. The existing ownership record, route
destination, gateway, interface, main-table and overlapping-route
checks are unchanged. Repeated enable is idempotent, and missing or
mismatched owner still blocks. Original full-Kingdoms route helpers
and Essos handling are untouched.

Post-fix read-only acceptance:

```bash
bash scripts/course1-rollout.sh --installed "$PWD/workspace/ac9fda-north-vmware/provider"
sudo bash scripts/provisioning-routes.sh --north status --provider-dir "$PWD/workspace/ac9fda-north-vmware/provider"
```

Expect route status OWNED while provision mode still retains the
temporary parent-route. This is not authorization to delete/recreate
routes manually or replace the owned route with another protocol.
### First NORTH Ansible run: reuse retained vulnerability files and resume

First live NORTH installation completed all four Windows VMware boots and
17 Ansible playbooks through the domain health stage. The next playbook,
`vulnerabilities.yml`, failed in the generic `vulns/files` role because it
constructed `../ad/NORTH/files/...`. All five referenced artifacts already
exist in the original Kingdoms repository under `ad/GOAD/files/`:
three DC02 PowerShell/SYSVOL scripts, SRV02 IIS `wwwroot` (including binaries),
and the Arya share letter. The scenario JSON is correct and unchanged.

The generic file role now selects `ad/GOAD/files` **only for NORTH**, just
as the existing vulnerabilities playbook selects retained GOAD PowerShell
scripts for NORTH. Other lab profiles retain their original relative paths.
The source preflight checks the role mapping and every declared retained file
or populated directory before Vagrant starts. No binaries are duplicated,
no VM is recreated, and no finished AD stages need to be replayed.

For a completed 17/21 partial provisioning state, use the native Ansible
`run_from` implementation through the guarded `resume-north` CLI. It primes
the existing 60-second sudo keepalive, checks the exact installed NORTH
network owner, uses the standard AD-aware provisioning network preparation,
then runs `vulnerabilities.yml`, `phase01.yml`, `ws01-lpe-install.yml`, and
`kingdoms-health-final.yml` in manifest order. The original provisioner
finalizes exercise isolation; READY is recorded **only on full success**.

After `--installed` source + live owner validation returns green:

```bash
./goad.sh -t resume-north -l NORTH -p vmware \
  -i ac9fda-north-vmware -r vulnerabilities.yml
```

This explicitly does **not** invoke Vagrant `up` or rebuild the two domains.
`-t install` would repeat earlier playbooks and is not the correct recovery
for a 17-playbook-complete fixture-copy failure.
## Batch Phase 03 prerequisite acceptance for installed NORTH

The first live NORTH installation completed, and Module 01, Module 02 and
the Phase 03 baseline checks returned **22/22**, **117/117** and **58/58**
respectively. Fresh RBCD and Shadow Credentials Ansible preflights also
confirmed clean WS01$ baseline attributes, the intended SELF privileges,
and WINTERFELL KDC certificate availability. Those are prerequisites, not
an executed attack path.

To avoid per-scenario terminal sessions, the repository now provides a
single **non-destructive** Phase 03 preflight runner for the installed
five-VM NORTH instance:

```bash
cd "$HOME/kingdoms-rebuild"
git pull --ff-only
sudo -v
bash scripts/course1-phase03-preflight.sh ac9fda-north-vmware
```

The runner checks exact instance ownership first; then Phase 03 baseline,
RBCD, Shadow Credentials, ADIDNS, WebDAV and WS01 RDP certificate state,
mitm6/WPAD tooling, and SMB/HTTP→LDAPS relay prerequisites. It reuses
existing original Kingdoms scripts or read-only Ansible playbooks but
forces `ad/NORTH/data/inventory` plus the current instance inventory.
Headless Rickon client checks are reported separately as optional local
configuration because private credential and certificate pin files are
intentionally not checked into Git. All logs and a `summary.txt` live
under `~/Kingdoms-evidence/phase03-batch-<timestamp>/` with owner-only
file modes. Every required stage must pass for `PHASE03_READONLY_ACCEPTANCE=PASS`.

No poisoning, outbound coerced authentication, relay session, AD mutation,
RBCD/Shadow proof, rollback or Windows service toggle runs in this audit.
`PHASE03_ATTACK_CHAIN_ACCEPTANCE=NOT_TESTED` remains explicit even on a
completely green preflight. Baseline-capture scripts that overwrite
local JSON snapshots and the old six-VM state-changing regression are
deliberately excluded. Runtime apply/prove/reset acceptance is a separate
future gate, not a claim made by the prerequisite runner.
## 2026-10-12 NORTH snapshot/start domain-time regression

After 11 required Phase 03 preflight gates passed (one optional Rickon
desktop-session warning), the operator invoked the native `snapshot`
operation. During its subsequent `start`, `GOAD-SRV02`/CASTELBLACK
authenticated to the domain but W32Time remained on `Local CMOS Clock`
instead of `winterfell.north.sevenkingdoms.local`. The existing bounded
NT5DS rediscover/resync was attempted once, but returned
`KINGDOMS_MEMBER_TIME_REPAIR_FAILED|stage=rediscover` with zero
command-level return codes and an unchanged clock source. The provider
correctly refused to certify restart readiness, and exercise isolation
restoration aborted during the SRV02 verification; the full post-failure
adapter/router state must therefore be audited, not assumed.

**Do not** retry snapshot/start/reset, force-enable NAT, replace secure
channel passwords or weaken the domain-time readiness gate until the
actual cause has been proven. The original read-only diagnostics for
CASTELBLACK, WINTERFELL and KINGSLANDING are reused through the
explicit NORTH inventory adapters and a one-command evidence collector:

```bash
cd "$HOME/kingdoms-rebuild" && git pull --ff-only
sudo -v
python3 -m unittest tests.test_course1_time_diagnostics
bash scripts/course1-diagnose-domain-time.sh ac9fda-north-vmware
```

This checks the current `lab-mode.sh status` router policy, protected
routes and persistent VM NIC settings, plus W32Time source/config/peers,
DC Locator TIMESERV/GTIMESERV, Netlogon secure channel, UDP/123
stripchart, event logs, and parent/child time advertising. Evidence stays
in owner-only `~/Kingdoms-evidence/north-domain-time-<timestamp>/` logs.
The diagnostic collector does not repair time, start/stop VMs or change
router/AD/VMware configuration. Its PASS indicates **evidence collection**
only, not restored domain-time readiness. Fix and regression must follow
the diagnostic evidence.

### First collected restart evidence (20261012-113745)

The operator uploaded all four diagnostic logs for the existing NORTH instance.
The collected state is **exercise mode**, protected host route **ABSENT**,
router forwarding **policy drop** with only DC01↔DC02 exception and
established flows, and all Windows ethernet0 adapters **persistent OFF**.
GOAD-DC01, GOAD-DC02 and GOAD-SRV02 remain powered on; GOAD-WS01 was
powered off when restart aborted. Status-collection PASS is not full
exercise-mode or startup readiness.

CASTELBLACK confirms DNS, domain secure channel, domain account
translation and Netlogon are healthy. W32Time runs with `Type=NT5DS`,
`ResolvePeerBackoffMinutes=1` and `ResolvePeerBackoffMaxTimes=0`,
but reports `Local CMOS Clock`, `LeapIndicator=3`, `Stratum=0` and
`LastSyncError=1`; its peer WINTERFELL is Active but stratum 0 from
this client's perspective. Two Event ID 24 warnings say the peer did
not respond after eight attempts. WINTERFELL independently advertises
TIMESERV and GTIMESERV, responds to NTP probes and synchronizes from
KINGSLANDING, stratum 2. WINTERFELL's W32Time NtpServer is enabled.

**Key diagnostic distinction:** `w32tm /stripchart` succeeded from
CASTELBLACK to WINTERFELL with ~5 ms offsets, but uses an *ephemeral
UDP source port*. The Windows Time synchronization client uses
*source UDP/123*, so stripchart is not proof that the native W32Time
port-specific path is permitted. Microsoft's Windows Time tools
documentation states this distinction explicitly:
https://learn.microsoft.com/en-us/windows-server/networking/windows-time-service/windows-time-service-tools-and-settings
The next discriminating check is a *passive* NTP capture on the NORTH
segment filtered to 10.4.10.22 ↔ 10.4.10.11 UDP/123 while waiting for
natural client polls. That can establish whether W32Time requests and
replies are visible from the host; if no frames are observed, VMware
virtual switching may prevent host observation and absence is not
proof that no traffic exists. Do not change W32Time, AD trust or router
policy before evidence distinguishes the source-port/firewall path.

The forest-root diagnostic reported dc01 unreachable over Kali WinRM
at 10.4.20.10:5986, consistent with the intentionally absent
protected host route. WINTERFELL independently confirmed healthy
KINGSLANDING time synchronization over the DC-to-DC router exception.
The forest-root diagnostic transport failure is not proof that
KINGSLANDING is damaged.

### Recovery checkpoint — subsequent installed NORTH start

After the failed snapshot-triggered cold start, the operator passively captured
one native NTPv3 request `10.4.10.22:123 -> 10.4.10.11:123` and its matching
server response in the opposite direction on `vmnet10`; both packets were
observed, zero kernel drops. This falsifies the initial simple UDP/123
connectivity-block hypothesis, **not** every possible packet-validation or
timing problem.

A later read-only `w32tm /query /source; /status; /peers` on CASTELBLACK
confirmed `winterfell.north.sevenkingdoms.local`, leap indicator `0`,
stratum `3`, reference IP `10.4.10.11` and active WINTERFELL peer.
No manual W32Time repair was applied after the passive capture.

The existing instance was recovered using **start**, not reinstall, reset
or snapshot. The screenshot showed all four Windows AD dependency contracts
proven, final exercise isolation clean, and
`GOAD_NOMAD: segmented lab started and readiness verified in 1m 41s
(mode: exercise)`.

**Release status:** existing deployment has recovered and is usable in
exercise mode. The earlier initial cold-start stall remains a **restart
reliability regression** until a clean repeated cold-start/restore
acceptance proves otherwise. Do not change domain trust, disable time
readiness checks, or claim the prior snapshot operation itself succeeded
without enumerating snapshots. First verify the snapshot actually exists
per VM, then investigate and test native W32Time cold-boot convergence.
This checkpoint does not certify the full Phase 03 active attack chain.

## Phase 03 active attack-chain acceptance — incremental promotion

The installed NORTH instance is now back in `exercise` mode. All five
VMware snapshot entries are present, but snapshot restoration and repeated
cold-start convergence are **not yet certified**. The first install recovered
after one SRV02 W32Time/NT5DS synchronization stall; keep this release
reliability defect open separately from Phase 03 vulnerability readiness.

The one-run read-only `scripts/course1-phase03-preflight.sh` passed with
**11 PASS, one Rickon interactive-desktop warning, zero FAIL**. This does
*not* imply successful poisoning or relay.

The original Kingdoms Phase 03 active scripts are powerful, but some still
hard-code GOAD inventories and depend on human-controlled foreground
listeners, locally retained passwords/certificates, or exact AD rollback
contexts. Running every script in a blind loop would risk partially
modified AD objects without verified cleanup. The NORTH acceptance suite
therefore promotes techniques **one atomic stage at a time**, while
reporting every unimplemented stage as `NOT_TESTED`.

`scripts/course1-phase03-acceptance.sh` initially supports:

- `<existing-instance> --plan`: no guest or host changes, prints scope.
- `<existing-instance> --run-http-ldaps --confirm`: reruns the existing
  NORTH-specific 11-gate prerequisite suite; verifies WS01 has no leftover
  HTTP callback scheduled task; runs the original mutation-disabled
  HTTP→LDAPS relay to WINTERFELL; triggers one WS01 LocalSystem callback;
  verifies successful `NORTH\\WS01# Course 1 — One-command rollout contract

## Accepted baseline

At commit `ecb2584`, the Kali operator validated the original unified source and clean-host command: **19/19 stages PASS, 477 tests PASS, 13 seconds**. This is a *read-only* milestone and is **not** installation authorization.

The full Kingdoms scenario (`GOAD`) is the implementation baseline. Course 1 (`NORTH`) removes Essos only, retaining KINGSLANDING, WINTERFELL, CASTELBLACK, WS01 and GOAD-ROUTER. The discarded experimental NORTH installer and its branch must not return.

## One operator entrypoint

```bash
cd "$HOME/kingdoms-rebuild"
git pull --ff-only
bash scripts/course1-rollout.sh
```

The default `--all` action runs the established `scripts/validate-course1.sh` suite, including dynamic discovery of every `tests/test_*.py`, both 10.4/10.5 topology variants, the original Kingdoms compatibility gate, and clean-host read-only checks. Then it reports *all five* release-engineering gates in one output. An unimplemented runtime gate produces a **nonzero exit status** by design; do not mistake 19/19 source validation for a deployable NORTH instance.

Other modes: `--source` runs the full source suite without live host inspection; `--plan` prints the five current engineering readiness states quickly without running the regression; `--prepare` runs the complete read-only validation and then uses the existing `./goad.sh -t prepare-north -l NORTH -p vmware` CLI task to generate and register a single genuine NORTH instance **without starting guests or applying VMware networking**; `--deploy` is deliberately **blocked** pending runtime adapter and acceptance evidence. `--prepare` refuses a duplicate registered NORTH instance.

## Host integration now committed (not live-proven)

The reduced host setup is connected through the **existing** `scripts/setup-vmware-networks.sh --north apply` dispatcher. Its privileged adapter calls the existing file transaction and creates the exact NORTH helper/service/timer using exclusive ownership checks. The adapter requires an existing instance-provider directory and a manually reviewed baseline SHA-256, rechecks VM/route/VMX collisions under the vmnet transaction lock, writes durable VMware netmap recovery evidence, and fails closed on interrupted restarts or unowned assets.

The Python unit tests now inject VMware restart, partial systemd activation, failed commit, and foreign file edits entirely in temporary directories. `scripts/course1-rollout.sh --all` automatically discovers those tests. **No live VMware apply, systemd activation, first NORTH VM launch, or AD acceptance has been performed.** The current NORTH lifecycle guard remains in place.

When future live acceptance is authorized, its reviewed `--north apply` workflow must be performed on the intended clean Kali host with explicit privilege and reconciled instance identity. It is **not** automatically invoked by `--all`, and it must not be confused with `--deploy`, which is still blocked.

### VMware Workstation netmap compatibility

The original GOAD host setup handles `/etc/vmware/netmap.conf` as **optional**. NORTH's native apply adapter must do the same. An absent file is not a host failure and must never be manufactured just to satisfy an installer prerequisite. If present, it must be a safe regular file and its bytes are backed up; if absent, rollback tracks VMware-created netmap state and refuses unknown or externally modified state. Offline regression tests explicitly cover absent netmap, failed restart, generated-file rollback, foreign changes and symlinks. The host apply remains a separate, explicitly privileged action—never part of `--all` or `--prepare`.

## Installed NORTH post-network gate

After a successful privileged NORTH vmnet apply, use **one read-only command**
that deliberately replaces the clean-host preflight (which must fail once the
owned vmnets exist):

```bash
sudo -v
bash scripts/course1-rollout.sh --installed "$PWD/workspace/<existing-instance>/provider"
```

It discovers all existing Python unit tests and the NORTH/GOAD source checks,
then calls the root-owned committed transaction verifier through the **same
Kingdoms VMware setup script**. The verifier refuses another instance ID, a
modified or unowned VMware configuration, missing baseline backups, unresolved
journals, invalid .254 interfaces, or disabled/mismatched systemd assets. It
does not apply networking or start Vagrant. The original provider's NORTH
guard calls this same verifier using non-interactive `sudo -n` before any
Vagrant launch; operator sudo credentials must be primed. Full GOAD continues
through the existing native lifecycle unchanged.

This is a host setup acceptance check, **not** proof of AD, child trust,
MSSQL, or Phase 03 readiness. Start the **existing** prepared instance only
after the installed check returns green; do not create a second NORTH instance.

### Resolution: reuse full Kingdoms runtime checks without losing NORTH ownership

The first installed-NORTH diagnostic confirmed **[TOPOLOGY] PASS**: VMware
reordered the VNET declarations, removed optional .254 metadata, rotated
the existing vmnet1/vmnet8 DHCP_CFG_HASH tokens, and appended vmnet8 NAT
forwards to generated guest addresses. A strict full-file SHA check mistakenly
treated those normal runtime operations as an ownership violation.

The immutable owner record, original baseline backup and committed transaction
journal remain mandatory and are **never rewritten**. Verification reconstructs
the original installed bytes and checks their saved hash, then uses the
validated full-Kingdoms semantic vmnet policy with a strict NORTH allowlist:
declaration ordering, correct optional .254 metadata, and already-present
foreign DHCP hash rotation.

New Vagrant NAT forwarding is allowed only on baseline vmnet8, via TCP,
to guests inside vmnet8's original NAT subnet on ports 22, 5985 or 5986.
Every other added, deleted or modified directive, including isolation changes,
foreign subnet drift, unexpected NAT forwards, and duplicate host ports,
is rejected. Live .254 addresses and systemd repair assets must also pass.

Use the source-and-live-owner **--installed** gate for the existing provider
before retrying Ansible provisioning. The separate **--north diagnose** command
shows raw byte drift and can still exit 2 even when expected VMware changes
pass the installed semantic verification.
### First live NORTH bring-up: VMware configuration drift

On the first official NORTH install, the original Kingdoms provider successfully
created all five guests (including WS01) in approximately 25 minutes, then
stopped before Ansible provisioning because the root-owned network config SHA
no longer matched the hash recorded during host-network installation.

This is a **post-VM-start ownership attestation**, not evidence of failed guest
creation or an AD provisioning failure. Do not destroy the prepared NORTH
instance, rerun host-network apply, overwrite the owner record or skip the
guard. The network layer needs an actual byte-level diagnosis before deciding
whether VMware performed an expected normalization or introduced an unsafe
change.

A guarded read-only diagnostic is available through the *existing* setup
entrypoint:

```bash
sudo bash scripts/setup-vmware-networks.sh --north diagnose \
  --provider-dir "$PWD/workspace/ac9fda-north-vmware/provider"
```

It reconstructs the original committed config from the owned baseline backup,
compares the present bytes, prints the SHA-256 values, topology check and a
bounded diff. Exit 2 means drift was found and is **expected diagnostic output,
not authorization for reinstallation**. The fix must be implemented and tested
against those exact differences before resuming the existing instance's
provisioning.

### NORTH provisioning-route protocol alias after first VM bring-up

The first real NORTH retry brought all five previously-created VMs back
without duplication, then stopped on the single, **already-owned**
parent-domain route to 10.4.20.0/24 via 10.4.10.1 on vmnet10.
Read-only diagnostics showed ownership matched the selected instance,
but Linux route JSON presented protocol 186 as its registered name **bgp**.
The NORTH verifier compared that name directly to the string 186 and
mistook its own existing route for a foreign/overlapping route.

The same route source now uses **ip -j -N -4 route show table all**.
The iproute2 -N presentation flag requests numeric protocol IDs;
it performs no host writes. The existing ownership record, route
destination, gateway, interface, main-table and overlapping-route
checks are unchanged. Repeated enable is idempotent, and missing or
mismatched owner still blocks. Original full-Kingdoms route helpers
and Essos handling are untouched.

Post-fix read-only acceptance:

```bash
bash scripts/course1-rollout.sh --installed "$PWD/workspace/ac9fda-north-vmware/provider"
sudo bash scripts/provisioning-routes.sh --north status --provider-dir "$PWD/workspace/ac9fda-north-vmware/provider"
```

Expect route status OWNED while provision mode still retains the
temporary parent-route. This is not authorization to delete/recreate
routes manually or replace the owned route with another protocol.
### First NORTH Ansible run: reuse retained vulnerability files and resume

First live NORTH installation completed all four Windows VMware boots and
17 Ansible playbooks through the domain health stage. The next playbook,
`vulnerabilities.yml`, failed in the generic `vulns/files` role because it
constructed `../ad/NORTH/files/...`. All five referenced artifacts already
exist in the original Kingdoms repository under `ad/GOAD/files/`:
three DC02 PowerShell/SYSVOL scripts, SRV02 IIS `wwwroot` (including binaries),
and the Arya share letter. The scenario JSON is correct and unchanged.

The generic file role now selects `ad/GOAD/files` **only for NORTH**, just
as the existing vulnerabilities playbook selects retained GOAD PowerShell
scripts for NORTH. Other lab profiles retain their original relative paths.
The source preflight checks the role mapping and every declared retained file
or populated directory before Vagrant starts. No binaries are duplicated,
no VM is recreated, and no finished AD stages need to be replayed.

For a completed 17/21 partial provisioning state, use the native Ansible
`run_from` implementation through the guarded `resume-north` CLI. It primes
the existing 60-second sudo keepalive, checks the exact installed NORTH
network owner, uses the standard AD-aware provisioning network preparation,
then runs `vulnerabilities.yml`, `phase01.yml`, `ws01-lpe-install.yml`, and
`kingdoms-health-final.yml` in manifest order. The original provisioner
finalizes exercise isolation; READY is recorded **only on full success**.

After `--installed` source + live owner validation returns green:

```bash
./goad.sh -t resume-north -l NORTH -p vmware \
  -i ac9fda-north-vmware -r vulnerabilities.yml
```

This explicitly does **not** invoke Vagrant `up` or rebuild the two domains.
`-t install` would repeat earlier playbooks and is not the correct recovery
for a 17-playbook-complete fixture-copy failure.
## Batch Phase 03 prerequisite acceptance for installed NORTH

The first live NORTH installation completed, and Module 01, Module 02 and
the Phase 03 baseline checks returned **22/22**, **117/117** and **58/58**
respectively. Fresh RBCD and Shadow Credentials Ansible preflights also
confirmed clean WS01$ baseline attributes, the intended SELF privileges,
and WINTERFELL KDC certificate availability. Those are prerequisites, not
an executed attack path.

To avoid per-scenario terminal sessions, the repository now provides a
single **non-destructive** Phase 03 preflight runner for the installed
five-VM NORTH instance:

```bash
cd "$HOME/kingdoms-rebuild"
git pull --ff-only
sudo -v
bash scripts/course1-phase03-preflight.sh ac9fda-north-vmware
```

The runner checks exact instance ownership first; then Phase 03 baseline,
RBCD, Shadow Credentials, ADIDNS, WebDAV and WS01 RDP certificate state,
mitm6/WPAD tooling, and SMB/HTTP→LDAPS relay prerequisites. It reuses
existing original Kingdoms scripts or read-only Ansible playbooks but
forces `ad/NORTH/data/inventory` plus the current instance inventory.
Headless Rickon client checks are reported separately as optional local
configuration because private credential and certificate pin files are
intentionally not checked into Git. All logs and a `summary.txt` live
under `~/Kingdoms-evidence/phase03-batch-<timestamp>/` with owner-only
file modes. Every required stage must pass for `PHASE03_READONLY_ACCEPTANCE=PASS`.

No poisoning, outbound coerced authentication, relay session, AD mutation,
RBCD/Shadow proof, rollback or Windows service toggle runs in this audit.
`PHASE03_ATTACK_CHAIN_ACCEPTANCE=NOT_TESTED` remains explicit even on a
completely green preflight. Baseline-capture scripts that overwrite
local JSON snapshots and the old six-VM state-changing regression are
deliberately excluded. Runtime apply/prove/reset acceptance is a separate
future gate, not a claim made by the prerequisite runner.
## 2026-10-12 NORTH snapshot/start domain-time regression

After 11 required Phase 03 preflight gates passed (one optional Rickon
desktop-session warning), the operator invoked the native `snapshot`
operation. During its subsequent `start`, `GOAD-SRV02`/CASTELBLACK
authenticated to the domain but W32Time remained on `Local CMOS Clock`
instead of `winterfell.north.sevenkingdoms.local`. The existing bounded
NT5DS rediscover/resync was attempted once, but returned
`KINGDOMS_MEMBER_TIME_REPAIR_FAILED|stage=rediscover` with zero
command-level return codes and an unchanged clock source. The provider
correctly refused to certify restart readiness, and exercise isolation
restoration aborted during the SRV02 verification; the full post-failure
adapter/router state must therefore be audited, not assumed.

**Do not** retry snapshot/start/reset, force-enable NAT, replace secure
channel passwords or weaken the domain-time readiness gate until the
actual cause has been proven. The original read-only diagnostics for
CASTELBLACK, WINTERFELL and KINGSLANDING are reused through the
explicit NORTH inventory adapters and a one-command evidence collector:

```bash
cd "$HOME/kingdoms-rebuild" && git pull --ff-only
sudo -v
python3 -m unittest tests.test_course1_time_diagnostics
bash scripts/course1-diagnose-domain-time.sh ac9fda-north-vmware
```

This checks the current `lab-mode.sh status` router policy, protected
routes and persistent VM NIC settings, plus W32Time source/config/peers,
DC Locator TIMESERV/GTIMESERV, Netlogon secure channel, UDP/123
stripchart, event logs, and parent/child time advertising. Evidence stays
in owner-only `~/Kingdoms-evidence/north-domain-time-<timestamp>/` logs.
The diagnostic collector does not repair time, start/stop VMs or change
router/AD/VMware configuration. Its PASS indicates **evidence collection**
only, not restored domain-time readiness. Fix and regression must follow
the diagnostic evidence.

### First collected restart evidence (20261012-113745)

The operator uploaded all four diagnostic logs for the existing NORTH instance.
The collected state is **exercise mode**, protected host route **ABSENT**,
router forwarding **policy drop** with only DC01↔DC02 exception and
established flows, and all Windows ethernet0 adapters **persistent OFF**.
GOAD-DC01, GOAD-DC02 and GOAD-SRV02 remain powered on; GOAD-WS01 was
powered off when restart aborted. Status-collection PASS is not full
exercise-mode or startup readiness.

CASTELBLACK confirms DNS, domain secure channel, domain account
translation and Netlogon are healthy. W32Time runs with `Type=NT5DS`,
`ResolvePeerBackoffMinutes=1` and `ResolvePeerBackoffMaxTimes=0`,
but reports `Local CMOS Clock`, `LeapIndicator=3`, `Stratum=0` and
`LastSyncError=1`; its peer WINTERFELL is Active but stratum 0 from
this client's perspective. Two Event ID 24 warnings say the peer did
not respond after eight attempts. WINTERFELL independently advertises
TIMESERV and GTIMESERV, responds to NTP probes and synchronizes from
KINGSLANDING, stratum 2. WINTERFELL's W32Time NtpServer is enabled.

**Key diagnostic distinction:** `w32tm /stripchart` succeeded from
CASTELBLACK to WINTERFELL with ~5 ms offsets, but uses an *ephemeral
UDP source port*. The Windows Time synchronization client uses
*source UDP/123*, so stripchart is not proof that the native W32Time
port-specific path is permitted. Microsoft's Windows Time tools
documentation states this distinction explicitly:
https://learn.microsoft.com/en-us/windows-server/networking/windows-time-service/windows-time-service-tools-and-settings
The next discriminating check is a *passive* NTP capture on the NORTH
segment filtered to 10.4.10.22 ↔ 10.4.10.11 UDP/123 while waiting for
natural client polls. That can establish whether W32Time requests and
replies are visible from the host; if no frames are observed, VMware
virtual switching may prevent host observation and absence is not
proof that no traffic exists. Do not change W32Time, AD trust or router
policy before evidence distinguishes the source-port/firewall path.

The forest-root diagnostic reported dc01 unreachable over Kali WinRM
at 10.4.20.10:5986, consistent with the intentionally absent
protected host route. WINTERFELL independently confirmed healthy
KINGSLANDING time synchronization over the DC-to-DC router exception.
The forest-root diagnostic transport failure is not proof that
KINGSLANDING is damaged.

### Recovery checkpoint — subsequent installed NORTH start

After the failed snapshot-triggered cold start, the operator passively captured
one native NTPv3 request `10.4.10.22:123 -> 10.4.10.11:123` and its matching
server response in the opposite direction on `vmnet10`; both packets were
observed, zero kernel drops. This falsifies the initial simple UDP/123
connectivity-block hypothesis, **not** every possible packet-validation or
timing problem.

A later read-only `w32tm /query /source; /status; /peers` on CASTELBLACK
confirmed `winterfell.north.sevenkingdoms.local`, leap indicator `0`,
stratum `3`, reference IP `10.4.10.11` and active WINTERFELL peer.
No manual W32Time repair was applied after the passive capture.

The existing instance was recovered using **start**, not reinstall, reset
or snapshot. The screenshot showed all four Windows AD dependency contracts
proven, final exercise isolation clean, and
`GOAD_NOMAD: segmented lab started and readiness verified in 1m 41s
(mode: exercise)`.

**Release status:** existing deployment has recovered and is usable in
exercise mode. The earlier initial cold-start stall remains a **restart
reliability regression** until a clean repeated cold-start/restore
acceptance proves otherwise. Do not change domain trust, disable time
readiness checks, or claim the prior snapshot operation itself succeeded
without enumerating snapshots. First verify the snapshot actually exists
per VM, then investigate and test native W32Time cold-boot convergence.
This checkpoint does not certify the full Phase 03 active attack chain.

 LDAPS authentication and read-only
  privilege enumeration; then stops **only that relay**, independently
  verifies callback-task absence, checks that no relay listener remains,
  and reports complete/failed evidence to a private directory.

The listener is restricted to `ldaps://10.4.10.11`; the retained
`ntlmrelayx` launcher uses `--no-dump --no-da --no-acl` and disables
non-required listeners. The temporary callback playbook uses a PowerShell
`finally` clause to remove its own scheduled task. The new runner also
runs listener stop and independent cleanup audits on failed stages and
signals. If cleanup cannot be independently proven, it exits failed and
blocks progression. Its listener `WORK` is isolated to a new mode-0700
evidence directory, so an older relay log is never overwritten.

The callback and read-only cleanup wrappers were updated to accept
`KINGDOMS_PHASE03_DATA_INVENTORY` and
`KINGDOMS_PHASE03_PROVIDER_INVENTORY` while retaining their original
GOAD defaults. The runner pins them to the exact installed NORTH inventory.

Run source tests first, then explicitly opt into the active stage:

```bash
cd "$HOME/kingdoms-rebuild"
git pull --ff-only
python3 -m unittest tests.test_phase03_overlay_source
bash scripts/course1-phase03-acceptance.sh ac9fda-north-vmware --plan
sudo -v
bash scripts/course1-phase03-acceptance.sh ac9fda-north-vmware --run-http-ldaps --confirm
```

A successful active stage reports
`PHASE03_HTTP_LDAPS_ACTIVE_ACCEPTANCE=PASS` and **still**
`PHASE03_FULL_ATTACK_ACCEPTANCE=NOT_TESTED`. Other techniques remain
pending until their **apply → consequence → rollback → neutral-state**
contracts are adapted to NORTH and verified. Raw relay logs and any
secret-bearing evidence stay owner-only under
`~/Kingdoms-evidence/phase03-active-<timestamp>/`, never in GitHub.

## Five contracts before enabling deployment

1. **VMware host networking**: connect `execute_testable_network_transaction()` to reviewed stop/restart/live-verification callbacks, with exact installed-VM and registered-VMX exclusion, reviewed baseline SHA-256, ownership, durable global lock, journal, and recovery of both `/etc/vmware/networking` and VMware-generated netmap state. A failure must restore only owned bytes and must not silently overwrite other clients' changes. Disposable Kali acceptance is mandatory.
2. **Persistent NORTH .254 interfaces**: install the already rendered helper, oneshot service and timer through an ownership-aware systemd transaction. Require vmnet10 and vmnet99 at .254/24, vmnet20 hidden, no foreign IPv4 bindings, no overwrites of unrelated helpers/units, and cleanup/rollback on failure.
3. **Native Kingdoms provider**: replace the GOAD-only hardcoding in existing segmented provider/lifecycle entrypoints with per-instance NORTH profile input *without* a second provider or generic Vagrant fallback. Preserve pre-AD bootstrap, serialized DC/member startup, time/secure-channel readiness, bounded Windows recovery, fail-closed exercise NAT isolation, clean stop/reset, and the six-host GOAD regression. The `_course1_unwired()` guard remains until every path is covered.
4. **Unified source plus runtime validation**: expand the one-command suite with offline failure injection and a controlled, separate live disposable-host acceptance. Tests must prove rollback on partial VMware restart, journal interruption, concurrent edits, asset ownership collisions, and provider profile dispatch. Do not place live VM/host mutations inside routine unit tests.
5. **First NORTH deployment acceptance**: only after the first four gates pass, run one deliberate operator-authorized installation using the original `./goad.sh` path, verify parent/child AD, DNS, NT5DS, member joins, retained MSSQL/Phase 01/Phase 03 fixtures, router isolation and absent NAT in exercise mode, then test stop/start/reset and measure runtime. Failures are evidence, not permission to suppress guards.

## Current truthful state

The current `course1-rollout.sh` is a **source-controlled orchestrator and hard safety gate**, not a live installer. A separately guarded `--north apply` path exists through the original network setup script, but has not received Kali live acceptance. It provides one operator command and reports the remaining implementation blockers together. Creating VMs and modifying VMware/systemd are not available in this revision. The next work must land as reviewed source and focused tests before changing its `--deploy` behavior.

Never ask the operator to apply quick local changes outside GitHub or run five separate isolated test scripts. Git commit -> push -> Kali pull -> one-command validation is the established workflow.
