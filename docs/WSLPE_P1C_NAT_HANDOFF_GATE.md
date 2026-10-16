# WSLPE P1-C — One-shot NAT handoff readiness and release gate

**Status:** Audit committed; new live run pending. WSLPE PROVIDED / NOT READY. NORTH frozen.

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
