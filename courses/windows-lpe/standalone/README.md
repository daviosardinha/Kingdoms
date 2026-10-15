# Kingdoms Windows Local Privilege Escalation: standalone lab

**Status: machine definition ready for validation, not yet deployed.**

This is one independently managed Windows workstation used to develop and verify the shared Kingdoms Windows LPE scenarios. It is not a copy of the NORTH course instance, it does not join Active Directory, and it does not configure any vulnerability on first boot.

## Architecture

- VMware Desktop, Vagrant `mayfly/windows10` box pinned to version `2024.01.06`
- Machine identity: `kingdoms-lpe-ws01`, distinct from all existing Kingdoms guests
- 2 vCPU, 4 GiB RAM
- Only the management NAT adapter is allowed during first boot; no Kingdoms segmented interfaces are attached
- No `ansible/ws01.yml`, domain join, learner account bootstrap, or vulnerability apply/reset is invoked
- No automatic RDP forwarding; use Vagrant/VMware management console first
- **Later requirement**: verify offline operation with the NAT interface disconnected once the local learner is configured

A single NAT interface for provisioning does **not** prove network isolation. Inspect the resulting VMX and Windows adapters. Never allow this VM to attach to the NORTH exercise network or assume its host management IP is the course exercise IP.

## Prerequisites

The operator's host must have Vagrant and the VMware Desktop plugin, the `mayfly/windows10` VMware box version `2024.01.06`, sufficient RAM/disk, and a clean Kingdoms standalone Git worktree.

Run these **read-only** validations first:

```bash
cd "$HOME/kingdoms-lpe-standalone"
git status -sb
ruby -c courses/windows-lpe/standalone/Vagrantfile
cd courses/windows-lpe/standalone
vagrant validate
vagrant status
```

Do not run these commands from the existing NORTH provider directory.

## Deliberate first boot

Only after the read-only validation succeeds:

```bash
cd "$HOME/kingdoms-lpe-standalone/courses/windows-lpe/standalone"
vagrant up --provider=vmware_desktop
vagrant status
vagrant winrm-config
```

`vagrant up` allocates a separate machine and changes the host's VMware inventory. It does **not** install vulnerabilities from the 20-scenario catalogue or the 15 new proposals.

Before applying any LPE scenario, confirm on the guest:

1. Actual Windows edition and build against the existing NORTH workstation's pinned build
2. No domain membership and no unexpectedly inherited domain accounts or policies
3. Unique MAC, guest identity and virtual machine directory, no segmented laboratory adapter
4. Functional Vagrant/WinRM management
5. UAC, Windows Defender and Windows Firewall operational
6. Evaluation/license grace sufficient to support practical sessions

The independent learner account, installation of the 20 pre-existing scenarios, and the 15 new scenarios are separate engineering stages. See `docs/WINDOWS_LPE_STANDALONE_CONTRACT.md`.

## Safe operation

- `vagrant status` and `vagrant winrm-config` are inspection commands.
- `vagrant halt` stops only this Vagrant machine when run from this directory.
- Do not use the Kingdoms segmented lab stop/start/reset scripts here.
- Do not run `vagrant destroy` without first confirming that the Vagrant project directory is this standalone directory and that the machine contains no irreplaceable evidence.
- Keep the existing Kingdoms instances intact while the new course is being built.
