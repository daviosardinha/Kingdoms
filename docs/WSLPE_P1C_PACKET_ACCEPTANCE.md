# WSLPE P1-C — Controlled guest-to-host packet-path acceptance

**Status: THREE-PHASE IPv4 GUEST-TO-HOST PACKET ACCEPTANCE — LIVE PASS (2026-10-16).**
NORTH is frozen. WSLPE stays PROVIDED, not READY.

## What the prior pilot proved

The 2026-10-16 remote 120-second host firewall pilot proved the exact
WSLPE-only nft filter could be applied and subsequently observed absent;
cert-verified operator WinRM HTTPS survived before, during and after.
It **did not** prove traffic from the vulnerable Windows guest was blocked.

This stage adds that missing dataplane evidence without probing other
machines, domains, host services, or NORTH. It does NOT disconnect
provisioning NAT or authorize learner access.

## Exactly what is tested

On the dedicated VMware host-only WSLPE exercise interface (currently
vmnet2, derived from the native registered instance) a disposable,
unprivileged IPv4 TCP listener binds **only** to the dynamically audited
host-side IP, currently 172.28.231.1, on TCP/47381. It never binds to
0.0.0.0 or any Tailscale/NAT interface.

The already working pinned, certificate-verified HTTPS/5986 operator
channel to exact machine WSLPE-WS01 runs one bounded, read-only Windows
TCP connection attempt to that dedicated listener, checking
COMPUTERNAME and PartOfDomain before returning an exact open/closed
marker. The host separately checks that the accepted peer is the
expected WSLPE exercise IPv4 (currently 172.28.231.31).

The **three-phase state-changing** acceptance (separately approved)
must establish all of:

1. **Positive control before filtering:** guest TCP OPEN and listener
   accepted one connection from the exact WSLPE guest.
2. **Negative control while WSLPE-owned filter active:** guest TCP CLOSED
   and host listener received no new guest connection. The existing
   verified remote pilot rechecks the dedicated VMX, co-tenants,
   nft -c, operator SSH route separate from all vmnet interfaces,
   transient timer smoke proof, authenticated HTTPS and installs
   ONLY the reviewed WSLPE nft table with independent 180-second timer.
3. **Recovery positive control:** after the host-side timer window,
   the exact nft table must be absent and the guest TCP test must be
   OPEN again, with an accepted guest peer and working certificate-
   verified WinRM HTTPS. The host listener is then closed.

If a phase fails after the pilot starts, the script attempts an immediate
rollback **only if it can verify the exact reviewed WSLPE nft policy**.
The independent host-side rollback timer remains armed. An unexpected
table, loss of management, missing positive control, or ambiguous result
must never be treated as PASS.

## One consolidated BASELINE command

From the Kali operator's existing SSH session (the same Tailscale route):

~~~bash
cd "$HOME/kingdoms-lpe-standalone" || exit 1
git pull --ff-only || exit 1
bash scripts/wslpe-p1c-packet-review.sh
~~~

This runs source regressions, verifies the unique WSLPE-native VMX,
candidate syntax and SSH-return path, exercises an independent 3-second
host timer smoke test (one temporary /run sentinel, subsequently deleted),
uses the existing WSLPE inventory credentials without a password prompt,
then opens one temporary, exact-host IPv4 listener and attempts a guest
connection to it. **It does not install an nft firewall table or change
NAT, VMware, Windows configuration, host routes or NORTH.**

Expected baseline marker: \`[PASS] WSLPE_PACKET_BASELINE=TRUE\`.

The tests/observations must first be reviewed before the guarded
state-changing attempt. When explicitly authorized, the same single
launcher supports \`--execute\` with an interactive typed confirmation:
\`PROVE WSLPE PACKET ISOLATION\`. That option temporarily installs the
reviewed host WSLPE nft policy for 180 seconds; it is not part of the
baseline command above. If SSH is interrupted, independent host timer
rollback should still occur; after reconnecting use
\`bash scripts/wslpe-remote-operator.sh --verify\` to verify table absence
and WinRM HTTPS. Allow at least 210 seconds for expiry.

## What this acceptance STILL cannot prove

This deliberately narrow test validates **one exact IPv4 guest->host
TCP service path** against the proposed host nft INPUT filter. It does
not prove every host service is blocked, IPv6 or ARP/L2 behavior, routed
FORWARD traffic, cross-VM access, hypervisor interfaces, NAT egress, or
anything about a future learner with SYSTEM privileges. Even three-phase
PASS does not by itself prove safe isolation for a commercial course.

NORTH must never be used as a test target or modified. NEXT:
design and verify an out-of-band recoverable **WSLPE-only NAT handoff**
with explicit exact VMX ownership, plus a broader cross-layer isolation
matrix and eventual local non-admin learner RDP acceptance.


## 2026-10-16 — First source regression defect and Kali desktop support

First operator attempt at the combined `--execute` workflow stopped at
unittest before any live listener, nft rules, Windows network change or
firewall operation. The log showed **35 tests, 34 PASS and 1 ERROR**:
`test_positive_control_demands_remote_and_matching_guest_listener`.
The mocked listener's `count.side_effect=[0,1]` was consumed by the
positive case. Reusing the same iterator for the negative case yielded
`StopIteration`, which is a regression test fixture bug, not a Windows
network failure.

The test now resets the listener mock before each independent case,
and additionally asserts that an uncorroborated guest OPEN result fails
when no accepted guest IP is observed. The failure is fail-closed because
the launcher has `set -euo pipefail`; **no firewall pilot occurred**.

Operator has returned to local Kali. The CLI formerly refused an
`--execute` without `SSH_CONNECTION`. It now distinguishes:
- **SSH**: existing independent operator route and systemd timer smoke
  checks, then remote guarded pilot.
- **Local Kali console**: an interactive TTY and actual independent
  systemd timer smoke proof before any WSLPE-owned filter installation,
  then the same 180-second bounded pilot and HTTPS/rollback gates.

The remote route check is never skipped on actual SSH execution. A local
non-interactive session cannot authorize firewall modifications.
No NORTH, VMware, guest NAT, routing, Windows guest or host firewall
changes were made by these source fixes.

The first accepted result must include **all source tests PASS** and
`[PASS] WSLPE_PACKET_BASELINE=TRUE` (guest-to-host positive control).
New regression tests and live packet-path probes remain pending operator
execution. The `--execute` option is still state-changing and requires
the exact typed confirmation string. Exercise NAT remains attached and
guest L2/IPv6/NORTH isolation remains unverified.


## 2026-10-16 — Three-phase IPv4 packet acceptance: LIVE PASS

The operator executed `bash scripts/wslpe-p1c-packet-review.sh --execute`
from the **local Kali desktop** and provided the complete terminal result.

Observed results:
- **38 source regression tests PASS, 0 failures**.
- **Independent host-side rollback timer smoke test PASS**.
- Exact guest identity `WSLPE-WS01`, standalone/domain-free, on the
  dedicated exercise network `vmnet2` (`172.28.231.0/24`); native
  registered WSLPE VMX confirmed. No other *running* VMware VMX was
  explicitly assigned to vmnet2 (five checked).
- **Positive before filtering:** Windows `172.28.231.31` initiated a
  connection to Kali's dedicated `172.28.231.1:47381` listener. The
  Windows socket returned OPEN **and** the Kali listener observed the
  accepted peer from exactly the expected guest IPv4.
- **Negative while filtering:** The bounded nftables policy was active on
  `vmnet2`. Certificate-verified authenticated WinRM HTTPS continued
  working. Windows returned CLOSED and the Kali listener did **not**
  observe a guest connection:
  `WSLPE_GUEST_HOST_TCP_BLOCKED_WHILE_FILTERED=TRUE`.
- **Recovery after 180-second timer window:** The unique WSLPE-owned nft
  table was absent (`WSLPE_FILTER_TABLE_ABSENT_AFTER_TIMER_WINDOW=TRUE`),
  the Windows TCP positive control returned OPEN again, the host listener
  accepted the exact peer, and verified HTTPS management remained healthy.
  `WSLPE_HOST_FILTER_PACKET_PROOF_AND_ROLLBACK=TRUE`.

**Result:** The narrow WSLPE *IPv4 guest-to-owned-Kali TCP INPUT filtering*
acceptance is now **complete**. A systemd smoke-test separately proved
the host timer infrastructure can execute. Table absence after the
scheduled interval does not alone establish the particular removal cause.
No WSLPE VMware NAT disconnect, Windows settings, host routing changes,
NORTH guest modification, or permanent host firewall installation
was requested by the test.

**Release gates still open:** IPv6, ARP/Layer 2 and hypervisor/VMware
paths; any other host service or routed packet path; guest NAT
egress/removal; exact VMX-only reversible NAT lifecycle with independent
management and restore; persistent host enforcement across restart;
non-admin learner/RDP access; 20 independently restorable LPE scenarios.
**WSLPE remains PROVIDED, NOT READY.**

**Next engineering batch (read-only before any cutover):** In one
consolidated WSLPE-only run, re-verify authenticated independent management,
NAT NIC and persistent VMX mapping, IPv4/IPv6 guest routes, current
guest/host VMnet exposure, host guard lifetime and exact-VM rollback
mechanism. No NORTH tests or changes. Design a bounded NAT cutover that
cannot affect shared VMware NAT services; require explicit approval
before modifying Ethernet0.
