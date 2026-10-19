## Deferred / Future Features

The repository backlog for intentionally deferred Kingdoms capabilities is:

- `docs/KINGDOMS_FUTURE_FEATURES.md`

Current deferred Phase 03 candidates include DFSCoerce / MS-DFSNM and
ShadowCoerce / MS-FSRVP. They do not block closure of the current Phase 03
baseline.

# Kingdoms — Major Project Milestones

This is the canonical engineering milestone tracker for **Kingdoms**.

The project was named **GOAD_NOMAD** through Milestone 1 and the `v1.0.0 — Segmented Foundation` release. Historical v1.0.0 release notes and the original Milestone 1 record keep that name intentionally. Development after v1.0.0 uses the **Kingdoms** identity.

A milestone is COMPLETE only after its implementation exists in committed Git source and its end-to-end validation gates pass from an origin-synchronized checkout. The mandatory development/test workflow is documented in [`DEVELOPMENT_WORKFLOW.md`](./DEVELOPMENT_WORKFLOW.md).

> [!IMPORTANT]
> **Engineering milestones and student learning Parts are different things.**
>
> Milestones describe what the project builds and validates. Parts describe what the student learns and in which pedagogical order. A single milestone may support several student Parts, and a student Part may reuse capabilities delivered across several milestones.

The project intentionally preserves the progressive learning philosophy of the original GOAD walkthrough while extending the environment with a first-class Windows workstation, Windows local privilege escalation, network segmentation, pivoting, consolidated subject chapters, and a much larger advanced Active Directory technique catalog.

---

## Architecture baseline

The segmented architecture established in v1.0.0 remains the network contract for all later milestones.

| VMware network | Zone | Subnet | Host-side access | Router address |
| --- | --- | --- | --- | --- |
| `vmnet10` | NORTH | `10.4.10.0/24` | `10.4.10.254/24` | `10.4.10.1/24` |
| `vmnet20` | SEVENKINGDOMS | `10.4.20.0/24` | none | `10.4.20.1/24` |
| `vmnet30` | ESSOS | `10.4.30.0/24` | none | `10.4.30.1/24` |
| `vmnet99` | MANAGEMENT | `10.4.99.0/24` | `10.4.99.254/24` | `10.4.99.1/24` |

Current Windows placement:

| Host | Role | Zone | Address |
| --- | --- | --- | --- |
| GOAD-DC02 / Winterfell | NORTH child-domain DC | NORTH | `10.4.10.11` |
| GOAD-SRV02 / Castelblack | NORTH member server / IIS / MSSQL | NORTH | `10.4.10.22` |
| GOAD-WS01 / WS01 | NORTH Windows workstation | NORTH | `10.4.10.31` |
| GOAD-DC01 / Kingslanding | root-domain DC | SEVENKINGDOMS | `10.4.20.10` |
| GOAD-DC03 / Meereen | ESSOS DC | ESSOS | `10.4.30.12` |
| GOAD-SRV03 / Braavos | ESSOS server / MSSQL / ADCS | ESSOS | `10.4.30.23` |
| GOAD-ROUTER | Debian routing plane | all zones | `.1` on each project zone |

The exercise firewall baseline preserves only the communication required for inherited GOAD relationships and deliberate training paths:

- Winterfell ↔ Kingslanding: required parent/child DC communication.
- Kingslanding ↔ Meereen: required forest-trust DC communication.
- Winterfell ↔ Meereen: TCP/UDP 53 for the validated cross-forest DNS path.
- Castelblack ↔ Braavos: TCP 1433 for the deliberate linked-SQL path.
- established/related return traffic.
- all other forwarded traffic denied by default.

The student attack machine starts in NORTH. SEVENKINGDOMS and ESSOS are not directly exposed through host-side VMware adapters.

---

## Source-of-truth rule

Testing follows one direction only:

```text
Git change -> commit -> push -> test checkout sync -> source gate -> test
```

Before milestone or reproducibility testing:

```bash
bash scripts/verify-test-source.sh
```

No milestone may be closed from a test checkout containing source changes that do not exist in Git.

---

# Completed work

## Milestone 1 — Network Segmentation

**Status: COMPLETE / RELEASED AS GOAD_NOMAD v1.0.0**

Release: **v1.0.0 — Segmented Foundation**  
Final validated source: `35f592184e87ba25f427403fde4674b444aad6c8`  
Final validation: **27 PASS / 0 WARN / 0 FAIL**  
Final runtime mode: **exercise**

Milestone 1 established:

- segmented NORTH / SEVENKINGDOMS / ESSOS / MANAGEMENT VMware networks;
- GOAD-ROUTER as the routed control plane;
- provisioning and exercise modes;
- persistent Windows provisioning-NAT isolation;
- deny-by-default exercise routing;
- router-first/fail-closed provider startup;
- bounded segmented `start` / `stop` lifecycle;
- VMware Tools/IP discovery recovery;
- deterministic WinRM management readiness;
- GOAD-compatible SSMS 18 provisioning;
- DNS/ADWS hardening exposed by clean-install testing;
- clean-source/runtime validation of trusts, GOAD bots, linked SQL and isolation.

The detailed historical M1 record remains at [`GOAD_NOMAD_MILESTONES.md`](./GOAD_NOMAD_MILESTONES.md) because it documents the project under the name used when v1.0.0 was built and released.

---

## Milestone 2 — NORTH Workstation Foothold & Windows Local Privilege Escalation

**Status: COMPLETE — RELEASED AS GOAD KINGDOMS v1.1.0**

Release: **v1.1.0 — NORTH Workstation & Windows LPE**  
Final validated source: `6285838af4dca55704092e2a6c0cc6a131be798f`  
Final runtime mode: **exercise**

### Goal

Add one first-class Windows workstation to NORTH and extend the beginning of the GOAD learning journey:

```text
valid NORTH user
    -> WS01 low-privilege foothold
    -> Windows local privilege escalation
    -> local Administrator / SYSTEM
    -> continue into the broader GOAD / Kingdoms learning path
```

Milestone 2 is an extension to GOAD's learning journey, not a separate standalone CTF.

### Validated WS01 foundation

WS01 clean-foundation validation completed on **2026-09-02** from origin-synchronized source.

| Property | Validated value |
| --- | --- |
| VMware VM | `GOAD-WS01` |
| Hostname | `WS01` |
| Zone | NORTH |
| Exercise NIC | `vmnet10` |
| Exercise address | `10.4.10.31/24` |
| Gateway | `10.4.10.1` |
| Domain | `north.sevenkingdoms.local` |
| Windows baseline | Windows 10 Enterprise 22H2 (`mayfly/windows10`) |
| Vagrant box version | `2024.01.06` |
| Starting identity | `NORTH\\rickon.stark` |
| Provisioning | Vagrant NAT using the M1 provisioning/exercise lifecycle contract |

Validated foundation properties:

- `NORTH\\rickon.stark` receives Remote Desktop access but is not a local administrator;
- provisioning NAT is persistently disabled in exercise mode;
- RDP (`3389/tcp`) and WinRM HTTPS (`5986/tcp`) are reachable from NORTH;
- UAC, Windows Firewall and Defender remain enabled;
- WS01 participates in domain enrollment, lifecycle control and management readiness;
- ICMP echo is not treated as a workstation health requirement because the intended service contract is RDP/WinRM.

### Windows LPE architecture

Kingdoms implements an Ansible-native, deterministic and resettable Windows LPE role rather than globally weakening the workstation.

The validated deterministic core contains exactly **20 techniques**:

1. unquoted service paths;
2. weak service DACLs;
3. weak service binary permissions;
4. weak service registry permissions;
5. service DLL hijacking;
6. PATH search-order hijacking;
7. AlwaysInstallElevated;
8. registry Run keys;
9. writable Startup folder;
10. scheduled-task binary permissions;
11. scheduled-task directory permissions;
12. unattend credential artifacts;
13. PowerShell history credential artifacts;
14. hardcoded application credentials;
15. stored RunAs credentials;
16. stored Winlogon credentials;
17. SeBackupPrivilege;
18. SeImpersonatePrivilege;
19. writable Program Files directory;
20. insecure custom service registry configuration.

Patch/build-dependent kernel CVEs remain optional additions rather than part of the deterministic core.

Profiles:

- `service-abuse`
- `credential-hunting`
- `registry-abuse`
- `token-abuse`
- `mixed`
- `full-lpe`

Every implemented technique passed the complete reversible lifecycle:

```text
apply -> validate vulnerable -> reset -> validate clean -> reapply -> validate vulnerable
```

### Final M2 acceptance

Final origin-synchronized clean-install acceptance passed on **2026-09-03** at `6285838af4dca55704092e2a6c0cc6a131be798f`.

Validated results included:

- network segmentation runtime: **28 PASS / 0 WARN / 0 FAIL**;
- parent/child trust: PASS;
- cross-forest DNS: PASS;
- Castelblack → Braavos linked SQL: PASS;
- WS01 low-privilege foundation: PASS;
- all 20 LPE scenarios apply/reset/reapply lifecycle: PASS;
- final state: **20 techniques APPLIED / VULNERABLE** for training;
- all six Windows provisioning NAT paths persistently isolated;
- router returned to deny-by-default `exercise` policy.

Milestone 2 is complete.

### Separate standalone Windows LPE course — 41-scenario deployment checkpoint (2026-10-19)

**Status: DEPLOYMENT COMPLETE / SCOPE FROZEN — COURSE RELEASE NOT YET ACCEPTED.**

This is a separate `WSLPE-WS01` Windows 10 **workgroup** course environment, not the NORTH domain-joined WS01 of Milestone 2. The user approved closing the earlier 45-target work at **41 active scenarios**: 20 standalone baseline entries (operator-reported, not recounted by this final journal) plus 21 newer scenarios with installation and vulnerable-configuration validation PASS. Four numbered candidates, #25/#36/#38/#40, are out of scope for the current course and must not be treated as pending blockers. Existing numeric IDs and historical `45` engineering filenames remain unchanged for provenance.

Guest evidence: private journal `wslpe45-resume-registered27-77c4f73d6782a328.json` reports `completed=true`, `failure=null`, `inflight=null` and `runtime_configuration_pass_count=21`, from committed source `6b612e9abf2547dc76e4d4a89f4df1be6137f6e6`. The final record preserves successful #27 in-place recovery and #30 existing-JEA validation. Learner exploitation for the 21 additions remains `NOT_TESTED`; six-stage qualification, student isolation/release checks and walkthroughs belong to subsequent phases. **Do not claim the course has been released.**

See [standalone WSLPE41 deployment closeout](./WSLPE41_DEPLOYMENT_CLOSEOUT_2026-10-19.md). This feature-branch engineering checkpoint does not alter the already released NORTH Milestone 2.

---

## v1.1.1 — Lifecycle Reliability Maintenance

**Status: COMPLETE — RELEASED AS GOAD KINGDOMS v1.1.1**

This is a maintenance release after Milestone 2, not a new student-learning milestone.

Release: **v1.1.1 — Lifecycle Reliability**  
Validated implementation: `e40f7d2e7fdbcdbe5de342787471ade4b4f54c9c`  
Release commit: `db4ca4cd3a84f3e13728ddc902117c9d16df2cce`

### Start lifecycle fix

Real long-running startup exposed a sudo-timestamp race: the lab could spend several minutes starting guests and only later discover that sudo had expired when temporary provisioning routes were needed.

v1.1.1 now:

- authenticates sudo before any VM state changes;
- starts a non-interactive sudo keepalive during segmented startup;
- runs network and collision preflight before guest bring-up;
- fails closed if privileged lifecycle state cannot be maintained;
- restores the recorded exercise mode before reporting success.

Validated with an intentionally expired sudo ticket and an approximately 7.5-minute real VMware startup.

### Stop lifecycle fix

A bounded global `vagrant halt` could time out while Vagrant/Ruby descendants still owned per-machine action locks. The old fallback could then race a second Vagrant operation against the same guest.

v1.1.1 now:

- runs bounded Vagrant commands in their own process group;
- terminates and fully reaps the complete Vagrant/Ruby process tree after timeout;
- refuses fallback until the previous controller is proven gone;
- allows already-requested guest shutdowns a grace period;
- uses VMware soft shutdown as the lock-free fallback;
- uses hard stop only as the final fallback;
- verifies final VMware power state before reporting success.

The real 180-second timeout path was exercised during validation. No Vagrant action-lock race was reproduced, and all six Windows guests plus GOAD-ROUTER finished powered off.

The merged `main` clean-install source gate passed after the maintenance fix.

---

## Maintenance backlog — post-release technical debt

These items were identified while stabilizing the current fresh-install/runtime lifecycle. They are deliberately tracked as maintenance work rather than being folded opportunistically into release acceptance.

### Ansible / dependency maintenance

- [ ] Migrate deprecated `ansible.windows.win_domain` to `microsoft.ad.domain`.
- [ ] Migrate deprecated `ansible.windows.win_domain_controller` to `microsoft.ad.domain_controller`.
- [ ] Migrate deprecated `ansible.windows.win_domain_membership` to `microsoft.ad.membership`.
- [ ] Migrate deprecated `community.windows.win_domain_group_membership` to the supported `microsoft.ad` group-management equivalent.
- [ ] Pin and regression-test compatible `ansible.windows`, `community.windows`, and `microsoft.ad` collection versions so future collection upgrades cannot silently break provisioning.
- [ ] Remove the `reset_connection task does not support when conditional` warning in the trust/NAT transition flow without changing lifecycle semantics.

### Idempotency / lifecycle cleanup

- [ ] Review child-domain/DNS replay tasks that still report `changed` on subsequent validation runs and make genuinely repeatable configuration idempotent where possible.
- [ ] Improve non-interactive destroy behavior. `./goad.sh -t destroy -i <instance>` currently reaches interactive `vagrant destroy`; scripted use should confirm once at the Kingdoms controller boundary and then destroy non-interactively.
- [ ] Keep the current fail-closed AD readiness and exercise-isolation contracts intact while making the maintenance changes above.

### Install / startup performance

- [ ] Shorten the full Kingdoms lab `start` lifecycle from the current validated baseline of roughly **10–11 minutes on an already-running host** and **15–17 minutes after a full host reboot**, without weakening any readiness or isolation guarantee.
- [ ] Profile startup by phase before changing behavior so the actual cost of router/network preparation, guest boot, WinRM, AD dependency gates, NT5DS convergence and exercise-mode restoration is measurable.
- [ ] Reduce VMware Tools / VIX guest-IP telemetry recovery overhead when authenticated WinRM and guest-side VMware Tools health are already authoritative.
- [ ] Profile and shorten the slowest fresh-build recovery cycles, especially WS01 and member-server first boot, without weakening readiness checks.
- [ ] Cache/pin PowerShell Gallery dependencies such as ActiveDirectoryDSC to reduce download latency and transient external failures.
- [ ] Evaluate safe dependency-aware parallelism for independent topology branches instead of serializing every machine. Preserve the dependency contract: DC01 and DC03 may proceed independently; DC02 waits for DC01; SRV02 and WS01 wait for DC02; SRV03 waits for DC03.
- [ ] Preserve NT5DS validation, bounded WinRM readiness, secure-channel / Netlogon checks, authenticated exercise-mode readiness proof, persistent NAT-off state, provisioning-route cleanup and fail-closed router isolation while optimizing startup.
- [ ] Add a faster development path that can reuse cached artifacts/base state, while keeping the true zero-state build as the release acceptance path.
- [ ] Consider explicit install/validation modes such as fast, full, and release after the current lifecycle is frozen.

### Low-priority naming cleanup

- [ ] Review remaining internal `GOAD_NOMAD` compatibility identifiers after lifecycle stabilization. Do not rename state files, scripts, or compatibility contracts purely cosmetically if doing so risks regressions.

---

## Phase 03 engineering baseline — Poisoning and relay

**Status: COMPLETE / VALIDATED / FROZEN FOR INTEGRATION**

The NORTH poisoning-and-relay runtime is now a validated Kingdoms baseline rather
than an experimental overlay.

Delivered attack/runtime families include:

- LLMNR, NBT-NS and mDNS poisoning with NetNTLMv2 capture;
- SMB relay target selection, automated relay, interactive relay and SOCKS reuse;
- privilege-dependent SMB consequences including share access, remote execution,
  LSASS material and native DPAPI credential decryption;
- MSSQL `xp_dirtree` outbound authentication coercion;
- PrinterBug / MS-RPRN and PetitPotam / MS-EFSR coercion;
- mitm6 IPv6/DNS takeover and WPAD;
- HTTP -> LDAPS read-only relay;
- RBCD via relay with S4U consequence and exact rollback;
- Shadow Credentials via relay with PKINIT consequence and exact rollback;
- ADIDNS secure record injection with exact absent-state restoration;
- WebDAV / malicious `.lnk` authentication behavior with exact service/DNS reset;
- permanent Rickon WS01 victim-session lifecycle with release-grade RDP acceptance.

Final acceptance on 2026-09-26:

- Phase 03 final orchestrator: **11 PASS / 0 FAIL**;
- NORTH segmentation lifecycle: **29 PASS / 0 WARN / 0 FAIL**;
- final no-residual-state gate: **PASS**;
- fresh NORTH RDP desktop-logon matrix: **15/15 PASS**;
- restored permanent Rickon runtime: **5 PASS / 0 FAIL**;
- final lab mode: `exercise`.

DFSCoerce / MS-DFSNM and ShadowCoerce / MS-FSRVP are deliberately deferred to
the future-feature backlog and do not block the current Phase 03 baseline.

The remaining Phase 03 work is curriculum production: final GOAD Part 4 parity
review, screenshot selection and the Notion teaching walkthrough.

---

# Student learning path

Kingdoms preserves the style of Mayfly's GOAD walkthrough while adding learning stages that the original flat/server-focused environment did not provide.

The intended curriculum is currently structured as follows:

| Part | Learning stage | Direction |
| --- | --- | --- |
| 1 | Reconnaissance and scanning | Preserve / expand original GOAD Part 1 |
| 2 | Finding users and unauthenticated enumeration | Preserve / expand original GOAD Part 2 |
| 3 | Authenticated enumeration via Linux | Expanded GOAD authenticated-enumeration stage |
| 4 | Authenticated enumeration via Windows | **Kingdoms addition using WS01** |
| 5 | Windows local privilege escalation | **Implemented in v1.1.0 — 20-technique catalog** |
| 6 | Poisoning and relay | Preserve original GOAD poison/relay learning stage |
| 7 | Exploitation with a domain user | Preserve / expand original GOAD authenticated exploitation |
| 8 | Active Directory Certificate Services | **Unified Kingdoms ADCS chapter** rather than two separate ADCS chapters |
| 9 | MSSQL attacks | Preserve / expand original GOAD MSSQL material |
| 10 | Server privilege escalation | Preserve server-side privilege-escalation context separately from WS01 LPE |
| 11 | Lateral movement | Preserve / expand original GOAD lateral-movement material |
| 12 | Network pivoting | **Kingdoms addition enabled by real segmentation** |
| 13 | Kerberos delegation | Preserve / expand unconstrained, constrained and RBCD learning |
| 14 | Active Directory ACL abuse | Preserve / expand GOAD ACL material |
| 15 | Domain and forest trusts | Preserve GOAD trust learning and combine it with network boundaries |
| 16 | Advanced domain attacks | Preserve GOAD advanced material and expand the technique catalog |
| 17+ | Persistence, cross-domain, cross-forest and later advanced material | Kingdoms expansion using additional Red Team / CRTE-style scenarios |

This is a learning path, not a requirement that every exercise be solved through one rigid attack chain. Individual vulnerabilities remain useful as focused labs while the full environment provides context and progression.

---

# Planned engineering milestones

## Milestone 3 — Authenticated Enumeration & Learning-Path Integration

**Status: PLANNED / NEXT**

Milestone 3 will connect the existing GOAD progression to the WS01/LPE work already delivered in Milestone 2.

The immediate objective is **not** to jump directly to NORTH Domain Admin or domain persistence. The objective is to make the student journey coherent before adding more advanced attack paths.

### M3 student progression target

```text
Part 1 — Reconnaissance
    -> Part 2 — unauthenticated enumeration / first valid NORTH identity
    -> NORTH\\rickon.stark
    -> Part 3 — authenticated enumeration via Linux
    -> discover and understand WS01 access
    -> Part 4 — authenticated enumeration via Windows on WS01
    -> Part 5 — Windows local privilege escalation
    -> Administrator / SYSTEM
    -> continue naturally into Part 6 and the wider GOAD learning path
```

### Part 3 — Authenticated enumeration via Linux

The student remains on the attack host and learns how a valid domain identity changes enumeration capability.

Planned learning areas include:

- LDAP/domain discovery;
- users and groups;
- computers and services;
- SMB shares and permissions;
- DNS;
- SPNs and Kerberos-oriented enumeration;
- BloodHound-compatible collection from Linux;
- identifying where the current identity can authenticate or obtain an interactive foothold;
- discovering WS01 as a logical next learning target rather than being told to teleport directly to it.

### Part 4 — Authenticated enumeration via Windows

After obtaining access to WS01, the student learns the same Active Directory concepts from a domain-joined Windows endpoint.

Planned learning areas include:

- current user, token, groups and privileges;
- local-versus-domain security context;
- native domain discovery;
- Active Directory PowerShell enumeration where appropriate;
- users, groups and computers;
- shares and SYSVOL;
- Windows DNS tooling;
- Kerberos ticket inspection;
- Windows-native BloodHound / SharpHound collection;
- local workstation enumeration that naturally prepares the student for Part 5.

### Part 5 integration

The Windows LPE catalog itself is already implemented and validated in v1.1.0. M3 will integrate that existing capability into the documented learning sequence rather than rebuilding it.

The campaign path only needs a valid local escalation route to continue; the complete 20-technique catalog remains available for focused Windows LPE study and repeatable practice.

### M3 design constraints

Milestone 3 must:

1. preserve the original GOAD learning philosophy rather than replace it with a rigid CTF chain;
2. clearly separate Linux and Windows authenticated-enumeration methodology;
3. make WS01 a discovered/useful workstation stage in the journey;
4. avoid unintentionally exposing later high-value attack paths so early that the workstation learning stage becomes optional by accident;
5. preserve the existing poison-and-relay subject as a later dedicated learning Part rather than deleting it;
6. preserve all v1.1.1 segmentation, lifecycle and isolation guarantees;
7. remain deterministic and source-testable like M1/M2.

### M3 acceptance direction

M3 will require source/runtime evidence that:

- Rickon remains a low-privilege NORTH identity;
- Linux authenticated enumeration exposes the intended domain information;
- WS01 access is discoverable and usable;
- Windows authenticated enumeration works from the domain-joined workstation;
- the existing LPE catalog remains intact and reversible;
- no M3 curriculum change accidentally grants direct Domain Admin, parent-domain or ESSOS control;
- inherited trusts, DNS, linked SQL and exercise isolation remain green.

---

## Milestone 4 — Pivoting & Segmented Movement

**Status: PLANNED**

Use the M1 network boundaries as a first-class learning feature rather than only an infrastructure control.

Planned scope includes:

- route and interface discovery from compromised systems;
- understanding direct versus routed reachability;
- SOCKS-style pivoting;
- port forwarding and tunneling concepts;
- proxy-aware tooling;
- accessing services through a pivot without reintroducing the provisioning bypass;
- later multi-hop/double-pivot exercises where the topology supports them.

The objective is for students to learn that owning an identity or machine does not automatically provide network reachability to every security zone.

---

## Milestone 5 — Unified Active Directory Certificate Services Curriculum

**Status: PLANNED**

Consolidate the ADCS learning material into one Kingdoms subject rather than splitting certificate-service attacks across separate distant chapters.

The chapter can grow incrementally as deterministic ADCS scenarios are implemented, while keeping enumeration, template abuse, certificate authentication and advanced ESC techniques in one coherent place.

The existing Braavos ADCS role remains the initial foundation.

---

## Milestone 6 — Advanced Domain Escalation & Persistence

**Status: PLANNED**

Expand beyond the core GOAD technique set with additional deterministic domain-escalation and persistence scenarios.

Candidate subject families include:

- targeted Kerberoasting;
- LAPS-related attack paths;
- gMSA abuse;
- richer delegation scenarios;
- Shadow Credentials;
- additional ACL combinations;
- credential/ticket material accessible after host compromise;
- Golden, Silver, Diamond and Sapphire ticket concepts where appropriate;
- AdminSDHolder persistence;
- other deterministic domain-persistence exercises.

The exact implementation set will be chosen incrementally and validated rather than enabled all at once.

---

## Milestone 7 — Cross-Domain Progression

**Status: PLANNED**

Expand NORTH child-domain → `sevenkingdoms.local` parent-domain progression so identity/trust abuse must coexist with the validated segmented network model and pivoting requirements.

Candidate advanced material includes child/root trust-key and SID-history style paths where appropriate for the lab.

---

## Milestone 8 — Cross-Forest Progression

**Status: PLANNED**

Preserve and expand SevenKingdoms/NORTH → `essos.local` attack paths, including the deliberate Castelblack ↔ Braavos MSSQL relationship and selected cross-forest techniques.

Candidate advanced material includes:

- cross-forest Kerberoasting;
- cross-forest constrained/unconstrained delegation;
- Foreign Security Principals and ACLs;
- trust-key abuse;
- SID filtering concepts;
- MSSQL database links;
- trust transitivity;
- PAM / Shadow Security Principals where compatible with the lab model.

---

## Milestone 9 — Optional Advanced / Hybrid / Defense-Evasion Layers

**Status: OPTIONAL / FUTURE**

Potential later scope includes:

- selected endpoint defense-evasion exercises;
- richer operational tradecraft;
- hybrid identity scenarios such as PHS/Azure AD integration if a suitable deterministic environment is added;
- additional Red Team material that does not fit naturally into the core GOAD domain/forest progression.

These layers must not weaken the stable default lab merely to make advanced exercises easier.

---

# Intended end-to-end progression

The current long-term learning direction is:

```text
NORTH reconnaissance
    -> first valid NORTH identity
    -> authenticated enumeration from Linux
    -> WS01 foothold
    -> authenticated enumeration from Windows
    -> Windows local privilege escalation
    -> poison / relay and authenticated GOAD attack material
    -> MSSQL / server exploitation / lateral movement
    -> real network pivoting across segmented zones
    -> delegation / ACL / ADCS / advanced domain attacks
    -> NORTH domain compromise and persistence
    -> SEVENKINGDOMS parent-domain progression
    -> ESSOS cross-forest progression
```

The conceptual security-scope progression remains:

```text
Machine -> Domain -> Parent Domain -> Forest -> Foreign Forest
```

The core project principle is that Kingdoms should continue teaching **what** GOAD teaches, while adding more realistic opportunities to learn **where**, **when**, and **why** those techniques are used in a segmented Windows/Active Directory environment.