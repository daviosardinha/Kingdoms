# Course 1 — Fall of the North: minimal Kingdoms rebuild contract

**Authoritative baseline:** `main` at
`a482992dc967124558a6d38c19488b0a8e89f437`.
The abandoned `feature/course1-reduced-profile-source` implementation is
**not** a base, dependency, or allowed source of copied deployment logic.
This branch was created **directly from main**.

## Intent

Course 1 is the working Kingdoms/GOAD_NOMAD deployment **minus Essos**,
not a separate provider, installer, VMnet controller, Ansible fork, or
lifecycle framework. Retain the same VMware Vagrant provisioning engine,
Ansible role sequence, installed-lab exercise isolation, restart/reset,
management-plane behavior, and security fixtures that work for Kingdoms.

## Lab definition (four Windows + original Debian router)

| Original VM | Host | Domain | Default IPv4 |
| --- | --- | --- | --- |
| GOAD-DC01 | KINGSLANDING | sevenkingdoms.local | 10.4.20.10 |
| GOAD-DC02 | WINTERFELL | north.sevenkingdoms.local | 10.4.10.11 |
| GOAD-SRV02 | CASTELBLACK | north.sevenkingdoms.local | 10.4.10.22 |
| GOAD-WS01 | WS01 | north.sevenkingdoms.local | 10.4.10.31 |
| GOAD-ROUTER | Debian router | management + three segment interfaces | 10.4.10.1 / 10.4.20.1 / 10.4.99.1 |

Delete GOAD-DC03 (MEEREEN) and GOAD-SRV03 (BRAAVOS) *from Course 1
definition*, along with Essos-only domain contents, inventory groups,
playbook targets, router segment, trust references and dependent
vulnerabilities. Do not delete GOAD files or hosts in the reference
`ad/GOAD` profile. Protect Course 1's SQL, WS01, Phase 01 and Phase 03
attack paths while removing unreachable Essos-only material.

Exact residual cross-domain dependencies identified in the working
`ad/GOAD/data/config.json` outside the two Essos host definitions and
Essos domain itself:

- `lab.hosts.srv02.mssql.linked_servers.BRAAVOS.data_src` -> braavos.essos.local
- `lab.domains.sevenkingdoms.local.trust` -> essos.local
- `lab.domains.sevenkingdoms.local.multi_domain_groups_member.AcrossTheNarrowSea` -> essos\\daenerys.targaryen

Audit ALL relevant playbook group memberships, trust/DNS/ADCS/
MSSQL/relay dependencies before removing these references.

## Network contract

Default lab prefix: **10.4.0.0/16** with isolated segments:
NORTH `10.4.10.0/24`, SEVENKINGDOMS `10.4.20.0/24`,
MANAGEMENT `10.4.99.0/24`. No Essos network.

User can override the lab prefix/second octet at provisioning time; for
example `10.5.0.0/16` yields `10.5.10.0/24`, `10.5.20.0/24`,
`10.5.99.0/24`, including gateways, host addresses, router rules,
inventory, DNS source bindings and any relevant fixtures. One profile
parameter must drive all derived networking; never edit dispersed
hardcoded guest IPs or copy the experimental NORTH network scripts.

Same-host concurrent instances require **separate VMware virtual
network IDs, MACs, host routes, guest ownership, resolver authority, and
nonoverlapping prefixes**. Fail early if a network or virtual NIC belongs
to another lab. Default 10.4 deployment is NOT legal when the original
10.4 Kingdoms instance is running on the same isolated-network namespace;
the user must choose another prefix such as 10.5. No DHCP/NAT resolver
may discover a foreign identically named AD forest.

## Permitted engineering changes

- A small declarative Course 1 profile (instance roster, domain subset,
  route segments, Ansible group selections and source vulnerability data).
- Minimal parameterization of the **existing** Kingdoms engine to render
  a nondefault prefix and independent vmnet allocation. New provider
  subclasses, alternate install pipelines or duplicate VMnet service
  stacks require explicit re-evaluation and are disfavored.
- Early stage checks for source validity, inventory group references,
  VMnet/MAC/CIDR collisions, actual per-guest NIC identities, parent
  DC/DNS authority, and required domain/role dependencies.

## Failure and acceptance contract

Before expensive Windows/Ansible steps, validate topology and source
integrity without touching the reference lab. A missing machine,
unresolved Ansible group, invalid dependency, foreign DNS/DC Locator,
wrong NIC, network collision, or missing role must fail *before* a
20-30 minute attempt. Successful checkpoints must be resumable and
idempotent; do not repeat completed provisioning blindly.

Live acceptance must prove: first Vagrant install; forest-root and child
DC promotion, trust/DNS and time hierarchy; member domain joins;
SQL and exact Course 1 attack fixtures; headless WS01/Phase 03 where
applicable; provisioning-to-exercise transition with NAT adapter
disconnection and restrictive router mode; no traffic to reference
Kingdoms; start/stop/reset and measured startup performance.

## Delete the discarded implementation

User direction is **discard**, not freeze or keep for a later migration.
The old experimental NORTH branch and disposable NORTH VM/workspace are
not part of this rebuild. Removal should occur as a deliberate cleanup
operation **after verifying the exact disposable instance/VMX IDs and
that none belong to reference GOAD**. Do not wait for a new lab to
succeed before performing requested cleanup, but do not run broad
`vagrant destroy` or `rm -rf` from a non-validated target directory.
Explicitly account for existing `6ca91b-north-vmware` state and the
`feature/course1-reduced-profile-source` remote branch.
