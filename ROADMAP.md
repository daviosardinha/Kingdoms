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
| **P3** | Provider-neutral architecture and VirtualBox on Linux | Only after all P0 items and required P1/P2 gates are complete |
| **P4** | Proxmox support | After the provider-neutral lifecycle is proven on VMware and VirtualBox |
| **P5** | Windows host support | Last: only after P0–P4 foundations relevant to the selected provider are complete |

**Hard gate:** do not start Windows host implementation while any P0 item remains open. Windows design and research may be recorded, but implementation waits until the existing installation and isolation lifecycle is dependable.

## Delivery policy

- Implement each checklist item in a separate issue and pull request.
- Do not test risky lifecycle or dependency changes first against the working `16b7a2` lab.
- Require source validation, failure-path testing and a rollback plan before merge.
- Preserve deny-by-default exercise isolation.
- Treat a non-zero provider, provisioning, extension or isolation result as an installation failure.
- Finish and validate each priority before promoting the next priority into active implementation.

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

### Linux distro portability (P1/P2; distinct from adding providers)

**Required:** All three existing VMware-based labs (KINGDOMS, NORTH and WSLPE)
must work across supported Linux host distributions, **not only Kali**.
This is a cross-distro host compatibility and prerequisite-isolation requirement,
not a claim of support for hosts where VMware Workstation or its plugin is
unsupported. See [Linux distribution portability contract](docs/kingdoms-linux-distribution-portability.md).

- [ ] Centralize invocation of the project-managed Python/Ansible environment;
  never depend on host system Python importing project packages such as `winrm`.
- [ ] Replace distro-specific paths/commands in installation, start/stop,
  diagnostics, VMnet setup and recovery with preflighted host capabilities.
- [ ] Test missing-dependency and conflicting-network fail-closed behaviors.
- [ ] Publish a Linux distro/version compatibility matrix backed by source/CI
  and actual provider runtime evidence for NORTH, KINGDOMS and WSLPE.
- [ ] Validate three-lab co-host coexistence on each supported combination.

## P2 — Automated validation and release gates

- [ ] Fix the malformed trailing comma in `ad/DRACARYS/data/config.json`.
- [ ] Add CI for Bash syntax, Python parsing, structured-data validation and existing source validators.
- [ ] Add regression tests proving failed operations return non-zero.
- [ ] Add clean-install, interrupted-install and resume test scenarios.
- [ ] Add isolation assertions after both successful and failed provisioning.
- [ ] Run a disposable release matrix before declaring a provider or platform supported.

## P3 — Provider-neutral architecture and VirtualBox on Linux

First extract provider-neutral lifecycle contracts for network preparation, runtime mode, adapter state, rollback and validation. Do not copy VMware-specific shell behavior into another provider.

- [ ] Define provider-neutral provisioning and exercise mode interfaces.
- [ ] Define provider-neutral transition state and rollback contracts.
- [ ] Reproduce NORTH, SEVENKINGDOMS, ESSOS and MANAGEMENT using VirtualBox host-only and internal networks.
- [ ] Port deterministic MAC and conflicting-instance protection.
- [ ] Port provisioning and exercise mode transitions and NAT isolation.
- [ ] Verify runtime adapter state through VirtualBox tooling.
- [ ] Validate clean install, resume, start, stop, failure cleanup and segmentation.

## P4 — Proxmox support

- [ ] Build reusable Windows and Debian router templates with Packer.
- [ ] Model the four zones using dedicated or VLAN-aware Linux bridges.
- [ ] Port deployment into Terraform using the provider-neutral lifecycle contracts.
- [ ] Preserve temporary provisioning reachability and deny-by-default exercise routing.
- [ ] Support remote Ansible provisioning and recovery.
- [ ] Validate segmentation from both the provisioning system and guest networks.
- [ ] Pass the complete provider release acceptance criteria.

## P5 — Windows host support

Upstream GOAD supports Windows through WSL or native Python with a provisioning VM. Kingdoms needs an explicit Windows control-plane design rather than a direct port of Linux-only Bash and systemd behavior.

Implementation starts only after the P0 reliability findings are closed and the relevant provider-neutral lifecycle is proven.

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
