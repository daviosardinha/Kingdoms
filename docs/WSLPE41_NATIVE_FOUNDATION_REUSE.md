# WSLPE41: reuse the existing learner/operator foundation

**State:** Stage 1 guest `bf5369-wslpe-vmware` is PROVIDED. Learner/operator
accounts and 41 scenarios are **not** yet installed on this new guest. The
previous WSLPE development machine is a different native VM and remains
unchanged. This is a **read-only pre-foundation acceptance step**, not a new
Windows provisioning system.

## Existing source to reuse (no replacement roles)

- `ansible/wslpe-foundation.yml`: established standalone Windows baseline,
  licensed/evaluation check, standard local `lpe.trainee`, RDP group, UAC,
  Firewall and Defender validation.
- `ansible/wslpe-operator-foundation.yml`: dedicated, privately credentialed
  `kingdom.operator`, group proof, and strict no-domain/no-existing-account
  guard. Account creation is NOT proof of a working authenticated management
  transport.
- `kingdoms/wslpe41_foundation_executor.py`: bounded source-connected
  playbook invocations, exact instance inventory and Windows marker checks.
- `kingdoms/wslpe41_native_foundation_handoff.py`: calls the existing
  foundation in order and requires separately authenticated operator control,
  actual console recovery and fresh-guest attestation.
- `scripts/wslpe-https-trust-audit.py`,
  `scripts/wslpe-https-auth-audit.py` and
  `scripts/wslpe-account-audit.py`: existing exact WSLPE-only, read-only
  pinned TLS and Windows account inspection. The account audit now supports
  `--pre-foundation` to observe a genuinely empty fresh VM without wrongly
  requiring `lpe.trainee` to exist already. Default learner-required release
  semantics remain intact.

## Exact Stage 1 guest: read-only account/TLS preflight

The **new VM** is `bf5369-wslpe-vmware` at `172.28.232.31`. It is NOT
the original `d986ad-wslpe-vmware` at `172.28.231.31`.
The source auditor scopes `scripts/wslpe-stage2-inspect.py` to the current
checkout workspace and proves a unique registered, running WSLPE VMX.
It cannot safely target the old WSLPE checkout or a cross-workspace guest.

1. In VMware Workstation, open the **new VM's** interactive Windows console
   (verify its VMX path), not a WinRM session and not the old VM. Read the
   new guest's HTTPS listener binding without modifying it:

   ```powershell
   winrm enumerate winrm/config/Listener
   ```

   Record the HTTPS listener's `CertificateThumbprint` independently. Do
   not reuse the previous WSLPE development VM's thumbprint
   `C773EC26D02940F559FE715B83628FEDAE2AA92D`. This is a public
   certificate fingerprint, not a Windows password.

2. From the fresh KINGDOMS checkout (Kali), after the commit passes source CI:

   ```bash
   cd "$HOME/kingdoms-wslpe41-fresh"
   git pull --ff-only
   "$HOME/.goad/.venv/bin/python" -m unittest -v tests.test_wslpe_account_audit
   "$HOME/.goad/.venv/bin/python" scripts/wslpe-account-audit.py \
     --pre-foundation --expected-thumbprint "<NEW-VM-HTTPS-THUMBPRINT>"
   ```

   The audit validates the new VM's exact bound TLS fingerprint,
   trust anchor, SAN and HTTPS/5986 authenticated WinRM, then inspects only
   the existing allowlisted Windows account names and local administrator
   membership. It uses no persistent host resolver/CA changes and does
   not create accounts. An absent learner and operator are **expected**
   on this genuinely fresh Stage 1 guest; a privileged learner, wrong
   VMX, mismatched certificate, invalid Windows account evidence or
   failed authentication blocks the audit.

3. Save only the read-only PASS/BLOCKED results. Never include passwords
   in a report, Git commit, screenshot or forum post. Do not rotate or
   disable `vagrant` during this audit.

## 2026-10-21: expired Windows evaluation blocks learner foundation

On the new `bf5369-wslpe-vmware`, Windows System Event 1074 identified
`C:\\Windows\\system32\\wlms\\wlms.exe` acting as SYSTEM and powering
down the guest at 06:30, 07:41 and 09:43. The event comment was:
"The license period for this installation of Windows has expired. The operating
system is shutting down." This is an **OS-license-controlled shutdown**,
not Vagrant, VMware Tools, NORTH or a KINGDOMS start/stop lifecycle race.
Stage 1 infrastructure readiness passed, but Windows long-lived licensing
was not attested.

**Existing code is already present:** `ansible/wslpe-foundation.yml` imports
the shared `settings/eval_rearm` role before it creates the learner and then
requires at least 1,440 minutes of remaining evaluation grace or a genuinely
licensed non-evaluation Windows installation. The role only invokes the
documented Windows `slmgr.vbs /rearm` mechanism for a detected expired
`TIMEBASED_EVAL` installation, performs a controlled reboot, and checks
the grace period again. It does **not** renew an exhausted evaluation
indefinitely or constitute a commercial Windows licensing solution. This
existing role should be invoked through the verified fresh foundation flow,
**not** reimplemented as another licensing script.

**Read-only guest console checks before deciding the next step** (on this
guest only, in elevated Windows PowerShell):

```powershell
Get-CimInstance SoftwareLicensingProduct |
  Where-Object { $_.Name -like 'Windows*' -and $_.PartialProductKey } |
  Select-Object Name, Description, LicenseStatus, GracePeriodRemaining
cscript.exe //NoLogo "$env:SystemRoot\\System32\\slmgr.vbs" /dlv
```

Check evaluation channel, actual grace/rearm state and Windows image
licensing before any rearm or account mutation. Do not execute license
service tampering, time rollback, registry bypass or repeated blind rearm.
If Windows reports no eligible remaining evaluation grace, supply a
properly licensed and compatible source image instead. Preserve the new
guest and original WSLPE reference until the operator approves its
replacement or repair. A source acceptance PASS is not a live license PASS.

**Installer acceptance correction:** the final one-command WSLPE41
installation must treat `WSLPE_LICENSE_READY=PASS` and enough remaining
licensed operating time as a mandatory **pre-learner and pre-scenario**
readiness gate. Its 41/41 completion must never be reported while the
guest can be terminated by WLMS due to evaluation expiry.

## 2026-10-21: isolated developer learner bootstrap integrated (source-only)

The new native operator command `foundation_learner` has been connected to the
**existing** `ansible/wslpe-foundation.yml`. This is a one-shot, scoped
developer integration stage for `bf5369-wslpe-vmware`; it does **not**
constitute final protected operator management or 41-scenario release.

It performs the following under explicit operator confirmation:

1. Require the loaded **PROVIDED** native WSLPE VMware instance and its exact
   workspace/provider registration, running VMX, NAT MAC and exercise IP.
2. Reuse the already-approved native WSLPE inventory and fresh Windows
   `WSLPE_LICENSE_READY=PASS` evidence.
3. Obtain the WinRM HTTPS listener thumbprint from the **authenticated native
   bootstrap Windows session**, then verify the same certificate through the
   existing TLS pin/SAN/hostname audit on the exact guest. This avoids
   manually copying the thumbprint for each new installation. A certificate
   learned solely from an unauthenticated network handshake is not trusted.
4. Use the original certificate-verified `wslpe-account-audit.py` routines.
   Refuse a preexisting learner, operator or vulnerability fixture: do not
   silently overwrite earlier or partially applied accounts.
5. Generate a unique password using the existing
   `kingdoms/wslpe_learner_credentials.py` code, saved privately as 0600
   under `~/.local/state/kingdoms-wslpe41-foundation/<instance-id>/`.
   The original WSLPE development credential is **not** reused.
6. Execute **once** the original `ansible/wslpe-foundation.yml`, with a
   one-VM, exact local Vagrant/NTLM forwarded management override and private
   password in the child Ansible environment. This bootstrap channel is
   temporary and **not** the final isolated operator channel.
7. Re-prove Windows/VMX/MAC registration, original TLS certificate binding,
   pinned HTTPS account state, and learner nonadmin + Remote Desktop Users
   group membership; verify the operator has not yet been created.
8. Fail without automatic retries or secret rotation. A partially created
   local user or credential requires explicit operator review.

### Execute the existing foundation on the fresh development guest

Only after source CI passes and the operator has confirmed this VM is the
intended local testing guest (not NORTH or the original WSLPE VM):

```bash
cd "$HOME/kingdoms-wslpe41-fresh"
git pull --ff-only
"$HOME/.goad/.venv/bin/python" -m unittest -v tests.test_wslpe41_learner_bootstrap
./goad.sh -c windows-lpe
```

Inside the KINGDOMS console:

```text
load bf5369-wslpe-vmware
foundation_learner
```

When prompted for this **specific existing guest**, authorize using the exact
phrase `INSTALL WSLPE LEARNER`. A clean PASS marker is
`WSLPE_LEARNER_FOUNDATION=PASS`. Never rerun after a partially completed
attempt; inspect the guest and private local credential state first. The
new command does not log the learner password.

**Not yet proven by this stage:** actual user RDP/NLA sign-in, independent
VMware-console rollback, isolated operator network, `kingdom.operator`
authenticated over pinned TLS, Vagrant retirement, fixture deployment or
any 41/41 learner exploitation. These remain separate gates.

## Before actually running either existing foundation playbook

The Stage 1 provisioner currently uses `vagrant` over HTTP/5985. Its
Vagrant-generated self-signed HTTPS listener is **not** by itself the
trusted, independently isolated operator management plane required by
`kingdoms/wslpe41_stage_executor.py`. That executor deliberately requires
instance-specific private inventory, validated HTTPS/5986 TLS and an
independent VMware-console recovery capability. It has not been wired to
the production `--execute` command.

The next changes must reuse native KINGDOMS instances and the existing
HTTPS/management audits to implement that single guest's capability; then
run learner foundation once, prove nonadmin login, create operator once
after a genuine WinRM-free recovery check, authenticate independently,
and validate operator-only management isolation. No parallel manager, new
Windows role or NORTH modification. Disable/bootstrap-retire `vagrant`
only after an explicitly approved operator handoff and recovery test.

**Do not run** `ansible/wslpe-foundation.yml` or
`ansible/wslpe-operator-foundation.yml` directly against the historical
`ad/WSLPE/data/inventory` and treat that as fresh installation proof.
That inventory is intentionally HTTP/5985 with the development bootstrap
account. The 41-scenario runtime and JEA #30 are later gated stages.

Source CI and this read-only audit are not live learner/operator account
creation, management-isolation or 41/41 deployment evidence.
