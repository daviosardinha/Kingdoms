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
## Five contracts before enabling deployment

1. **VMware host networking**: connect `execute_testable_network_transaction()` to reviewed stop/restart/live-verification callbacks, with exact installed-VM and registered-VMX exclusion, reviewed baseline SHA-256, ownership, durable global lock, journal, and recovery of both `/etc/vmware/networking` and VMware-generated netmap state. A failure must restore only owned bytes and must not silently overwrite other clients' changes. Disposable Kali acceptance is mandatory.
2. **Persistent NORTH .254 interfaces**: install the already rendered helper, oneshot service and timer through an ownership-aware systemd transaction. Require vmnet10 and vmnet99 at .254/24, vmnet20 hidden, no foreign IPv4 bindings, no overwrites of unrelated helpers/units, and cleanup/rollback on failure.
3. **Native Kingdoms provider**: replace the GOAD-only hardcoding in existing segmented provider/lifecycle entrypoints with per-instance NORTH profile input *without* a second provider or generic Vagrant fallback. Preserve pre-AD bootstrap, serialized DC/member startup, time/secure-channel readiness, bounded Windows recovery, fail-closed exercise NAT isolation, clean stop/reset, and the six-host GOAD regression. The `_course1_unwired()` guard remains until every path is covered.
4. **Unified source plus runtime validation**: expand the one-command suite with offline failure injection and a controlled, separate live disposable-host acceptance. Tests must prove rollback on partial VMware restart, journal interruption, concurrent edits, asset ownership collisions, and provider profile dispatch. Do not place live VM/host mutations inside routine unit tests.
5. **First NORTH deployment acceptance**: only after the first four gates pass, run one deliberate operator-authorized installation using the original `./goad.sh` path, verify parent/child AD, DNS, NT5DS, member joins, retained MSSQL/Phase 01/Phase 03 fixtures, router isolation and absent NAT in exercise mode, then test stop/start/reset and measure runtime. Failures are evidence, not permission to suppress guards.

## Current truthful state

The current `course1-rollout.sh` is a **source-controlled orchestrator and hard safety gate**, not a live installer. A separately guarded `--north apply` path exists through the original network setup script, but has not received Kali live acceptance. It provides one operator command and reports the remaining implementation blockers together. Creating VMs and modifying VMware/systemd are not available in this revision. The next work must land as reviewed source and focused tests before changing its `--deploy` behavior.

Never ask the operator to apply quick local changes outside GitHub or run five separate isolated test scripts. Git commit -> push -> Kali pull -> one-command validation is the established workflow.
