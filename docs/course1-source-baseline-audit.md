# Course 1 — Source Baseline Audit

Status: **source review complete; no Course 1 VMs installed or source deployment modifications yet**.

## Authoritative starting point

Course 1 **Fall of the North** must derive from Kingdoms `main` and
`ad/GOAD`. The `rebuild/course1-from-kingdoms` branch was created
directly from that base. The discarded `feature/course1-reduced-profile-source`
branch has been deleted by the operator and must not be resurrected or copied.

Source-derived finding: the original setup is **not** a generic, topology-
agnostic GOAD installation. It is a proven GOAD_NOMAD/Kingdoms segmented
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
   The GOAD sequence includes child-domain creation, member joins, time,
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

1. Add **one new profile definition**, tentatively `ad/NORTH` (Course 1),
   by pruning a source copy of `ad/GOAD` without altering GOAD or
   importing anything from the deleted experimental branch.
2. Add one corresponding `NORTH` playbook manifest reproducing the
   **GOAD Kingdoms sequence**, but with Essos-only activities omitted
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
6. Prove both full GOAD baseline and reduced Course 1 contracts offline
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
