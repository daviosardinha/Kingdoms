# WSLPE P1-C — One-shot NAT handoff readiness and release gate

**Status:** Consolidated live read-only audit PASSED on 2026-10-16. NAT cutover LOCKED; WSLPE PROVIDED / NOT READY. NORTH frozen.

## Evidence already accepted (October 16)

The operator proved 38/38 source tests plus three-phase guest-to-Kali
TCP acceptance: OPEN before filtering, CLOSED with exact WSLPE-only nft
filter active, OPEN after host-side timer interval and table removal.
Pinned authenticated HTTPS/5986 survived. This proves the scoped
IPv4 packet path, NOT persistent isolation or NAT removal.

## One complete read-only command

    cd "$HOME/kingdoms-lpe-standalone" || exit 1
    git pull --ff-only || exit 1
    bash scripts/wslpe-p1c-completion-gate.sh

The gate combines source safety tests, the existing consolidated WSLPE
host/guest checks, and new exact VMX/NIC/MAC, Windows IPv4/IPv6 default
route, pinned HTTPS, nftables, listener and reboot-service diagnostics.
It confirms prior WSLPE-only firewall-table removal and does NOT rerun
the previously accepted three-minute packet pilot. Credentials are
resolved from the existing WSLPE-only Ansible inventory automatically.

No Vagrant/VMware lifecycle, Linux/Windows network mutation,
nft application, Windows credential rotation, reboot or NAT disconnect
is authorized by this command. No NORTH guest is contacted or changed.
The gate prints ALL findings in one report rather than introducing
another sequence of individual tests.

## Required coordinated changeset after this evidence

1. Persistent, WSLPE-only host INPUT/FORWARD firewall including IPv6;
   preserve the existing guarded, wildcard-bound Vagrant WinRM forward.
   Demonstrate exact table persistence over host reboot. Do not alter
   shared VMware NAT (vmnet8), NORTH or other nft tables.
2. Proven independent VMware/VMX rollback: exact registered WSLPE VMX,
   owned saved configuration with integrity validation, safe power-state
   handling, independent timed restore and out-of-band host console.
   A hypothetical recovery method is not enough to authorize cutover.
3. Vendor-safe VMware Ethernet0 NAT disconnect while powered off,
   persist startConnected=FALSE only for WSLPE, verify runtime NIC state
   after startup, preserve independent Ethernet1/vmnet2 management.
   Changing VMX while guest is running is not accepted as disconnection.
4. Post-cutover denial: no guest NAT egress or unprotected host forwarding,
   authenticated direct HTTPS still working, positive/negative owned
   packet-path proofs for IPv4/IPv6 plus ARP/L2 and VM host isolation.
   Do not probe NORTH as a test target.
5. Then nonadmin local learner/RDP/NLA acceptance, scenario-level
   vulnerability/recovery tests, and appropriately licensed Windows
   deployment for commercial learners.

## Completion semantics

The new preflight deliberately emits
WSLPE_NAT_CUTOVER_AUTHORIZED=FALSE even if its read-only checks pass,
because no independent VMX restore process or reboot-persistent host
firewall has yet been demonstrated. Do not equate a successful source
run with a safe NAT cutover or a learner-ready release.

NORTH is untouched; all source changes remain on the WSLPE feature branch.


## October 16 — Accepted complete live audit and single implementation milestone

The operator ran the complete one-shot P1-C gate on Kali. The submitted
terminal log shows **66/66 source/safety tests PASS** plus **29/29
additional consolidated review tests PASS**. An early [BLOCKED] ValueError
appearing between these sections was the deliberately simulated negative
test for missing VMX; it was **not** a live infrastructure failure. This
test now captures its own expected output to remove that confusing marker.

Actual evidence, all scoped to WSLPE:
- Exact registered and uniquely running `windows_10.vmx`, exercise
  `vmnet2`, host `172.28.231.1`, guest `172.28.231.31`.
- NAT Ethernet0 remains attached; distinct exercise Ethernet1 remains
  attached. Windows NICs match both VMware VMX MAC identities exactly.
  Windows NAT NIC index 6 has one default route; dedicated exercise NIC
  index 8 has **no IPv4 or IPv6 default route**.
- **One IPv6 address exists on the exercise NIC**. This is exposure
  evidence, not a successful IPv6 attack or a proof of isolation.
- Co-tenant detection found no other *running* VMX explicitly on
  vmnet2 among five checked. Powered-off VMs, dynamic attachments and
  hypervisor paths remain unverified.
- Certificate-pinned, authenticated WinRM HTTPS/5986 **PASS** and
  domain-free Windows identity **PASS**. Windows security baseline
  **9/9 PASS**; guard table present.
- Previous scoped nft policy not installed; no collision; syntax
  check accepted; WSLPE pilot table absent after prior timer;
  post-rollback HTTPS **PASS**.
- Host nftables boot service was **disabled**. Host firewall
  persistence across reboot has NOT been proved.
- Existing host has **18 TCP/UDP listeners** bound to its dedicated
  WSLPE interface or wildcard addresses. This does not mean all
  are reachable from the guest; positive/negative packet tests
  must demonstrate the actual allowed paths.
- `WSLPE_NAT_READINESS_AUDIT=PASS; REMAINING_GATES=4`;
  `WSLPE_NAT_CUTOVER_AUTHORIZED=FALSE`.

**Engineering decision:** Stop repeating source/read-only audits.
The next GitHub change must deliver one reviewed WSLPE-only
implementation containing (a) host reboot-persistent filtering with
safe scoped rollback, (b) an independent exact-VMX/NAT restore runbook
and timer that is actually executable under the existing VMware owner
context, (c) a vendor-safe powered-off Ethernet0-only cutover, and
(d) IPv4/IPv6/ARP/L2 and post-restart acceptance. The new implementation
must not promise complete guest isolation merely because the IPv4
INPUT filter passed. If VMware host-only vmnet2 cannot meet the L2
boundary, redesign the exercise/management boundary rather than
weaken the acceptance criteria.

**No VM lifecycle or firewall changes were authorized or made by the
read-only gate.** NORTH is frozen, and no learner RDP or training release
may be enabled until the new controls pass live acceptance.


## VMware host-only boundary — isolation design decision

VMware's documented **host-only** network type explicitly places the
hypervisor host and attached guests on a *shared private LAN*:
https://knowledge.broadcom.com/external/article?legacyId=1006480

This is correct for the **current trusted local development** topology,
but it is not, by itself, an isolation boundary against a Windows guest
where the course deliberately grants a learner SYSTEM privileges.
Our audited `vmnet2` has a Kali host-side `172.28.231.1` interface and
the WSLPE guest has a link-local IPv6 address. The successful host nft
INPUT IPv4 TCP test is evidence for *that one path*, not ARP/L2 or
all host/hypervisor attack surfaces.

Therefore, **do not declare learner-grade safe isolation just by
disconnecting Ethernet0 NAT**. Keep vmnet2 for private development,
with the temporary protections already proven, until the separate
learner-grade architecture is selected. A guest-only VMware LAN Segment
(or another provider-native isolated virtual switch with no host adapter),
coupled to a deliberately trusted and separately isolated operator/
attacker access path, is a candidate design; it is not implemented and
its Linux VMware Workstation behavior still requires validation.

Vendor networking reference:
https://knowledge.broadcom.com/external/article/307810/creating-subnets-in-vmware-workstation.html

VMware Workstation and vSphere are different management planes. A
vSphere PowerCLI `Set-NetworkAdapter -Connected` example must **not**
be treated as proof that local Linux Workstation `vmrun` supports an
equivalent safe hot disconnect. Any cutover/restore action must use
proven commands for the existing VMware Workstation version and the
exact registered WSLPE VMX, with a host-independent recovery option.

This is an architectural release decision, not a new diagnostic loop.


## 2026-10-16 — Boot-time host firewall guard must track live Vagrant port

The accepted owner-context read-only recovery gate passed **30/30**
source tests. The independent host-side systemd worker successfully ran
`vmrun -T ws list` as the registered WSLPE VMX owner, observing six
running VMware guests but selecting the **one exact WSLPE VMX only**.
The real VMX was untouched; scratch NAT-change and original-byte
restoration passed.

### Persistence dependency discovered in source

The current WSLPE forwarded WinRM port is discovered at runtime through
`scripts/wslpe-stage2-inspect.py::forwarded_winrm_port()`, ultimately
using `vagrant port WSLPE-WS01`. The existing
`kingdoms/wslpe_winrm_guard.firewall_batch(port)` deliberately drops
non-loopback traffic at the **exact discovered host TCP port**.
Historically VMware/Vagrant has reassigned this forwarded port after
collision. **A boot service that blindly hardcodes TCP/2210 is unsafe**:
it could fail to protect a newly reassigned host listener.

The next boot-persistence implementation must therefore be one
coordinated WSLPE-only change that proves the live forward mapping
matches the protected port, revalidates the guard after Vagrant/VMware
port reassignment, and fails closed rather than silently leaving the
current listener exposed. It must never rely on restarting shared
VMware NAT services or importing NORTH router/nftables configuration.

The boot-stage guard needs to be verified **before** any untrusted
learner can reach a running WSLPE VM. Dedicated nftables table identity,
INPUT/FORWARD hook priority, IPv4/IPv6 packet evidence and startup
ordering must all be validated after a real host restart. Enabling
`nftables.service` without proving it preserves the existing host
rulesets is forbidden.

The host-only vmnet2 L2/ARP boundary is a separate unsolved blocker,
even if boot persistence and NAT disconnect subsequently pass. No
release readiness promotion or live VMX mutation is authorized from
the successful read-only recovery gate.


## Recovery-state machine and boot-port candidate — source staged

The 2026-10-16 engineering branch now includes actual **WSLPE-only
recovery logic**, with live mutation still locked behind separate
authorization and independent-timer integration:

- `kingdoms/wslpe_exact_restore.py`: accepts only the exact
  registered WSLPE VMX and verified non-root owner. Generates a
  SHA256-bound Ethernet0-only candidate, refuses unknown VMware
  rewrites, and can restore original VMX bytes by atomic rename
  **only after powered-off state has been independently confirmed**.
- `kingdoms/wslpe_vmware_recover.py`: NORTH-derived explicit
  `vmrun stop <exact VMX> soft` → wait until absent from unique VMware
  inventory → exact offline restore → optional `vmrun start <exact VMX>
  nogui` with readiness check. Never forces power off, touches a
  second VMX or restarts a guest that was already stopped. Ambiguous
  duplicate aliases in VMware inventory fail closed. No live caller
  is yet wired to this mutation-capable module.
- `kingdoms/wslpe_boot_policy.py`: reuses the existing verified
  `kingdoms_wslpe_winrm` and `kingdoms_wslpe_exercise` nftables
  renderers. It requires the **current WSLPE Vagrant forwarded port**
  and dynamic exercise vmnet/subnet, rejects global firewall/NAT
  changes, and marks boot installation **NOT AUTHORIZED**.
- `scripts/wslpe-p1c-boot-policy-preview.py`: read-only registered
  VMX, dynamic `vagrant port`, unique root `ss` vmnet-nat listener
  and current guard verification. No host firewall writes.
- `tests/test_wslpe_exact_restore.py`,
  `tests/test_wslpe_vmware_recover.py`,
  `tests/test_wslpe_boot_policy.py`: scratch-only and mocked
  fail-closed regressions, also included in the existing parity gate.

**One new first-run operator command**:

```bash
cd "$HOME/kingdoms-lpe-standalone" || exit 1
git pull --ff-only || exit 1
bash scripts/wslpe-p1c-recovery-and-boot-gate.sh
```

This command runs source tests and live read-only port/VMX
checks. **It does NOT run the new VMX restore function on a real VM,
register a rollback service, install persistent nftables tables,
enable `nftables.service` or disconnect NAT.** Its read-only checks passed on Kali (31/31 source tests and boot-policy preview PASS).

**Not yet implemented:** durable owner-context recovery bundle and
independent timed execution of the *real* VMX restore; boot-service
ordering ensuring an untrusted WSLPE guest cannot start before the
dynamic forwarded WinRM guard and scoped exercise filter are active;
host-reboot persistence validation. The host-only VMnet2 ARP/Layer2
boundary remains a separate architectural release blocker.

A boot service that reconciles the port only AFTER VMware exposes
a newly forwarded listener cannot prove zero exposure during the
interval. Fail-safe startup ordering or a stronger guest-only network
boundary must be proven, not asserted from a successful preflight.
Until then, **NAT cutover and learner access remain locked**.


## 2026-10-16 — 31/31 recovery and boot-policy source acceptance

The Kali operator executed
`bash scripts/wslpe-p1c-recovery-and-boot-gate.sh` and confirmed
**31/31 source tests PASS**. The live read-only preview additionally
confirmed the exact registered `windows_10.vmx`, Vagrant's currently
assigned host-side TCP/2210 forwarded to guest WinRM, an exact wildcard
`vmnet-nat` listener, existing `kingdoms_wslpe_winrm` table matching
this port, and the fingerprinted WSLPE-only guard+exercise filter source.

Acceptance marker:
`WSLPE_P1C_RECOVERY_AND_BOOT_POLICY_PREVIEW=TRUE`.
Explicitly **not** accepted:
`BOOT_INSTALL_AUTHORIZED=FALSE`.

Next combined implementation must do **real lifecycle testing without
endangering NORTH** and host firewall persistence in a fail-closed
fashion. Source success is not proof of durable protection. Independent
recovery needs registered VMX ownership, immutable approved original
bytes, exact current candidate match, definite powered-off state and
an actually executing owner-side host timer before any persistent NAT
change. VMware may rewrite VMX after a lifecycle transition; such a
rewrite must trigger manual recovery, not blind overwrite.

A post-start attempt to discover and guard the dynamic forwarded
WinRM port cannot protect the period between port assignment and
guard installation. The hard safety property is that **VM startup is
blocked until a verified boot guard exists**, or its NAT forward is
already disabled. Do not auto-enable the global `nftables.service`,
set broad TCP port-range drops that could affect NORTH, or advertise
vmnet2 as ARP/Layer-2 isolated.

No VMware lifecycle, Windows, NAT, firewall, systemd, or NORTH state was
changed by this acceptance command. WSLPE remains PROVIDE-only.


## Recovery bundle staging — before any live NAT cutover

After the clean 31/31 recovery/boot-policy acceptance, source work
continues on the missing independent recovery prerequisite. The
new `kingdoms/wslpe_recovery_bundle.py` creates a **private,
write-once-by-path recovery manifest** holding exactly the original
WSLPE VMX bytes, the deterministic Ethernet0 NAT-disabled candidate,
both SHA256 digests, the registered VMX path, exercise VMnet and exact
non-root owner UID. JSON parsing rejects unknown schema/fields,
mismatched owner, registration, candidate, checksum, symlinks and
insecure ownership/modes; the candidate is independently re-rendered
from the original. Source regressions operate only on disposable VMX
copies under a private temporary directory.

This bundle cannot be reconstructed from the NAT-disabled VMX after a
cutover: it **must** be captured and verified against the real registered
WSLPE VMX while provisioning NAT is still attached. The recovery bundle
is private and checked for accidental corruption; **SHA256 alone is not
an authenticity signature** and does not prevent an owner with host
filesystem access from replacing both the manifest and hashes. A live
worker must verify a separately approved/pinned manifest digest and the
current exact VMware identity and power state before any restore.

The existing `wslpe-p1c-recovery-and-boot-gate.sh` now also runs the
bundle source tests. The additional tests have **not yet run on Kali**.
No systemd timer is wired to write the real VMX, and no automated cutover
or boot firewall installation is authorized. NORTH remains frozen.

For commercial learner deployment, host-only VMnet2 is NOT accepted as
a sufficient L2 boundary against compromised SYSTEM-level guests.


## 2026-10-16 — 36/36 recovery bundle acceptance, rollback timer contract staged

The operator ran `bash scripts/wslpe-p1c-recovery-and-boot-gate.sh`
after the `umask 077` fixture correction: **36/36 PASS**.
The live read-only dynamic Vagrant WinRM forward inspection again
confirmed exact native WSLPE `windows_10.vmx`, TCP/2210 owned by
`vmnet-nat`, current exact-port guard verification, and the
fingerprinted scoped nft source. No VM/guest/host changes occurred.
`BOOT_INSTALL_AUTHORIZED=FALSE` remains correct.

**New coordinated source batch** (no runtime execution yet):
`kingdoms/wslpe_rollback_worker.py` verifies that a private
recovery.json is pinned to an **externally approved SHA256**, rereads
the native WSLPE instance, checks the same exact registered VMX and
non-root owner UID, and refuses unexpected VMware VMX modifications.
The digest must be captured before any NAT disconnection. The worker
does not trust a bundle's own claimed VM identity as authority.
`kingdoms/wslpe_rollback_timer_plan.py` renders a 240-second
systemd *system* timer candidate under that exact user, with a
unique-unit contract and fail-closed arming prerequisites.
`scripts/wslpe-p1c-rollback-plan.py` previews registration,
bundle digest and timer settings with **no files or units written**.
`tests/test_wslpe_rollback_timer_plan.py` rejects wrong digest,
NORTH/foreign registration, wrong owner, unsafe timer arguments,
and spoofed systemd environment variables. The CLI executable
`scripts/wslpe-p1c-rollback-worker.py` **intentionally rejects
all real --restore invocations** until a separately approved,
root-owned authorization context is implemented and accepted.
A spoofable `INVOCATION_ID` or other environment flag is not
an authorization boundary.

The one command for the **entire new pending source checkpoint** is:

```bash
cd "$HOME/kingdoms-lpe-standalone" || exit 1
git pull --ff-only || exit 1
bash scripts/wslpe-p1c-rollback-and-boot-review.sh
```

This combines the existing recovery suite, additional timer tests,
exact VMX registration, and dynamic WinRM port/firewall read-only
preview. It does NOT install systemd units, schedule a real recovery
timer, stop a VM, edit a VMX, touch nftables or NORTH.

**Next release engineering (still incomplete):** independently trusted
root-owned recovery approval, a separately proven systemd-host
restore path, a boot-time WSLPE-only firewall/startup ordering
contract validated across a Kali restart, and a learner-grade network
isolation design that does not expose Kali at ARP/L2. None of these
requirements may be marked PASS based on source tests alone.


## 2026-10-16 — 42/42 rollback timer preview accepted; separate release scopes

Live Kali output of `bash scripts/wslpe-p1c-rollback-and-boot-review.sh`
confirmed **42/42 tests PASS**, in-memory private recovery-bundle digest,
registered `WSLPE-WS01` VMX, scoped WinRM/host policy on current
Vagrant TCP/2210, and the 240-second rollback timer **preview**.
`TIMER_ARMED=FALSE`, `BOOT_INSTALL_AUTHORIZED=FALSE`, and
`WSLPE_NAT_CUTOVER_AUTHORIZED=FALSE` remain the truthful live statuses.

We detected and corrected a planning-policy mismatch: the prior
`approve_arming()` demanded learner-grade guest-to-host L2 isolation
even for **trusted local WSLPE engineering** on the existing Kali
host-only vmnet2 network. These are now separate explicit scopes:

- **local_dev:** may continue toward an exact-VMX WSLPE-only NAT
  transition and restore rehearsal after **real** recovery acceptance,
  management return route verification, and reboot-proven WSLPE boot
  firewall and startup protection. It deliberately acknowledges
  Kali's existing L2 exposure and NEVER permits an untrusted learner.
- **learner:** requires **all** the above AND proven guest-to-host
  Layer-2/hypervisor isolation plus local non-admin learner/RDP
  acceptance, scenario resets and compliant Windows licensing.
  `vmnet2` host-only is **not** adequate for this release.

The gate defaults to **learner**, fails closed on unknown scopes and
preserves the explicit blocking status for both currently.
`scripts/wslpe-p1c-rollback-plan.py` now prints independent lists
of missing proofs in one run; source unit tests enforce that
`local_dev` cannot accidentally promote `learner`.

No WSLPE reboot/start/stop, NAT disconnect, nft write, guest changes
or NORTH change occurred in this source update. The new scope tests
have not yet run on Kali. The next engineering work is *not another
source preview*: it is root-owned recovery approval and host firewall
persistence installed with a bounded, independently tested rollback
and startup race mitigation. Learner topology remains a separate
architecture milestone.
