# WSLPE local account security and provisioning handoff

**State (2026-10-17): SOURCE PREPARATION ONLY.** No guest account, WinRM listener, VMware snapshot, NAT, NORTH instance or shared role was modified by this change.

## Purpose

The standalone Windows LPE course intentionally contains vulnerable local administrative accounts for credential-hunting exercises. They are not infrastructure accounts. The Vagrant bootstrap principal has a publicly known default password and must not be usable in any student-ready lab. It must remain until a separately verified administrator can safely replace its management role.

## Account disposition

| Local account | Purpose | Student-ready decision |
| --- | --- | --- |
| lpe.trainee | Standard nonadmin local learner | Keep enabled, nonadmin, RDP |
| vagrant | Bootstrap/WinRM provisioning | Disable only AFTER independent operator handoff |
| kingdom.operator | Dedicated WSLPE operator, not a lab fixture | New unique per-instance credential; operator-only |
| Administrator | Built-in break-glass | Disable if unused or protect with unique unreleased secret |
| kingdom.deploy | Unattend file credential fixture | Keep but assign unique per-instance exercise secret |
| kingdom.pshistory | PowerShell history credential fixture | Keep but assign unique per-instance exercise secret |
| kingdom.appsvc | Hardcoded application config credential fixture | Keep but assign unique per-instance exercise secret |
| kingdom.runas | Credential Manager/RunAs fixture | Keep but assign unique per-instance exercise secret |
| kingdom.autologon | Winlogon credential fixture | Keep but assign unique per-instance exercise secret |

The five fixture accounts are defined in ansible/roles/windows_lpe/defaults/main.yml and their role-specific technique tasks. Their source passwords are currently fixed and publicly visible. The NORTH/shared role must remain **frozen**; WSLPE-only per-instance overrides are a **release blocker not yet implemented**.

## Stage A0 — read-only account inspection (permitted)

After source CI, from the WSLPE standalone checkout:

    "$HOME/.goad/.venv/bin/python" scripts/wslpe-account-audit.py --expected-thumbprint C773EC26D02940F559FE715B83628FEDAE2AA92D

Uses exact registration and pinned authenticated HTTPS, checks existence/enablement/Administrator membership of the eight named accounts and domain-free learner status. Does not collect secrets or modify Windows. An enabled vagrant is an expected **release blocker** at this development stage.

## Stage A1 — private operator secret preparation (no Windows changes)

    python3 scripts/wslpe-operator-secret.py
    python3 scripts/wslpe-operator-secret.py --prepare

The second command explicitly prepares one unique operator secret stored in a mode-0700 directory and mode-0600 file under ~/.local/state/kingdoms-wslpe-operator/<native-instance-id>/credential. No password is printed; existing secrets are reused, never silently rotated. Do not commit, screenshot or distribute it.

## Stage A2 — controlled operator creation (NOT AUTHORIZED)

A dedicated WSLPE-only opt-in playbook exists at ansible/wslpe-operator-foundation.yml. It refuses domain/DC inventories, wrong host, unexpected existing operator and privileged learner; it requires operator secret supplied privately and wslpe_operator_handoff_approved=true. It creates ONLY kingdom.operator, validates local Administrators membership, and does not disable vagrant or alter WinRM.

Before this stage: demonstrate independent VMware Workstation console access to the exact VM, maintain the approved KINGDOMS-WSLPE-PRE-JEA development snapshot, and authorize this particular guest mutation. The successful systemd and scratch VMX rehearsal is not a full real-VM rollback test.

## Stage A3 — authenticated handoff and retiring vagrant (NOT IMPLEMENTED/APPROVED)

1. Authenticate kingdom.operator via an independent, pinned TLS WinRM HTTPS/5986 session. Prove working administrative control and intact nonadmin learner, independently of vagrant.
2. Update **only WSLPE** inventory, operator secrets and all provisioning workflows to use the new identity, verify that Vagrant/bootstrap dependence is absent, and re-check VMware recovery.
3. Under a separately approved, verified out-of-band rollback, disable vagrant from the new operator context. Confirm old default credentials are rejected and new HTTPS management continues. Never disable vagrant by running generic ansible/disable_vagrant.yml: that file targets the domain inventory.
4. Override source-fixed passwords for five intended privilege escalation fixtures with unique per-instance WSLPE secrets, without touching the frozen NORTH role. Prove each exercise still has its intended discovery path.
5. Verify host isolation and complete the fresh-install acceptance gate. Only then capture the final fully vulnerable local baseline snapshot.

## Immutable boundaries

NORTH read-only; exact standalone workgroup WSLPE-WS01 only. No automatic WinRM restart, NAT cutover, full batch activation, guest lifecycle changes or snapshot reversion. The current PRE-JEA snapshot is a developer recovery point, not a student-ready image.
