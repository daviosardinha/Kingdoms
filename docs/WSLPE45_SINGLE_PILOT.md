# WSLPE45 – isolated #28 App Paths deployment pilot

**Scope:** standalone native workgroup `WSLPE-WS01` only. No GOAD/NORTH mutation, no changes to the frozen 20-technique shared role, no batch flag changes. This pilot is an engineering tool, **not** permission to release a vulnerability as learner-proven.

## Why #28 first

The 17 October candidate audit identifies the scoped App Paths registry entry and owned SYSTEM task as a source candidate without the specific global-SCM privilege risk (#22), updater path-containment defect (#24), JEA activation defect (#30) or junction cleanup problem (#34). Actual low-privilege control and elevated proof remain unverified. This is why the pilot intentionally selects **only** #28.

## Safeguards

- Offline preview by default; native WinRM/VMware/Ansible never contacted unless `--execute` is explicitly supplied.
- Requires clean dedicated feature checkout; existing registered native WSLPE VMware snapshot; exact standalone inventory, private management credentials and absence of NORTH address range.
- Read-only Windows preflight checks hostname, workgroup identity, local standard learner, no #28-owned task, registry key or directory. It also stops if the partial #25 fixture remains or the #40 RPC host is active. **Use a clean disposable WSLPE snapshot/clone rather than altering another interrupted fixture.**
- The existing `batch.command` is reused with `--limit ws01,localhost` and the source-checked #28 Ansible playbook only. One common lock and recovery sentinel prevent an interrupted or concurrent WSLPE45 run being bypassed.
- Runs apply, vulnerable configuration validation, reset, clean validation, reapply, revulnerable validation. Private journal saved after every step. Failure stops immediately and preserves the recovery sentinel: **never delete the sentinel as a workaround**.
- No learner proof is claimed by the automated lifecycle. Following a passing cycle, independently test the learner-edited App Paths registry value, the SYSTEM consumer and protected proof under the real `lpe.trainee` token; collect negative cases and clean rollback.

## Kali operator flow (after reviewing and committing the patch)

From the reviewed and *clean* `feature/wslpe45-single-candidate-pilot` worktree:

```bash
python3 -m unittest tests.test_wslpe45_single_pilot tests.test_wslpe45_batch_operator
python3 scripts/wslpe45-single-pilot.py
```

Run the **separate read-only guest gate** only after reviewing the source-only results:

```bash
python3 scripts/wslpe45-single-pilot.py --preflight
```

This checks the registered snapshot, native standalone inventory and live #28 guest absence **without installing or resetting a fixture**. It refuses the currently interrupted #25 fixture. A blocked report is a genuine unresolved prerequisite, not permission to delete the #25 directory or clear a recovery sentinel.

These are source-only and preview. If the read-only preflight passes, the guest is a disposable isolated WSLPE development instance, and the operator approves the first fixture write, the deliberately separate live invocation is:

```bash
python3 scripts/wslpe45-single-pilot.py --execute
```

Never launch the live command on the guest with the currently incomplete #25 fixture. First complete its owned recovery, or prepare a **separate clean development clone** that passes the exact native inventory and snapshot gates. Do not test on NORTH or a shared/student VM. Redact private logs before sharing.

This single-scenario runner does **not** unlock or replace `scripts/wslpe-45-qualify.py` and does not change `batch_execution_authorized: false`. The full 25-scenario release gate is intentionally separate.
