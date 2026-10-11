# Course 1 — Source Baseline Audit

Status: **source review complete; no Course 1 VMs installed or source deployment modifications yet**.

## Authoritative starting point

**Kingdoms is the sole product and engineering baseline. We are NOT rebuilding from upstream GOAD.** Course 1 **Fall of the North** derives from the validated Kingdoms `main` codebase, including its hardened VMware/Vagrant provider, AD provisioning, exercise isolation, lifecycle, Windows workstation and security fixtures. The current Kingdoms repository happens to store its original full scenario under the legacy path `ad/GOAD`; that directory is *Kingdoms-owned scenario data*, not a request to use a separate upstream GOAD checkout. The `rebuild/course1-from-kingdoms` branch was created directly from **Kingdoms `main`**. The discarded `feature/course1-reduced-profile-source`
branch has been deleted by the operator and must not be resurrected or copied.

Source-derived finding: the validated **Kingdoms** setup is **not** a generic, topology-
agnostic GOAD installation. It is a proven Kingdoms segmented
VMware implementation containing hard-coded six-Windows, four-segment
contracts. Keep its mechanisms, but parameterize the input data that those
mechanisms currently assume.

This audit is grounded in current Kingdoms `main` repository source,
not inferred from a fresh successful live installation of Course 1.

## Actual deployment flow and ownership

1. `goad/lab_manager.py` and `goad/instance.py` create an instance from
   the `ad/<LAB>/data` and `ad/<LAB>/providers/vmware` templates.
   The instance generation already supplies `ip_range` to Jinja.
2. `goad/provider/provider_factory.py` dispatches VMware to the existing
   `ProfiledGoadKingdomsVmwareProvider`, which subclasses
   `GoadKingdomsVmwareProvider` → `GoadNomadVmwareProvider` →
   `VmwareProvider` → `VagrantProvider`. **No new provider class.**
3. The segmented install uses the host-network verifier/setup scripts,
   deterministic Vagrant VMX/WinRM lifecycle, router-first boot, and temporary
   provisioning routes; these are already supported for `lab_name == GOAD`.
4. `goad/provisioner/ansible/ansible.py` follows `playbooks.yml`.
   The **Kingdoms GOAD-profile sequence** includes child-domain creation, member joins, time,
   AD data, WS01 baseline, ADCS, services, security, Phase 01, LPE, and
   health gates. A plain `default` playbook sequence is **not** equivalent.
5. On success, provider finalization re-enters **exercise mode**; the existing
   `scripts/lab-mode.sh`, router nftables rules and NAT disconnection
   enforce exercise isolation. Start, stop and reset follow the existing
   hardened Kingdoms provider lifecycle. These must survive reduction.

## Inventory to KEEP unchanged in meaning

| Guest | Name | Domain | Default address | VMware lab vmnet |
| --- | --- | --- | --- | --- |
| GOAD-DC01 | KINGSLANDING | sevenkingdoms.local | 10.4.20.10 | vmnet20 |
| GOAD-DC02 | WINTERFELL | north.sevenkingdoms.local | 10.4.10.11 | vmnet10 |
| GOAD-SRV02 | CASTELBLACK | north.sevenkingdoms.local | 10.4.10.22 | vmnet10 |
| GOAD-WS01 | WS01 | north.sevenkingdoms.local | 10.4.10.31 | vmnet10 |
| GOAD-ROUTER | Debian routing plane | — | 10.4.10.1, 10.4.20.1, 10.4.99.1 | vmnet10/20/99 |

Remove from the **new Course 1 profile only**: GOAD-DC03, GOAD-SRV03,
`essos.local` and vmnet30. Original `ad/GOAD` is read-only baseline.

## Verified Essos references beyond guest definitions

After removing `lab.hosts.dc03`, `lab.hosts.srv03` and
`lab.domains.essos.local` from the Course 1 profile, the original
`ad/GOAD/data/config.json` still retains exactly these named
Essos dependencies:

- `lab.hosts.srv02.mssql.linked_servers.BRAAVOS`, including
  `data_src=braavos.essos.local`.
- `lab.domains.sevenkingdoms.local.trust=essos.local`.
- `lab.domains.sevenkingdoms.local.multi_domain_groups_member.AcrossTheNarrowSea`
  referencing an `essos.local` principal.

The `ad/GOAD/data/inventory` groups also reference deleted machines
and services: `domain`, `dc`, `server`, `parent_dc`, `trust`,
`adcs`, `adcs_customtemplates`, `mssql`, `webdav`, `laps_dc`,
`laps_server`, `no_update`, `defender_on`, etc. Resolve each group
consistently in the new profile. The other unchanged host security
fixtures still require a separate dependency check before promotion.

## Hard-coded lifecycle/network coupling (minimum refactor targets)

| Existing source | Assumption to remove **for Course 1 only** |
| --- | --- |
| `goad/provider/vagrant/vmware.py` | Explicit six-Windows `goad_nomad_windows` roster |
| `goad/provider/vagrant/vmware_nomad.py` | Only `GOAD` activates segmented lifecycle; fixed IP mapping and four network zones; router policy path anchored to `ad/GOAD` |
| `goad/provider/vagrant/vmware_kingdoms.py` | `GOAD` gating; six-host Vagrant bring-up/readiness/stop/reset; GOAD-specific inventory synchronization and WS01 fixed IP |
| `goad/provider/vagrant/vmware_kingdoms_profile.py` | Keep existing installation timing wrapper unchanged as much as possible |
| `scripts/lab-mode.sh` | Fixed six Windows, three DCs and Essos domain/member identity and ordering |
| `scripts/setup-vmware-networks.sh` + `check-vmware-networks.sh` | Fixed vmnet10/20/30/99, 10.4 IPs, host .254 addresses, helper/timer |
| `scripts/provisioning-routes.sh` | Installs/removes 10.4.20 and 10.4.30 routes via fixed NORTH router |
| `scripts/check-vmware-instance-conflicts.sh` | MAC identities and VMX source from `ad/GOAD` |
| `ad/GOAD/providers/vmware/router/provision.sh` + nftables policies | Four interfaces and Essos-only DC/DNS/SQL forwarding rules |
| `playbooks.yml` and `ansible/phase01.yml` | GOAD-specific pipeline and Phase 01 explicit `domain_name == GOAD` / GOAD config lookup |
| `goad/settings.py` + `goad/instances.py` | GOAD segmented scope displayed as fixed 10.4.0.0/16 |
| `ad/GOAD/providers/vmware/Vagrantfile` | Fixed IPs, vmnet IDs and deterministic MACs across all guests |

The provider already has bounded Vagrant recovery, authenticated WinRM
readiness, AD/time gates and rollback behavior. **Reuse these** and change
only the roster/topology inputs. Never reimplement child promotion,
Windows NIC discovery or NAT handling as separate Course 1 roles.

## Network parameter contract

At default network base **10.4.0.0/16**:

- NORTH: `10.4.10.0/24`; guest DC02 .11, SRV02 .22, WS01 .31;
  router .1, host .254 on the lab-visible vmnet.
- SEVENKINGDOMS: `10.4.20.0/24`; DC01 .10, router .1; **no direct
  Kali host-side adapter** (protects pivoting).
- MANAGEMENT: `10.4.99.0/24`; router .1 and host .254.
- No Essos VLAN or guest.

A user-selected base **10.5.0.0/16** maps those same third/fourth
octets to 10.5.10/20/99. The existing GOAD `ip_range` field denotes
*three octets for flat-network templates*; it is **not** an implemented
segmented /16 override. Introduce one validated, instance-scoped
segment-base parameter rather than pretending current `set_ip_range`
already controls this topology.

Same-host concurrent labs require independent VMware vmnet IDs, IP/CIDRs,
VM MAC addresses, router policy, DNS authority and source binding.
A unique /16 alone does **not** isolate a lab if both attach to the same
vmnet10/20/99. Allocations must be validated before writing system-wide
VMware networking or starting Vagrant. Do not let VMware NAT's DNS resolve
an already installed forest with identical AD FQDNs.

## Approved minimal engineering approach

1. Add **one new profile definition**, `ad/NORTH` (Course 1),
   by reducing the **Kingdoms-owned** legacy scenario at `ad/GOAD` without altering its full Kingdoms profile or
   importing anything from the deleted experimental branch.
2. Add one corresponding `NORTH` playbook manifest reproducing the
   **validated Kingdoms provisioning sequence**, but with Essos-only activities omitted
   and data file selection bound to the current profile. Never silently
   fall back to `default`.
3. Make the **existing** VMware provider derive its guest roster,
   network/IP mapping, router template and lifecycle checks from the
   selected lab profile. Preserve exact GOAD six-host behavior.
   No separate NORTH provider, alternative installer or new recovery stack.
4. Make prefix + vmnet assignment instance-scoped and validate collision
   ownership, MAC and FQDN authority **before** creating or starting VMs.
5. Implement fast, source-only checks for unresolved inventory/deleted
   host references, playbook prerequisites, unrendered Jinja values,
   networking conflict and output consistency before long Ansible runs.
6. Prove both the full **Kingdoms** baseline and reduced Course 1 contracts offline
   before performing a single fresh live Course 1 install on clean Kali.
   Validate DCs, members, attack paths, routing, NAT isolation,
   start/stop/reset and measured timings before calling it complete.

## Specific anti-regression constraints

- No mutation of the working `ad/GOAD`, its existing six-host scenario,
  or VMware/Goad shared defaults merely to make NORTH pass.
- Do not introduce `run_once` NIC facts as an assumption for every Windows
  host. The discarded NORTH failed at precisely this boundary.
- Do not run AD installation into a forest found on any non-instance DNS
  resolver. Reject cross-instance DC Locator answers.
- No live Vagrant/Ansible run until static inventory, isolation and
  profile-routing checks are green.
- The course content and attack fixtures should be kept in scope; the
  Essos linked-server challenge necessarily disappears with Essos, but
  the retained CASTELBLACK SQL exercises must still function.

**Acceptance gate currently OPEN:** source-design phase only. No Course 1
installation or provisioning changes have been made by this audit.

## Implementation checkpoint — reduced profile source created

The first new, **source-only** Course 1 profile now exists at `ad/NORTH`.
It was derived exclusively from **Kingdoms `main`** (using its internal legacy `ad/GOAD` scenario data), not from upstream GOAD or the deleted experimental feature branch, and contains:

- Four retained Windows hosts plus router in the VMware Vagrantfile.
- Two retained AD domain definitions and pruned domain/provider inventories.
- A three-segment Debian router bootstrap and original policy style,
  retaining only North-to-parent DC forwarding in exercise mode.
- CASTELBLACK SQL link to BRAAVOS, parent Essos trust, cross-forest group
  member, and KINGSLANDING `sidhistory.ps1` (which actually runs
  `netdom trust ... /d:essos.local`) removed from Course 1.
- Original **Kingdoms-owned** PowerShell scripts referenced from the existing
  `ansible/vulnerabilities.yml` for `domain_name == NORTH`;
  GOAD still uses its original per-lab script directory unchanged.
  No cloned/offshoot lesson script implementations.

`tests/test_course1_minimal_profile_source.py` contains nine focused
source regressions verifying the exact **Kingdoms-minus-Essos** data delta,
inventories, Vagrant roster, router policy, source scripts and original
GOAD preservation. A separate static GitHub source pass verified eleven
required files and source invariants.

**IMPORTANT: NOT YET INSTALLABLE.** This source profile is intentionally
not wired to a `NORTH:` playbook manifest. The existing segmented
provider still contains six-host/GOAD-name/10.4-network assumptions.
Next gate: adapt the **existing provider** to profile-driven input and
create a `NORTH:` manifest based on the GOAD sequence, then validate
all templates and lifecycle behavior offline before ever starting Vagrant.
Do not invoke `./goad.sh` to install NORTH until that stage passes.

## Implementation checkpoint — original Kingdoms provider receives Course 1 topology inputs

We added `ad/NORTH/topology.json`, a **single declarative planning
source** for the four existing Windows guests and three retained routing
segments, and the read-only `goad/kingdoms_topology.py` resolver. It
derives the exact guest/gateway/host addresses and VMware vmnet mapping
for default `10.4.0.0/16`; an explicit custom allocation can preview
`10.5.0.0/16`, e.g.:

```bash
python3 -m goad.kingdoms_topology
python3 -m goad.kingdoms_topology --network-base 10.5.0.0/16 \
  --vmnet north=11 --vmnet sevenkingdoms=21 --vmnet management=98
```

The **existing** `GoadNomadVmwareProvider` constructor loads this
profile **only when `lab_name == NORTH`**, initializing per-instance
four-host roster, management IP map, and network-zone metadata.
The GOAD/Kingdoms full-lab class defaults are not mutated and retain the
original six-host/four-zone behavior. No new VMware provider class,
installer, NIC handler, or lifecycle framework was introduced.

Importantly, this is still **source and provider-metadata integration**
rather than end-to-end deployment readiness. The existing networking
helpers, Vagrant template, router scripts, route operations, lifecycle
program and Windows Ansible group references are not yet parameterized
from this model for all network bases. To prevent accidental 30-minute
failures, `GoadKingdomsVmwareProvider` temporarily **refuses NORTH
install/start/guest start/reset/prepare_install/Ansible provisioning**
before any Vagrant or Windows action. The full Kingdoms profile remains
operational via the unchanged runtime paths.

The reduced Vagrant router slot definition was also corrected to have
exactly three lab NIC PCI-slot assignments (Essos' fourth has gone).

Regression sources added:
- `tests/test_course1_topology.py`: ten pure topology /16, alternate
  prefix, address, protection and vmnet identity tests.
- `tests/test_course1_provider_guard.py`: five class-level tests for
  original six-host preservation, reduced instance roster and blocked
  incomplete NORTH lifecycle.

**Required next work:** render selected network settings into Vagrant,
both Ansible inventories, VMnet preflight/setup, router bootstrap,
network routes, nftables policies, MAC identity, and lifecycle scripts;
wire a Course 1 playbook manifest retaining the exact Kingdoms
provisioning cadence; run the full existing Kingdoms regression suite.
Only after all these gates pass may the temporary Course 1 install guard
be removed. Until then, never attempt a live NORTH install.

A source-level connector comparison verified that removing the new
`GoadNomadVmwareProvider.__init__` constructor and its new resolver import
leaves the **entire original provider source byte-identical to Kingdoms
`main`**. Thus GOAD behavior was not refactored as part of this step.
The three dedicated Course 1 test modules now contain **24 tests**.
Kali runtime test execution is pending; an offline source check is not
a claim that the provider is installation-ready.

## 2026-10-11 — successful Kali source checks; new render/preflight gates

Kali proved **58 passing tests**, valid Ruby Vagrantfile syntax and a
read-only `10.5.0.0/16` alternate topology preview. This does **not**
prove VM/AD deployment readiness.

Subsequent source review found two errors and fixed them before install:
the Course 1 `[trust]` inventory group improperly retained DC01 even
though Essos trust was removed; post-Vagrant inventory lacked a
connection definition for WS01. Both corrections are committed.

The **read-only** `goad.course1_source_preflight` now rejects broken
domain/trust/inventory references, missing retained Kingdoms scripts,
and Vagrant/router/firewall inconsistencies; its six regression tests
cover both successful and deliberately broken fixtures.

The **in-memory only** `goad.course1_artifact_render` uses the single
`ad/NORTH/topology.json` model to render five mutually consistent
VMware/Ansible/router/firewall artifacts, preserves default 10.4 text,
and derives alternate 10.X subnet/vmnet/MAC assignments without
writing files. Six new tests cover byte-identical default output,
10.5 artifact agreement, seven MAC identities and unsafe allocations.
The topology resolver now forbids reusing any default Kingdoms vmnet
IDs for a nondefault /16.

**NEXT GATE**: The 12 newly added regressions and both read-only tools
have not yet been executed on Kali. Their success will validate source
rendering only. The existing Kingdoms instance generator, host vmnet
services, provisioning routes and lifecycle still need to consume the
rendered artifacts. The explicit NORTH install/start guard remains in
place and must **not** be removed yet.

## 2026-10-11 — Kali 70/70 source acceptance; existing instance generator integration

Kali screenshot verified **70 tests passed in 0.342s**. The source
preflight produced five PASS messages, including exact AD/inventory
membership and Vagrant/router topology. The standalone renderer
produced five artifact PASS messages for the alternate
`10.5.0.0/16` example. **No VMs or host VMware networks were modified.**

The NEXT integration step is now committed into
`goad/instance.py`, the **existing Kingdoms `LabInstance` creator**:

- Source integrity and default topology rendering are checked **before**
  the first instance workspace directory is created.
- New NORTH instances normalize the legacy default flat setting
  `192.168.56` into `10.4.0` instance metadata. The full GOAD/
  Kingdoms instance configuration is unchanged.
- Exactly the canonical five artifacts feed the existing generated
  Vagrantfile, provider inventory, post-Vagrant inventory, and
  instance-scoped router bootstrap/exercise nft policy. The Vagrantfile
  refers to its new local `router/provision.sh`, not the global source
  path, so a future selected network is instance-bound.
- Only the NORTH+VMware branch uses the new render path; all other labs
  keep the original template/instance generation unchanged.
- A nondefault `10.5.0` or other alternate `ip_range` currently
  **fails BEFORE workspace creation**, because instance-scoped vmnet ID
  persistence, source route policies and collision gates are not yet
  installed. The 10.5 offline preview is still supported but is NOT
  yet install enabled.
- The full Kingdoms VMware Jinja template condition is broadened from
  `GOAD` to `GOAD` or `NORTH`, preserving all GOAD output while making
  NORTH use the already hardened WinRM/VMrun and bounded halt behavior.
- Existing `goad/instances.py` now displays NORTH as segmented /16
  instead of misleading flat /24, while preserving full GOAD display.

Eight new `tests/test_course1_instance_generation.py` cases validate
default/alternate instance metadata, failure before directory creation,
four-host generated Vagrant/inventory/router consistency, inherited
Kingdoms hardened Jinja output, and both network-scope displays.

**Acceptance stage: source-only integration.** The new eight tests have
not yet run on Kali. Neither the shared Kingdoms vmnet-creation scripts,
runtime routing, installed lifecycle controller nor the NORTH Ansible
playbook sequence consumes the selected renderer output end-to-end yet.
The `_course1_unwired` NORTH install/start/reset/Ansible guard remains
active, and no deployment should be attempted. The host owner should
run the new tests before the next wiring phase.

## 2026-10-11 — Kali 78/78 source acceptance; explicit NORTH Ansible cadence

Operator's Kali screenshot confirms **78 tests passed** after the existing
`LabInstance` generator was connected to the source-only NORTH
Vagrant/Ansible/router renderer. This accepted the previous source
integration, not a live installation.

The next committed source-only step adds `NORTH:` to the **existing
Kingdoms `playbooks.yml`**. Its sequence is the validated 22-play full
Kingdoms `GOAD:` manifest in identical order **minus exactly the
external Essos `ad-trusts.yml` step**, leaving 21 existing Kingdoms
plays, including child-domain creation, WS01 baseline, Phase 01,
Windows LPE and final AD-health gate. No new Ansible role tree or
upstream GOAD installation path was introduced.

`ansible/phase01.yml` now accepts only `GOAD` or `NORTH` and
reads `../ad/{{ domain_name }}/data/config.json`, so it uses the
selected Kingdoms-owned scenario rather than accidentally importing
the six-host profile. GOAD's path resolves identically to before.

The `goad/course1_source_preflight.py` gate now validates the explicit
NORTH playbook mapping, its exact ordering and every referenced file
BEFORE creating an instance workspace. The original
`goad/provisioner/ansible/ansible.py` selector is also protected:
NORTH **cannot silently fall back to `default`**, skip a missing
playbook or run with an empty/nonmapping manifest. All other labs
retain the prior selection behavior.

Tests updated:
- `tests/test_course1_source_preflight.py` now contains nine tests,
  including missing NORTH stanza, missing referenced playbook and
  accidentally restored Essos trust.
- `tests/test_course1_ansible_manifest.py` adds five tests for the
  exact reduced 21-play cadence, original GOAD preservation,
  absence of default fallback and explicit Phase 01 data selection.

**NEW TESTS PENDING ON KALI**. This is not permission to install NORTH:
the existing Kingdoms host networking, provisioning route controller,
AD/exercise lifecycle and vmnet ownership preflight still hardcode
the full six-host topology. The NORTH fail-closed install guard
remains active. Next integrate those runtime components before
running a single controlled first install.

## 2026-10-11 — Kali 86-test run identified only two broken test fixtures

Operator ran the 86 selected source/regression tests after adding the
explicit NORTH Kingdoms Ansible manifest. Result: **86 run, two failures**,
both in `tests.test_course1_source_preflight`:

- `test_playbook_manifest_missing_blocks_before_vagrant` attempted
  to match the literal backslash-n characters `NORTH:\\n` instead of
  a Python string containing the actual newline. The assertion failed
  before calling the preflight under test.
- `test_external_trust_play_is_rejected_for_course1` used the same
  double-escaped `NORTH:\\n` in `partition`, leading to an empty
  separator and assertion failure, before the trust-rejection check.

Commit `ef2ab744ae1cd4f1f96dd3ee28b5d1d5ef8d343a` replaced only
those negative-fixture literals (including the injected
`ad-trusts.yml` newline) with correctly escaped Python newline
sequences. No Kingdoms engine, production preflight, Ansible manifest,
virtual network or deployment behavior was modified by this fix.

**Acceptance is pending a new Kali test run.** Expected 86/86,
then rerun `python3 -m goad.course1_source_preflight`.
The temporary NORTH install/lifecycle guard remains active. Do not
start Vagrant or Ansible until runtime network/lifecycle integration
is separately completed and validated.

## 2026-10-11 — 86/86 accepted; read-only live host ownership preflight

The user's Kali terminal confirms **86 tests PASS** in 0.485s and
all **six** `python3 -m goad.course1_source_preflight` proofs PASS.
This closes the exact 21-play NORTH manifest/source-fixture checkpoint.
Neither Vagrant, Windows provisioning nor host network setup was run.

Subsequent inspection of the existing Kingdoms networking/lifecycle
sources confirms `scripts/setup-vmware-networks.sh` and
`scripts/check-vmware-networks.sh` still hard-code
vmnet10/20/**30**/99; `scripts/provisioning-routes.sh` still
adds both the Seven Kingdoms route AND the removed Essos route;
`scripts/lab-mode.sh` still requires all six Windows machines
and Essos; the original `GoadKingdomsVmwareProvider` currently retains
the intentional Course 1 install guard. These are not safe to run
unmodified for NORTH.

The **read-only** `goad/course1_network_preflight.py` adds a
separate source-derived host ownership gate. It validates exact
requested vmnet numbers against `/etc/vmware/networking` and live
Linux interfaces, refuses overlapping host IPv4 addresses/routes,
requires zero running VMware guests AND no VMware GUI/VMX process,
and inspects every registered existing VMware VMX for requested
vmnet and deterministic MAC conflicts. Missing/unreadable registered
VMX and unavailable host-inspection commands block the operation
instead of silently assuming safety. It does not write files,
change routes, start guests, or call VMware host setup.

Run from an otherwise idle Kali host after source tests:
```bash
python3 -m unittest tests.test_course1_network_preflight
python3 -m goad.course1_network_preflight
```

The fourteen new tests in `tests/test_course1_network_preflight.py`
cover absence/presence of vmnets, host IPs, overlapping routes,
VMX ID/MAC collisions and process failures.

**NOT YET LIVE VALIDATED**; running the preflight is safe but does not
authorize installation. Other collision classes (unregistered VMX,
DNS/DC Locator authority, VMware MAC ownership across Vagrant caches)
and the actual source-driven host vmnet setup/route/lifecycle binding
still require controlled validation before removing the install guard.
The full Kingdoms GOAD network scripts were not modified in this step.

## 2026-10-11 — existing Kingdoms provisioning route now supports NORTH ownership

Following the operator's 86/86 PASS source validation, the
`scripts/provisioning-routes.sh` original full-Kingdoms code was
retained **byte-for-byte** behind an explicit `--north` dispatcher.
For the original GOAD/full Kingdoms profile, both temporary protected
routes remain unchanged; no Essos behavior is altered.

The **same existing route entrypoint** now delegates
`--north plan|status|enable|disable` to the small
`goad/course1_routes.py` profile-specific controller, which uses the
authoritative `ad/NORTH/topology.json`. Default NORTH creates only
`10.4.20.0/24 via 10.4.10.1 dev vmnet10`: it never creates the
retired Essos route `10.4.30.0/24`. An alternate layout changes both
the protected subnet and vmnet from the same resolved topology.

For actual enable/disable, it requires root and an exact provider
directory. Each new kernel route is tagged with protocol 186, and its
provider identity + exact route are recorded in root-owned, mode-0600
`/run/kingdoms-course1-routes/<hash>.json`; a missing or foreign state
record prohibits deletion of any existing route. The controller
uses the structured Linux route table to reject overlap/foreign route
ownership; it refuses missing NORTH host-adapter identity, a
nonresponding router gateway, stale state, or unexpected collisions,
and never calls `ip route replace`. On a state-record write failure,
it attempts rollback of only the newly added exact route.

The **existing** `GoadNomadVmwareProvider._enable_provisioning_routes`
now dispatches NORTH with
`sudo -n bash scripts/provisioning-routes.sh --north enable --provider-dir
<exact instance provider>`. Full Kingdoms continues to execute the
unchanged `sudo bash provisioning-routes.sh enable` command.

New offline tests:
- `tests/test_course1_routes.py`: 12 cases for exact one-route
  topology, alternate 10.5, foreign/VPN route refusal, missing/stale
  ownership, idempotence, safe remove and explicit Bash dispatch.
- `tests/test_course1_provider_route_dispatch.py`: three tests
  confirming the NORTH-specific provider command and byte-preserved
  full Kingdoms command path.
- The preceding `tests/test_course1_network_preflight.py` provides
  14 additional read-only host ownership tests.

**Kali acceptance pending** for the 29 newly written tests. Read-only
route preview:
```bash
bash scripts/provisioning-routes.sh --north plan
```

**Still explicitly NOT installable:** the physical VMware host vmnet setup,
router exercise-mode lifecycle and final source/instance network collision
contracts are not wired. The `_course1_unwired` gate continues to deny
NORTH Vagrant/Ansible/start/reset. Never execute `--north enable`
or `--north disable` against the host until the runtime integration
is fully validated.

## 2026-10-11 — Kali NORTH route-tests fixture correction (awaiting rerun)

Kali pulled the instance-owned provisioning-route integration and ran the
29 selected route/network tests. **28 passed; one failed**:
`test_bash_script_dispatches_only_for_explicit_north` in
`tests/test_course1_routes.py`. The failure was caused by a bad test
literal asserting that shell code contained a literal backslash before
`\${1:-}`; the actual Bash script correctly uses `${1:-}`.
The same assertion also incorrectly looked for a backslash before
`${ESSOS_NET}` in the original full-Kingdoms route code.

Commit `4adb144a3730c39878fc7ab4199ce6ada02571e3` changed ONLY
those two test strings. Verified against GitHub source: both corrected
test literals match the Bash source; no production code, network
configuration, routes or guests were changed. **Kali confirmation
pending**: rerun the 29 tests, `bash -n` and read-only NORTH route
`plan` before proceeding to host-vmnet/exercise-lifecycle work.
The NORTH install/start guard remains in effect.

## 2026-10-11 — Kali 29/29 route acceptance; additive NORTH VMware network plan

Kali screenshot confirms **29/29 route/network-preflight/provider-dispatch
tests PASS** in 0.021 seconds. The read-only shared Kingdoms
`scripts/provisioning-routes.sh --north plan` confirms exactly
`10.4.20.0/24 via 10.4.10.1 dev vmnet10`, host address
`10.4.10.254/24`, and Linux protocol 186. This does **not** mean the
route has been installed.

The next source-only checkpoint extends the **existing** Kingdoms
`scripts/setup-vmware-networks.sh` and
`scripts/check-vmware-networks.sh` with an explicit `--north`
dispatcher. Source comparison against Kingdoms `main` confirms the
original full-lab setup and check script bodies remain **byte-for-byte
identical** after the dispatcher.

`goad/course1_vmnet_config.py` is a pure, read-only planner, using
`ad/NORTH/topology.json` for three requested host-side vmnets only:

- vmnet10 North `10.4.10.0/24`: host-visible .254, DHCP/NAT off
- vmnet20 Seven Kingdoms `10.4.20.0/24`: NO host adapter, DHCP/NAT off
- vmnet99 Management `10.4.99.0/24`: host-visible .254, DHCP/NAT off

It preserves every line of the existing VMware networking file,
appending only the three Course 1 segments. It rejects any requested
vmnet ID already configured, foreign VMware subnet overlaps, malformed
subnets, or an exposed Seven Kingdoms host adapter. The same model can
**preview** alternate 10.X ranges with distinct vmnet numbers.
The `--north check` command validates only the config-level desired
state (exact DHCP, NAT, subnet, netmask and host-adapter policy) and
does NOT assert the live Linux interfaces or persistence service exists.

**Only these commands are implemented and safe to run now:**

```bash
python3 -m unittest tests.test_course1_vmnet_config
bash -n scripts/setup-vmware-networks.sh
bash -n scripts/check-vmware-networks.sh
bash scripts/setup-vmware-networks.sh --north plan
python3 -m goad.course1_network_preflight
```

The new regression module has **16 tests**, not yet executed on Kali.
`scripts/check-vmware-networks.sh --north` should be used **only
after** managed vmnets have been installed; a missing configuration
is expected to block now.

**No mutating NORTH vmnet setup action is enabled yet**: the next
engineering gate must implement owned-only changes, exact VMware
config backup/atomic apply/restart verification, address-persistence
service and rollback without corrupting foreign networks. The full
Kingdoms setup remains available through the unchanged legacy path,
and the NORTH Vagrant/Ansible/install/start/reset guard remains active.
Exercise-mode lifecycle is also still pending.

## 2026-10-11 — vmnet 45-test run stopped at test-module syntax error

The operator pulled the three-vmnet planning changes and attempted the
45-test network/route suite. `unittest` stopped during **module import**
with `SyntaxError: unterminated string literal` at
`tests/test_course1_vmnet_config.py` line 138. No tests ran: this is
a damaged generated test file, not a VMware configuration failure.
The committed file contained a truncated
`test_original_kingdoms_check_script_preserved_with_explicit_north`
assertion, followed by duplicated and mispositioned test code/footer.

Commit `8c77e6caf11768dea2afb1d75d6b21c09500c7b5` restored the
tail from that test method onward. The file now has exactly **16 test
methods** and one normal module footer. The repaired fragment's
Python AST was independently checked, but the **complete 45-test run
is not yet confirmed on Kali**. No production source, VMware networking,
route or systemd behavior changed in this corrective commit.

Before retrying the suite, compile both new modules to catch syntax
problems without executing tests:
```bash
python3 -m py_compile tests/test_course1_vmnet_config.py goad/course1_vmnet_config.py
```
Continue with the same non-mutating 45-test validation and
`--north plan` plus read-only ownership preflight after compile passes.
NORTH installation remains blocked.

## 2026-10-11 — Kali 45/45 vmnet planning + ownership preflight accepted; transaction staging

The operator's Kali terminal confirms **45 tests passed** and the
read-only `scripts/setup-vmware-networks.sh --north plan` generated
the intended three segments under `10.4.0.0/16`: North vmnet10
(`10.4.10.0/24`, host .254), Seven Kingdoms vmnet20
(`10.4.20.0/24`, no host adapter), and Management vmnet99
(`10.4.99.0/24`, host .254), DHCP/NAT disabled for all. The
`goad.course1_network_preflight` verified no running VMware process/
guest, no requested vmnet reuse or host subnet/route collision and no
conflicting registered VMX adapters or MAC identities. **No networks were
created** by this acceptance run.

The next source-only stage is committed:
- `goad/course1_vmnet_transaction.py` implements callback-driven,
  **offline-testable** atomic configuration replacement. It requires
  an existing absolute instance provider directory for ownership,
  verifies the reviewed SHA-256 baseline, refuses symlinks/hardlinks,
  writes a permanent backup before replacing a file, preserves
  mode/ownership, and records the owner and exact network layout
  *only after* injected restart/live-verification callbacks succeed.
  Failed callback execution rolls back when (and only when) the active
  configuration still matches the proposed bytes; a third-party edit
  results in a fail-closed error with backup preserved rather than
  overwriting their changes.
- Nine `tests/test_course1_vmnet_transaction.py` tests exercise a
  temporary directory instead of `/etc/vmware`: success, wrong
  plan hash, failed restart, failed live validation, concurrent edit,
  existing ownership, missing provider, symlinked config, and
  disabled live CLI.
- `goad/course1_vmnet_config.py` now honors existing VMware
  `HOSTONLY_NETMASK` when determining subnet overlap, rather than
  assuming all foreign VMware networks are /24; two additional
  tests cover a foreign /16 overlap and duplicate netmask.
- Existing full-Kingdoms VMware network setup/check script bodies
  were compared against `main` and remain **byte-for-byte preserved**.
  The explicit `--north plan` and `--north check` branches remain
  read-only. NORTH install/start/reset guard still refuses deployment.

**The new selected test target is 56 tests; Kali run is pending.**
Run the regression suite and a read-only host preflight. Importantly,
the transactional layer **has no host-applying CLI**. It has not yet
been wired to VMware stop/start, the exact in-use `/etc/vmware`
files, `netmap.conf` rollback, systemd .254 address persistence or
cross-process transaction lock. Those are required before explicitly
enabling a controlled network-creation action. This stage does not
authorize a NORTH lab installation.

## 2026-10-11 — 56/56 Kali transaction tests passed; NORTH .254 address persistence

Kali screenshot confirms **56 selected tests PASS** and all five
read-only live host ownership checks PASS. Three planned North/
Seven Kingdoms/Management vmnets remain unused on that host. No
VMware vmnets, host routes, or systemd services were installed.

New source-only work: goad/course1_hostaddrs.py derives exactly two
host-visible .254/24 interfaces from the selected NORTH topology
(vmnet10 and vmnet99), and requires protected parent vmnet20 to
remain absent on Kali. The repair plan allows only the .254/24
owned address or VMware's known .1/24 replacement, checks BOTH
interfaces for unrecognized addresses before proposing any change,
and never calls ip addr flush. It generates a NORTH-only helper,
oneshot systemd service and recurring 15-second timer definition
that do not replace the existing full-Kingdoms host-address service.

The same source module provides a read-only live iproute2 JSON
inspector that rejects missing .254/24, unexpected .1 addresses and
an exposed parent-domain interface. Both hooks now use the existing
Kingdoms script entrypoints, without changing full-Kingdoms behavior:

    bash scripts/setup-vmware-networks.sh --north hostaddr-plan
    bash scripts/check-vmware-networks.sh --north --live

The live check is **expected to refuse until the networks exist**;
it must not be treated as a prerequisite on a still-clean host.
Alternative 10.5 configurations also produce coherent read-only
unit previews when given explicit independent vmnet assignments.

Seventeen newly added tests in tests/test_course1_hostaddrs.py cover
normal/different network layouts, .1 recovery, foreign IP refusal,
the hidden parent adapter, Bash helper syntax, service/timer
rendering, the read-only live command and default/alternate previews.

**Kali execution of these 17 new tests remains pending**. Source-level
comparison confirms original full Kingdoms network setup and check
script bodies remain unchanged; the NORTH install/start/reset guard
remains enabled. No mutating NORTH network action exists yet. Before
authorizing one, we still need crash-safe ownership lock/journal,
owned VMware restart/netmap recovery, service/timer transactional
materialization, multi-instance NORTH service identities and
disposable-host rollback validation.

## 2026-10-11 — 73/73 host-address tests accepted; crash recovery staged

The user's Kali screenshot confirms **73/73 tests passed**, and the
read-only default NORTH host-address preview showed the two precise
host-visible interfaces vmnet10=10.4.10.254/24 and
vmnet99=10.4.99.254/24, with only VMware's known .1/24 as a repair
candidate. Seven Kingdoms vmnet20 remains hidden. No systemd units
or vmnets were installed by this verification.

The next code-only stage adds goad/course1_vmnet_journal.py and
integrates it into the existing goad/course1_vmnet_transaction.py.
A stable inode at backup_root/.north-network.lock is protected by
nonblocking fcntl flock; every transaction requires this lock throughout
its baseline recheck, atomic file replacement, supplied VMware restart,
and supplied validation callback. A locked/untrustworthy inode refuses
a second transaction rather than guessing ownership.

A 0700 transaction backup directory now contains a durable,
atomic journal.json file. Stages are PREPARED (written before any
networking file change), WRITTEN, VERIFYING, COMMITTED, ROLLED_BACK,
or MANUAL_RECONCILIATION. Interrupted stages block future attempts
until reviewed; a fully journaled rollback permits a clean retry.
An unexpected concurrent edit preserves the original backup and
marks manual reconciliation instead of overwriting it. The owner
record is bound to the selected instance provider and only written
after supplied live verification passes.

New offline tests: 9 in tests/test_course1_vmnet_journal.py;
the existing transaction module now has 11 tests (2 extra).
This brings the focused source network+route+hostaddr+transaction
target from **73 to 84 tests**. All simulate file changes in temporary
directories. The original full Kingdoms setup source remains intact.

**The 84 tests have not yet run on Kali**. The transaction still has no
live host-applying entrypoint: VMware restart/netmap recovery, managed
systemd asset installation, active VMX ownership recheck and exercise
lifecycle must be bound and accepted before an install action exists.
The NORTH install/start/reset guard remains active.
