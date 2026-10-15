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

## Unified Kingdoms installer: operator-only WSLPE instances

**Architecture decision (October 2026):** Extend the validated Kingdoms core, **not** the experimental parallel Vagrant bootstrap. `WSLPE` is the proposed new first-class lab name; `windows-lpe` is the existing operator course identifier. The course remains `development`. Only an explicitly confirmed **Stage 1 guest boot** is implemented through the native instance/provider path; full course installation remains unavailable until Windows, learner and scenario acceptance gates pass.

The existing `goad/labs.py`, `goad/lab_manager.py`, `goad/instance.py`, VMware provider factory, Ansible provisioner and `windows_lpe` role are authoritative. `ad/` is the present historical lab-recipe directory; its name is not an Active Directory requirement. Extensions attach to a lab's instance, while WSLPE needs its **own** independent instance and VM.

The intended private operator flow is:

```text
./goad.sh
> courses
> select_course windows-lpe
KINGDOMS/windows-lpe > install
```

Interactive `install` with `windows-lpe` selected now asks for an operator-chosen private /24 prefix and the exact confirmation `CREATE WSLPE`, reruns all 13 consolidated preboot checks and creates **one native WSLPE instance plus its Windows guest** via Kingdoms' existing `LabManager` and VMware provider. This is Stage 1 only; it neither provisions the learner nor installs vulnerabilities and can mark the instance only `PROVIDED`, never `READY`. On failures it refuses automatic cleanup/retry. The noninteractive WSLPE `install` route remains denied, and NORTH retains its original lifecycle.

The superseded `courses/windows-lpe/standalone/Vagrantfile` and `kingdoms/windows_lpe_vmware.py` remain as experimental engineering artifacts on the draft branch, not the final installer path. The direct creation commands `course_vm_create` and `-t course-vm-create` are now retired in the operator console to avoid confusing prototype state with a real Kingdoms instance. Their read-only inspection helpers may still report the prototype state but are not WSLPE installation readiness. **Do not delete or force-reset earlier Vagrant state.**

See [WSLPE core integration plan](WSLPE_CORE_INTEGRATION_PLAN.md) for the exact source mappings, instance guards, role reuse, the original 20-scenario regression, the next 15 candidate scenarios and later NORTH integration.

## Operator control plane versus learner attack surface

**Operators (trusted infrastructure administrators)** have access to the Kingdoms installer, GitHub engineering source, Vagrant/VMware or future cloud credentials, Ansible, scenario provisioning, snapshots, reset, deployment health, and lifecycle operations. Those services and secrets remain on the operator's trusted management environment.

**Learners (untrusted lab users)** receive only the target VM or explicitly authorized lab segment, a standard local Windows learner account or other course-specific foothold, and the walkthrough. Their assigned network and account must not provide access to the installer, hypervisor APIs, host filesystems, provisioning credentials, administrative WinRM listener, Ansible inventory, provider tokens, snapshot operations, or another learner's lab. Privilege escalation inside their deliberately vulnerable guest is the educational objective and must not cross the guest's infrastructure boundary.

The lab engine is reusable, but **deployment backend** and **access delivery** are separate concerns. The operator chooses a provider and provisions a machine; an access-delivery step provides only the learner's machine-specific connection details and permitted credential. Any future learner self-service, if explicitly introduced, must use a separately authorized access broker, never the operator installer directly.

## Future cloud deployment (not part of current work)

A future AWS-backed Windows LPE course may use the same local-only scenario role and a tested guest image, but it requires a separate provider adapter and image-build/import pipeline. An AWS machine is not automatically equivalent to the VMware guest. Validate available Windows guest licensing, image compatibility, instance hardware support, network isolation and per-learner lifecycle before choosing AMI or import mechanics.

The cloud control plane must remain operator-only. Each learner receives access only to their assigned lab VM via the approved remote-access channel. No IAM or cloud console permissions, image-management rights, instance-control API access, deployment source or operator keys are delivered to learners. Provisioning, learner assignment, credential delivery, expiration, teardown and cleanup require independent acceptance tests. None of this cloud orchestration is implemented in PR #33.

## WSLPE native deployment path

The **authoritative** Windows LPE lab is the native `WSLPE` recipe in `ad/WSLPE/`. Its generated Vagrantfile and inventory belong to an independent Kingdoms instance managed by the **existing** lab manager, VMware provider and Ansible provisioner. The repository's former `courses/windows-lpe/standalone/` Vagrant project is retained only as a superseded developer prototype; its direct guest-creation command is retired. **Do not run `vagrant up` from that old project.**

The native source and preboot checks have passed on the current operator workstation, and the Stage 1 operator-boot implementation is now committed but **not yet executed on that host**. After safely booting the guest, we must verify actual VMX/NIC assignment, WinRM and Windows security baseline, then provision the local learner and validate the original 20 techniques individually. Finally add the proposed 15 techniques to the same shared role, and later regression-test all 35 on NORTH WS01.

Only trusted Kingdoms operators create and manage instances. Learners receive access solely to their assigned vulnerable Windows guest. See [WSLPE core integration plan](WSLPE_CORE_INTEGRATION_PLAN.md) for the current gates and source mappings.

## Existing Windows LPE source gate

See `docs/WINDOWS_LPE_STANDALONE_CONTRACT.md` for the reusable role contract, independent guest preflight and 15 proposed standalone scenarios.
