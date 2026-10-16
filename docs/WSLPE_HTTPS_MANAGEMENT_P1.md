# WSLPE P1: operator HTTPS transport bootstrap

Status: **P1-A LIVE TLS PIN/SAN PASS; P1-B AUTHENTICATED HTTPS PROBE COMMITTED, LIVE TEST PENDING**.

NORTH is completely frozen. No NORTH guest, provider, Vagrantfile, network,
credential, shared role, DC, or VM is changed by this verification.

## Starting point

The WSLPE live access audit on 2026-10-15 reported exact machine
`WSLPE-WS01` not joined to any AD domain. Its HTTPS WSMan listener exists
at TCP/5986, with certificate subject `CN=WSLPE-WS01`,
thumbprint `C773EC26D02940F559FE715B83628FEDAE2AA92D`,
and expiry 2029-10-13. RDP is NLA-required with TLS. Existing HTTP/5985
NTLM management works but is a *bootstrap* channel, not the final
learner-safe operator path.

A TCP/5986 listener and time-valid certificate are **not proof** of identity,
chain trust, Subject Alternative Name or authenticated secure management.

## Stage P1-A: read-only pinned TLS transport

The new `scripts/wslpe-https-trust-audit.py` does the following:

1. Verifies the unique native WSLPE instance and exact **running registered**
   VMX using the existing Stage 2 guards; derives the instance's validated
   exercise address, not a hardcoded vmnet or NORTH address.
2. Contacts TCP/5986 **without credentials** to discover the HTTPS leaf.
   This first retrieval is explicitly **untrusted** and never an approval.
3. Compares the observed SHA-1 thumbprint to the independently collected
   certificate binding from the earlier WSLPE live audit. A mismatch stops.
4. Creates a temporary, **in-process** TLS trust context pinned to that exact
   certificate. Performs a fresh TLS handshake to the IPv4 address using SNI
   `WSLPE-WS01`, OpenSSL certificate verification, and hostname checking.
   Requires an exact DNS Subject Alternative Name for `WSLPE-WS01`
   (CN-only acceptance is prohibited). Enforces TLS >= 1.2 and that
   the verified leaf remains the pinned certificate; reports SHA-256.
5. Exits fail-closed with no remediation, no credentials sent, no certificate
   import, no /etc/hosts changes, no Windows/VMware/firewall writes.

The Windows bootstrap box may use a **self-signed certificate**. Pinning
it explicitly is a private operator trust bootstrap, not proof of public PKI
chain trust or a long-term CA strategy. If the certificate lacks a DNS SAN or
its self-signed chain cannot validate, **STOP** and plan a WSLPE-only
certificate maintenance/rollback procedure after operator approval.

Command, on the existing Kali clone:

```bash
cd "$HOME/kingdoms-lpe-standalone" || exit 1
git pull --ff-only || exit 1
"$HOME/.goad/.venv/bin/python" -m unittest -v tests.test_wslpe_https_trust_audit
"$HOME/.goad/.venv/bin/python" scripts/wslpe-https-trust-audit.py \
  --expected-thumbprint C773EC26D02940F559FE715B83628FEDAE2AA92D
```

The fingerprint is not a password. Reconfirm it from out-of-band Windows VM
console evidence before treating it as the root of trust in a production setup.
SHA-256 is emitted for an additional stronger pin.

## P1-B: authenticated HTTPS (NOT YET COMPLETE)

Do **not** assume P1-A is authenticated WinRM. After P1-A passes, arrange a
verified local operator resolution `WSLPE-WS01` => the native instance IP,
then test WinRM NTLM with **certificate validation enabled** and a scoped trust
anchor. DNS/hosts and any trust-store changes require separate operator
approval and WSLPE-only rollback. Operator credentials must never be logged.
Do not use `ansible_winrm_server_cert_validation=ignore` as an HTTPS acceptance
result.

## P1-C: operator-only boundary (NOT YET COMPLETE)

Operator management currently enters through the same exercise NIC that will
eventually be learner-facing, and WSLPE's provisioner still uses the well-known
`vagrant` bootstrap identity. Before learner activation, create an
independent restricted control path, ensure read-only and read/write recovery
can survive network transitions, replace exposed bootstrap credentials,
verify firewall source restrictions and NAT-guard persistence.

**Release state:** WSLPE remains `PROVIDED`, NOT `READY`.
No NAT cutover, learner, NORTH, VM lifecycle or scenario mutation is
authorized by a P1-A transport check.


## 2026-10-15: P1-A live verified; P1-B new probe

The operator's live `wslpe-https-trust-audit.py` execution passed:
- Six existing source regression tests PASS
- Observed 5986 leaf SHA-1 matches `C773EC26D02940F559FE715B83628FEDAE2AA92D`
- TLS 1.2 handshake verified against the exact pinned certificate, with DNS SAN `WSLPE-WS01`
- No Windows, VMware, host trust store, DNS or NORTH changes

The expected `[BLOCKED]` output inside the source tests was an intentional
negative certificate case. The actual operator live TLS probe returned PASS.
P1-A is therefore closed, but not equivalent to authenticated WinRM.

The new **P1-B** `scripts/wslpe-https-auth-audit.py` tests actual NTLM WinRM
over HTTPS, certificate verification **enabled**. It replays the P1-A pin
and TLS/SAN validation before asking for any credentials. For the WinRM
request it uses a process-temporary PEM trust anchor (deleted afterward)
and a process-only socket resolution shim which permits **only**
`WSLPE-WS01:5986` to resolve to the uniquely registered private guest
IP. The WinRM URI stays `https://WSLPE-WS01:5986/wsman`, preserving HTTPS
hostname validation. Any attempts to resolve foreign or unrelated hosts
fail closed. Environment-driven HTTP proxies/.netrc are disabled within the
dedicated Python requests session.

The remote command reads `COMPUTERNAME` and `Win32_ComputerSystem.PartOfDomain`,
then prints unambiguous PASS markers; it never changes Windows configuration,
account privileges, firewall, RDP, VMware NICs, DNS or NORTH. The source
contains no operator password. If the secure read-only probe fails, stop and
inspect the failure type; **do not** use an insecure TLS fallback.

Operator command:

```bash
cd "$HOME/kingdoms-lpe-standalone" || exit 1
git pull --ff-only || exit 1
"$HOME/.goad/.venv/bin/python" -m unittest -v tests.test_wslpe_https_auth_audit
"$HOME/.goad/.venv/bin/python" scripts/wslpe-https-auth-audit.py \
  --expected-thumbprint C773EC26D02940F559FE715B83628FEDAE2AA92D
```

An operator password is requested interactively if the private
`KINGDOMS_WSLPE_BOOTSTRAP_PASSWORD` environment variable is not present.
**Do not paste the password into logs or commit it to Git.** The current
bootstrap vagrant identity remains temporary; final operator isolation and
bootstrap secret rotation are separate P1-C gates. This new P1-B audit has
not yet run against the operator's live WSLPE machine. The instance remains
`PROVIDED`, not `READY`.


## 2026-10-15: P1-B live authenticated HTTPS PASS; P1-C host boundary pending

The operator executed `tests.test_wslpe_https_auth_audit` (**6/6 PASS**) and
then `scripts/wslpe-https-auth-audit.py`, which reported:

- `[PASS] WSLPE-only TLS pin, chain, SNI and SAN: WSLPE-WS01 @ 172.28.231.31:5986`
- `[PASS] WSLPE_AUTHENTICATED_HTTPS=TRUE`
- `[PASS] WSLPE_DOMAIN_FREE=TRUE`

**P1-B is closed:** HTTPS transport and remote local machine identity were
successfully authenticated with scoped TLS verification, without changing DNS,
the host trust store, VMware, Windows, the firewall or NORTH.

**P1-C remains unverified and mandatory.** The operator channel is currently
on the future learner exercise NIC. VMware Ethernet0 provisioning NAT remains
connected. The VMware custom host-only exercise vmnet exposes the **host-side
interface** to the guest unless *external* filtering prevents traffic.
Learner SYSTEM rights are an intended exercise outcome; guest-only firewall
and restricted user tokens therefore are not isolation boundaries.

Added `scripts/wslpe-p1c-topology-audit.py` and its source regression.
This command only reads the **one exact registered WSLPE VMX**, the local
host's VMware vmnet definitions, its interface IPv4 and its route to the
WSLPE guest. It does not ping or connect to NORTH, and does not modify the
host/guest. It intentionally reports `[RELEASE BLOCKED]` even with
correct VMX mapping because it does not prove the external firewall,
NAT/forwarding removal, outage recovery or guest-to-host/NORTH denial.

```bash
cd "$HOME/kingdoms-lpe-standalone"
git pull --ff-only
"$HOME/.goad/.venv/bin/python" -m unittest -v tests.test_wslpe_p1c_topology_audit
"$HOME/.goad/.venv/bin/python" scripts/wslpe-p1c-topology-audit.py
```

**Operator authorization before any future mutations:** choose and prove
independent out-of-band console rollback, guest-to-host drop enforcement,
persistent host firewall guard, expected learner RDP reachability, and
a WSLPE-only NAT cutover. Never rely on interface metadata alone. Do not
assume P1-C is complete after its passive topology audit.
