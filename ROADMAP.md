# Kingdoms Roadmap

This roadmap tracks the work required to make future Kingdoms installations deterministic, recoverable and portable without destabilizing currently working deployments.

Baseline audited: `4ca0be89b2552c421942a1f1a1674752e569a903`.

## Mandatory priority order

Work must follow this order. A lower-priority platform expansion must not displace an unfinished reliability or isolation item.

| Priority | Scope | Start condition |
| --- | --- | --- |
| **P0** | Current Kingdoms VMware correctness and fail-closed isolation | Start immediately |
| **P1** | Fresh-install bootstrap and dependency reliability | After P0 behavior is protected by regression tests |
| **P2** | Automated validation and release gates | Develop alongside P0/P1; complete before provider expansion |
| **P3** | Provider-neutral lifecycle contracts; VirtualBox follow-up deferred | Only after all P0 items and required P1/P2 gates are complete |
| **P4** | Course 1 Ludus on Proxmox | After Course 1 VMware release and required provider-neutral contracts are validated; VirtualBox is not a prerequisite |
| **P5** | Windows host and additional provider support | Later: after the relevant existing-provider foundations are complete |

**Hard gate:** do not start Windows host implementation while any P0 item remains open. Windows design and research may be recorded, but implementation waits until the existing installation and isolation lifecycle is dependable.

## Course rollout sequence — explicit provider priority

**Active course target: Kingdoms Course 1 — Fall of the North.**

1. **Now — VMware Workstation:** finish the isolated four-Windows-VM + router installer, per-instance network identities, KINGDOMS2 SQL, lifecycle, reset and Phase 03 attack parity. Complete the Course 1 walkthrough and VMware release acceptance.
2. **Next — Ludus on Proxmox:** after VMware Course 1 is ready, port the *same validated course profile* into Ludus. Validate template provisioning, per-learner instance isolation, routed WireGuard access and the dedicated attacker Layer 2 path needed for NORTH poisoning/relay demonstrations. Do not declare Ludus supported before its own end-to-end acceptance.
3. **Later — other providers/courses:** VirtualBox, direct Proxmox control, Windows hosts and future Course 2 profiles are separate backlog tracks. The existing six-Windows-VM reference environment must not automatically be renamed Course 2.

**Architectural rule:** a Kingdoms course profile describes the domain topology, roles, exercises and required behavior; a provider adapter implements deployment, network attachment and lifecycle. Neither course identity nor installation authority may be inferred from Git branch, VM name or a CLI-only profile label. Bind both to a validated installed instance.

The necessary **provider-neutral contracts** from P3 must precede Ludus. VirtualBox-specific work listed under P3 is deferred, so it does not block the user-prioritized Ludus rollout. No Ludus implementation should interrupt the current VMware Course 1 reliability and release gates.

## Mandatory Kingdoms foundation contract

**Never use upstream GOAD as the source for NORTH or future courses.**
Every course inherits the validated, patched **Kingdoms** provisioning,
AD readiness, VMware Tools/WinRM recovery, lifecycle, network isolation,
collision protection, sudo authorization, rollback and logging foundations.
Legacy folders/VM names (\`ad/GOAD\`, \`GOAD-DC01\`, \`goad.sh\`) exist for
compatibility with the working reference, not to authorize upstream defaults.

- [x] Declare a Kingdoms foundation identity for NORTH and future course
  manifests; reject missing/mismatched identities.
- [x] Verify the current patched Kingdoms source before rendering reduced
  NORTH preview artifacts; add removal/failure regressions.
- [ ] Extract a reusable, course-neutral Kingdoms base from the existing
  patched reference **without losing behavior or changing the installed
  reference**; replace transitional \`ad/GOAD\` source derivation.
- [ ] Port the established source/runtime/integration regression gates
  into the course-neutral provider lifecycle contract.
- [ ] Prove NORTH clean install/start/stop/mode/reset/failure rollback,
  dual-domain AD/SQL and Phase 03 offensive parity on a disposable instance
  before marking its VMware provider available.
- [ ] Ensure future Course 2+ lab recipes use that validated reusable
  Kingdoms foundation rather than copied GOAD topology/config defaults.

Full policy: \`docs/kingdoms-foundation.md\`.

## Native Kingdoms lab catalog — one console for every course

**Canonical operator entry point:** `./goad.sh` at the root of the
**primary Kingdoms project**. Lab identities are native `ad/<LAB>` recipes
and appear in the existing `labs` command. Their provider adapters and
installed instances stay scoped to that selected lab; separate source
checkouts are temporary developer working trees, not an operational UI.

**Course 1 identity:** `NORTH` (course title: *Fall of the North*).
`ad/NORTH/course.json` maps it to
`course1-fall-of-the-north` and declares VMware `preview` only.
`ad/NORTH/providers/vmware` participates in the existing lab directory
discovery; the console displays `preview` rather than a misleading
green supported-provider check. `unload` the loaded reference
GOAD instance, then `labs` and `set_lab NORTH` to select the new
lab. **NORTH install/create/provision/start/stop remain blocked** until
the provider and per-instance lifecycle pass release acceptance.

Once released, native `set_lab NORTH` → `install` creates an independent
instance with exactly four Windows guests and its Debian router. A
future Course 2 will get another named `ad/<LAB>/course.json` profile,
its own provider recipe and isolated instances; no Course 2 has been
named or deployed. Ludus is the subsequent provider for NORTH after
VMware Course 1 release. Never present the older GOAD/ESSOS reference
as a Course 2 release.

**Merge contract:** the existing `main` checkout keeps the live
`GOAD` reference lab until all changes are reviewed. Native NORTH
registration currently lives only in draft PR #30. Do not synchronize
the feature checkout's empty `workspace` over the existing main
`workspace`; merging Git source does not migrate installed VM state.

## Delivery policy

- Implement each checklist item in a separate issue and pull request.
- Do not test risky lifecycle or dependency changes first against the working `16b7a2` lab.
- Require source validation, failure-path testing and a rollback plan before merge.
- Preserve deny-by-default exercise isolation.
- Treat a non-zero provider, provisioning, extension or isolation result as an installation failure.
- Complete P0–P2 reliability gates before provider expansion. For P3→P4, validate the provider-neutral contracts first; VirtualBox-specific implementation is deferred until after the Ludus Course 1 rollout.

## P0 — Current installation correctness and isolation

These findings from the full-project audit have priority over every new platform or provider.

- [ ] Propagate truthful noninteractive CLI exit codes for install, start, stop and validate.
- [ ] Propagate extension installation and provisioning failures.
- [ ] Restore the original network mode after failed or interrupted provisioning.
- [ ] Make cleanup conditional and idempotent when only part of the VM set exists.
- [ ] Verify actual VMware runtime NIC state instead of ignoring `vmrun` device errors.
- [ ] Add bounded retries for VMware device transitions.
- [ ] Make provisioning-mode entry transactional with rollback for partial failures.
- [ ] Record enough transition state to recover safely after interruption.
- [ ] Prove failed provisioning cannot leave NAT, protected host routes or permissive router forwarding enabled.
- [ ] Add focused fault-injection regression tests for every repaired lifecycle path.

### P0 completion gate

- Every lifecycle failure returns non-zero.
- Every failure either restores the original mode or reports a verified fail-closed state.
- Re-running install after an injected failure succeeds without manual network repair.
- The existing VMware deployment passes source and runtime segmentation validation.

## P1 — Bootstrap and dependency reliability

- [ ] Build `~/.goad/.venv` atomically in a temporary location.
- [ ] Preserve an existing valid environment when bootstrap fails.
- [ ] Add an installation-complete marker and validate it before skipping bootstrap.
- [ ] Enforce provider prerequisites before instance and workspace creation.
- [ ] Pin Python dependencies, Galaxy collections and roles to tested versions.
- [ ] Produce a reproducible dependency lock and update process.
- [ ] Move from EOL `ansible-core==2.18.0` to a tested supported release.
- [ ] Test the selected Ansible release against every Kingdoms playbook.
- [ ] Define supported controller Python versions and reject unsupported combinations.
- [ ] Pin and validate the Debian router box.
- [ ] Monitor availability of all pinned Windows boxes.

## P2 — Automated validation and release gates

- [ ] Fix the malformed trailing comma in `ad/DRACARYS/data/config.json`.
- [ ] Add CI for Bash syntax, Python parsing, structured-data validation and existing source validators.
- [ ] Add regression tests proving failed operations return non-zero.
- [ ] Add clean-install, interrupted-install and resume test scenarios.
- [ ] Add isolation assertions after both successful and failed provisioning.
- [ ] Run a disposable release matrix before declaring a provider or platform supported.

## P3 — Provider-neutral contracts (VirtualBox follow-up deferred)

First extract provider-neutral lifecycle contracts for network preparation, runtime mode, adapter state, rollback and validation. Do not copy VMware-specific shell behavior into another provider. The **first two** contract checklist items are prerequisites for Ludus; the subsequent VirtualBox-specific items are future work, not Ludus release blockers.

- [ ] Define provider-neutral provisioning and exercise mode interfaces.
- [ ] Define provider-neutral transition state and rollback contracts.
- [ ] Reproduce NORTH, SEVENKINGDOMS, ESSOS and MANAGEMENT using VirtualBox host-only and internal networks.
- [ ] Port deterministic MAC and conflicting-instance protection.
- [ ] Port provisioning and exercise mode transitions and NAT isolation.
- [ ] Verify runtime adapter state through VirtualBox tooling.
- [ ] Validate clean install, resume, start, stop, failure cleanup and segmentation.

## P4 — Ludus / Proxmox support (after VMware Course 1 release)

Ludus is the **next Course 1 provider after VMware**. Prefer its native deployment lifecycle for the port; any separate direct-Proxmox Terraform implementation is independent follow-up work, not an assumption about Ludus.

- [ ] Build an explicit Ludus Course 1 profile using the four Windows guests plus router, without an ESSOS domain or legacy ESSOS network.
- [ ] Preserve per-instance isolation, course entitlements/identity boundaries and repeatable deployment/reset semantics.
- [ ] Validate remote Kali over WireGuard, and provide a tested attacker Layer 2 path for LLMNR/NBT-NS/mDNS, IPv6 mitm6/WPAD and relay scenarios.
- [ ] Run fresh AD, MSSQL, certificate services, Phase 03 and full Course 1 release regressions independently on Ludus.

- [ ] Build reusable Windows and Debian router templates with Packer.
- [ ] Model the four zones using dedicated or VLAN-aware Linux bridges.
- [ ] Port deployment into Terraform using the provider-neutral lifecycle contracts.
- [ ] Preserve temporary provisioning reachability and deny-by-default exercise routing.
- [ ] Support remote Ansible provisioning and recovery.
- [ ] Validate segmentation from both the provisioning system and guest networks.
- [ ] Pass the complete provider release acceptance criteria.

## P5 — Windows host and additional provider support

Upstream GOAD supports Windows through WSL or native Python with a provisioning VM. Kingdoms needs an explicit Windows control-plane design rather than a direct port of Linux-only Bash and systemd behavior.

Implementation starts only after the P0 reliability findings are closed and the relevant provider-neutral lifecycle is proven. VirtualBox-specific work remains deferred until after the Course 1 Ludus portability milestone.

- [ ] Support Windows 11 hosts with VMware Workstation and VirtualBox.
- [ ] Define and test WSL and native-Python control paths.
- [ ] Replace or abstract `sudo`, systemd, `ip`, nftables and `/usr/local/sbin` assumptions.
- [ ] Configure and validate Windows VMware and VirtualBox host adapters safely.
- [ ] Discover interfaces dynamically and never hard-code interface indexes.
- [ ] Validate route selection, source address and interface metric before Ansible.
- [ ] Test repository paths containing spaces and Windows/WSL filesystem boundaries.
- [ ] Back up and roll back Windows routes and hypervisor network settings.
- [ ] Pass the complete platform release acceptance criteria.

## Windows regression references

These are requirements for P5, not authorization to move P5 ahead of P0–P4.

### Host route selection and WinRM HTTPS

Reference: [Orange-Cyberdefense/GOAD issue #497](https://github.com/Orange-Cyberdefense/GOAD/issues/497)

The reported installation failure demonstrated two distinct conditions:

1. Windows selected Wi-Fi instead of the VMware host-only adapter for the GOAD subnet.
2. After routing was corrected, some guests still needed WinRM HTTPS listener, certificate and firewall recovery.

Required regression coverage:

- [ ] Detect when traffic to a lab subnet selects Wi-Fi or another incorrect interface.
- [ ] Confirm the expected source address and hypervisor adapter.
- [ ] Test every guest on TCP port 5986 before Ansible.
- [ ] Perform an authenticated WSMan probe, not only a TCP test.
- [ ] Recover WinRM through an independent Vagrant or NAT management path where possible.
- [ ] Validate HTTPS listener, certificate binding and firewall state after recovery.

### Missing guest prerequisite

Reference: [Orange-Cyberdefense/GOAD issue #157](https://github.com/Orange-Cyberdefense/GOAD/issues/157)

- [ ] Validate required Windows features and tools such as `dnscmd` before dependent Ansible tasks.
- [ ] Install or repair missing prerequisites idempotently.
- [ ] Produce a specific diagnostic instead of failing deep inside domain provisioning.

## Provider and platform release acceptance criteria

A provider and platform combination is supported only when all of the following pass:

- [ ] Clean installation from an empty host and provider state.
- [ ] Resume after a deliberately interrupted provider phase.
- [ ] Resume after a deliberately failed Ansible playbook.
- [ ] Failure returns a non-zero exit code.
- [ ] Failure restores or safely preserves the original network mode.
- [ ] Successful installation finishes in exercise mode.
- [ ] Runtime segmentation validation passes.
- [ ] Repeated install, start and stop operations are idempotent.
- [ ] Installation and recovery documentation is complete.
