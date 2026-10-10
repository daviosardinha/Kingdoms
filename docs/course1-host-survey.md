# Kingdoms Course 1 — VMware host read-only survey

Status: observed host configuration only. Course 1 deployment remains blocked.

## Operator workflow

Continue using the single consolidated command, now with an optional host
survey flag:

    cd "$HOME/kingdoms-course1-src" && git pull --ff-only && bash scripts/course1/validate-course1.sh --survey-host

The default command (without --survey-host) still runs the offline suite.
The extra stage **never** edits networking or virtualization state. It reads:

- Linux interface IPv4 addresses using `ip -j address show`;
- Linux IPv4 route tables using `ip -j route show table all`;
- configured VMware virtual networks from `/etc/vmware/networking`,
  discovered VMware vmnet devices/directories and active interface names;
- running VMware VMX list via `vmrun -T ws list`;
- Workstation's user-level `~/.vmware/inventory.vmls` registry, including
  registered powered-off guests;
- *only* Ethernet network settings from running **and registered** VMX files.
  Neither the library file nor VMX files are modified.

Sensitive VMX non-network settings are never printed. Full filesystem paths
are not printed: each VM uses a short SHA256-derived identifier plus its
folder/VMX basenames. The script requires no sudo and does not execute
Vagrant, VM power changes, systemctl, ip route modifications or VMware
network configuration changes.

## Result semantics

`OBSERVED_SNAPSHOT` means the four base visibility sources completed:
Linux interfaces, routes, VMware networking config and readable running VMX.
It does **not** prove a vmnet is free. The new optional Workstation GUI library
source is reported independently as `INSPECTED`, `NOT_FOUND`,
`INCOMPLETE` or `UNREADABLE`.

When `inventory.vmls` exists and is complete, the host-fit gate also rejects
collisions in registered but powered-off VMs. If it contains missing or
unreadable VMX entries, host-fit fails closed. When the library is absent,
the survey reports that registered powered-off coverage is unavailable, **not**
that zero powered-off VMs exist. Unregistered / unknown-location VMX files,
other users' inventories and external providers are still not exhaustively
inventoried. No status authorizes allocation.

`INCOMPLETE` exits nonzero and provides a structured list of missing data.
Do not interpret missing access or missing VMware binaries as free networks.

Both statuses explicitly report `candidate_allocation_authorized=false`
and `deployment_authorized=false`. Review the output before proposing a
per-instance allocation. PR #30 remains draft and the original Kingdoms
reference lab must not be modified.

After this survey, we will design the explicit four-VM router/Vagrant/Ansible
address mapping, audit its effect on NORTH attack traffic, and only then
introduce a disposable deployment and separate live regression gates.

## Course 1 three-network observational fit

After reviewing the operator's full snapshot at `68f54bc`, the proposed Course 1
topology excludes ESSOS entirely and uses **only** NORTH, SEVENKINGDOMS and
MANAGEMENT. The checked-in `docs/course1-network-candidate.example.json`
is **non-deployable example input**, not an allocation of actual vmnets or MACs.
It models NORTH and MANAGEMENT host-side `.254` interfaces, a management
router gateway, a parent DC and three NORTH hosts.

`goad.course1_host_fit` checks both the proposal's static identity contract
and a fresh read-only host survey. It rejects observed vmnet collisions, IPv4
subnet overlaps in interface addresses/routes/VMware configuration, and MAC
collisions in running VMX files. Even a clean result is only
`NO_OBSERVED_CONFLICTS_NOT_PROVEN_AVAILABLE`; powered-off or unregistered
VMs and VMware limitations still require separate verification. The candidate
**cannot** be deployed or used to enable Course 1 activation.

`validate-course1.sh --survey-host` now prints a compact host survey followed
by the non-authorizing fit summary, while continuing to run the full offline
regression suite. Use `python3 -m goad.course1_host_survey --check` separately
if the detailed route/VMX inventory is required.


## One-snapshot acceptance (read-only)

`validate-course1.sh --survey-host` now runs `ip` / VMware inspection exactly
**once**, saves the complete JSON in a private ephemeral root (mode 0700,
files created with umask 077), and passes that same snapshot to the proposal
comparison. It outputs only a compact host summary plus collision report.

The snapshot is automatically removed at the end of the command. This
improves performance and avoids comparing a host-fit report with a separately
collected, potentially changed running-VM list.

Workstation inventory documentation:
https://knowledge.broadcom.com/external/article?legacyId=57224
