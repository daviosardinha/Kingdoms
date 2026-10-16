# WSLPE P1-C — Controlled guest-to-host packet-path acceptance

**Status: SOURCE COMMITTED; new packet acceptance not yet executed on Kali.**
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
