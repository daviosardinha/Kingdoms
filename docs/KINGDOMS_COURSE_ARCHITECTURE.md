# Kingdoms course architecture

**Kingdoms** is the platform and engineering project. Its courses are separate learning products that may share reusable laboratory components without inheriting each other's infrastructure dependencies.

## Course catalogue

| Course | Student-facing title | Training environment | Status |
| --- | --- | --- | --- |
| 1 | **The Fall of the North** | **NORTH**, a domain-joined, multi-machine Windows/Active Directory lab | Existing course and lab |
| 2 | **Title not yet confirmed** | Future course, separate from NORTH unless explicitly designed otherwise | Future course |
| Windows LPE | **Windows Local Privilege Escalation** (working label: `windows-lpe`) | Independent Windows workstation, local learner and local attack surface | Engineering foundation in progress |

A course title is not a repository path, virtual-machine identifier, or compatibility alias. Do not expose historical upstream/fork names as course or platform branding.

## Engineering boundaries

- `courses/` holds course-specific operator deployment adapters, learner-target definitions, and eventually course-specific configuration.
- `ansible/roles/windows_lpe/` is a shared Windows local privilege escalation scenario engine used by multiple courses. It must not assume a specific Windows hostname, AD account, domain controller, or external domain services.
- `courses/windows-lpe/standalone/` is the **independent Windows LPE deployment**, not a clone of a domain-joined NORTH guest.
- The existing NORTH installation and source gates remain untouched unless a separate, proven compatibility migration is explicitly undertaken. Old code names may remain as **legacy compatibility identifiers** while they are still referenced by functioning scripts, inventory, hypervisor guest names, or installation state.
- Learners receive only an assigned vulnerable machine or narrowly scoped course network and their authorized access credentials. They must be able to enumerate, exploit and confirm results using the target alone. All provisioning, instructor resets, snapshots, installation, lifecycle control and machine administration remain operator-only.

## Migration policy

1. Name all **new** course directories, documents, student outputs, VM display names, script names and evidence as Kingdoms.
2. Leave existing provider paths and proven lifecycle identifiers intact during the first standalone release. Do not perform a global find-and-replace across historical namespaces.
3. Add adapters that explicitly pass domain-specific values to the shared scenario engine, while the independent course passes a **local** user context.
4. After the independent course passes its own compatibility and full scenario gates, rename any remaining inherited internal identifiers incrementally with regression tests and exact migration steps.
5. The 15 new Windows LPE scenarios remain **planned** until implemented and verified on the pinned standalone Windows build. Original 20 scenarios were previously proven in the NORTH environment, not yet as standalone exercises.

## Unified Kingdoms installer: operator-only control plane

The interactive installer is the **operator-facing control plane** for every Kingdoms course. It must never be installed on learner machines, exposed over learner networks, included in course images, or shared with learners. Operators should not have to enter internal Vagrant directories to install a course. The current compatibility entry point is `./goad.sh`, which dispatches to `goad_nomad.py`. A future `./kingdoms.sh` can become the operator launcher while `./goad.sh` remains a backwards-compatible alias after its behavior is tested.

**Private interactive installer (development stage 1, pending host validation):**

```text
$ ./goad.sh

Kingdoms > courses
    north          The Fall of the North [available]
    course-2       Course 2 (title pending) [planned]
    windows-lpe    Windows Local Privilege Escalation [development]

Kingdoms > select_course windows-lpe
KINGDOMS/windows-lpe > install

Windows LPE Stage 1: create only the isolated Windows VM.
Create the standalone Windows LPE VM? [y/N]: y

KINGDOMS/windows-lpe > course_vm_status
```

The interactive `install` command uses the **selected course**, not the legacy default lab. It confirms the action before creating one separate Windows LPE guest under `courses/windows-lpe/standalone/`. NORTH continues using its existing installation logic when that course is active. The console prompt makes the selected environment explicit.

At this engineering stage, **Windows LPE `install` means guest bootstrap only**, not complete course installation. Learner accounts and vulnerabilities are not provisioned yet. All other Windows LPE lifecycle operations remain blocked, including reset and destroy, until independently validated. The noninteractive `-c windows-lpe -t install` also remains disabled because it must not imply a complete installation; a separate explicitly confirmed guest-only CLI action is retained for diagnostics.

Read-only checks remain available as `course_preflight` and `course_vm_status`. `course_vm_create CREATE windows-lpe` is a lower-level diagnostic, not the expected interactive workflow.

**Vagrant state caution:** `vagrant status` may create empty directories or harmless `index_uuid` metadata before any VM exists. The bootstrap no longer treats their presence alone as a registered VM. It requires a `not created` status and refuses a provider `id`, unexpected files, symlinks or ambiguous state. Do not delete local Vagrant files or force retries to bypass that guard.

The same private installer will eventually provision local learner accounts and apply all validated scenarios through a dedicated course adapter. The Windows LPE VMware backend still must be validated on the operator's real workstation and with a fresh Windows guest before any course is promoted as ready.

## Operator control plane versus learner attack surface

**Operators (trusted infrastructure administrators)** have access to the Kingdoms installer, GitHub engineering source, Vagrant/VMware or future cloud credentials, Ansible, scenario provisioning, snapshots, reset, deployment health, and lifecycle operations. Those services and secrets remain on the operator's trusted management environment.

**Learners (untrusted lab users)** receive only the target VM or explicitly authorized lab segment, a standard local Windows learner account or other course-specific foothold, and the walkthrough. Their assigned network and account must not provide access to the installer, hypervisor APIs, host filesystems, provisioning credentials, administrative WinRM listener, Ansible inventory, provider tokens, snapshot operations, or another learner's lab. Privilege escalation inside their deliberately vulnerable guest is the educational objective and must not cross the guest's infrastructure boundary.

The lab engine is reusable, but **deployment backend** and **access delivery** are separate concerns. The operator chooses a provider and provisions a machine; an access-delivery step provides only the learner's machine-specific connection details and permitted credential. Any future learner self-service, if explicitly introduced, must use a separately authorized access broker, never the operator installer directly.

## Future cloud deployment (not part of current work)

A future AWS-backed Windows LPE course may use the same local-only scenario role and a tested guest image, but it requires a separate provider adapter and image-build/import pipeline. An AWS machine is not automatically equivalent to the VMware guest. Validate available Windows guest licensing, image compatibility, instance hardware support, network isolation and per-learner lifecycle before choosing AMI or import mechanics.

The cloud control plane must remain operator-only. Each learner receives access only to their assigned lab VM via the approved remote-access channel. No IAM or cloud console permissions, image-management rights, instance-control API access, deployment source or operator keys are delivered to learners. Provisioning, learner assignment, credential delivery, expiration, teardown and cleanup require independent acceptance tests. None of this cloud orchestration is implemented in PR #33.

## First standalone machine

The feature branch contains a dedicated Vagrant project at `courses/windows-lpe/standalone/`.

- **Source image:** `mayfly/windows10`, version `2024.01.06`, as used by the existing Kingdoms workstation.
- **Hypervisor:** VMware Desktop with a separate Vagrant state directory and guest identity.
- **Resources:** 2 vCPUs, 4096 MiB RAM.
- **Network:** Single VMware NAT adapter for initial provisioning and communication only; no connection to Kingdoms' segmented lab adapters. Do not treat NAT connectivity as proof of an offline lab.
- **No domain join, no course scenario provisioning yet.** First establish the pinned Windows build, local account model and baseline controls, then perform a disconnected/offline acceptance test.
- **Never run existing NORTH installation, apply/reset, network-mode or VMware scripts against the independent guest.** They contain assumptions about the original lab.

The independent VM is an engineering environment, not yet a production-ready course image. Avoid claiming local privilege escalation works until the account, per-scenario, and rollback gates pass.

## Low-level developer diagnostics until installer integration

Run from `~/kingdoms-lpe-standalone` after committing and fetching the approved branch updates:

```bash
cd "$HOME/kingdoms-lpe-standalone"
git status -sb
ruby -c courses/windows-lpe/standalone/Vagrantfile
cd courses/windows-lpe/standalone
vagrant validate
vagrant status
```

The commands above do not boot a machine. Only after reviewing those results, deliberately provision a **separate** VM from that directory with `vagrant up --provider=vmware_desktop`. It may take significant time to clone the Windows image, and Vagrant may need to configure its management WinRM listener. Do not reuse the existing Kingdoms provider state directory.

Next inspect the guest's OS build, domain membership, services, security baseline and configured VMware network attachments. Once ready, disconnect its external network path and prove exercises remain usable through the VMware console.

## Existing Windows LPE source gate

See `docs/WINDOWS_LPE_STANDALONE_CONTRACT.md` for the reusable role contract, independent guest preflight and 15 proposed standalone scenarios.
