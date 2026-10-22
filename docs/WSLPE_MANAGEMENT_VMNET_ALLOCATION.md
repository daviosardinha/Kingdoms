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


## 2026-10-22: operator evidence — current WSLPE vmnet4 registry cleared

**Current native exercise:** vmnet3 (172.28.232.0/24). **Proposed management:** vmnet4 (172.28.233.0/24). The preceding vmnet2/vmnet3 plan at the top of this document is historical and applies to a different WSLPE pilot. Do not allocate vmnet3 for this guest.

The Kali owner reran the offline Workstation library audit with these exact workspace roots:
- $HOME/kingdoms-wslpe41-fresh/workspace
- $HOME/kingdoms-lpe-standalone/workspace
- $HOME/kingdoms-rebuild/workspace
- $HOME/vmware/KINGDOMS-WSLPE41-LEARNER-TEST (the preserved, registered learner-test clone)

Observed output: **8** Workstation library entries; **0** VMXs referencing vmnet4; vmrun=**2** and vmware-vmx=**2**; no OTHER OWNER or NOT IN LIBRARY markers; **[DEFERRED] Guests still running; NO NETWORK RESTART.** This closes the specifically observed missing-workspace audit finding. This is not evidence of an installed vmnet4, actual guest NIC isolation, or an exhaustive inventory of other users' unregistered/offline files.

### Unblocked vs still blocked

**Source planning gate complete:** exact exercise/management proposal; running-VM and user-library ownership audited against supplied workspaces. **No VMware network mutation is authorized.**

**Remaining implementation/acceptance work:**
1. Review other user accounts/VMware registrations, stray VMXs outside the Workstation library and any externally managed VM network consumers. Check for state changes again immediately before the maintenance action.
2. Implement and review actual root-only VMware Workstation 26 stop/start, persistent lock/journal locations, preflight-to-apply capability and independent adapter/IP/isolation verification. The existing Python transaction is source-only and its VMware callbacks are deliberately missing.
3. In a separately agreed maintenance window, let each VM owner arrange an orderly guest shutdown. Never auto-stop these two VMs. Require dual zero-guest checks just before touching shared networking and re-prove expected /etc/vmware/networking bytes.
4. Create **only** the vmnet4 management network via the reviewed transaction with a durable backup, and prove recovery and preservation of every pre-existing vmnet/NORTH route/NAT directive before guest changes.
5. Attach and accept a dedicated management NIC on only the exact new WSLPE guest, with authenticated pinned-TLS WinRM via kingdom.operator and verified network isolation. Keep the historical master, learner-test VM, NORTH and other labs untouched.
6. Only after the management handoff and WinRM-free console recovery pass, move to the existing one-shot 41-scenario installer. No premature claim that scenarios are deployed.

**Operator instruction for now: do nothing on VMware; preserve both running guests.** All clearance evidence is point-in-time and must be reacquired after any host configuration or registration changes.


## 2026-10-22: bounded VMware Workstation service adapter (source implementation)

To reduce the gap between the previously source-tested transaction and a
controlled operator action, the branch now includes
`kingdoms/wslpe_management_vmnet_workstation.py`:

- `WorkstationNetworkService.action()` recognizes **only** `stop` and `start`, verifies root context and the VMware binary's trust/mode,
  then invokes `/usr/bin/vmware-networks --stop/--start` without a shell
  using a bounded subprocess. There is no guest power operation.
- `WorkstationHostAdapterVerifier.verify_host_adapter()` uses
  read-only iproute2 JSON for the selected vmnet. It expects **exactly**
  `vmnet4`, `172.28.233.254/24`, an UP host adapter,
  the one connected `172.28.233.0/24` route, and VMware config
  metadata with DHCP/NAT disabled and a host virtual adapter enabled.
- It is a **host-address/metadata proof only**: it cannot establish Windows
  WinRM reachability, absence of host routing/firewall leaks into NORTH,
  or persistence over reboot/restart. Those remain separate acceptance
  requirements before it could serve as a transaction commit gate.

The adapters remain **unwired from any CLI or active installer**. In particular,
no call to `vmware-networks` can be triggered through
`goad.sh` or `scripts/wslpe41-install.py`. Do not invoke the
internal Python classes directly on Kali. Before production wiring, reconcile
the Workstation 26 binary locations and service semantics on the real host,
guard all other-user VM consumers, implement full network-isolation acceptance,
and verify the actual fail/rollback path during an owner-approved guest-free
maintenance window.

Additional simulated gate:

```bash
cd "$HOME/kingdoms-wslpe41-fresh"
git pull --ff-only
"$HOME/.goad/.venv/bin/python" -m unittest -v \
  tests.test_wslpe_management_vmnet_plan \
  tests.test_wslpe_management_vmnet_transaction \
  tests.test_wslpe_management_vmnet_host_gate \
  tests.test_wslpe_management_vmnet_registry \
  tests.test_wslpe_management_vmnet_workstation
```

**Stop condition unchanged:** two VMware guests are running. The next operator
command is source testing only, not a vmnet4 creation command.


## 2026-10-22: confirmed host command paths (read-only operator evidence)

The Workstation host reported:
- `command -v vmware-networks` = `/usr/bin/vmware-networks`
- `command -v ip` = `/usr/bin/ip`
- Both executables reported as root-owned, permissions `755` using `stat -L`.

The `WorkstationHostAdapterVerifier` default was corrected from
`/usr/sbin/ip` to `/usr/bin/ip`, and a source regression pins both
observed executable paths. Because `stat -L` dereferences symlinks,
these results alone **do not prove** that either executable or a parent
directory is not a symlink; real execution remains gated on the
adapter's own path validation and operator verification. Do not assume
the Linux command check proves network service lifecycle semantics.

The service adapter remains **unwired** from any runtime action.
No network restart, VM stop, guest NIC change, or scenario installation
is authorized by this checkpoint.


## 2026-10-22: consolidated operator readiness batch (single command)

Repeated one-by-one preflights are now replaced by a **single operator
invocation**. This batch runs the five existing management-network source
test modules, checks the existing 41/41 installer manifest, validates the
exact running fresh native guest, verifies the live management vmnet/subnet
proposal, reconciles the running guest VMX/process inventory, audits all
eight current-user registered VMware library entries (without relying on
their count), and checks the proven host binaries.

Four explicit existing workspace roots are already included, including the
preserved `KINGDOMS-WSLPE41-LEARNER-TEST`. Do not edit or remove any
VMs to satisfy the batch.

```bash
cd "$HOME/kingdoms-wslpe41-fresh"
git pull --ff-only
"$HOME/.goad/.venv/bin/python" scripts/wslpe41-readiness-batch.py
```

Interpretation:

- `[PASS]` means the individual read-only check succeeded.
- `[DEFERRED]` means both running guests are accounted for and shared
  VMware networking **must not** be restarted.
- `[BATCH PASS]` with a maintenance deferral is a **successful read-only
  checkpoint**, not installation permission.
- `[BATCH BLOCKED]` reports all independent failures together, not one
  issue per separate user turn. Return the complete output for repair.
- `[NOT INSTALLED]` explicitly states that vmnet4, operator auth and 41
  scenario deployment are still separate live gates.

Source CI also runs the batch's `--source-only` mode using mocks/fixture
tests. The batch has **no apply or power command**, and must not be
run with sudo. Run it once at the start of the next operator session or
after a meaningful infrastructure change, not after every source commit.

**Next engineering workstream after the batch:** finish the separately
reviewed vmnet4 privileged transaction plus full host firewall/isolation
and recovery capability, then use an owner-approved guest-free VMware
maintenance window. After host management is established, attach only
the fresh guest's management NIC, validate kingdom.operator and
independent console recovery, and deploy/configuration-validate the 41
scenarios. Release still requires a second clean independent build
and learner-path acceptance. No changes to NORTH or the historical WSLPE
master.


## 2026-10-22: consolidated readiness PASS; guarded maintenance runtime source integration

The operator ran `scripts/wslpe41-readiness-batch.py` on the native fresh
WSLPE checkout. **PASS:** verified host binaries, management-source tests,
41-scenario manifest, native instance. **DEFERRED (expected):** vmnet4
proposal, running-VM ownership, registered/offline VMX ownership because
two VMware guests remain active. `[BATCH PASS]` does **not** install
vmnet4, operator credentials or the 41 Windows configurations.

The feature branch now includes
`kingdoms/wslpe_management_vmnet_runtime.py`. It binds the existing
journaled transaction to the existing Linux Workstation adapter, while
enforcing:
- Root-only maintenance assembly with a pre-existing private 0700
  root-owned state directory for its journal and exclusive lock.
- Zero running guest agreement from *both* global `vmware-vmx`
  processes and `vmrun` executed under the original non-root Workstation
  owner's account rather than root's potentially empty user inventory.
- Fresh candidate route/IP and all specified workspace VMX collision
  checks; rereads the original owner's `inventory.vmls` library immediately
  before the transaction and refuses foreign registrations.
- The real vmnet4 host-only adapter validator **and a separate required
  firewall/network isolation acceptance** before marking a transaction
  committed. There is **no permissive/default isolation implementation**.

Mock-only regressions validate owner UID scoping, independent zero-guest
proof, collision refusal, private transaction state, explicit isolation
acceptance, and refusal when live guests still exist. The dedicated source
CI passed **73/73 tests**, with all six relevant GitHub workflows green.

**Not yet executable on the host:** the owner-reviewed isolation acceptance
implementation, the approved maintenance CLI/transaction enablement,
real Workstation 26 restart/restore validation and controlled shutdown
of running VMs. `scripts/wslpe41-readiness-batch.py` remains read-only;
there is no production `--apply`. No extra one-by-one operator tests
are needed at this stage.

**Next controlled milestone:** implement and qualify the non-routing
isolation verifier and final transaction entrypoint *as one package*;
during an explicitly approved guest-free window, apply only vmnet4 and
verify rollback with real host evidence. Only then attach the fresh
native WSLPE guest management NIC and complete
`kingdom.operator`/41-scenario Windows acceptance.

No NORTH VM, historical WSLPE learner-test/master VM or original
KINGDOMS topology is to be modified by this work.


## 2026-10-22: vmnet4 guarded maintenance entrypoint + kernel isolation (source-tested)

`kingdoms/wslpe_management_vmnet_isolation.py` implements a read-only,
fail-closed Linux **kernel non-routing** invariant for vmnet4: interface-
scoped IPv4/IPv6 forwarding and global IPv6 forwarding must be disabled,
the vmnet4 adapter must have no Linux bridge/master association, and
the IPv4 routing tables must have only the directly connected vmnet4
unicast route (normal local/broadcast kernel routes are allowed).
It neither modifies the host firewall nor changes global forwarding
settings. This is **not end-to-end network isolation proof**: the final
Windows guest/NIC/WinRM policy and a negative connectivity test from
the learner to NORTH and operator management still need live validation.

`scripts/wslpe-vmnet4-maintenance.py` now offers an explicitly guarded
`--apply` and emergency `--recover`. These operations invoke the
existing owner-scoped VMware runtime, backup/journal transaction and
Workstation service adapter. They **do not shut down VMware guests** or
install a Windows scenario. They require:

1. An operator-approved downtime window with **every VMware guest
   already shut down by its owner**. Both `pgrep` and original-owner
   `vmrun` inventory must report zero. If either sees a guest, the
   operation is refused before creating transaction state.
2. Run as root, supply the actual non-root Workstation owner
   (`--owner stark` for the current Kali host), the exact
   `I_APPROVE_GUEST_FREE_VMNET4_MAINTENANCE` token and, for apply,
   the pinned current networking SHA256. A stale hash blocks.
3. All four verified existing WSLPE/Kingdoms workspace roots must
   exist unchanged, including the historical learner-test clone.
   A re-audit of original-user VMware inventory and live host
   address/route collisions is mandatory immediately before mutation.
4. A private root-only journal/lock state and exact in-transaction
   rollback on recognized failure. Unexpected VMware metadata drift
   stops automated restore and requires explicit manual recovery.
5. Exact `vmnet4` host adapter, host-only network metadata
   (`172.28.233.254/24`, no DHCP/NAT) and kernel no-forward/no-bridge
   acceptance before recording a commit.

The new maintenance code and isolation probe are covered by mocks in
the dedicated source regression. **No real VMware restart or Windows NIC
installation has been performed by CI.**

### Maintenance procedure (reserved; DO NOT execute while any VM is running)

After the WSLPE checkout source is reviewed and owners approve downtime,
the guests must be stopped independently, outside this script. The single
operator maintenance invocation is then:

```bash
cd "$HOME/kingdoms-wslpe41-fresh"
git pull --ff-only

# Read-only pinned-source checksum. No VM stop or networking mutation.
"$HOME/.goad/.venv/bin/python" scripts/wslpe-vmnet4-maintenance.py \
  --status --owner stark

# Later, after guest-free proof and explicit downtime approval only,
# a root operator uses --apply with the freshly printed exact SHA256.
# Never replace this with the SHA from a previous session.
```

The final privileged apply syntax is:

```bash
sudo "$HOME/.goad/.venv/bin/python" scripts/wslpe-vmnet4-maintenance.py \
  --apply --owner stark \
  --expected-sha256 '<freshly-approved-64-digit-hash>' \
  --approve I_APPROVE_GUEST_FREE_VMNET4_MAINTENANCE
```

If a crash interrupts before commit, the owner may inspect the
root-only journal and run `--recover` with the same owner and exact
maintenance-approval token, **again only with zero running guests**.
Do not delete the private journal or apply twice. A committed allocation
is never silently reverted.

**Do not run either privileged command yet.** The active operator
evidence still reports **2 running VMware guests**. Root-owned code
execution, the shared networking restart and failure recovery have only
been source-simulated; the real host's post-restart and guest recovery
must be accepted during a deliberate maintenance window.

**After vmnet4:** attach only the new native guest management NIC,
authenticate the dedicated `kingdom.operator` over pinned HTTPS/5986,
prove WinRM-independent console recovery and negative learner-to-
management/NORTH connectivity, then install and validate 41/41 and
repeat a second independent clean build. Return to NORTH after WSLPE
acceptance; do not alter the existing NORTH network or course as
part of this vmnet change.


## 2026-10-22: first live maintenance blocker resolved in source (binary path trust)

The owner-confirmed maintenance command passed BOTH live guest-free checks
and matched the pinned original VMware source SHA256:
`538955e59ce433b3764e19e5d46073f2b476af54c15d5260465867d87ca15bff`.

The first privileged invocation refused with
`[BLOCKED] ... Unsafe VMware/IP binary path`, **before** transaction
journaling, VMware network restart, host NIC creation, or VMX edits.

Root cause in source: the generic strict executable validator rejected
symbolic-link launchers for `/usr/bin/vmrun` and/or `/usr/bin/pgrep`
while those two are normally installed via trusted system symlinks on
some Linux Workstation hosts. The VMware network-changing binaries
(`/usr/bin/vmware-networks` and `/usr/bin/ip`) retain strict no-link
validation. Only `vmrun` and `pgrep` may use their root-owned symlink
forms, and only if the resolved destination stays under root-controlled
non-writable `/usr` parent directories with an executable regular file.
The error reports the exact rejected path rather than a generic label.

A new regression covers permitted vendor links, non-root owned links,
unsafe directory chains and non-system targets. The consolidated
readiness batch now checks all four executable paths. Do not reuse
old code by bypassing the checker or creating filesystem aliases.

**The host network is still NOT installed.** Before the next apply,
re-run the single consolidated readiness batch and dynamically verify
the exact original networking SHA256, zero VMware guests, and absence
of any prior transaction journal. Refuse on any drift. The previous
hash is evidence only, not a blanket authorization to apply later.


## 2026-10-22: powered-off maintenance readiness gate (corrected)

During the approved guest-free window both WSLPE Windows VMs were shut down.
The regular consolidated readiness command correctly found no VMware guests,
but incorrectly treated this as a failure: `--native-status` and the
original vmnet proposal utility require the fresh VMX to be *running*.
This was a source/phase mismatch, not a failed Windows deployment.

The new `--maintenance` mode replaces **only those two live-guest
assertions** with `scripts/wslpe-management-vmnet-offline-native.py`.
It validates the exact fresh WSLPE instance manifest, original Vagrant
VMX registration, presence in the Workstation owner's offline library,
the on-disk native ethernet0 NAT / ethernet1 custom vmnet3 topology and
the corresponding unchanged host vmnet3 / 172.28.232.0/24 metadata.
It continues to run source tests, 41-scenario manifest inspection,
host running-VM inventory and offline VMware registration collision
checking. No VM is booted and no VMware network operation is performed
by the readiness command.

Use **one** maintenance batch while ALL VMware VMs remain powered off:

```bash
cd "$HOME/kingdoms-wslpe41-fresh"
git pull --ff-only
"$HOME/.goad/.venv/bin/python" scripts/wslpe41-readiness-batch.py --maintenance
```

Expected: five `[PASS]` checks and `[BATCH PASS]`, with **no**
`[FAIL]` or `[DEFERRED]`. Any block must stop the protected
transaction. Revalidate the current networking SHA256, zero guest
processes, journal absence and owner authorization in the same operator
maintenance procedure before privileged `--apply`.

The normal `scripts/wslpe41-readiness-batch.py` remains unchanged
in its intent: it requires a running fresh VMX and is for *normal
live-guest* readiness only. Never start a guest merely to pass that
check during a network maintenance window.

The 41-scenario Windows runtime installer, dedicated
`kingdom.operator`, guest NIC and cross-reboot isolation acceptance
remain separate release requirements. This gate does not claim that
vmnet4 is installed.


## 2026-10-22: live vmnet4 transaction rollback — preserve failure evidence

The first valid powered-off maintenance readiness passed every gate; during
`sudo scripts/wslpe-vmnet4-maintenance.py --apply`, the privileged
transaction reported `Allocation failed; original configuration restored`.
This means the in-process rollback path reported success, **not** that
all host interfaces, VMware services or other labs have been proven
restored. The exact initial failure type was suppressed by the old
exception wrapper; a `rolled_back` journal may exist and intentionally
blocks an unsafe blind re-apply.

A dedicated **read-only** forensic command was added:

```bash
cd "$HOME/kingdoms-wslpe41-fresh"
git pull --ff-only
sudo "$HOME/.goad/.venv/bin/python" scripts/wslpe-vmnet4-postmortem.py --owner stark
vmrun -T ws list
```

It reports a whitelist of transaction status, original/candidate/current
SHA256 fingerprints, any recorded failure stage, current vmnet4 interface
and route state, forwarding flags and global VMware VM process count.
It does **not** emit the journal's original_b64 network backup or alter
host state. The previous transaction schema did not store the first
failure reason; this report may therefore establish only rollback
consistency rather than the exact failed acceptance predicate.
A filtered contemporaneous VMware host log excerpt may also be required.

The transaction source now preserves a bounded `failure_stage`,
`failure_class` and `failure_reason` in **future** protected root
journals and reports the stage on failed rollback. It does not modify
or reinterpret the existing journal, and does not bypass any
authorization/ownership/guest-zero checks.

**Stop gate:** keep both Windows guests off; do not delete/rename the
existing journal, force another apply, manually alter /etc/vmware/networking
or assume that the original hash proves complete service recovery.
Investigate the report, then design a single targeted repair and controlled
recovery path that preserves NORTH and both WSLPE workspaces.

## 2026-10-22: rollback forensics and protected archival

The live protected postmortem confirms journal status **rolled_back**,
with the exact original VMware source SHA256
`538955e59ce433b3764e19e5d46073f2b476af54c15d5260465867d87ca15bff`
matching the current /etc/vmware/networking file; no vmnet4 directive,
interface or IP exists, and both VMware inventories show zero running guests.
The earlier journal did not preserve the initial failure phase.

The NORTH host-address repair service ran approximately every 16 seconds
in the sampled logs; no evidence shows it caused the vmnet4 failure.
Preserve NORTH service configuration and avoid speculative changes.

A separate root-only `--archive-rolled-back` mode now archives the completed
rollback journal verbatim in the same protected private directory, under the
transaction lock. The operation refuses a non-rolled_back journal, source
hash drift, unexpected vmnet4 presence, a guest-free check failure or an
existing identical archive. It requires a **different explicit approval**
from the later maintenance `--apply`. There is no implicit retry and no
VMware service invocation during archiving.

The next new `--apply` is separately authorized. It captures the original
failure stage and a bounded reason in the root journal before a successful
rollback, so a subsequent failure can be diagnosed without another blind
attempt. Never overwrite or delete either historical or active journal.

The 41-scenario Windows fresh installer remains unimplemented at runtime;
do not confuse management host-network completion with `41/41` deployed.

## 2026-10-22: second live failure = vmnet4 host-address normalization

The second approved host maintenance attempt provided an exact failure phase:
`host-adapter-and-isolation-acceptance`, with
`vmnet4 must have only 172.28.233.254/24`.
After automatic rollback the protected journal is `rolled_back`,
the original networking SHA256 matches, vmnet4 is absent, and no
VMware guests are running. The error proves an unexpected **post-start
IPv4 state**, but does not by itself reveal whether vmnet4 had .1, no
address, or multiple addresses during the transient transaction.

Previous design already warned that Workstation may ignore HOSTONLY_HOSTADDR
when starting a host-only network. The guarded runtime now includes
`kingdoms/wslpe_management_vmnet_hostaddr.py`. Only after VMware's start,
it examines exactly the new vmnet4 link, expected host-only metadata,
current IPv4 and routes, **before** the original strict adapter and
kernel isolation acceptance. It can normalize only an unnumbered vmnet4
or a single correct-/24 IPv4 in 172.28.233.0/24 to
172.28.233.254/24 using exact `/usr/bin/ip` argv. It refuses
bridges, unexpected routes, off-subnet or multiple addresses, missing
metadata, and running guests. No NORTH address, route, vmnet or system
forwarding configuration is changed; a failure invokes the preexisting
rollback transaction, recording a bounded cause in the new private journal.

This source change is NOT proof of real host success or reboot persistence.
It addresses only the observed address mismatch; vmnet4 isolation and
NORTH coexistence must still pass existing live gates. Under another
owner-approved guest-free window the old rolled-back journal can be
preserved using the separately approved `--archive-rolled-back`
operation; a fresh `--apply` still requires its own approval and pinned
original hash. Do not blindly retry or delete any journal.

Next live acceptance: verify vmnet4 is only 172.28.233.254/24 and
networking checksum is committed. Then address reboot/restart persistence
before declaring complete operator management, attach only the fresh
WSLPE management NIC, authenticate kingdom.operator, and run the 41
Windows LPE scenarios with full validation. Retain all other workspaces.

## 2026-10-22: third live failure — unexpected vmnet4 route

The third owner-approved, guest-free allocation again restored the original
VMware networking configuration. The protected journal recorded:
`host-adapter-and-isolation-acceptance` / `Unexpected vmnet4 route;
refusing host IP repair`. The postmortem found zero running VMs,
no remaining vmnet4 interface, and the original networking source hash.
The transient offending route was not recorded in the old failure journal.

The vmnet4-only reconciler now accepts **only** the exact directly connected
172.28.233.0/24 link route and optional in-subnet local/broadcast host
routes. It continues to reject extra connected networks, foreign local
routes, gateways, bridged adapters, off-subnet addresses, multiple IPv4
addresses and wrong metadata. This is not a general relaxation of
routing policy. No NORTH or global route mutation is performed.

If VMware presents another unexpected route, a bounded, whitelisted
`failure_network_evidence` snapshot now survives rollback in the
root-only transaction journal and is shown by the read-only postmortem.
It includes vmnet4-only route destinations, types, scopes, devices and the
interface IPv4 address/prefix; it never serializes VMX, Windows credentials,
the networking original_b64 backup, or arbitrary host routes.

The root cause **cannot be stated conclusively from the third log**,
because the failed route existed only between VMware start and rollback.
Use no more speculative changes: any subsequent failed attempt must be
diagnosed from the captured route evidence. The already rolled-back
journal should be archived only with existing exact-hash, zero-VM and
explicit maintenance approval gates. No new apply occurs implicitly.

Return to NORTH only after actual vmnet4 host acceptance, the guest
management NIC, authenticated operator identity, 41/41 Windows scenario
validation and lifecycle recovery have been established.

## 2026-10-22: exact post-start vmnet4 route JSON source fix

The fourth guest-free transaction produced the previously missing evidence:
`ip -j -4 route show dev vmnet4` returned a connected kernel route
with `dst=172.28.233.0/24`, `prefsrc=172.28.233.1`,
`protocol=kernel`, `scope=link`, and **no explicit `dev` JSON key**.
The filtered command itself constrains the result to vmnet4, but the
validator assumed every record still includes a device key. This caused
`Unexpected vmnet4 route; refusing host IP repair`. The original host
config was restored; the latest journal is `rolled_back`, and there
were zero running VMware guests. The record does *not* prove that .254
would have survived a service restart or that network isolation is ready.

The fix updates BOTH the post-start vmnet4 IPv4 reconciler and the final
host adapter validator. Instead of weakening `dev == vmnet4`, both
query the **unfiltered IPv4 main route table**, select routes with
an explicit `dev=vmnet4`, and reject any conflicting route to
172.28.233.0/24 owned by another device or with an absent device
attribute. Foreign gateways, cross-subnet routes and unexpected
routes **on vmnet4** remain forbidden. The address reconciler may
then replace only VMware's in-subnet .1/24 with .254/24 and re-run
the independent strict adapter and kernel isolation verification.

CI fixtures replay the exact failed `prefsrc=.1` route and assert
the absence of any bypass for foreign/non-attributed routes.
This is still source-tested only, not a confirmed live allocation.

Do not start guests until a new guest-free, approved maintenance action
either commits or the rollback has been independently reviewed.
Retain every archived historical journal.


## 2026-10-22: live vmnet4 allocation COMMITTED — host checkpoint

The operator ran the guarded guest-free maintenance transaction on Kali.
Live output reported:

- `[COMMITTED]` vmnet4 source SHA256
  `9717eecc5c8f05f4d214018a7da280c4484dc3d2e9a26a33902a9efe3e89f990`.
- `ip -br -4 addr show dev vmnet4` = `vmnet4 UNKNOWN 172.28.233.254/24`.
- Connected route: `172.28.233.0/24 proto kernel scope link src 172.28.233.254`.
- Root journal state: `committed`.
- Original networking SHA256:
  `538955e59ce433b3764e19e5d46073f2b476af54c15d5260465867d87ca15bff`.
- Kernel non-routing and host-only interface gates passed within the protected transaction.

**This closes initial live host vmnet4 allocation only.** Do not archive,
recover, reapply or remove the committed journal. Historical rolled-back
journals remain preserved. No fresh Windows guest management NIC was
attached by this host transaction, no `kingdom.operator` handoff was
completed and the 41-scenario installer was not executed.

**Next acceptance:** Verify that the exact committed configuration and
the pinned vmnet4 host address survive a controlled VMware networking
service restart with every guest powered off. VMware Workstation can
reassign an interface address after service recreation despite a
HOSTONLY_HOSTADDR directive: do not claim persistence without testing.
Any persistence repair must be vmnet4-only, separately guarded, and must
never stop/start NORTH guests or alter another vmnet.

Once host-side persistence is established, attach the management NIC
ONLY to the fresh registered instance bf5369-wslpe-vmware. Verify
two-adapter topology, learner/operator isolation, independently pinned
Windows HTTPS WinRM certificate, operator credential application and
authentication, WinRM-independent console recovery, and eventually
41/41 Windows scenarios, including original release and clean-build gates.


## 2026-10-22: first shared-network restart revealed host-address persistence gap

The host allocation is **committed**, but the operator's deliberate,
guest-free `vmware-networks --stop/--start` acceptance failed:

| Network | Before restart | After restart |
| --- | --- | --- |
| WSLPE operator `vmnet4` | 172.28.233.254/24 | **172.28.233.1/24** |
| NORTH `vmnet10` | 10.4.10.254/24 | **10.4.10.1/24** |
| NORTH management `vmnet99` | 10.4.99.254/24 | **10.4.99.1/24** |
| WSLPE exercise `vmnet3` | 172.28.232.1/24 | 172.28.232.1/24 |

The config remained under the committed root journal, but the live
`WorkstationHostAdapterVerifier` correctly refused `vmnet4` after
VMware regenerated its default .1 addresses. This does **not** invalidate
the committed allocation journal, and **must not** trigger a fresh apply,
rollback or new VMware restart.

The existing GOAD_NOMAD / NORTH network bootstrap implements an
independent systemd host-address repair service and timer for
`vmnet10` and `vmnet99`. WSLPE must **not** replace or alter it.

Source integration now provides an independent, root-owned
`kingdoms-wslpe-vmnet4-hostaddr.service/.timer` and standalone keeper
`scripts/wslpe-vmnet4-hostaddr-keeper.py`. It requires the exact committed
vmnet4 journal, verifies all pre-existing VMware network directives and
the exact vmnet4 host-only metadata (tolerating only Workstation's
documented removal of HOSTONLY_HOSTADDR hints), checks interface/route
ownership, forwarding/bridge state, and corrects **only** VMware's
`172.28.233.1/24` default or empty host address to
`172.28.233.254/24`. Other addresses, extra routes, unexpected
configuration and uncommitted journals refuse changes.

The service runs **only a root-owned installed copy**, not executable
Python from the user's writable repository. The independent 15s timer
repairs vmnet4 after later VMware recreation; it cannot restart shared
VMware networking, touch NORTH/WSLPE exercise interfaces or boot a VM.
The guarded installer is
`scripts/wslpe-vmnet4-install-persistence.sh`; it requires both guests
off, exact clean source, a committed journal, explicit approval, and
NORTH's address recovery verified **read-only** after its independent
timer runs. It checks at least one vmnet4 timer interval.

**Status:** source implemented and CI tested; not yet live installed.
No new VMware restart is needed for this fix. Before starting a
guest, receive `VMNET4_HOSTADDR_PERSISTENCE_INSTALLED` plus read-only
NORTH addresses `10.4.10.254/24` and `10.4.99.254/24`.

Further acceptance still requires actual post-recreation persistence,
a fresh guest management NIC, credentialed `kingdom.operator` HTTPS
WinRM, WinRM-free operator recovery, 41/41 scenario provisioning, and
independent clean-build acceptance.


## 2026-10-22: live WSLPE host-address persistence installed

Operator's latest Kali evidence confirms:
- `VMNET4_HOSTADDR_PERSISTENCE_INSTALLED` and two successive
  `VMNET4_HOSTADDR_PERSISTENCE=PASS` results, including a timer interval.
- `vmnet4`: `172.28.233.254/24` after VMware previously reset it to .1.
- The dedicated `kingdoms-wslpe-vmnet4-hostaddr.timer` is enabled and active.
- `vmnet10`: `10.4.10.254/24` and `vmnet99`: `10.4.99.254/24`
  were independently restored without WSLPE writes.
- `vmnet3`: `172.28.232.1/24` remained the learner exercise interface.
- VMware network configuration still corresponds to the committed
  `vmnet4` allocation; no Windows NIC or scenario installation was performed.

**Host persistence keeper live installation gate: PASS.** This confirms
correct installation and at least one timer interval, but does not yet
prove full system reboot or another VMware service restart. Do not
repeat shared network restarts as a generic diagnostic.

**Next engineering milestone:** add the dedicated management adapter
(slot 2 / `ethernet2`) to **only** registered fresh
`bf5369-wslpe-vmware`, preserve NAT `ethernet0` and exercise
`ethernet1` on `vmnet3`, and configure guest-side operator address
`172.28.233.31/24` with no operator-network default gateway.
Bind the management Windows NIC by its unique VMware MAC and preserve
Vagrant/provider compatibility. Prove independent console restoration,
pinned WinRM HTTPS/5986 operator authentication and negative
learner-to-management/NORTH reachability before retiring Vagrant/NAT.
Then execute the existing scenario journal and validate 41/41.
