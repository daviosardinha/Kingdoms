# WSLPE — Live workstation and security audit (2026-10-15)

**Assessment state: BASELINE VERIFIED / NOT READY FOR LEARNER RELEASE.**

Scope: **only** the independently registered `WSLPE-WS01` in the Kingdoms
`WSLPE` lab, plus its dedicated management/host safeguards. No AD
domain, no modifications or tests targeting NORTH guests, NAT infrastructure,
NORTH routes, DCs, or shared identity policies.

Evidence is from the operator's posted live
`bash scripts/wslpe-access-audit.sh` output, preceded by the same
operator's `bash scripts/wslpe-network-acceptance.sh` and 38/38
source-parity tests. This is **not** a network penetration test or proof of
interactive RDP access.

## Live evidence and outcome

| Control | Observed evidence | Status |
| --- | --- | --- |
| Exact machine | `Machine=WSLPE-WS01` | PASS |
| Active Directory separation | `DomainJoined=false`; prior 9/9 Windows baseline also confirmed standalone | PASS |
| WSMan provider | Two entries (`WSManProviderListenerCount=2`) | PASS |
| WinRM HTTP | One configured listener; TCP 5985 listening; authenticated HTTP/5985 proven separately | PASS for **bootstrap** only |
| WinRM HTTPS | One configured listener; TCP 5986 listening; matched HTTPS listener thumbprint present in LocalMachine/My | PASS for listener/attachment only |
| HTTPS certificate | Subject `CN=WSLPE-WS01`, time-valid at observation; expires 2029-10-13 | PASS for presence/time validity only |
| HTTPS transport security | Certificate chain trusted by Kali/operator, SAN/hostname match for selected endpoint, revocation handling and authenticated HTTPS action | **NOT VERIFIED** |
| RDP service | `TermService=Running`, `RDPConnectionsEnabled=true`, TCP 3389 listening | PASS for service only |
| RDP security | `RDPNLARequired=true`, `RDPSecurityLayer=2` (Windows SSL/TLS security layer) | PASS for configured prerequisites only |
| Effective local learner RDP | New `lpe.trainee` interactive sign-in, non-admin token, user rights, profile and tested restricted source | **NOT VERIFIED** |
| WinRM management safety | Prior host nftables audited WSLPE-only non-loopback drop for host NAT-forwarded TCP/2210 | PASS at time of earlier check; **persistence NOT VERIFIED** |
| Windows security baseline | Prior 9/9 live check: UAC, Defender, 3 Windows Firewall profiles enabled, correct Windows 10 identity, current evaluation grace | PASS for prior point-in-time observation |
| Network layout | Prior VMX has nat Ethernet0 + custom vmnet2 Ethernet1; guest `172.28.231.31/24`, NAT `192.168.213.248/24`, no default route via exercise NIC | PASS for metadata; **egress/isolation NOT VERIFIED** |
| Windows evaluation | Prior status=1 with 129598 minutes grace after operator-authorized rearm | PASS for short-lived private test only; **commercial entitlement NOT VERIFIED** |
| Source regression | 38/38 WSLPE/NORTH parity tests; 0 domain indicators in 25 scanned shared role files; live access audit 4/4 tests + 3/3 Ansible tasks, `changed=0` | PASS for covered checks |
| LPE scenarios | 20 existing techniques available in shared engine; WSLPE single-technique harness exists | **NONE proven with standalone learner yet** |

### What the live 3/3 Ansible result really means

The audit successfully authenticated using the **existing WSLPE HTTP/5985
operator channel**, inspected the TLS/WSMan/RDP configuration, and checked
preconditions. It did **not** authenticate over HTTPS/5986, validate
TLS hostname trust, log in by RDP, create the local learner, test
cross-network filtering, exercise the NAT handoff, or install/exploit any LPE
scenario.

## Prioritized risks and remediation requirements

### Critical before learner release — trusted operator/learner separation

- **The operator credential is still a bootstrap fixture**: current
  `ad/WSLPE/data/inventory` and `inventory_disable_vagrant` specify
  `ansible_user=vagrant` with a known default password; read-only Stage 2
  also defaults to that account. Do not expose that identity or its inventory
  to any learner. Implement a **WSLPE-only** operator secret rotation and
  protected material distribution with a verified recovery path, after the
  management HTTPS channel is proven.
- **The operator currently uses NTLM WinRM over HTTP/5985** on
  `172.28.231.31`, the very NIC intended to be vulnerable/learner-facing.
  Although WinRM NTLM uses message protections, the port and admin context
  must not remain learner-accessible. Move operator management to
  authenticated, trusted HTTPS with correct endpoint name, then restrict it to
  a private operator-only path. TCP 5986 being open is not proof.
- **VMware NAT remains connected** during bootstrap; host-only vmnet2 alone
  does not prevent access to its VMware host or routed networks. Learner
  escalation to local SYSTEM is an expected outcome of this course, so
  isolation must withstand *full guest compromise*, not merely standard
  learner permissions. Test host, hypervisor, NORTH routes and adjacent VMs
  from the compromised-guest perspective. Do not disconnect NAT until
  rollback/recovery and independent management are verified.

### High — RDP authorization is still incomplete

- RDP is enabled with NLA and TLS, but we have **no evidence of effective
  local learner authorization**. WSLPE foundation defines a standard local
  account only; it does not grant `Remote Desktop Users` nor prove effective
  `SeRemoteInteractiveLogonRight` or lack of deny rights. Need a WSLPE-only
  local SID/group/right contract and *real* RDP logon/token test.
- Validate Windows Firewall **effective remote-address/profile matching**
  for both RDP and WinRM, not just profile-enabled settings. NORTH's
  Domain-profile RDP rule does not work as a policy template for a workgroup
  Windows machine: design explicit Public/Private source-scoped rules.
- Do not make the learner a local Administrator merely to get RDP working.

### High — management listener and NAT guard lifecycle

- The known VMware NAT forwarded socket listens on wildcard, mitigated by a
  specific nftables INPUT restriction; this rule was documented as
  **runtime-only**, not guaranteed after reboot. Verify host reboot
  persistence or block WSLPE startup/learner access on missing guard.
- Verify the HTTPS certificate chain, SAN/name, expiration, intended thumbprint
  and authenticated connection against a *trusted operator resolver*.
  `ansible_winrm_server_cert_validation=ignore` does not qualify as trust.
- Preserve exact VMX targeting, unique native instance registration, bounded
  wait and **manual** rollback, without restarting host-wide VMware NAT.

### Medium — repeatability, portability, time-limited Windows evaluation

- Current Vagrant **resume** with temporary direct WinRM passed live; a
  clean, newly created WSLPE host has not yet passed full install-to-ready
  parity, secure post-cutover management or reproducibility.
- A valid Windows Enterprise Evaluation rearm restores about 90 days in the
  private developer VM, but does not supply redistribution/hosted-course
  licensing. A separately licensed, distributable Windows image is a
  hard release condition.
- The 20 existing LPE techniques have reversible NORTH results but must
  independently prove local-account apply/vulnerable/exploit/reset/clean/
  reapply under WSLPE, including Stored RunAs credential targets.

## Hard WSLPE-only boundaries

1. **NORTH remains untouched**: no NORTH VMX, guest, route, vmnet,
   controller, AD DNS, firewall, identity, playbook or deployment command.
   NORTH sources are **read-only reference material**.
2. No operations on the currently running WSLPE guest without an explicit
   stage-specific operator approval.
3. New implementation belongs in `ansible/wslpe-*`,
   `scripts/wslpe-*`, `tests/test_wslpe_*`,
   `kingdoms/wslpe_*`, `ad/WSLPE/*` or WSLPE-only documentation.
4. **Shared-role caution:** the feature branch had earlier changed
   `ansible/roles/windows_lpe/tasks/techniques/stored_runas_credentials.yml`
   to add a WSLPE override with a NORTH-compatible default. This is a shared
   consumer file, so it is *not* an example for future changes under the new
   NORTH freeze policy. Review such shared changes for zero NORTH behavioral
   impact; prefer a WSLPE-only adapter going forward.
5. WSLPE status remains `PROVIDED`, never `READY` as a result of these
   read-only audits.

## Next gates in strict order

1. **Operator HTTPS proof**: non-mutating certificate/SAN/chain validation
   and authenticated HTTPS/5986 test using an explicit operator-side trust
   policy; then design operator-only network path/secret rotation/rollback.
2. **RDP local learner contract**: WSLPE-only SID/group/right policy,
   effective NLA/TLS access from intended learner ingress, actual non-admin
   token/proof of deny to privileged management, explicit rollback.
3. **Network isolation**: fail-closed, repeatable WSLPE-only NAT transition
   that retains operator recovery, verifies all host/NORTH/adjacent-network
   reachability from the *fully privileged guest*, and verifies nftables
   guard persistence.
4. **Technique acceptance**: validate 20 individual scenarios on the
   standalone workstation, then full-set collision testing; workgroup/no-AD
   evidence must remain true throughout.
5. **Release**: appropriate Windows image licensing, tenant isolation,
   per-learner ownership and lifecycle governance.

**Current decision: the live WinRM/RDP CONFIGURATION PRECHECK is green;
the secure ACCESS AND ISOLATION gates are still blocked/unverified.**
