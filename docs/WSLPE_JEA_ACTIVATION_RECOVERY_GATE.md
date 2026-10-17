# WSLPE #30 JEA activation / independent recovery gate

**State: READ-ONLY PREFLIGHT ONLY — JEA installation and activation NOT AUTHORIZED.**

Scope: exact registered Windows 10 workgroup `WSLPE-WS01` (local learner `WSLPE-WS01\lpe.trainee`). No NORTH, shared role, other VMware guests, NAT, routing or general WinRM modifications.

## Established evidence (2026-10-17)

- Local 25-fixture source readiness: 21/25 source candidates; #25/#36/#38/#40 pending. No new scenario has live six-stage acceptance.
- WSLPE WinRM HTTP baseline and HTTPS listener, RDP/NLA/TLS configuration: read-only Ansible PASS, **not learner logon evidence**.
- Certificate pin, chain, DNS SAN, TLS >=1.2, and authenticated WinRM HTTPS/5986: operator-provided live PASS.
- Independently scheduled owner-context host systemd timer **fired** after `sudo -v`, and the owner-context timer ran `vmrun -T ws list`; exact WSLPE VMX included. Private scratch VMX restore was byte-for-byte correct.
- **Not demonstrated:** real VM shutdown/start, a tested recovery of disrupted WinRM, a safe out-of-band guest console, RDP learner logon, host reboot/NAT/firewall guard persistence, or independent sudo authorization for arming a *new* timer after sudo cache expiry.

## Stage J0 — read-only endpoint inspection (permitted)

```bash
if (
  cd "$HOME/kingdoms-lpe-standalone" &&
  test -z "$(git status --porcelain)" &&
  "$HOME/.goad/.venv/bin/python" -m unittest -v tests.test_wslpe_jea_readiness &&
  "$HOME/.goad/.venv/bin/python" scripts/wslpe-jea-readiness.py \
    --expected-thumbprint C773EC26D02940F559FE715B83628FEDAE2AA92D
); then
  echo "[PASS] Read-only JEA baseline recorded"
else
  echo "[BLOCKED] Do not apply or restart JEA/WinRM"
fi
```

This command uses existing WSLPE-only credentials through temporary process-local trust, verifies exact hostname and learner non-admin status, and reads only the local JEA endpoint count and lab-owned source/fixture presence. It does not prove JEA functional access, install anything or connect to NORTH. If existing JEA/fixture state is found, stop for manual review; **never infer ownership from the endpoint name alone**.

## Stage J1 — recovery authorization before ANY guest mutation (blocked)

Prepare and independently verify, with a human operator:

1. Exact registered WSLPE VMX, VM owner and only-this-guest scope; no other VM names/paths in the recovery plan.
2. Operator console/VMware control that does not depend on WinRM/5985/5986 or on the user's current SSH shell/sudo ticket. An already-armed, bounded host systemd service can continue after the console disconnects, but a transient sudo ticket does **not** authorize unattended *new* work.
3. Known-good recovery-point/snapshot mechanism appropriate to the live guest, and verified ability to roll back the **real** WSLPE guest safely in a separately approved rehearsal (not merely a scratch VMX).
4. Exact rollback scope: JEA's owned endpoint, module and fixture; preserve unrelated WinRM listeners, security settings, sessions, services and machine-wide session configurations.
5. Independent authenticated HTTPS success before and after a controlled test, plus a fail-closed stop criterion if management is lost.
6. Reviewed human approval for the exact stage, change window and anticipated interruption; record secure recovery evidence privately. **Do not** reuse the general NAT-cutover restoration timer as a JEA/WinRM rollback implementation. They restore different state.

## Stage J2 — JEA source correction and isolated activation design (not yet performed)

The existing `ansible/files/wslpe45/WslpeJea.psm1` uses `Register-PSSessionConfiguration -NoServiceRestart` and `Unregister-PSSessionConfiguration -NoServiceRestart`. Source checks only prove registration/role-file existence, not whether WinRM loaded and exposes the endpoint. A WinRM restart is NOT authorized by source readiness.

Require separately verified JEA activation (local learner permitted for the dedicated endpoint and genuinely constrained), proof that the normal management endpoint still works, and a deliberate cleanup/rollback path. No use of a machine-wide WinRM restart without the verified J1 independent recovery contract.

## Current decision

**Go:** J0 read-only state inspection, source tests and further design/review.  
**No-go:** JEA registration, activation, WinRM restart, NAT cutover, automatic VM restore, 25-fixture execution and learner release.

NORTH remains frozen. Keep `batch_execution_authorized: false` throughout.
