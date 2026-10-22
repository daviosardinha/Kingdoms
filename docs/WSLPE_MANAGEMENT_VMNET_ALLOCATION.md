# WSLPE management vmnet3 candidate allocation preflight

**Status: READ-ONLY source plan. Not a host installation.** The source tests and current operator evidence show that the management network `172.28.232.0/24` is a nonoverlapping candidate, `vmnet3` is unallocated and five NORTH VMware machines are running. This means configuring VMware networks **now** would violate the project's live-VM networking stop gate.

## Facts retained

- Existing WSLPE exercise network: `vmnet2`, `172.28.231.0/24`.
- Proposed **operator-only** management network: `vmnet3`, `172.28.232.0/24`, Kali host `172.28.232.254`, future disposable Windows NIC `.31`, no DHCP, no NAT.
- NORTH VMware networks vmnet10/20/30/99, WSLPE vmnet2 and the global NAT vmnet8 must not change.
- Existing three-port WSLPE host firewall remains installed in memory, not reboot-persistent; retain it until the guest's port forwards have actually been removed and verified.
- Existing registered WSLPE golden/master and learner-test VM must never be adopted by this experiment.

## Candidate planner usage

After pulling this code into the existing development checkout, the read-only command is:

```bash
cd "$HOME/kingdoms-wslpe45-pilot"
python3 -m unittest tests.test_wslpe_management_vmnet_plan -v
sudo python3 scripts/wslpe-management-vmnet-plan.py \
  --vmnet vmnet3 --management-prefix 172.28.232 \
  --workspace-root "$HOME/kingdoms-rebuild/workspace" \
  --workspace-root "$HOME/kingdoms-lpe-standalone/workspace"
```

The CLI also reads all host IPv4 addresses/routes from the existing WSLPE host checker, validates exact unchanged vmnet2 exercise subnet metadata, checks duplicate VMware vmnet keys, inspects all `.vmx` files under the two supplied workspaces for `vmnet3`, records the current `/etc/vmware/networking` SHA256 and prints an **additive proposal** only.

Expected during the currently running NORTH lab: `[DEFERRED] 5 VMware guest process(es) running - DO NOT CHANGE SHARED NETWORKING`, exit 2. This is a successful safety refusal, not permission to shut down these VMs.

If a separate third-party VMware workspace or manually registered/offline VM exists elsewhere, it must be independently inventoried before network allocation. This tool can only prove ownership for explicitly inspected workspace roots.

## Not yet approved

- No `--apply` flag exists and no host services are changed.
- A separate owner-verified transaction, a captured VMware network backup and a scheduled full maintenance window will be needed to allocate vmnet3, because the existing VMware network bootstrap uses shared `vmware-networks --stop/--start` and refuses running VMs.
- Do not manually edit `/etc/vmware/networking`, restart VMware networking with NORTH guests running, or delete WSLPE VM registrations.
- After vmnet creation, independently prove host adapter address persistence across VMware Workstation 26 restarts and isolate vmnet3 from NORTH and vmnet2.
- Only then validate the new disposable guest NIC, Windows management firewall restrictions, direct authenticated WinRM, Vagrant lifecycle and exact removal of that guest's host forwards.

**NORTH integration and WSLPE release to main remain blocked pending runtime acceptance.**

## 2026-10-21: native fresh WSLPE41 auto-candidate (source only)

The historical planner assumed the original WSLPE exercise vmnet2 and
172.28.231.0/24. That must **not** be applied to the new
`bf5369-wslpe-vmware` guest at `172.28.232.31`. The existing planner now
accepts `--native-workspace` to derive the exercise VMnet and subnet from the
**registered, running exact WSLPE VMX** and authoritative VMware metadata.
It then uses the existing host route/address/VMware network collision selector
to choose an **unused** private /24 and checks all operator-supplied workspace
VMX files before selecting an unclaimed operator vmnet. The explicit legacy
`--vmnet` and `--management-prefix` flags remain supported in the old
mode, preserving the previous WSLPE source tests.

Read-only command (include all actual relevant existing workspace roots):

```bash
cd "$HOME/kingdoms-wslpe41-fresh"
git pull --ff-only
"$HOME/.goad/.venv/bin/python" -m unittest -v tests.test_wslpe_management_vmnet_plan
"$HOME/.goad/.venv/bin/python" scripts/wslpe-management-vmnet-plan.py \\
  --native-workspace "$HOME/kingdoms-wslpe41-fresh/workspace" \\
  --workspace-root "$HOME/kingdoms-lpe-standalone/workspace" \\
  --workspace-root "$HOME/kingdoms-rebuild/workspace"
```

If some specified workspace does not exist on this Kali host, do not replace
its path with an arbitrary directory; include the real location or inspect
and justify its absence. The tool fails closed for missing roots, subnets,
conflicting VMX references and running VMware guests. **`[DEFERRED]` is
expected with the new WSLPE and original master running.** Do not use the
proposal as permission to edit /etc/vmware/networking or reboot VMware
network services while guests are running. No actual management NIC is yet
attached and operator authentication/isolation remains blocked.


## 2026-10-21: journaled management network allocation core (NOT activated)

The fresh native WSLPE guest binds its exercise NIC to **vmnet3 /
172.28.232.0/24**. The read-only planner selected **vmnet4 /
172.28.233.0/24** for an independent operator-only interface. The latest
operator output reports **two running VMware guests**, so any actual
shared VMware network restart remains **DEFERRED**.

`kingdoms/wslpe_management_vmnet_transaction.py` now provides an **internal,
unwired** allocation/recovery component. It has no CLI, is not called by
`goad.sh` or `wslpe41-install.py`, and has made **no** VMware/Windows/host
changes. It is not authorization to edit `/etc/vmware/networking`.

Source contract:
- Require explicit maintenance authorization, root-owned VMware metadata,
  a pinned source SHA256, and an exclusive operation lock.
- Recompute an additive vmnet proposal using the existing planner; preserve
  all original metadata, NAT forwards and other vmnet directives.
- Require an independently supplied live workspace/VMX registration and host
  collision preflight and prove zero VMware guests before and after stopping
  the shared network service.
- Persist the original **exact bytes**, owner/mode and both hashes in a
  root-only 0600 journal *before* the first network mutation. Use fsync and
  same-filesystem atomic rename for the proposed config and journal.
- Invoke VMware stop/start through an intentionally unimplemented integration
  callback. The interface verifier is also deliberately unimplemented; it
  must prove the real host adapter/IP, host-only isolation, retained NORTH
  network metadata and non-leakage to the WSLPE learner network.
- On an ordinary simulated failure, roll back the exact original bytes
  if and only if guest activity is still zero and the metadata still matches
  one of the two known hashes. On a crash, explicit `recover()` uses the
  durable journal. Any unexpected external config drift blocks rollback for
  manual intervention. A committed allocation is never silently rolled back.

Unit-test command (read-only simulated VMware callbacks):

```bash
cd "$HOME/kingdoms-wslpe41-fresh"
git pull --ff-only
"$HOME/.goad/.venv/bin/python" -m unittest -v \
  tests.test_wslpe_management_vmnet_plan \
  tests.test_wslpe_management_vmnet_transaction
```

**Remaining blockers before wiring an executable transaction:** independently
validate a complete VMware registration inventory (including offline/
third-party workspaces), authenticated cross-checks for both `vmrun` and the
OS guest processes, root-owned private persistent journal/lock directories,
a maintenance window with **all** VMware guests stopped by their owners,
and real VMware Workstation 26 restart/adapter/isolation/rollback tests.
Do not power off the two active VMs automatically, or expose `--apply`
while these gates are outstanding. The `kingdom.operator` WinRM/TLS handoff
and 41/41 installation remain subsequent separate acceptance gates.


## 2026-10-21: real-host guest inventory audit (read only)

Before any VMware Workstation network restart, independently cross-check
`vmrun -T ws list` against the Linux `vmware-vmx` process count, and verify
that each running VMX is actually located under an explicitly supplied
existing workspace. Reject mismatched counts, foreign running guests,
duplicates, symlinked VMXs, missing workspace coverage, or a VMnet already
claimed in host metadata / provided workspaces. This is **not** an inventory
of all offline Workstation registrations.

Read-only operator command on Kali (do not use sudo):

```bash
cd "$HOME/kingdoms-wslpe41-fresh"
git pull --ff-only
"$HOME/.goad/.venv/bin/python" -m unittest -v \
  tests.test_wslpe_management_vmnet_plan \
  tests.test_wslpe_management_vmnet_transaction \
  tests.test_wslpe_management_vmnet_host_gate

"$HOME/.goad/.venv/bin/python" scripts/wslpe-management-vmnet-host-audit.py \
  --candidate-vmnet vmnet4 \
  --workspace-root "$PWD/workspace" \
  --workspace-root "$HOME/kingdoms-lpe-standalone/workspace" \
  --workspace-root "$HOME/kingdoms-rebuild/workspace"
```

If a workspace path is missing or a VMX is outside the supplied roots, do
not substitute an arbitrary directory: identify the real registration owner
and repeat the audit. Existing reported two running guests should produce
`[INVENTORY] vmrun=2 vmware-vmx=2` and `[DEFERRED]`, provided both running
VMXs belong to the supplied workspace set. An inconsistent inventory should
produce `[BLOCKED]`, not permission to power off or reconfigure guests.

Source-only gate: `kingdoms/wslpe_management_vmnet_host_gate.py`;
CLI: `scripts/wslpe-management-vmnet-host-audit.py`.
The dedicated CI checks these read-only functions using simulated
VMware outputs. Passing does not prove offline-VM ownership, stable host
network allocation, vmnet4 isolation, WinRM/TLS, or Windows operator access.

**Still not approved:** applying vmnet4, creating the new guest NIC,
removing NAT forwards, modifying Vagrant, or running the 41-stage install.
A reviewed maintenance window and independently implemented VMware
network restart/rollback/host adapter acceptance are still required.


## 2026-10-22: Workstation registered/offline VM library audit (read only)

The running-VM audit on Kali matched both sources: vmrun=2 and
vmware-vmx=2; both live VMXs are under the supplied workspaces. It also
confirmed that vmnet4 is free in current network metadata and those
workspaces. The two running guests still prohibit shared network restart.

A **separate read-only** source gate inspects the current VMware Workstation
user's ~/.vmware/inventory.vmls library, follows its vmlistN.config
VMX paths (including powered-off registered guests), and inspects explicit
VMnet assignments. A registered VMX claiming vmnet4 blocks; missing,
symlinked, malformed, out-of-workspace or library-omitted running VMXs
fail closed or require further ownership review.

Run this on the current Workstation owner's Kali account without sudo:

```bash
cd "$HOME/kingdoms-wslpe41-fresh"
git pull --ff-only
"$HOME/.goad/.venv/bin/python" -m unittest -v \
  tests.test_wslpe_management_vmnet_plan \
  tests.test_wslpe_management_vmnet_transaction \
  tests.test_wslpe_management_vmnet_host_gate \
  tests.test_wslpe_management_vmnet_registry

"$HOME/.goad/.venv/bin/python" scripts/wslpe-management-vmnet-registry-audit.py \
  --candidate-vmnet vmnet4 \
  --workspace-root "$PWD/workspace" \
  --workspace-root "$HOME/kingdoms-lpe-standalone/workspace" \
  --workspace-root "$HOME/kingdoms-rebuild/workspace"
```

A missing library is not silently treated as an empty VMware registry.
The user library is NOT a global inventory of all user accounts, unregistered
VMXs, snapshots or detached disks. Inventory drift, unsupported encoding
or paths and other-user VMware registrations require manual review.
The audit never changes VMware files, never powers off guests, and never
tries a network restart. It is source-tested only and still returns
[DEFERRED] when the two guests remain on.
