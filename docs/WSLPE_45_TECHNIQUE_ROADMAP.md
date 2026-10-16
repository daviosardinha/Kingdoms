# Kingdoms — Standalone Windows Local Privilege Escalation (45 Techniques)

**Decision:** 2026-10-16 — This is the canonical scope boundary for Windows LPE expansion.

## Two different release scopes

| Environment | Target | Change policy |
| --- | ---: | --- |
| **NORTH WS01 (AD / GOAD)** | **20 techniques, permanently scoped to the original NORTH curriculum** | Existing validated role, deployment, fixtures and course remain unchanged. No propagation of standalone-only techniques, learner accounts, WinRM, isolation or provisioning changes into NORTH. |
| **Standalone WSLPE-WS01 (workgroup)** | **45 techniques total** | Its own independent Windows LPE course, with local non-admin learner identity, scenario qualification, repeatability and isolation gates. |

The initial 20 standalone WSLPE techniques **reuse** the existing NORTH-proven `ansible/roles/windows_lpe` implementations through the WSLPE adapter. Reuse is intentionally one-way: changes and future expansion in standalone WSLPE must not silently alter NORTH.

## WSLPE roadmap

| Stage | Added | Cumulative | Scope |
| --- | ---: | ---: | --- |
| **Foundation** | 20 | 20 | Adapt and validate the existing NORTH techniques on a domain-free local Windows account, with apply → vulnerable validation → reset → clean validation → reapply → vulnerable validation. |
| **Advanced expansion** | +15 | 35 | New standalone-only local privilege escalation scenarios. Exact technique catalog, prerequisites and learning sequence are to be defined and versioned before implementation. |
| **Expert expansion** | +10 | **45** | Further standalone-only scenarios. Exact technique catalog, prerequisites and learning sequence are to be defined and versioned before implementation. |

**Do not mark 45 implemented or tested merely because this roadmap exists.**
The existing 20 are the starting library, not the intended final standalone course. Newly designed 25 techniques are not yet selected, implemented or accepted.

## Non-negotiable engineering boundaries

1. **Freeze NORTH at 20:** do not modify NORTH VM configuration, AD identities, its course scope, or deploy additional techniques to NORTH. Any future proposed NORTH work requires an explicit separate authorization and is outside this roadmap.
2. **Reuse proven source without fork drift:** the existing NORTH 20 may be invoked from WSLPE, but standalone-specific adapters and fixtures must stay in WSLPE-scoped files. Build the 25 additional scenarios under standalone-only contracts, not by expanding the shared NORTH role's default catalog.
3. **Domain-free learner:** `WSLPE-WS01\lpe.trainee` is a non-admin local account. Validate behavior from this context; do not inherit NORTH domain users, group policy, trusts, DCs or VLAN assumptions.
4. **Every technique must be repeatable:** apply; assert vulnerable; reset; assert clean; reapply; assert vulnerable. Validate actual escalation from a non-admin learner context separately from setup-state assertions. Keep private failure evidence and bounded, auditable recovery.
5. **Protect the host and future learners:** isolation, local account RDP/NLA, management recovery, reset reliability, Windows license compliance and per-instance student separation are independent release gates. Neither passing source CI nor provisioning 45 vulnerabilities alone authorizes untrusted learner access.
6. **Do not disrupt completed scenarios:** preserve already qualified techniques and use checked, immutable resume records with read-only revalidation before continuing failures.
7. **No repetitive operator confirmations:** explicit `--execute` authorizes the scoped action; operator command wrappers must preserve Kali's interactive shell. CI covers syntax, safe execution order, negative paths, and Windows-native behavior where feasible.

## Current known checkpoint (2026-10-16)

- **FOUNDATION ACCEPTED — 20/20 standalone WSLPE scenario lifecycles.** The operator's successful qualification output includes `WSLPE_STANDALONE_20_TECHNIQUES_ACCEPTED=TRUE` and independently revalidated the earlier 16 vulnerable scenario states.
- The final private continuation report, `wslpe-qualification-20261016T222229Z.json`, records **24/24 passing steps** for SeBackupPrivilege, SeImpersonatePrivilege, writable program directory and insecure service registry. Each of these four completed apply → vulnerable → reset → clean → reapply → vulnerable. The earlier accepted scenarios are recorded in the prior private reports; **the final JSON is not, by itself, a 120-step artifact**.
- Standalone guest has a local non-admin learner account and working management-side WinRM. This establishes provisioning/rollback validation, **not** real learner exploitation.
- **25 additional standalone scenarios remain to be designed and implemented:** +15 advanced and +10 expert, targeting **45/45**. Do not claim the course is complete.
- **Still unverified for learner release:** actual non-admin RDP/NLA login, hands-on privilege escalation evidence, learner isolation, repeatable startup/recovery and lesson content.
- NORTH's original 20 remain fixed and untouched.

## Execution milestones

1. **COMPLETE:** reach **20/20** standalone deployment/reset/validation acceptance, preserving NORTH.
2. Specify and implement the **advanced +15** standalone-only catalog; qualify **35/35**.
3. Specify and implement the **expert +10** standalone-only catalog; qualify **45/45**.
4. In parallel, validate local learner login and real non-admin-to-elevated attack paths, reset consistency, host isolation and course walkthroughs. Release only after **45/45 + learner exploitation + isolation + lifecycle + content** acceptance.

This document controls scope; it does **not** authorize modifications to NORTH or declare course completion.
