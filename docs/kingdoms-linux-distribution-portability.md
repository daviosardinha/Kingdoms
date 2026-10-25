# KINGDOMS Linux distribution portability contract

**Status:** Required engineering/release acceptance; implementation and cross-distro runtime validation pending.

## Goal and scope

KINGDOMS, NORTH (Fall of the North), and WSLPE must be runnable from Linux hosts **without requiring Kali Linux**. Host-specific bootstrap, diagnostics, installation, provisioning, VMware networking, start/stop, runtime validation, snapshot/restore and recovery must not rely on Kali-only packages, configuration, filenames, usernames or assumptions.

**Support is conditional on the selected virtualization provider actually supporting that distro/version.** "Any Linux distro" is the portability design target, not a claim that VMware Workstation runs on every distribution. Publish an evidence-backed support matrix and fail early on unsupported platform/provider combinations. This concerns host/platform portability only; it must not redesign the already-developed labs or their vulnerabilities.

## Non-negotiable implementation rules

1. **Python dependency isolation.** Invoke the project-managed environment (currently `$HOME/.goad/.venv/bin/python` and `$HOME/.goad/.venv/bin/ansible-playbook`) through one canonical resolver. Honor explicitly configured interpreter/venv paths. Never assume host/system `python3` includes `pywinrm`, Ansible or any project dependency. Check interpreter availability and required module imports before any action that can modify virtual machines or networking.
2. **Distro-neutral preflight.** Detect versions and availability of Python, `venv`, VMware Workstation/`vmrun`, Vagrant and the VMware plugin, Bash, `iproute2`, SSH, `sudo`, and the host service management capabilities used by a given workflow. Keep optional diagnostics (for example `tcpdump`) optional. Provide a clear actionable error for missing, obsolete or unsupported tooling. Bootstrap instructions may be distro-specific, but core orchestration must not silently assume `apt`.
3. **No hard-coded operator paths.** Resolve repository, instance, provider, evidence and venv paths dynamically. Never bake `/home/stark`, Kali-specific desktop paths, or a fixed login username into shipped scripts.
4. **Do not own unrelated host configuration.** Detect DNS resolver and network manager variants before proposing network changes. No automatic replacement of `/etc/resolv.conf`, no disabling independent `dnsmasq`/systemd-resolved services, no unscoped interface or route changes, and no overwriting other VMware VMnet or lab ownership. Host-side network transitions must be exact-owner-scoped, transactional and fail closed.
5. **Keep the labs independent.** No host distribution workaround may alter KINGDOMS, NORTH or WSLPE domain topology, exercise vulnerabilities, router policies, guest images or scenarios, or interfere with another lab installed on the same host.
6. **Non-destructive diagnostics by default.** Diagnostic commands only observe state unless explicitly documented as lifecycle actions; require the correct instance ID and owner proof for any state-changing action.

## Current failure illustrating the requirement

During NORTH sixth-instance post-install troubleshooting on 2026-10-25, an ad-hoc Python command invoked system `python3` and failed with `ModuleNotFoundError: No module named 'winrm'`; the module was available in the existing project-managed venv. The correct *immediate* command was to use the managed interpreter, **not** to install packages into Kali's system Python. This is distro-neutral practice, not a Kali workaround.

## Release acceptance matrix

For **each supported distro/version and provider combination**, record the exact kernel, distro, VMware Workstation, Vagrant/plugin and Python/Ansible versions and evidence for:

- [ ] Fresh setup on a clean host with no global Python package dependencies.
- [ ] Preflight failures for unavailable venv/plugin and unsupported host networking without partial installation.
- [ ] Each of NORTH, KINGDOMS and WSLPE: clean install, failed-install/resume, start, stop, independent runtime validation and exercise isolation.
- [ ] Failed cold-start and interrupted transition preserve a verified fail-closed network state.
- [ ] Snapshot creation, restore and post-restore checks where supported.
- [ ] Three-lab coexistence: operations for one lab do not alter the two others' VMs, VMnets, routes, policy or state.
- [ ] CLI regression/source tests under Ubuntu, Debian, Fedora, Arch-based Linux and Kali where practical, with actual **VMware runtime** tests only on versions supported and available in the validation environment.
- [ ] Distribution-neutral installation/troubleshooting documentation and a published support matrix with explicit "tested", "not tested", or "unsupported" per combination.

A passing unit-test matrix **does not** certify VMware runtime functionality on that distro. Mark unsupported or untested combinations clearly.

## Prioritization and evidence rule

This belongs to the **P1/P2 reliability and qualification work** in [ROADMAP.md](../ROADMAP.md), not P3 VirtualBox provider expansion. Continue the current NORTH cold-start/W32Time reliability investigation first; do not paper over its failing acceptance or confuse distro support with provider changes.

Source of truth is GitHub. Every implementation requires regression tests, a documented fail-closed path, and separate cross-distro evidence before claiming compatibility.
