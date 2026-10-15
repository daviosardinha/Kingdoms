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

**Current operator-only registry slice (committed, requires operator-side validation):**

```text
$ ./goad.sh
KINGDOMS | OPERATOR CONSOLE
> courses
    north          The Fall of the North [available]
    course-2       Course 2 (title pending) [planned]
    windows-lpe    Windows Local Privilege Escalation [development]
> select_course windows-lpe
    Selected Kingdoms course: Windows Local Privilege Escalation [development]
    Deployment adapter is not validated. Lifecycle commands are blocked.
> course
    Course: Windows Local Privilege Escalation; state=development
> status
    Course adapter pending. Installation and lifecycle disabled.
> install
    Command blocked; the loaded NORTH instance was not touched.
> select_course north
    Selected Kingdoms course: The Fall of the North [available]
```

`courses`, `select_course <slug>`, `course`, a read-only pending-course `status`, and Windows LPE backend inspection commands (`course_preflight`, `course_vm_status`) are implemented on the feature branch. Selection is session-local and never deploys a machine. The current console continues to support legacy install/start/stop/status/reset on an existing NORTH lab; selecting an unfinished course **blocks** all lifecycle commands, including reset and destroy, rather than forwarding them to NORTH. The separate `-c/--course` argument also fails closed for unsupported non-interactive actions.

**Operator preflight commands (implemented, pending execution on the operator workstation):**

```text
Kingdoms > select_course windows-lpe
Kingdoms > course_preflight
Kingdoms > course_vm_status

$ ./goad.sh -c windows-lpe -t course-preflight
$ ./goad.sh -c windows-lpe -t course-vm-status
```

These commands inspect only the standalone VMware project at `courses/windows-lpe/standalone/` and do not create, start, stop or reset any VM. The preflight checks the pinned Windows image, Vagrant/VMware tools, Ruby syntax and Vagrantfile validity. Status inspects only the standalone Vagrant project. Both are **operator-only diagnostics**, not learner features. The source test suite uses mock subprocess calls; validation on the actual operator host is still outstanding.

**The full Windows LPE installer adapter is not implemented.** Do not interpret the course appearing in the registry as a deployable environment. It discovers labs under `ad/` and its NORTH-specific VMware provider includes segmented routing, identity and exercise-mode behavior. Do **not** register standalone Windows LPE as an Active Directory lab just to make it appear in that list, and do not reuse the NORTH provider's network transitions for the standalone course.

**Design requirement:** the first, fail-closed course registry/selection layer is now in place on the feature branch. Next add a dedicated `windows-lpe` course adapter. That adapter should orchestrate the isolated Vagrant VM, initial local account provisioning, build/security preflight, scenario application, validation, start, stop and reset through the same Kingdoms console. For Course 1, delegate to the existing, validated NORTH lifecycle without changing its semantics. Each course keeps its own inventory, provider state, VM identity, snapshots and reset contract. Shared Ansible scenario roles remain reusable.

`vagrant up --provider=vmware_desktop` is a low-level **operator/developer diagnostic**, not a learner interface or the final operator installation workflow. Retain the standalone Vagrantfile because the course adapter must still create a real VM through the provider. Do not call the manual Vagrant command part of the normal operator installation steps once the integrated installer exists.

**Engineering order:** validate the registry/menu and read-only standalone VMware adapter tests on the operator workstation, then implement a separate, explicitly approved Windows LPE VM creation and guest provisioning lifecycle. Only after a real target and its local learner pass the independent readiness gates should the installer expose mutating lifecycle commands. Do not encourage a production installation through the menu until the full adapter is implemented and validated.

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
