# WSLPE45 – isolated #28 App Paths deployment pilot

**Scope:** standalone native workgroup `WSLPE-WS01` only. No GOAD/NORTH mutation, no changes to the frozen 20-technique shared role, no batch flag changes. This pilot is an engineering tool, **not** permission to release a vulnerability as learner-proven.

## Why #28 first

The 17 October candidate audit identifies the scoped App Paths registry entry and owned SYSTEM task as a source candidate without the specific global-SCM privilege risk (#22), updater path-containment defect (#24), JEA activation defect (#30) or junction cleanup problem (#34). Actual low-privilege control and elevated proof remain unverified. This is why the pilot intentionally selects **only** #28.

## Safeguards

- Offline preview by default. `--preflight` runs read-only native VMware, WinRM and Ansible checks; only explicit `--execute` can stage the dedicated #28 fixture.
- Requires clean dedicated feature checkout; existing registered native WSLPE VMware snapshot; exact standalone inventory, private management credentials and absence of NORTH address range.
- Read-only Windows preflight checks hostname, workgroup identity, standard learner and absence of the #28 task, key and fixture. If interrupted #25 exists, it accepts **only** the exact protected, administrator-owned single `.kingdoms-owned.json` marker, matching learner SID and source-pinned common library SHA-256. Unexpected data or ACL drift fails closed. An active #40 RPC host still blocks the pilot. Never delete or modify #25 to unblock #28.
- The existing `batch.command` is reused with `--limit ws01,localhost` and #28's source-checked Ansible playbook only. Verified marker-only #25 state disables shared library reconfiguration and overwrite during the #28 lifecycle. One common lock and recovery sentinel prevent bypassing interrupted WSLPE45 operations.
- Runs apply, vulnerable configuration validation, reset, clean validation, reapply, revulnerable validation. Private journal saved after every step. Failure stops immediately and preserves the recovery sentinel: **never delete the sentinel as a workaround**.
- No learner proof is claimed by the automated lifecycle. Following a passing cycle, independently test the learner-edited App Paths registry value, the SYSTEM consumer and protected proof under the real `lpe.trainee` token; collect negative cases and clean rollback.

## Kali operator flow (GitHub pull-only workflow)

From the reviewed and *clean* `feature/wslpe45-single-candidate-pilot` worktree:

```bash
python3 -m unittest tests.test_wslpe45_single_pilot tests.test_wslpe45_batch_operator
python3 scripts/wslpe45-single-pilot.py
```

Run the **separate read-only guest gate** only after reviewing the source-only results:

```bash
python3 scripts/wslpe45-single-pilot.py --preflight
```

This checks the registered snapshot, native standalone inventory, live #28 absence, and the exact #25 ownership state **without installing or resetting anything**. It accepts only the verified marker-only #25 interruption state; all other partial states block. A blocked report does not authorize clearing any fixture or recovery sentinel.

These are source-only and preview. If the read-only preflight passes, the guest is a disposable isolated WSLPE development instance, and the operator approves the first fixture write, the deliberately separate live invocation is:

```bash
python3 scripts/wslpe45-single-pilot.py --execute
```

Run the live command only after a passing read-only guest preflight and on the snapshot-backed isolated development VM. If #25 exists in any state beyond the one verified marker-only interruption, stop for separate recovery. Do not test on NORTH or a shared/student VM. Redact private logs before sharing.

This single-scenario runner does **not** unlock or replace `scripts/wslpe-45-qualify.py` and does not change `batch_execution_authorized: false`. The full 25-scenario release gate is intentionally separate.
