# Kingdoms Course 1 — three-network candidate

Source: read-only VMware host snapshot from 2026-10-09 (reference running on
vmnet10/20/30/99; other observed vmnets 0/1/8). This file is NOT a host reservation.

`docs/course1-network-candidate.example.json` is a **synthetic, proposed**
three-zone layout intended for *collision discovery only*. It deliberately
uses other vmnet names, private /24 IPv4 ranges and distinct static MAC values.
Unobserved vmnets are not necessarily free or supported by VMware.

| Segment | Example VMware network | Example subnet | Host-side endpoint |
|---|---|---|---|
| NORTH | vmnet11 | 10.41.10.0/24 | 10.41.10.254 (attacker) |
| SEVENKINGDOMS | vmnet12 | 10.41.20.0/24 | none required |
| MANAGEMENT | vmnet13 | 10.41.99.0/24 | 10.41.99.254 |

Each route/gateway, Windows address, MAC, and router adapter requires generation
of an isolated installer recipe; the present full reference lab must not be edited.
Course 1 does not have ESSOS, vmnet30 or an ESSOS router adapter. Existing
Kingdoms reference deployment keeps them unchanged.

The existing Course 1 preview still shares old vmnets/IPs/MACs, and remains
PREVIEW_ONLY_NOT_INSTALLABLE. The proposal file is not consumed by Vagrant.

Current hard blockers before any VM creation: VMware vmnet availability/host
route review, correct new router PCI/NIC mapping and provisioning, Windows
network/IP and AD/Ansible address propagation, per-instance binding, SQL
KINGDOMS2, lifecycle/Phase 03 parity.

Run `bash scripts/course1/validate-course1.sh --survey-host` for combined
offline regression + live observational fit. A clean result never grants
network allocation or deployment authorization.

## VMware static-MAC compatibility correction

The example candidate now uses VMware Workstation's documented manual
static Ethernet range `00:50:56:00..3F:YY:ZZ` instead of the unsupported
`02:44` test MACs. It also proposes unallocated vmnet11/12/13 rather than
vmnet41/42/49, for conventional Workstation naming. These identifiers are
not reserved; dormant guests and host VMware configuration require separate
collision/compatibility validation before deployment.

VMware reference: https://knowledge.broadcom.com/external/article?legacyId=507
