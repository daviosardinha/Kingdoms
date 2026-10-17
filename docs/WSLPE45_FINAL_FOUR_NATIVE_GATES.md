# WSLPE45 — final four native-source and acceptance gates

**State: INCOMPLETE — do not deploy or release.**

Repository source of truth: `feature/windows-lpe-45-batch`.
Verified source checkpoint: 21/25 accepted *source candidates*; four still planned.
New live six-stage qualifications: 0/25. New independent learner-side exploit proofs: 0/25.

## What remains

| Number | Distinct Windows-native mechanism | Source acceptance |
| --- | --- | --- |
| 25 | MSI repair custom action | Build genuine per-machine MSI; verify elevated repair boundary for a non-admin learner; uninstall and rollback. No `AlwaysInstallElevated` policy changes. |
| 36 | WMI privileged provider authorization | Register a dedicated managed/native provider and unique namespace; verify intended provider token, method-access permissions, and targeted removal. Never relax WMI root namespace ACLs. |
| 38 | DCOM server launch ACL | Build a dedicated out-of-process COM server; create task-owned CLSID/AppID and per-AppID permissions, prove non-admin activation, restore only owned registration. No global DCOM settings. |
| 40 | Custom Windows RPC authorization | Build MIDL interface and local-only RPC client/server; prove a local standard-user caller can reach the bounded lab operation and verify exact endpoint cleanup. No remote transport. |

## Batch-wide non-negotiable rules

- Target **WSLPE-WS01** only: Windows 10 workgroup and local non-admin `WSLPE-WS01\lpe.trainee`. The original **NORTH WS01** and the AD shared Ansible role remain frozen and untargeted.
- Use dedicated fixture directories, registry keys, service and interface names; disallow adoption of existing foreign objects.
- Each mechanism must use its authentic Windows primitive; a generic privileged script/service is not equivalent.
- Native CI must compile/build the actual artifacts and preserve their reproducible source/version provenance. CI parsing is not a runtime vulnerability proof.
- Keep `kingdoms/wslpe45_implementation_index.yml` truthful: these four remain `planned`/`source_ci: pending` until committed complete source plus CI evidence exists.
- `batch_execution_authorized: false` must stay disabled until an independent human review of exact-guest scope, artifact trust, and rollback.
- One consolidated operator run must cover all 25 additions: apply → vulnerable validation → reset → clean validation → reapply → revulnerable validation. Independent `lpe.trainee` proofs and clean RDP/WinRM access are separate release gates.

## Current blocker and safe resolution

The GitHub connection and branch writes work, but selected offensive native-source and build-workflow write attempts have been blocked by platform safety checks. Do not route identical rejected content through an alternative method. Redesign or review the flagged material and pursue an approved implementation path.

A GitHub Issue could not be created because **Issues are disabled on this repository (HTTP 410)**, so this branch document tracks the release gate.

**Do not claim 25/25 source complete or deploy the consolidated operator while any of these gates remain open.**
