# WSLPE 45 — single execution contract for the new 25

**Scope: standalone WSLPE-WS01 ONLY.** NORTH WS01 is a reference implementation and may never be contacted, reconfigured, patched or included in inventory by this work. The shared NORTH 20-technique Ansible role remains frozen.

## Where we actually are

- **Foundation #1–20:** reversible six-stage lifecycle previously accepted on the standalone guest, **not** accepted for learner exploit proofs.
- **Advanced #21–35 and Expert #36–45:** all **25/25 native Windows API checks passed** on workgroup WSLPE-WS01. A native API read does **not** prove an attack is possible or correctly simulated.
- **#35:** dedicated source candidate (Windows SYSTEM service) with CI parse/compile and cleanup controls; no six-stage or learner-side live proof yet.
- **Remaining 24:** design catalog only. No implementation or deployment claim.
- **Course:** nowhere near a 45-technique release claim until distinct mechanisms, 150 lifecycle stages, learner-side attack evidence, isolation and course content are accepted.

## One command, not 25 stop-and-start exercises

The operator is `scripts/wslpe-45-qualify.py`. It reads the strict, 25-row `kingdoms/wslpe45_implementation_index.yml`, checks each standalone playbook is distinct and source-qualified, and **refuses any guest contact unless all 25 meet the source contract**.

When all fixtures exist and pass source CI, one explicit `--execute` call will do the following without interactive confirmations:

1. Establish the exact registered native WSLPE VMware instance, isolated guest WinRM target and workgroup inventory using the already proven 20-scenario safety harness.
2. Require the exact local learner and guest identity at the beginning of every playbook; reject NORTH and all other Windows hosts.
3. Run each of the 25 techniques serially through **apply → vulnerable validation → reset → clean validation → reapply → vulnerable validation** (150 required successful guest markers total).
4. Write private owner-only JSON after every stage, preserve evidence on failure and refuse automatic unsafe restart after a partially applied technique.
5. Report lifecycle-qualified count, without treating that as learner exploitation success.

All scripts must generate stage-specific evidence `WSLPE45_BATCH_STAGE=<id>:<stage>:PASS` **only after** the relevant real Windows operation succeeds. Source CI is not permitted to forge live results. When a scenario requires special containment (machine-wide SCM ACL, JEA, privileges, WMI subscriptions or reparse points), its own reversible contract must explicitly protect shared OS state.

## Current operator status

The plan command is non-mutating:

```bash
if (
  cd "$HOME/kingdoms-lpe-standalone" &&
  "$HOME/.goad/.venv/bin/python" scripts/wslpe-45-qualify.py
); then
  echo "[PASS] Read-only 25-fixture source readiness plan"
else
  echo "[BLOCKED] Plan failed; terminal remains open"
fi
```

**Do not run `--execute` yet.** The incomplete source index makes it fail closed before WinRM/VMware. No need for individual technique operator steps or further repetitive feasibility runs. Implementation continues in this single branch until all 25 scenarios have real Windows source, exact artifact ownership, restoration and Windows-native CI checks.

### Release separation

A passing 150-stage lifecycle report is **not** proof that learner `WSLPE-WS01\\lpe.trainee` exploited a privilege boundary. Those real learner-side artifacts, repeatability, RDP/NLA access, student isolation and Windows licensing remain separate acceptance gates.

There is deliberately no claim that 25 new vulnerabilities have been implemented by this coordinator.
