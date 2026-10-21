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
