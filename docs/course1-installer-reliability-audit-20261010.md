# NORTH Course 1 — first-install/retry reliability audit (2026-10-10)

**Status:** GitHub source corrections committed; new live retry NOT YET VALIDATED.
This record is for the disposable NORTH instance `6ca91b-north-vmware`.
All source changes are committed on `feature/course1-reduced-profile-source`;
do not modify Kali source files manually or mutate the reference GOAD lab.

## Evidence-driven failures (not speculative)

1. Initial disposable provider bring-up completed (router and four Windows
   Vagrant creation; 18m35s). Router management SSH, vmnet11/13 .254 addresses,
   source binding and foreign VMX collision gates passed. DC01's initial Vagrant
   guest-communication race recovered through the bounded VMware/WinRM path.
2. Ansible stopped BEFORE its first playbook: the shared Ansible install-profile
   selector excluded NORTH and dispatched the already-installed mode controller,
   which waited 300 seconds for unpromoted forest-root DC01. Fixed earlier by
   selecting the exact, successful instance-bound NORTH first-install profile
   and using `prepare_provisioning()`'s pre-AD management path.
3. Ansible failure left `10.41.20.0/24 via 10.41.10.1 dev vmnet11` on the
   host. On retry, NORTH's route helper treated that displayed route as
   foreign because it compared the entire, potentially annotated iproute2
   **human-formatted line** as one exact string; enabling AND cleanup refused.
4. This audit changes NORTH-only route identity to the structured
   `ip -j -4 route show exact` model. One exact, unicast, main-table
   `10.41.20.0/24` via `10.41.10.1` on `vmnet11` is recognized as owned,
   even with harmless protocol/metric annotations. Absent routes can be
   installed with `ip route add` (not overwrite/`replace`), and only the
   verified route may be deleted. Unknown, malformed, multiple, off-interface,
   wrong-gateway and foreign-table routes remain blocked.
5. A failed NORTH full Ansible install now attempts route removal plus restrictive
   router forwarding without invoking DC-Locator-dependent installed-lab mode
   transitions. **This is partial compensating cleanup, NOT proof of full
   Windows NAT/exercise isolation.** The instance remains NOT READY.
6. If a pending NORTH first-install profile fails its authorization,
   successful-provider or instance checks, Ansible now refuses it explicitly
   instead of silently entering the AD-aware mode controller and waiting for
   an unpromoted DC01. An already-installed/normal run has no such pending
   first-install profile and retains its standard lifecycle.
7. The unified read-only readiness command, when explicitly scoped to a
   verified NORTH provider directory, probes the real parent-route state.
   It reports a foreign/unverifiable route BEFORE suggesting another retry.

## Reference parity and bounded differences

| Layer | Established Kingdoms behavior | NORTH adaptation / audit conclusion |
| --- | --- | --- |
| VMware guest lifecycle | hardened Windows recovery, VMware Tools and WinRM checks | inherited; first live provider bring-up succeeded |
| Guest roster | six Windows plus Debian router | four Windows plus router; selected instance is mandatory |
| Host networking | vmnet10/20/30/99, existing reference .254 addresses | isolated vmnet11/12/13, vmnet11/13 .254; no reference mutations |
| Router startup | management SSH and host-address repair | inherited checks with NORTH management IP 10.41.99.1; live passed |
| Provisioning host routes | GOAD helper replaces routes, later removes before exercise | NORTH helper must enforce ownership and safe re-entry; corrected |
| First Ansible handoff | source-marked pre-AD bootstrap | NORTH now admitted only for exact pilot and current successful attempt |
| AD roles | shared parent/child and member playbooks | lab-specific inventory/data selected; actual domain promotion untested |
| DC/time readiness | AD/DC Locator and child hierarchy before isolation | NORTH DC01 and DC02 map to forest root/child; live promotion untested |
| Final isolation | router restrictive policy, route cleanup, NAT persistent off | correctly scoped arrays/policies; full runtime execution not yet proven |
| Other attacks | source SQL/Phase 01/Phase 03 fixtures | require post-install live behavioral acceptance |

## Remaining P0/P1 checks (not permission to bypass)

- **P0:** Kali executes *both* targeted route/handoff/abort regression and
  the complete scoped source+VMware readiness. Report actual route state.
- **P0:** Verify the previously created instance is loaded and source-bound
  before retrying `install --non-interactive`. Never create a second instance
  to conceal the failed attempt.
- **P0:** Confirm router/Windows provider readiness then observe the
  `fresh install bootstrap before AD exists` message and first actual playbook.
- **P0:** Prove parent DC01 AD, child DC02 creation, trust/DNS/DC Locator
  and forest-root/child time order before member joins.
- **P0:** Prove final exercise mode: parent host route absent, router policy
  restrictive, Windows NAT startConnected FALSE and runtime disconnected,
  then exact four-host AD readiness. A failed playbook is NEVER a ready lab.
- **P1:** Validate SQL Server and Phase 03 fixtures (including L2 poison/relay,
  Windows/WS01 interactions). Source-level checks cannot prove these.
- **P1:** The post-deployment survey observed four owned VMX identities.
  The scoped survey now reports the verified and unobserved guest **names**
  without guessing why. Inspect which of the five is missing before declaring
  provider coverage complete; do not auto-register or clone any missing guest.
- **P1:** Test interruption/retry, idempotent start/stop, and measured startup
  time only after the initial successful AD installation.

## Two independent review passes required

1. **Source/parity audit**: inspect NORTH route helper against established
   reference helper, provider startup, Ansible pre-AD selector, mode controller,
   reference VMX/network protections, and parent/child playbook selection.
   Check code for no reference-path changes.
2. **Behavioral regression audit**: route state fixtures (owned, absent,
   annotations, foreign, malformed), sandboxed shell enable/disable with
   fake `ip` commands, NORTH-only failed-Ansible cleanup with no AD wait,
   Python/Bash/Ansible parsing and complete host/collision checks.

The second pass must be executed on Kali against the committed SHA; this
document deliberately does not claim it has already passed.

## Next operator test — no VMware mutation

```bash
cd "$HOME/kingdoms-course1-src" && git pull --ff-only &&
python3 -m unittest tests.test_course1_route_state tests.test_course1_bound_lifecycle &&
bash scripts/course1/check-install-readiness.sh --refresh \
  --instance-provider "$HOME/kingdoms-course1-src/workspace/6ca91b-north-vmware/provider"
```

A final `RESULT: NOT INSTALLABLE YET` from the dashboard is expected until
live AD and exercise isolation acceptance; the command must nevertheless
report all source regressions, host/network/foreign collision gates, and
the NORTH route classification as passing. If the route remains classified
foreign, STOP and inspect its raw structured evidence; never delete it by hand.
