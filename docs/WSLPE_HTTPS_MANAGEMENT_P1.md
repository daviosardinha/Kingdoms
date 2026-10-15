# WSLPE P1: operator HTTPS transport bootstrap

Status: **CERTIFICATE PIN AUDIT SOURCE READY; OPERATOR RUNTIME TEST PENDING**.

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
