# WSLPE41 operator management on bf5369

Scope: the already-running `bf5369-wslpe-vmware` / `WSLPE-WS01` in
`~/kingdoms-wslpe41-fresh`, on `feature/wslpe41-fresh-full-installer`.
This repairs only account/WinRM management. No vulnerability deployment,
VM creation, VMware/NIC changes, NORTH changes, historical-instance changes,
or merge into main.

## Cause and correction

The existing learner foundation passed on October 21, and the private operator
credential was prepared, but `wslpe-operator-foundation.yml` was never executed
on this fresh guest. That playbook creates an account only; it does not configure
or prove management transport. The future foundation executor requires final
TLS/inventory/recovery evidence before running, so it is not a usable bootstrap
handoff for the current guest. The older management-firewall CLI also assumes
the historical two-NIC `vmnet2` layout. Re-running those unrelated prerequisites
does not create a functioning operator channel.

The first live repair attempt stopped at `Inspect` before account or firewall
changes. The original compressed inspection still expanded to a 17,755-character
command through `Session.run_ps()`, which defaults to WinRM's `cmd.exe` path and
therefore exceeds its 8,191-character limit. The direct-process correction in
`120002c` still failed on the live guest with the now-visible command-length
error. Its local CreateProcess tests did not reproduce WinRM's server behavior.

The runner now starts a fixed PowerShell input loader below 2 KB and sends the
public source through WinRM's stdin stream in 8 KB chunks with explicit EOF.
UTF-8/base64 preserves source bytes independently of the Windows console code
page. Script size no longer lengthens the command line, regardless of whether
WinRM honors `WINRS_SKIP_CMD_SHELL`. The authenticated/encrypted transport stays
the same; no guest temporary file or automatic retry is introduced. Cleanup
closes the remote command and shell even when input transfer fails.
The decompression step is also inside the diagnostic catch, and errors without
our marker report an exit code and output lengths without printing raw stderr.
A split `Get-NetRoute` invocation was corrected so `-ErrorAction` belongs to the
route query and an absent management default gateway does not fail inspection.

For this initial-Inspect failure, update the branch and rerun the same `--apply`
command below. No receipt deletion, password replacement, rollback or VM restart
is required. `--verify` is meaningful only after the handoff succeeds.

`scripts/wslpe41-operator-management.py` connects the existing pieces for this
one instance:

1. Reuses the native registration, three-MAC identity and the existing read-only
   `vmnet4` keeper checks. The route must use `172.28.233.254` directly.
2. Reads, without regenerating, the private operator credential at
   `~/.local/state/kingdoms-wslpe-operator/bf5369-wslpe-vmware/credential`.
   It reuses the existing instance learner credential when invoking the original
   operator foundation. No password is printed or passed in command-line arguments.
3. Reads the existing HTTPS public certificate through the authenticated native
   loopback bootstrap, verifies it through the existing pin/chain/hostname/SAN
   checker, and uses NTLM over certificate-validated HTTPS to the management IP.
   The URI/SNI remains `WSLPE-WS01`, mapped only inside this process to
   `172.28.233.31:5986`. No resolver or system trust-store edits, certificate
   replacement, Basic authentication, or certificate-validation bypass.
4. Saves the original changed WinRM settings and a console rollback script in
   an Administrators/SYSTEM-only Windows folder. A local elevated-console check
   exercises creation/deletion of a disabled temporary firewall canary and
   records this transaction's nonce before account creation or cutover.
5. Executes the existing operator foundation once if the account is absent.
   An existing account must authenticate with its existing private secret; it
   is never reset or silently re-created. The standard learner is not changed.
6. Proves a fresh elevated `WSLPE-WS01\kingdom.operator` HTTPS session, and a
   still-working bootstrap session, before adding isolation rules.
7. Adds persistent, narrowly named Windows Firewall rules: HTTPS only through
   the management NIC at `.31` from `.254`; HTTP blocked on every NIC; HTTPS
   blocked on NAT/learner NICs and other management sources/addresses, including
   IPv6. Existing broad image rules are left intact but cannot override these
   explicit blocks. HTTP is restricted only after operator authentication passes.
8. Reconnects as the operator and the original bootstrap account over verified
   management HTTPS. Checks effective policy, then makes credential-free negative
   TCP probes to this WSLPE guest using local learner, NAT and NORTH source IPs.

The existing listener may still display `Address=*`. That does not mean it is
reachable on every interface: the effective Windows Firewall rules enforce the
boundary. Restricting the listener alone would not prove source isolation.

The original `vagrant` account/password and HTTP listener are retained for
console rollback; the account remains usable over validated management HTTPS.
After successful cutover, the old HTTP bootstrap runner cannot connect until
rollback restores its original access. Do not run an old HTTP-based provisioner
after this handoff. Integrating later scenario execution is outside this fix.

## One consolidated live procedure

Keep the existing fresh VM running and its elevated VMware-console PowerShell
open. On **Kali, as the normal Workstation owner**, run:

```bash
cd "$HOME/kingdoms-wslpe41-fresh" || exit 1
git switch feature/wslpe41-fresh-full-installer &&
git pull --ff-only &&
sudo -v &&
"$HOME/.goad/.venv/bin/python" scripts/wslpe41-operator-management.py --apply
```

The runner pauses once and prints an exact command containing a public nonce.
Run that command in **elevated Windows PowerShell in the fresh VMware console**,
then press Enter on Kali after `WSLPE_OPERATOR_CONSOLE=PASS`. Do not run this
console step through WinRM or on the historical WSLPE guest.

Successful live completion requires:

```text
[PASS] kingdom.operator authenticated and elevated over certificate-validated HTTPS
[PASS] WSLPE_OPERATOR_MANAGEMENT=PASS (live HTTPS, console record, policy and source probes)
```

For a repeatable, read-only acceptance run:

```bash
cd "$HOME/kingdoms-wslpe41-fresh" || exit 1
sudo -v &&
"$HOME/.goad/.venv/bin/python" scripts/wslpe41-operator-management.py --verify
```

The verification fails if learner, NAT or NORTH host source addresses are
missing, a forbidden WSLPE port accepts a connection, certificate validation
fails, the account token is wrong, or effective policy is incomplete. No
packets are sent to NORTH hosts; binding a local NORTH-interface source tests
the WSLPE source policy without modifying NORTH. These probes and the existing
non-routing `vmnet4` check are current management-access evidence, not a full
adversarial network assessment from a NORTH guest.

If an operation fails, the runner stops and retains the exact original credential
and recovery record. It does not automatically replay the foundation, erase a
journal, reset a password or undo the new protections. A deliberate rerun
re-authenticates an already-created operator before continuing. If a private
credential or recovery record is missing, restore the original rather than
generating a replacement.

## Local recovery

On this VM's **elevated VMware-console PowerShell**, independent of WinRM:

```powershell
& 'C:\ProgramData\Kingdoms\OperatorManagement-bf5369\management.ps1' -Mode Rollback
```

Rollback removes only this repair's named rules and restores its saved
LocalAccountTokenFilterPolicy value. Basic and AllowUnencrypted remain disabled;
native bootstrap uses NTLM message encryption. It does not delete
accounts, rotate passwords, touch NICs/IPs/certificates, or overwrite the prior
NIC/network transaction journals. Removing the isolation rules restores the
image's broad bootstrap reachability; it is a recovery action, not successful
management acceptance.

## Validation limits

Source tests use mocked Windows commands and do not establish live success.
Windows CI tests the input loader in real Windows PowerShell 5.1 and over an
actual NTLM-encrypted loopback WinRM connection. Both paths check a benign
successful Prepare payload and the early wrong-guest rejection with the actual
management source, and reproduce failure of the old oversized argument. The
WinRM fixture is restricted to an explicitly enabled disposable GitHub-hosted
runner, uses a temporary account and cleans up its account/listener/token policy.
No lab VM is contacted, and no firewall rule or insecure authentication is enabled.
The runner's live PASS is required on the actual VM. A console canary proves
independent elevated recovery capability, not a completed outage/rollback drill.
The rules are stored persistently, but reboot persistence needs a later live
`--verify` after a user-controlled restart; this repair does not reboot anything.

Guest firewall rules do not contain a learner who has already achieved SYSTEM
and can change them. The final LPE distribution/isolation assessment remains
separate. No scenario, full-installation or course-release PASS is emitted.

Implementation references:

- [Microsoft: Windows Firewall rule precedence](https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/rules)
- [Ansible: workgroup WinRM configuration and NTLM](https://docs.ansible.com/projects/ansible/latest/os_guide/windows_winrm.html)
- [Microsoft: UAC remote token filtering](https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/user-account-control-and-remote-restriction)
- [Microsoft: WinRM direct command option](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-wsmv/c793e333-c409-43c6-a2eb-6ae2489c7ef4)
- [Microsoft: cmd.exe command length](https://learn.microsoft.com/en-us/troubleshoot/windows-client/shell-experience/command-line-string-limitation)
