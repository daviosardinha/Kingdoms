<div align="center">

# Kingdoms

<img width="1672" height="941" alt="Kingdoms" src="https://github.com/user-attachments/assets/a7f99c97-94af-408b-95df-1624bad2b6f1" />

### Offensive Security Training Platform

**Recon. Compromise. Pivot. Escalate. Persist.**

Kingdoms began as a fork of [Orange Cyberdefense's GOAD](https://github.com/Orange-Cyberdefense/GOAD), created by Mayfly. That foundation is credited here; the platform documented below is **Kingdoms**.

</div>

---

> [!NOTE]
> The repository name and a few internal compatibility identifiers still reflect the project's ancestry. They are implementation details retained to avoid breaking a validated lifecycle. The project identity, curriculum, architecture and roadmap are **Kingdoms**.

## What is Kingdoms?

Kingdoms is an offensive-security training platform built around separate, reusable course environments. The first released lab is a deliberately vulnerable, segmented Active Directory environment. The Windows Local Privilege Escalation course under development will use an independent Windows workstation and will not require a domain controller.

Within **Course 1, The Fall of the North**, the objective is not to present a flat collection of vulnerable servers. Learners begin inside a constrained security zone, learn the environment, obtain identities and footholds, escalate local privileges, abuse authentication, pivot through network boundaries, and progressively move from a machine-level compromise toward domain, parent-domain and forest-level attack paths.

### Courses

- **Course 1: The Fall of the North**. Existing NORTH / Active Directory course environment.
- **Course 2: Title pending**. Future Kingdoms course, not yet named.
- **Windows Local Privilege Escalation** (`windows-lpe`). Working course identifier and name; independent Windows training environment with no domain-controller dependency.

See [Kingdoms course architecture](docs/KINGDOMS_COURSE_ARCHITECTURE.md). These are distinct courses under the **Kingdoms** platform, not alternate names for a single lab.

**Access model:** The Kingdoms installer, provisioning systems and lifecycle controls are exclusively for trusted operators. Learners receive access only to their assigned vulnerable machine or explicitly authorized course network, plus their learner-level credentials. They never receive the installer, deployment source, hypervisor/cloud administration or operator credentials. Future cloud deployment must preserve this separation.

### Course 1 environment

The range combines:

- realistic routed network segmentation;
- a first-class Windows workstation foothold;
- Linux and Windows authenticated-enumeration stages;
- deterministic Windows local privilege-escalation scenarios;
- poisoning, coercion and authentication-relay scenarios;
- explicit post-exploitation consequences;
- reversible attack state and exact rollback where a scenario mutates the directory;
- lifecycle automation that separates management access from the student attack surface;
- runtime validation designed to fail closed instead of silently hiding a broken lab;
- an expandable curriculum for later delegation, ACL, ADCS, pivoting, persistence and trust-abuse phases.

A central design rule is simple:

> **Identity reachability and network reachability are different things.**

Owning a credential does not automatically make every system reachable. Owning one machine does not automatically mean the domain is owned. Crossing a boundary should require the student to understand why the path exists.

---

## Where Kingdoms is today

Kingdoms has moved beyond an experimental fork. The current `main` branch is a reproducible, validated training baseline.

| Capability | Status |
| --- | --- |
| Segmented NORTH / SEVENKINGDOMS / ESSOS architecture | **COMPLETE** |
| Provisioning / exercise lifecycle | **COMPLETE** |
| Deny-by-default student isolation | **COMPLETE** |
| First-class NORTH Windows workstation | **COMPLETE** |
| 20-technique Windows LPE catalog | **COMPLETE** |
| Course Phase 00 | **COMPLETE** |
| Course Phase 01 | **COMPLETE** |
| Course Phase 02 | **COMPLETE** |
| Phase 03 poisoning / relay infrastructure | **COMPLETE** |
| Fresh installation from `main` | **VALIDATED** |
| Clean-install runtime acceptance | **PASS** |
| Stop / start lifecycle after fresh installation | **PASS** |
| Phase 03 final engineering regression | **11 / 11 PASS** |
| NORTH segmentation lifecycle | **29 PASS / 0 WARN / 0 FAIL** |
| Fresh RDP release acceptance | **15 / 15 PASS** |
| Final runtime state | **exercise / deny-by-default** |

The current engineering baseline was also reproduced from a completely fresh installation rather than only validated on the long-lived development environment.

---

## Milestones achieved

The detailed engineering history is tracked in [**Kingdoms Milestones**](docs/KINGDOMS_MILESTONES.md), while future platform work is tracked in the [**Kingdoms Roadmap**](ROADMAP.md).

### Segmented Foundation — COMPLETE

Kingdoms introduced a routed four-zone architecture and separated the management plane from the student-facing attack surface.

Delivered:

- NORTH, SEVENKINGDOMS, ESSOS and MANAGEMENT zones;
- deterministic VMware networking;
- a dedicated routing plane;
- deny-by-default cross-zone forwarding;
- explicit trust/DNS/application exceptions only where the lab requires them;
- temporary provisioning reachability that is removed before students begin;
- persistent disconnection of Windows provisioning adapters in exercise mode;
- lifecycle validation for `install`, `start`, `stop` and mode transitions.

### NORTH Workstation & Windows LPE — COMPLETE

A first-class Windows 10 workstation, **WS01**, became part of the NORTH environment.

Delivered:

- domain-joined interactive workstation foothold;
- low-privilege Rickon Stark access;
- preserved UAC, Defender and Windows Firewall baseline;
- exactly **20 deterministic Windows local privilege-escalation techniques**;
- resettable technique profiles;
- apply → vulnerable → reset → clean → reapply validation;
- workstation runtime and source acceptance gates.

### Course Foundation — PHASES 00–02 COMPLETE

The first three course phases are complete and form the current student entry path.

| Phase | Title | Status |
| --- | --- | --- |
| **00** | **Know The Kingdoms** | **COMPLETE** |
| **01** | **Outside The Wall** | **COMPLETE** |
| **02** | **Test The Gates** | **COMPLETE** |
| **03** | **Poison The Wells** | **ENGINEERING COMPLETE — CURRICULUM REFINEMENT IN PROGRESS** |

The course writing standard follows an attacker-thinking progression rather than a command dump: understand normal behavior, identify the weakness, reason about the attack surface, interact with it, interpret the evidence, understand the consequence, and choose the next move.

### Poisoning & Relay Runtime — ENGINEERING COMPLETE

Phase 03 established a validated NORTH attack surface for poisoning, authentication coercion and relay.

Implemented and proven families include:

- LLMNR, NBT-NS and mDNS poisoning;
- NetNTLMv2 capture;
- SMB relay target selection;
- automated SMB relay;
- interactive SMB relay;
- SOCKS-backed relay reuse;
- privilege-dependent share and remote-execution consequences;
- LSASS credential-material consequence;
- native DPAPI credential decryption consequence;
- MSSQL outbound SMB authentication through `xp_dirtree`;
- PrinterBug / MS-RPRN coercion;
- PetitPotam / MS-EFSR coercion;
- mitm6 IPv6 / DNS takeover;
- WPAD authentication paths;
- HTTP → LDAPS read-only relay;
- RBCD through relay with S4U consequence and exact rollback;
- Shadow Credentials through relay with PKINIT consequence and exact rollback;
- secure ADIDNS record injection with exact absent-state restoration;
- WebDAV / malicious `.lnk` authentication behavior with service and DNS rollback.

Phase 03 infrastructure is frozen unless the teaching walkthrough exposes a concrete defect.

### Reproducible Release Baseline — COMPLETE

The current platform has been rebuilt from a fresh checkout of `main` and independently accepted after installation.

The clean-install acceptance reproduced:

- segmentation;
- directory relationships;
- WS01;
- all 20 LPE scenarios;
- final exercise isolation.

The fresh range was then stopped and started again successfully with authenticated readiness proven across all members, workstation and domain controllers before exercise isolation was restored.

---

## Current architecture

<img width="1536" height="1024" alt="Kingdoms segmented topology" src="https://github.com/user-attachments/assets/7bd531d6-de4f-427f-8ca2-499fac183f37" />

| Zone | VMware network | Subnet | Systems |
| --- | --- | --- | --- |
| **NORTH** | `vmnet10` | `10.4.10.0/24` | Winterfell `10.4.10.11`, Castelblack `10.4.10.22`, WS01 `10.4.10.31` |
| **SEVENKINGDOMS** | `vmnet20` | `10.4.20.0/24` | Kingslanding `10.4.20.10` |
| **ESSOS** | `vmnet30` | `10.4.30.0/24` | Meereen `10.4.30.12`, Braavos `10.4.30.23` |
| **MANAGEMENT** | `vmnet99` | `10.4.99.0/24` | Router management plane |

The student attack host connects directly to **NORTH**.

The host does not receive direct adapters into SEVENKINGDOMS or ESSOS. Those zones must be reached through the paths intentionally exposed by the range.

### Exercise policy

The exercise plane preserves only the cross-zone relationships required by the environment and the designed attack paths.

Examples include:

- NORTH child-domain ↔ SEVENKINGDOMS parent-domain directory communication;
- SEVENKINGDOMS ↔ ESSOS forest-trust communication;
- required cross-forest DNS;
- the deliberate Castelblack ↔ Braavos MSSQL relationship;
- established and related return traffic.

Everything else crossing the routed exercise plane is denied by default.

---

## Two lifecycle modes

Kingdoms always remains segmented. The two modes control whether temporary operator-management paths are available.

### `provisioning`

Used by installation and maintenance.

- management adapters are available;
- temporary protected-zone host routes are enabled;
- the router permits provisioning traffic;
- authenticated Windows and directory readiness is checked before automation proceeds.

### `exercise`

The normal student-facing state.

- management adapters are persistently disconnected;
- temporary protected-zone host routes are removed;
- the router returns to deny-by-default forwarding;
- NORTH remains the initial student zone;
- only designed cross-zone relationships remain available.

A successful install and a successful normal start both finish in **exercise mode**.

---

## Quick start

### Preflight

Before creating a new range:

```bash
cd <path-to-kingdoms-repository>

git switch main
git pull --ff-only

sudo -v
bash scripts/preflight-goad-kingdoms-fresh-install.sh
```

The expected result is:

```text
FAIL: 0
KINGDOMS_FRESH_INSTALL_PREFLIGHT_READY=True
```

### Fresh installation

```bash
./goad.sh -t install -l GOAD -p vmware
```

The CLI path is designed for unattended installation after the initial sudo authentication. It includes lifecycle timing, bounded VMware recovery and final exercise-mode isolation.

### Interactive management console

```bash
./goad.sh
```

Common commands:

```text
list
status
start
stop
validate
network
mode status
```

### Clean-install acceptance

After a fresh build, validate the exact new provider explicitly:

```bash
GOAD_PROVIDER_DIR="$PWD/workspace/<INSTANCE_ID>/provider" \
bash scripts/validate-goad-kingdoms-clean-install-runtime.sh
```

Successful acceptance confirms the segmented relationships, WS01 foundation, all 20 LPE scenarios and final exercise isolation against the newly created instance.

---

## Phase 03 engineering acceptance

The completed Phase 03 baseline is protected by a dedicated final orchestrator.

Accepted results:

```text
PASS: 11
FAIL: 0
PHASE03_FINAL_REGRESSION_COMPLETE=True
```

The final regression covers:

- source identity and source tests;
- Phase 03 runtime/readiness;
- pre- and post-run residual-state checks;
- earlier-phase readiness;
- MSSQL;
- RDP;
- the full segmentation lifecycle;
- WS01 foundation;
- permanent Rickon victim-session lifecycle;
- restoration to a neutral exercise state.

The release-only RDP gate additionally proved fourteen expected denials and one fresh Rickon → WS01 non-admin interactive allow:

```text
RDP_DESKTOP_LOGON_MATRIX=PASS:15/15
RDP_RELEASE_ACCEPTANCE_COMPLETE=True
```

---

## What comes next

### Finish Phase 03 curriculum

The infrastructure is complete. The current work is turning the validated attack paths into the final **Poison The Wells** teaching experience with the same depth and attacker-thinking cadence used in the previous phases.

### Later curriculum expansion

Planned directions include:

- network pivoting and proxy-aware movement;
- unified ADCS training;
- Kerberos delegation;
- ACL abuse;
- server privilege escalation;
- domain and forest trust abuse;
- advanced domain escalation;
- persistence;
- cross-domain progression;
- cross-forest progression.

Deferred Phase 03 candidates already tracked for later implementation:

- DFSCoerce / MS-DFSNM;
- ShadowCoerce / MS-FSRVP.

These do not block the current Phase 03 baseline.

---

## Design principles

Kingdoms changes carefully. A new technique or feature should not silently weaken earlier phases just to make a later attack easier.

The project follows several recurring rules:

1. **Student isolation is a security boundary.** Provisioning access must not leak into the exercise surface.
2. **State-changing attacks must be reversible.** Capture the baseline, mutate deliberately, prove consequence, roll back exactly, and verify restoration.
3. **Runtime proof matters more than configuration intent.** A file saying something is enabled is weaker evidence than the live system proving it.
4. **Validation should fail closed.** A broken directory relationship, management channel or exercise boundary should stop the lifecycle instead of being hidden.
5. **Fresh installation must remain reproducible.** Long-lived development state is never accepted as the only proof that a feature works.
6. **The course teaches reasoning, not command memorization.** Tools are part of the interaction, not the lesson itself.

---

## Repository notes

A few filenames, commands and VM identifiers retain historical compatibility names. Renaming them purely for appearance would risk breaking a validated environment, so those identifiers are being treated as implementation details rather than branding.

The public face of the project, its curriculum and its future direction are **Kingdoms**.

---

## Responsible use

Kingdoms is intentionally vulnerable and is designed for controlled education, research and authorized offensive-security training.

Run it only in environments you own or are explicitly authorized to test. Do not expose vulnerable lab systems directly to untrusted networks.

---

## License

This repository retains the licensing obligations and history of its upstream foundation. See [LICENSE](LICENSE) for the applicable terms.
