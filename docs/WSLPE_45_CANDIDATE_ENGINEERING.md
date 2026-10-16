# Standalone WSLPE 45 — candidate implementation workstream

The consolidated 2026-10-16 read-only result found **25/25 native Windows API prerequisites available** on the exact standalone workgroup `WSLPE-WS01`. These are API availability checks, **not** proof that any new technique is exploitable. All 25 results still reported `fixture: not_implemented`.

## First implemented *source candidate* inside the coordinated batch

`ansible/files/wslpe45/WslpeFixture.psm1` defines shared ownership and guarded cleanup rules for all future 21–45 fixtures. It refuses domain-joined or misidentified machines, non-Windows 10 machines, administrative learner identity, outside-root paths, and reparse-point traversal during cleanup.

`ansible/wslpe45/traversal.yml` and `ansible/files/wslpe45/KingdomTraversalService.cs` are the initial standalone-only **candidate for #35, Privileged File-Write Path Traversal**. The dedicated service is registered as LocalSystem, with only query/start authorization delegated to the exact local learner SID. The learner can edit its own `inbox/request.txt`; a `..\\protected\\proof.txt` relative path exercises a deliberately unsafe base-directory assumption. However, the code checks that the resolved write destination is precisely one test-owned protected marker under the same fixture. It cannot write a path elsewhere and cannot start a shell.

The service action intentionally demonstrates a **privileged file-write primitive**, not a SYSTEM shell. It does not modify NORTH or the shared `windows_lpe` role, change global SCM permissions, disable security controls, or touch Windows system objects. Apply/validate/reset/clean actions are separate and require an exact-WSLPE authorization preflight. The six-step loop and actual `lpe.trainee` proof must still be executed and accepted in the standalone guest.

## Strict acceptance state

- Foundation 1–20: qualified standalone deployment/reset lifecycle.
- #35: source candidate with native Windows build/parse and static safety tests; not yet applied or exploit-qualified.
- The remaining #21–34 and #36–45: planned; no new fixtures deployed.
- Commercial learner release: not approved.

We are deliberately **not** giving the operator a partial scenario-by-scenario deployment command. Continue the remaining candidate implementations and run one consolidated source gate and one single batch lifecycle qualification when all techniques meet their own preconditions.

NORTH is reference-only and must never be connected to, changed or enrolled in these playbooks.
