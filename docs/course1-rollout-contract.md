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

Other modes: `--source` runs the full source suite without live host inspection; `--plan` prints the five current engineering readiness states quickly without running the regression; `--deploy` is deliberately **blocked** pending runtime adapter and acceptance evidence.

## Five contracts before enabling deployment

1. **VMware host networking**: connect `execute_testable_network_transaction()` to reviewed stop/restart/live-verification callbacks, with exact installed-VM and registered-VMX exclusion, reviewed baseline SHA-256, ownership, durable global lock, journal, and recovery of both `/etc/vmware/networking` and VMware-generated netmap state. A failure must restore only owned bytes and must not silently overwrite other clients' changes. Disposable Kali acceptance is mandatory.
2. **Persistent NORTH .254 interfaces**: install the already rendered helper, oneshot service and timer through an ownership-aware systemd transaction. Require vmnet10 and vmnet99 at .254/24, vmnet20 hidden, no foreign IPv4 bindings, no overwrites of unrelated helpers/units, and cleanup/rollback on failure.
3. **Native Kingdoms provider**: replace the GOAD-only hardcoding in existing segmented provider/lifecycle entrypoints with per-instance NORTH profile input *without* a second provider or generic Vagrant fallback. Preserve pre-AD bootstrap, serialized DC/member startup, time/secure-channel readiness, bounded Windows recovery, fail-closed exercise NAT isolation, clean stop/reset, and the six-host GOAD regression. The `_course1_unwired()` guard remains until every path is covered.
4. **Unified source plus runtime validation**: expand the one-command suite with offline failure injection and a controlled, separate live disposable-host acceptance. Tests must prove rollback on partial VMware restart, journal interruption, concurrent edits, asset ownership collisions, and provider profile dispatch. Do not place live VM/host mutations inside routine unit tests.
5. **First NORTH deployment acceptance**: only after the first four gates pass, run one deliberate operator-authorized installation using the original `./goad.sh` path, verify parent/child AD, DNS, NT5DS, member joins, retained MSSQL/Phase 01/Phase 03 fixtures, router isolation and absent NAT in exercise mode, then test stop/start/reset and measure runtime. Failures are evidence, not permission to suppress guards.

## Current truthful state

The current `course1-rollout.sh` is a **source-controlled orchestrator and hard safety gate**, not a live installer. It provides one operator command and reports the remaining implementation blockers together. Creating VMs and modifying VMware/systemd are not available in this revision. The next work must land as reviewed source and focused tests before changing its `--deploy` behavior.

Never ask the operator to apply quick local changes outside GitHub or run five separate isolated test scripts. Git commit -> push -> Kali pull -> one-command validation is the established workflow.
