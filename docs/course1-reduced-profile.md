# Kingdoms Course 1 — Fall of the North (reduced deployment)

**Status: preview-only source profile, NOT a deployable lab.** This work does
not modify the six-Windows-VM GOAD reference lab or any existing instance.

## Scope

- Retain GOAD-DC01 KINGSLANDING (parent), GOAD-DC02 WINTERFELL (NORTH),
  GOAD-SRV02 CASTELBLACK (IIS, SQL, WebDAV), GOAD-WS01 workstation, and GOAD-ROUTER.
- Remove ESSOS Windows guests (GOAD-DC03, GOAD-SRV03) and essos.local
  from the candidate Active Directory configuration.
- Keep NORTH child domain and forest-root parent for optional Enterprise
  Admin challenge, which is NOT yet validated end-to-end.
- Keep SQL Server SQLEXPRESS. BRAAVOS linked-server fixture is absent in the
  preview; PR #29 demonstrates KINGDOMS2 feasibility but its provisioner
  still needs implementation. Do not claim 00-09 parity.

## Source validation (read-only)

Run from the repository:

    python3 scripts/course1/generate-profile.py --check

The command validates GOAD config, inventory groups, Vagrant declarations,
and the **actual rendered instance Vagrantfile** entirely in memory. It never
starts VMs or creates a deployment. It also requires a management-host entry
for every reduced guest in the post-Vagrant inventory. Specifically, it
derives WS01's administrator management identity from the validated NORTH
SRV02 entry, matching the existing full-lab runtime behavior without storing
new credentials in this source branch.

To create a PRIVATE candidate recipe outside Git:

    python3 scripts/course1/generate-profile.py --output "$HOME/Kingdoms-course1-preview" --acknowledge-lab-credentials

Generated recipe contains existing fixture passwords. Keep it private, do
not commit the output. File modes are 0600 inside a 0700 directory.
Existing output is never overwritten.

The preview includes data/inventory_disable_vagrant with an explicit WS01
management entry, providers/vmware/Vagrantfile with the five Ruby box entries,
and instance-preview/Vagrantfile rendered through the same Jinja2 outer
VMware template used by GOAD. **Do not execute** Vagrant against these files
or move them into the installed workspace: runtime activation is blocked.

Run tests:

    python3 -m unittest tests.test_course1_reduced_profile

## Release blockers — MUST be closed before a four-VM install

1. Lifecycle: current GOAD management, start/stop, lab-mode.sh, domain-time
   and readiness contracts assume exactly six Windows guests. These must
   select an explicit per-instance roster; do not use candidate Vagrantfile
   with legacy lifecycle.
2. Vagrant/provider: GoadPath resolves ad/GOAD and provider sources are
   composed for full GOAD. Need a separate opt-in install profile and
   source/instance isolation gate.
3. Router: preview deliberately retains unused vmnet30 interface to avoid
   untested NIC/PCI slot renumbering. A reduced router/network profile
   can follow after lifecycle work.
4. SQL: build idempotent per-instance KINGDOMS2 provisioning, explicit 1444,
   separate identities and scoped linked-login permissions. Original
   MSSQL role is single-instance.
5. AD: test fresh parent/child install, DNS, time authorities, SQL, CA,
   Phase 03 overlay, and complete 00-09 attacks in a disposable instance.
6. Topology collision: candidate preserves fixed addresses/MACs. Never
   run concurrently with the original reference deployment.
7. Optional Enterprise Admin challenge: still requires demonstrated
   parent-domain escalation path before being advertised as proven.

## Roadmap

Do not modify main or replace the current installed lab in place.
Promote the Course 1 recipe to an explicit install profile only when
its router, provider, lifecycle, Ansible, SQL, and course regressions pass.
