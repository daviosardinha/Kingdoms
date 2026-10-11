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
