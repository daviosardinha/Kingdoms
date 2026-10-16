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
