# WSLPE 45 — one standalone batch, NORTH frozen

> **Historical proposed 45-scenario batch contract.** The 2026-10-19 decision caps the current standalone Windows LPE curriculum at **41 scenarios** and de-scopes #25/#36/#38/#40. The selected 21 additions have passed installation and configuration validation; this old proposal is not the live next-phase requirement. See [final deployment closeout](./WSLPE41_DEPLOYMENT_CLOSEOUT_2026-10-19.md). Six-stage and learner proof claims below remain unachieved unless separately evidenced.

**Execution boundary:** only the native workgroup `WSLPE-WS01` with local non-admin learner `WSLPE-WS01\lpe.trainee`. NORTH/GOAD WS01 is an untouched reference design, never a deployment target. The original shared 20-technique role must remain byte-for-byte unchanged by the expansion.

## Verified checkpoint and missing work

- **1–20:** qualified on standalone for the reversible six-stage provisioning lifecycle. This is not proof of hands-on student exploitation.
- **21–35:** 15 distinct Advanced scenarios are **planned**, not installed. #21's Task Scheduler descriptor read-only probe has returned blocked guest diagnostics. Do not treat CI syntax or COM connection as proof of learner task editing.
- **36–45:** ten **proposed**, standalone-only Expert scenarios. Their designs are in `kingdoms/wslpe_expert_catalog.yml`; native Windows feasibility is still unproven.
- **45/45:** only a target. There are currently **25 unimplemented** scenarios.

## Engineering batch

Build and review **all 25 added fixtures together** rather than repeatedly running one technique, pulling one commit, and stopping at each blocker. Each needs a unique isolated elevated consumer, attacker-controlled entry, protected baseline, read-only feasibility, apply/validate/reset implementation, negative-path tests and owned artifacts. No editing pre-existing operating-system services/tasks, globally weakening Windows, or modifying NORTH.

Before any live execution, preserve and reuse the `scripts/wslpe-fast-track-20.py` exact native VMX, workspace, instance, inventory and WinRM identity checks. Never accept a target within `10.4.0.0/16` or a domain-joined guest. Plan/source CI cannot contact Windows. Only an explicit `--execute` may later authorize live changes, and it must fail closed on ambiguous guest identity or missing isolated recovery.

## Acceptance rules

Keep the per-scenario evidence chain **apply → vulnerable → reset → clean → reapply → vulnerable**. Real non-admin exploitation requires a separate trace of local `lpe.trainee` reaching a lab-owned elevated proof marker. A configuration vulnerability alone is not exploitation. Persist private logs outside Git and do not leak credentials.

Do not stop source development of the other 24 scenarios because one Windows capability probe is blocked. However, never bypass a failed prerequisite and never automatically run unsafe live steps on a blocked scenario. Aggregate results into one 45-row matrix with `PLANNED`, `BLOCKED`, `SIX-STEP-QUALIFIED`, `LEARNER-EXPLOITABLE`, or `ACCEPTED`—no fictitious passes.

**Release:** one consolidated PR only after the complete, reviewed implementation and qualified evidence. Workgroup learner isolation, management recovery, RDP/NLA, per-student separation and licensing still gate release.

## Non-mutating current command

```bash
cd "$HOME/kingdoms-lpe-standalone" || exit 1
python3 -m unittest -v tests.test_wslpe_batch_catalog
python3 scripts/wslpe-45-batch.py
python3 scripts/wslpe-45-batch.py --json
```

This reads source catalogs only. It **does not** deploy 25 vulnerabilities. Deliberately there is no live batch `--execute` until the implementation is actually present.
