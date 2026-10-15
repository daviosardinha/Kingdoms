# WSLPE ← NORTH WS01: domain-free workstation parity audit

Status: **source audit complete; parity implementation PARTIAL; no learner release**.
Audited against `feature/windows-lpe-standalone-foundation` on 2026-10-15.
This is an engineering contract for the independently registered WSLPE guest,
not approval to run NORTH's deployment scripts on WSLPE.

## Goal and non-negotiable boundaries

Create a reliable, repeatable local Windows privilege escalation workstation with
the same engineering rigor as NORTH WS01 but **no AD dependency of any kind**.
The one Windows client runs under its own `WSLPE` native instance, on an
operator-chosen private subnet, with its own standard *local* learner.
A clean WSLPE deployment MUST NOT require DNS from a DC, domain controllers,
domain accounts, join/rejoin, LDAP, GPO, trust relationships, SMB to NORTH,
NORTH routers/vmnets, or an authenticated NORTH session.

NORTH is frozen. The only permitted cross-course shared components are
provider-neutral Windows behaviors whose inputs and effects have been reviewed;
all WSLPE configuration, networking and runtime checks remain instance-scoped.

## Full NORTH WS01 path versus WSLPE

| Stage | Proven NORTH WS01 source | WSLPE source/decision | Current state |
| --- | --- | --- | --- |
| Machine identity/image | `ad/GOAD/providers/vmware/Vagrantfile`, `GOAD-WS01`, pinned `mayfly/windows10:2024.01.06`, 2 vCPU/4096 MB | `ad/WSLPE/providers/vmware/Vagrantfile`, independent `WSLPE-WS01`, same box and capacity | SOURCE ALIGNED |
| Instance boundary | Native LabManager/LabInstance/VMware provider | Same native instance/VMX registration, separate workspace | LIVE VERIFIED |
| VMware Windows startup | `template/provider/vmware/Vagrantfile` with GOAD-only VMware Tools IP guard; `goad/provider/vagrant/vmware_nomad.py` | Vagrant template, WSLPE-only verified resume using temporary direct WinRM | RESUME LIVE VERIFIED, FRESH BOOT PARITY PENDING |
| Host-exercise network | Static MAC + vmnet10 + NORTH router in `ad/GOAD/providers/vmware/Vagrantfile`, `vagrant/fix_ip.ps1` | Dedicated vmnet2 observed; subnet derives from instance, not fixed in source | METADATA VERIFIED; FULL ISOLATION PENDING |
| Initial WinRM | `vagrant/ConfigureRemotingForAnsible.ps1` creates HTTP/HTTPS listeners/cert; NORTH provider uses bounded auth checks | Vagrant Windows bootstrap source shared; inventories explicitly HTTP/5985 for current direct path | HTTP AUTH VERIFIED; HTTPS CERT/TRUST PENDING |
| Guest licensing | `ansible/roles/settings/eval_rearm`, post-reboot validation | Exactly same role reused, operator-approved recovery completed; Windows license gate | PRIVATE DEV PASS (TIME-LIMITED) |
| Hostname | `ansible/roles/settings/hostname` | Same role in WSLPE future foundation, canonical `WSLPE-WS01` only | SOURCE ADOPTED; LIVE FOUNDATION APPLY PENDING |
| Windows baseline | `ansible/ws01.yml`: `common`, keyboard, updates, admin password, hostname | Explicit independent WSLPE baseline: exact host/workgroup, Defender, UAC, firewall, licensing, local-only learner | WINDOWS GATE 9/9 PASS; LEARNER NOT PROVISIONED |
| RDP service/NLA | `ansible/roles/common/tasks/main.yml`, `scripts/rdp-host-evidence.ps1` | WSLPE-only `ansible/wslpe-access-audit.yml`, keep NLA; local learner group later | TCP OPEN; POLICY AND LOGIN NOT YET PROVEN |
| RDP authorization | `settings/adjust_rights`, `settings/user_rights`, NORTH Rickon group policy | Explicit local non-admin `WSLPE-WS01\\lpe.trainee`, isolated user-right contract; no domain principal | NOT YET IMPLEMENTED/ACCEPTED |
| Session acceptance | `scripts/validate-rdp-runtime.sh`, `scripts/validate-rdp-release-acceptance.sh` | Fresh local RDP login proof, token/SIDs, NLA and negative/admin checks needed | PENDING |
| Exercise cutover | `scripts/lab-mode.sh`, `scripts/validate-ws01-runtime.sh`; persistent NAT disconnect with verification/rollback | New WSLPE-only bounded network handoff, no NORTH scripts, no fixed vmnet names | NOT IMPLEMENTED; CUTOVER LOCKED |
| LPE profiles | `ansible/ws01-lpe-install.yml` + `windows_lpe` full profile | `ansible/wslpe-lpe-test.yml` uses same role, one selected technique; `WSLPE-WS01\\lpe.trainee` | SHARED SOURCE; ALL 20 LIVE STANDALONE TESTS PENDING |
| Rollback/release | NORTH per-technique apply/validate/reset and source/runtime gates | Operator-only status/reset; fresh learner privilege proof and isolation recheck | PENDING |

## Review of imports: reuse, adapt, exclude

**Reuse unchanged** (with explicit WSLPE caller): `settings/eval_rearm`
and `settings/hostname`. These are not domain-join roles. The
`windows_lpe` framework is shared but individual scenarios still require
standalone validation and local identity-specific parameters.

**Adapt, never copy wholesale**: WinRM listener/certificate setup from
`vagrant/ConfigureRemotingForAnsible.ps1`; RDP NLA/listener checks from
`scripts/rdp-host-evidence.ps1`; bounded readiness, fail-closed registration,
exercise-interface isolation and rollback from NORTH's lifecycle.
The WinRM bootstrap script can enable Basic authentication,
`LocalAccountTokenFilterPolicy=1`, and a broad HTTPS firewall rule.
Do **not** use those defaults as a learner-facing security policy.
`ansible/roles/common` opens RDP specifically on the **Domain** firewall
profile, not applicable to WSLPE's Public/Private workgroup interfaces. Future
WSLPE inbound rules must be source scoped and proved against the real trusted
operator/learner network model, not copied from NORTH.

**Exclude entirely**: `commonwkstn` (domain DNS, default route to
NORTH router, join and domain profile), `ad-data`, `ad-servers`,
`settings/adjust_rights` with domain memberships, NORTH's global `user_rights`
policy unless redesigned around WSLPE local SIDs, `lab-mode.sh` and
the NORTH vmnet10/20/30/99 policy, `settings/no_updates` which disables
Windows Update, NORTH SMB exposure/Phase01 fixtures and
`NORTH\\rickon.stark` credentials.

## Concrete source discrepancies and fixes

1. The WSLPE guest's Vagrant bootstrap management forward on vmnet8 mapped to
   the guest's host-only exercise IP, leaving Vagrant waiting. A temporary
   instance-scoped direct WinRM override is now used only for an authorized
   resume; it was proven in a real resume. Fresh boot still needs the same
   deterministic management handoff acceptance instead of long blind timeouts.
2. WSLPE inventory originally fell back to Ansible HTTPS/5986; explicit HTTP
   5985 settings now match the verified direct management path. Operator
   access to HTTP via the vulnerable exercise NIC is **temporary only**.
3. An ad-hoc diagnostic used `winrm.exe`; the NORTH-compatible read-only
   access audit now relies on WSMan PowerShell APIs and tests.
4. The shared Stored RunAs scenario validates that its credential target matches
   `$env:COMPUTERNAME`. NORTH defaults to `WS01\\kingdom.runas`. WSLPE
   explicitly overrides the **target only** to
   `WSLPE-WS01\\kingdom.runas`, leaving NORTH's deployed default intact.
   **Runtime standalone scenario proof remains mandatory.**
5. WSLPE's future baseline now guards the exact Windows name and imports the
   idempotent shared hostname role; neither has been applied to the running
   WSLPE workstation through foundation provisioning.
6. Existing WSLPE inventories include a Vagrant bootstrap password and direct
   HTTP management. Those are **operator bootstrap fixtures, never release
   credentials**. Before learners receive access, rotate/disable the bootstrap
   identity, remove operator secrets from learner reachability, and migrate to
   a trusted authenticated HTTPS management path with verified trust.
7. The pinned Windows 10 evaluation image is time-limited. A successful private
   rearm on 2026-10-15 is **not a commercial course licensing solution**.
   The hosted/paid course needs a separately licensed Windows image and
   deployment rights for each assigned learner instance.

## Phased implementation — preserve live machine

- **P0 Source parity / acceptance contract**: compare upstream NORTH,
  prohibit domain dependencies in WSLPE, pin local identity and scenario
  host variables, keep `install` limited to Stage 1, run unit/source tests.
- **P1 Authenticated operator management**: audited certificate binding and
  trusted WinRM HTTPS, remote reachability and credentials, scoped firewall
  rules. An open TCP 5986 is insufficient.
- **P2 Local learner/RDP**: WSLPE-only account/group/rights contract with
  SID-based checks, RDP NLA, actual new low-privilege desktop token, source
  restriction and independent operator-only control plane.
- **P3 Exercise isolation**: test rollback before modifying guest interfaces.
  Implement exact-VMX, WSLPE-only bounded NAT cutover and persistence, verify
  host/hypervisor/NORTH cannot be reached from the learner interface, including
  if the learner escalates to SYSTEM; verify the wildcard WinRM forwarding
  listener is not left exposed. Preserve an out-of-band recovery channel.
- **P4 Scenario and commercial acceptance**: confirm a licensed Windows image,
  test 20 existing techniques individually on the standalone local learner,
  `apply -> vulnerable -> learner exploit -> reset -> clean -> reapply`,
  then full collision/offline regression; add 15 new scenarios only after
  independently successful proof.

## Single source and runtime gates

Before any mutation, validate the feature branch and the source-only parity
test contract:

```bash
cd "$HOME/kingdoms-lpe-standalone"
git pull --ff-only
bash scripts/wslpe-ws01-parity-source.sh
```

Separately, once those source checks pass, run the existing **read-only**
`bash scripts/wslpe-access-audit.sh` and
`bash scripts/wslpe-network-acceptance.sh`. Any baseline drift blocks
provisioning. These checks do **not** imply fresh RDP login, isolation or
the final 20 LPE scenarios have been validated. All stage-changing actions
require operator approval; never invoke NORTH's lab-mode or reinstall WSLPE.

**Current decision:** WSLPE remains `PROVIDED`, **NOT READY**, independent
of AD. It must not be offered to learners until P1–P4 are validated.


## Operator validation: source parity gate 38/38 PASS

On 2026-10-15 the operator synced the feature branch through commit
`e83ec61` and executed:

```bash
bash scripts/wslpe-ws01-parity-source.sh
```

Observed results: **38 tests PASS / 0 FAIL**, strict standalone role source audit
**0 domain indicators in 25 scanned files**, `[PASS] WSLPE/NORTH source
contract`, and `[NO CHANGES]` to Windows, VMs, NAT or NORTH. This closes
the **source-only parity gate**; it does **not** establish WSLPE live HTTPS
certificate trust, authenticated HTTPS, local learner RDP, exercise isolation,
or scenario exploitation.

The next existing committed command is the read-only
`bash scripts/wslpe-access-audit.sh`, which discovers the native registered
WSLPE VMX and uses the already verified Ansible HTTP/5985 connection to inspect
WSMan listeners/HTTPS certificate, RDP/NLA and service state. Do not apply the
foundation, disconnect NAT or run LPE actions until the evidence passes and
the control-plane/learner access design is approved.
