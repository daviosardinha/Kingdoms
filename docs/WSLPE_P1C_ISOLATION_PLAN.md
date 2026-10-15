# WSLPE P1-C — Host-side exercise firewall candidate

Status: SOURCE PROPOSAL COMMITTED; NO LIVE HOST FIREWALL CHANGES.
WSLPE remains PROVIDED / NOT READY. NORTH is completely frozen.

## Starting evidence

The operator has proved native WSLPE-WS01 on its exact registered VMware VMX,
using a distinct exercise network vmnet2 (172.28.231.0/24). Kali's vmnet2
address is 172.28.231.1; WSLPE's is 172.28.231.31. The provisioning NAT
adapter Ethernet0 remains connected. Authenticated WinRM HTTPS with a checked
certificate and hostname passed P1-B. The earlier passive topology audit
passed 6 source tests and returned the expected network mapping.

## WSLPE-only host policy proposal

kingdoms/wslpe_isolation_policy.py renders a candidate table named
inet kingdoms_wslpe_exercise. There are no functions that install it.

INPUT: on the dedicated exercise vmnet, accept conntrack-established and
related reply traffic to already host-initiated sessions (for example HTTPS
WinRM from the Kali operator); drop other IP packets from that vmnet aimed
at Kali services.

FORWARD: drop IP packets forwarded into or out of the exercise vmnet.
OUTPUT: untouched, as are other nftables tables, policies, VMware services,
Vagrant files and all NORTH interfaces.

The inet nftables family covers IPv4 and IPv6 but not ARP, other Layer 2
traffic or VMware virtual switching. It is only one layer of defense.
Firewall acceptance in this table cannot override separate drop rules in
other chains. A runtime test is required before trusting management access.

scripts/wslpe-p1c-isolation-plan.py dynamically verifies the single running,
registered native WSLPE guest, the dedicated vmnet, VMX and subnet, host
interface and guest host route. It prints the nftables candidate and a
table-only rollback; it **never executes either**.

## Read-only operator check

    cd "$HOME/kingdoms-lpe-standalone" || exit 1
    git pull --ff-only || exit 1
    PY="$HOME/.goad/.venv/bin/python"
    "$PY" -m unittest -v tests.test_wslpe_isolation_policy
    "$PY" scripts/wslpe-p1c-isolation-plan.py

DO NOT pipe the displayed candidate into nft; it is for engineering review.

## Release-blocking limitations

1. Current WSLPE NAT Ethernet0 provides independent egress and possibly
   access to shared VMware networks. Filtering vmnet2 does not filter NAT.
   Persistent NAT disconnect must be WSLPE-only, planned and reversible.
2. The host-only segment physically includes the Kali host. ARP, VMware
   host-only services and neighboring guests on the same vmnet may bypass
   the proposed IP filter or require separate isolation. Do not equate this
   plan with isolation from a compromised SYSTEM guest.
3. Any host nftables operation requires a reviewed ruleset snapshot, an
   isolated syntax check, proof the selected vmnet has no other workloads,
   external negative-path tests, a bounded rollback that cannot affect
   NORTH, and a verified operator console recovery path.
4. The temporary Vagrant bootstrap admin credentials and the current
   HTTP/5985 management path must never become student-facing. After
   independent management design, prove HTTPS/5986 operator access through
   the actual intended protected route, then rotate bootstrap secrets.
5. Host firewall reboot persistence and existing nftables WinRM forwarded
   port guard still require explicit verification.
6. The Windows learner has not been provisioned or proven with RDP/NLA and
   a non-admin token. No LPE scenarios have passed standalone acceptance.

## No change contract

No NORTH machine, domain controller, route, lab-mode, shared VMware NAT
daemon, VMX, nftables table or Windows setting was modified by preparing
this proposal. The earlier dedicated WSLPE WinRM nftables guard remains
untouched. Only new WSLPE code and source tests were committed.

Further state-changing work needs explicit operator approval after the
read-only output is reviewed. Any eventual rollback must remove ONLY
the exact inet kingdoms_wslpe_exercise table and never flush all rules.
