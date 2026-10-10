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

## Second live resume: Windows Vagrant host-vmnet drift (2026-10-10)

The preserved NORTH instance resumed with all existing VMX files. GOAD-WS01
was previously powered off but had a valid Vagrant VMX ID. Its subsequent
`vagrant up GOAD-WS01` completed, with VMware Tools and WinRM healthy at
`10.41.10.31`. VMware then left `vmnet11` configured as
`10.41.10.1/24` instead of NORTH's required `10.41.10.254/24`.
The provisioning-route helper correctly refused to proceed. Rollback reported
`host owns NORTH router gateway 10.41.99.1`, consistent with management
vmnet13 having been reassigned to VMware's .1 address as well. The cleanup
failure was **reported**, not ignored; do not claim exercise isolation from it.

**Root cause in shared Kingdoms lifecycle:** the instance-bound NORTH
host-address service was invoked immediately after router bring-up, but
the subsequent Windows Vagrant operations can independently recreate the
host vmnet adapters. The provider was missing a Windows post-Vagrant
reconciliation boundary, not an Ansible/WinRM dependency. The original
reference GOAD recovery path remains unchanged.

**Source correction:** the NORTH provider now performs a read-only
`kingdoms-north-vmnet-hostaddrs status` after EACH Windows `vagrant up`
and after bounded guest recovery, before proceeding to the next guest.
Only on drift, with the original exact-instance collision guard and cached
sudo authorization still valid, it restarts
`kingdoms-north-vmnet-hostaddrs.service` and verifies status again.
The established helper only repairs vmnet11 and vmnet13 from allowed .1/absent
states to their expected .254; it refuses unexpected addresses, missing
reference .254, or host presence on isolated vmnet12. NORTH route enable
and router policy application independently require the same reconciliation,
including during compensating failure rollback. No runtime changes are made
by Git pull or the offline tests.

**Boundaries to keep:** do not restart all VMware networking, modify
`/etc/vmware/networking`, power off any reference guest, alter vmnet10/20/30/99,
or manually add/delete host routes. The installer must report fail-closed
if reconciliation cannot establish the exact expected host addresses.

**Initial-retry preflight:** the failed run already left the host with
VMware's `.1` addresses. The native NORTH `prepare_install()` now runs the
same guarded reconciliation AFTER instance source/VMX collision checks and
cached sudo, but BEFORE the inherited preflight demands `.254`. Without this
additional boundary, every subsequent retry would fail before the new
post-Windows hooks could run. GOAD's preflight behavior is unchanged.

**New acceptance gate, in safe order:** First run all offline source
regressions, including `tests.test_course1_north_vmnet_reconciliation`
(preflight, post-Windows, policy/route, rollback cases) and
`tests.test_course1_bound_lifecycle`. Do NOT demand a green live-host
readiness survey while the last failed Vagrant boot has left vmnet11/13
at VMware's `.1` address: the survey must fail closed until repaired.
Next, after operator review, enter the already-authorized native NORTH
installation path and observe its instance-bound preflight restoring
`.254` BEFORE any Vagrant up. Only AFTER that succeeds, repeat the
full instance-scoped host readiness and continue with AD/Ansible/exercise
acceptance. Source tests do NOT prove live repair or isolation.

## Offline regression discovery correction

Kali on `9fad91d` confirmed 55/55 targeted lifecycle/VMnet tests and
355/355 tests in the canonical `validate-course1.sh` suite. On review, the
explicit test list unintentionally OMITTED two independently exercised
modules: `tests.test_course1_north_vmnet_reconciliation` (14 cases) and
`tests.test_course1_route_state` (6 cases). Both are now included in the
canonical offline suite, alongside a discovery-contract regression that
requires these safety modules exactly once. The new full-suite expected count
is 376, subject to Kali execution. No VM/host runtime changes were made.
An offline `validate-course1.sh` success does NOT certify the live host while
vmnet11/13 remain at VMware's `.1` addresses.

## Child-domain promotion collision evidence (2026-10-10)

During the first live NORTH AD configuration, `KINGSLANDING` reports
`sevenkingdoms.local` and `DomainRole=5` while NORTH's `WINTERFELL`
remains `WORKGROUP`, `DomainRole=2`. Child-domain DNS-zone validation
failed after `Install-ADDSDomain` was attempted and dc02 rebooted.

A collected `C:\\Windows\\debug\\DCPromoUI.log` tail shows a
`DsGetDcName` lookup for `north.sevenkingdoms.local` resolving
`winterfell.north.sevenkingdoms.local` at **10.4.10.11**, the reference
Kingdoms DC, not disposable NORTH's **10.41.10.11**. The log reports
"the name north.sevenkingdoms.local is already in use" (exit code 31).
The exact log entry's modification timestamp and applicability to the
current PowerShell `Install-ADDSDomain` attempt are NOT YET PROVEN.

**Likely root class:** DNS/DC Locator cross-instance discovery of an
identically named forest/child domain during concurrent reference/NORTH
provisioning. Different vmnets, MAC collision protection and per-instance
Vagrant identities do not themselves guarantee forest/DNS isolation.
The role points the child exercise NIC at parent `dc01` but only disables
DNS *registration* on its provisioning NAT NIC; that does not prove Windows
will never use that NIC's resolver or cached foreign DC Locator answers.

**No runtime changes yet.** Before repairing, capture read-only evidence
on NORTH dc02: DNS client servers by interface, current forced DC Locator
result, authoritative SRV lookup explicitly against new parent DC01
`10.41.20.10`, route to `10.4.10.11`, and DCPromoUI file modification
time. Verify source of foreign discovery and parent forest identity.
Prevent unwanted reference DC discovery, rather than deleting the reference
domain, renaming course assets without a plan, or blindly retrying promotion.

**Source correctness debt:** the shared child-domain role sets
`$Ansible.Changed = $true` before proving `Install-ADDSDomain`
succeeded, calls `-SkipPreChecks`, and checks child DNS-zone existence
rather than AD promotion success after reboot. Follow-up correction must
be **NORTH-scoped** or carefully preserve established GOAD behavior:
reject unexpected AD/DC Locator endpoints, fail fast on promotion failure,
verify actual post-reboot domain role/services before DNS-zone checks,
and provide a negative test against reference `10.4.10.11`. Do not certify
a cause or a fix until live observations confirm it.
