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

## How this should be installed

**Target operator workflow:** the private Kingdoms console manages this course. The feature branch supports read-only `courses`, `select_course windows-lpe`, `course`, `status`, `course_preflight` and `course_vm_status`. It now also supports an **explicit guest-only bootstrap** with `course_vm_create CREATE windows-lpe`, which creates just the isolated Windows VM. For noninteractive automation, use `./goad.sh -c windows-lpe -t course-vm-create --confirm-vm-create`. This is **not full course installation**. The ordinary `install`, `reset`, `destroy`, `start` and `stop` remain blocked until the target OS baseline, local learner and scenario acceptance gates have been proved. Manual Vagrant calls remain developer diagnostics and are not a learner workflow.

The Vagrant project in this directory remains the course's low-level VMware backend and a narrow **operator/developer test harness**. It must never be copied to the learner's machine, added to the vulnerable guest, exposed on the learner's network or given to course participants. The eventual learner handoff contains only machine-specific access details and a learner-scoped account, not infrastructure or management credentials.

## Operator-only integration checks

From the repository root, after fetching the latest feature-branch commit:

```bash
./goad.sh -t courses
./goad.sh -c windows-lpe -t course-preflight
./goad.sh -c windows-lpe -t course-vm-status
```

These commands must not boot, reset, destroy, or otherwise modify any virtual machine. The preflight checks the expected Windows box, VMware plugin and Vagrant project syntax. It does **not** prove the standalone guest exists or that LPE scenarios work.

## Explicit operator guest creation (VM only)

After updating the feature branch, passing the source tests and the `course-preflight` check, a trusted operator can deliberately create **one isolated Windows test VM**:

```bash
cd "$HOME/kingdoms-lpe-standalone"
./goad.sh -c windows-lpe -t course-vm-create --confirm-vm-create
./goad.sh -c windows-lpe -t course-vm-status
```

Or from the interactive console:

```text
> select_course windows-lpe
> course_preflight
> course_vm_create CREATE windows-lpe
> course_vm_status
```

This action checks that the dedicated Vagrant state is *not created*, refuses ambiguous or leftover partial state, and runs a single `vagrant up kingdoms-lpe-ws01 --provider=vmware_desktop` **internally from the dedicated project directory**. It does not touch NORTH, create learner accounts or apply any of the 20+15 intended vulnerabilities. It refuses to destroy or auto-retry on failure. **The operator must investigate any partial VMware state before another attempt.**

Once the VM is running, we still need to independently prove its OS build, lack of domain membership, unique network and VMware identity, Windows security baseline, WinRM management, and local-account model. Only then can we begin standalone scenario testing. A running VM is not an installed Windows LPE course.

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
