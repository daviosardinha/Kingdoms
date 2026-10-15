# Kingdoms course architecture

**Kingdoms** is the platform and engineering project. Its courses are separate learning products that may share reusable laboratory components without inheriting each other's infrastructure dependencies.

## Course catalogue

| Course | Student-facing title | Training environment | Status |
| --- | --- | --- | --- |
| 1 | **The Fall of the North** | **NORTH**, a domain-joined, multi-machine Windows/Active Directory lab | Existing course and lab |
| 2 | **Title not yet confirmed** | Future course, separate from NORTH unless explicitly designed otherwise | Future course |
| Windows LPE | **Title to be chosen** | Independent Windows workstation, local learner and local attack surface | Engineering foundation in progress |

A course title is not a repository path, virtual-machine identifier, or compatibility alias. Do not expose historical upstream/fork names as course or platform branding.

## Engineering boundaries

- `courses/` holds course-specific deployment adapters, student environment definitions, and eventually course-specific configuration.
- `ansible/roles/windows_lpe/` is a shared Windows local privilege escalation scenario engine used by multiple courses. It must not assume a specific Windows hostname, AD account, domain controller, or external domain services.
- `courses/windows-lpe/standalone/` is the **independent Windows LPE deployment**, not a clone of a domain-joined NORTH guest.
- The existing NORTH installation and source gates remain untouched unless a separate, proven compatibility migration is explicitly undertaken. Old code names may remain as **legacy compatibility identifiers** while they are still referenced by functioning scripts, inventory, hypervisor guest names, or installation state.
- Students taking the standalone course must be able to discover, exploit, confirm and restore a scenario using the workstation alone. Provisioning may use a controller/hypervisor; *exploitation* must not require one.

## Migration policy

1. Name all **new** course directories, documents, student outputs, VM display names, script names and evidence as Kingdoms.
2. Leave existing provider paths and proven lifecycle identifiers intact during the first standalone release. Do not perform a global find-and-replace across historical namespaces.
3. Add adapters that explicitly pass domain-specific values to the shared scenario engine, while the independent course passes a **local** user context.
4. After the independent course passes its own compatibility and full scenario gates, rename any remaining inherited internal identifiers incrementally with regression tests and exact migration steps.
5. The 15 new Windows LPE scenarios remain **planned** until implemented and verified on the pinned standalone Windows build. Original 20 scenarios were previously proven in the NORTH environment, not yet as standalone exercises.

## Unified Kingdoms installer: the required public workflow

The interactive installer is the product-facing entry point for **every course**. Operators should not have to manually enter an internal Vagrant directory to install a course. The current compatibility entry point is `./goad.sh`, which dispatches to `goad_nomad.py`. A future `./kingdoms.sh` can become the public launcher while `./goad.sh` remains a backwards-compatible alias after its behavior is tested.

**Target interaction (not implemented yet):**

```text
$ ./goad.sh
Kingdoms > courses
  1. The Fall of the North        [available]
  2. Course 2                     [not released]
  3. Windows Local Privilege Escalation [development]

Kingdoms > select-course windows-lpe
Kingdoms [windows-lpe] > install
Kingdoms [windows-lpe] > status
Kingdoms [windows-lpe] > start
Kingdoms [windows-lpe] > stop
Kingdoms [windows-lpe] > reset
```

These commands represent the proposed **user interface**, not commands supported by today's console. The existing console already exposes install/start/stop/status/reset on the selected **lab instance**. It discovers labs under `ad/` and its NORTH-specific VMware provider includes segmented routing, identity and exercise-mode behavior. Do **not** register standalone Windows LPE as an Active Directory lab just to make it appear in that list, and do not reuse the NORTH provider's network transitions for the standalone course.

**Design requirement:** add a course registry and course selection layer above the existing lab/provider implementation, then a dedicated `windows-lpe` course adapter. That adapter should orchestrate the isolated Vagrant VM, initial local account provisioning, build/security preflight, scenario application, validation, start, stop and reset through the same Kingdoms console. For Course 1, delegate to the existing, validated NORTH lifecycle without changing its semantics. Each course keeps its own inventory, provider state, VM identity, snapshots and reset contract. Shared Ansible scenario roles remain reusable.

`vagrant up --provider=vmware_desktop` is a low-level **developer diagnostic**, not the learner/operator installation interface. Retain the standalone Vagrantfile because the course adapter must still create a real VM through the provider. Do not call the manual Vagrant command part of the normal course installation steps once the integrated installer exists.

**Engineering order:** implement a source-validated course registry/menu first, then connect its standalone adapter to the pinned Vagrant definition, then local learner provisioning and runtime gates. Do not encourage a production installation through the menu until the full adapter is implemented and validated.

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
