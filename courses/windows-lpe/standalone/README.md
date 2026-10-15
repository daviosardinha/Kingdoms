# Kingdoms Windows Local Privilege Escalation: standalone lab

**Status: independent VMware backend definition ready for validation, not yet deployed. Kingdoms' operator-only course selector is present on the feature branch, but the Windows LPE deployment adapter is not implemented.**

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

## Private operator installation workflow

The unified Kingdoms console is the normal operator entry point. From the feature-branch repository root:

```text
./goad.sh
> courses
> select_course windows-lpe
KINGDOMS/windows-lpe > install
Create the standalone Windows LPE VM? [y/N]: y
KINGDOMS/windows-lpe > course_vm_status
```

**Current Stage 1 only:** `install` creates the one independent VMware Windows guest after confirmation. It does **not** create the local learner account, apply any of the original 20 or proposed 15 scenarios, or report the whole course installed. The Windows LPE `start`, `stop`, `reset` and `destroy` commands are still blocked, and the noninteractive `-c windows-lpe -t install` remains disabled.

The `course_preflight` and `course_vm_status` commands inspect the standalone backend without booting anything. If manual developer diagnostics are needed, the separate `course_vm_create CREATE windows-lpe` entry point still exists. No operator should normally need to invoke Vagrant from this directory.

### VM registration versus Vagrant metadata

A prior Vagrant status check can leave empty directories or `index_uuid` metadata under `.vagrant/machines/kingdoms-lpe-ws01/vmware_desktop/` even when it reports `not created`. The bootstrap accepts these harmless inspection artifacts if the target is still definitively uncreated. A provider `id`, unknown artifacts, symlinked state or an ambiguous Vagrant status continues to block creation. **Never delete state or retry blindly** if an unrecognized partial state is reported.

This directory and the private operator console are never exposed to learners. Learners receive only their assigned vulnerable guest and approved scoped connection credentials. AWS delivery is a future provider adapter, not part of this local VM bootstrap.

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

## Deliberate developer-only first boot

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

## Access delivery boundary

Only trusted Kingdoms operators use this directory and the future course installer. Learners access the **deployed vulnerable Windows machine only**. They must not receive the Vagrantfile, Ansible inventory, VMware host access, provisioning WinRM credentials, VM snapshots, API keys, privileged local administrator account or another learner's lab. Any future cloud provider must enforce the same boundary with distinct instance assignment and a restricted remote-access method. AWS packaging and learner provisioning are future provider work, not functionality delivered by this VM definition.

## Safe operation

- `vagrant status` and `vagrant winrm-config` are inspection commands.
- `vagrant halt` stops only this Vagrant machine when run from this directory.
- Do not use the Kingdoms segmented lab stop/start/reset scripts here.
- Do not run `vagrant destroy` without first confirming that the Vagrant project directory is this standalone directory and that the machine contains no irreplaceable evidence.
- Keep the existing Kingdoms instances intact while the new course is being built.
