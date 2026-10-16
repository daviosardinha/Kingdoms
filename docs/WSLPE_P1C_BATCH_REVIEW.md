# WSLPE P1-C: Consolidated read-only review

Status: SOURCE COMMITTED, FIRST LIVE BATCH REVIEW PENDING. Instance remains
PROVIDED / NOT READY. NORTH is completely frozen.

## One operator command

Run from the owner Kali account:

    cd "$HOME/kingdoms-lpe-standalone" || exit 1
    git pull --ff-only || exit 1
    bash scripts/wslpe-full-review.sh

The launcher compiles the source and executes mock/source regressions before
collecting live evidence. It asks for sudo once to inspect local firewall
and listener state. It uses nft --check (never nft --apply), nft JSON listing,
ss and iptables-save/ip6tables-save. It then runs the existing WSLPE-only
read-only postboot, WSMan/RDP and HTTPS authentication checks and the
new Windows-side local account and firewall inventory.

## Scope of the one-shot audit

- Exact registered and uniquely running native WSLPE VMX.
- Host/guest subnet, VMware adapter and route mapping.
- VMX metadata only for other *running* VMware guests using the dedicated
  WSLPE vmnet. No packet probes, Windows commands or changes to NORTH.
- Kernel check-mode validation of the candidate WSLPE nftables rules;
  existing firewall table conflict, INPUT/FORWARD chain counts and
  legacy iptables/ip6tables rule counts. Raw host rules are not displayed.
- Host socket exposure counts on WSLPE interface or wildcard addresses.
- Systemd nftables service enabled state, explicitly not a reboot proof.
- Existing WSLPE NAT-forwarded WinRM listener/guard, 9-point Windows
  baseline, network adapter, security and licensing checks.
- Existing WSMan listener, HTTPS certificate, RDP/TLS/NLA baseline.
- New WSLPE-only read-only guest-side Ansible inventory for local learner
  existence, disabled/admin/RDP group membership, inbound Windows firewall
  rule sources and profiles, routes, network profiles and listener ports.
- Previously independently pinned HTTPS/5986 NTLM authentication, strict
  certificate validation and domain-free WSLPE identity.

The collector continues after an individual audit fails and prints one
consolidated report of passed, blocked and unverified evidence. The
operator credentials are never printed or added to GitHub.

## Limits

A syntactically accepted host firewall proposal is NOT proof of effective
packet filtering or L2 isolation. vmnet2 also connects the vulnerable
guest to Kali, and its separate provisioning NAT adapter remains attached.
Future learner SYSTEM privileges can invalidate Windows-only defenses.
NAT disconnection, firewall application, nft reboot persistence, IPv6/ARP
and full co-tenant isolation, packet-level guest-to-host/NORTH denial,
an independently protected operator route and out-of-band rollback
must still be separately designed, explicitly approved and tested.

A zero exit here does not make the machine READY. Do not apply the printed
nft rules, restart VMware NAT or invoke NORTH lab-mode. The only acceptable
future rollback removes exact WSLPE-owned objects; never flush global
firewall chains or affect NORTH.

## Workflow change

Use this single batch once. Return its complete consolidated summary.
Then prepare one reviewed WSLPE-only fix/rollback plan from all findings
rather than repeating ad-hoc one-line checks between messages.


## 2026-10-15: First source regression run and correction

First operator execution updated the WSLPE-only feature branch through
`304e047`, ran **28 source tests**, with **27 passing and 1 failing**.
The only failure was `test_no_uncontrolled_output_or_mutating_calls`
checking for the stale literal `WSLPE guest local access`, while the
collector consistently uses `Windows guest local access`. This is an
assertion/label mismatch; it says nothing about the running Windows guest.

Because the launcher uses `set -euo pipefail`, **no live P1-C batch
inspection executed** after this source-test failure. The single test
was corrected in the feature branch. Mock tests were also made quieter
to avoid printing simulated negative-case BLOCKED findings, and an
additional exact WSLPE-only Ansible command-scope contract was added.

Next operator action remains the **same single command**:
`bash scripts/wslpe-full-review.sh` after `git pull --ff-only`.
This is source code under review; newly changed tests and the full
runtime pipeline have not been independently executed on Kali yet.
No NORTH or VMware/Windows/networking changes were performed.
