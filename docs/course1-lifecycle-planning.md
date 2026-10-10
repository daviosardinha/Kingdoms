# Course 1 — offline lifecycle planning gate

Status: **static planning only**, not an install/start/stop/reset interface.

The reduced Course 1 recipe has passed Python source contracts and native
Ruby/Ansible artifact parsing. The next boundary is separating *which guests
should be considered* from the actual VMware/Vagrant operations.

The planner uses the existing canonical `FULL` and `COURSE1` RuntimeRoster
objects and exposes a **read-only** preview for `start`, `stop`, `reset`,
`provisioning`, and `exercise`. The full profile preserves legacy
machine/member/DC ordering. The Course 1 profile contains only DC01, DC02,
SRV02 and WS01, plus the common router. Partial starts include AD dependency
closure. Mode transitions preserve the child-before-parent exercise cycling
rule; the reset plan identifies snapshot scope, not an execution sequence.

Run from the repository, on the exact committed branch:

```bash
python3 -m unittest tests.test_course1_lifecycle_plan
python3 -m goad.course1_lifecycle_plan --check \
  --profile course1-fall-of-the-north --action start --machine GOAD-WS01
python3 -m goad.course1_lifecycle_plan --check \
  --profile course1-fall-of-the-north --action exercise
```

Every JSON result explicitly states
`"execution": "BLOCKED_STATIC_PLAN_ONLY"`. A profile label supplied on the
CLI is **not** an instance identity or deployment authorization. Neither the
VMware provider nor `scripts/lab-mode.sh` consumes these plans yet.

## Gates before runtime integration

1. Bind to a *deployed* instance using a verified manifest plus concrete
   Vagrant roster. Never infer from Git branch or CLI selection.
2. Refactor provider start/stop/reset and lab-mode transitions to consume
   the bound profile. Preserve legacy behavior and fail-closed recovery
   including snapshot auto-start and NAT adapter normalization.
3. Validate startup/AD time readiness, router policy, VMX availability,
   DNS/WinRM, and all four machines' source inventories.
4. Implement and validate KINGDOMS2 SQL provisioning and full Course 1
   exercises in a **disposable isolated clone** before enabling activation.
5. Prove a clean six-Windows-VM baseline regression before merging.

Do not run a reduced Vagrantfile, replace the original instance, or remove
the deployment guard on the strength of this static planning gate.

## Installed-reference controller integration

The hardened VMware controller now consumes the lifecycle plan ONLY after
`inspect_instance_binding` has identified a deployed **six-Windows-VM**
Kingdoms reference instance, and the controller's machine roster and management
IP mapping exactly match the canonical reference contract. Start obtains its
ordered dependencies **before** inventory synchronization or router power-on;
stop obtains its shutdown order before guest state inspection; reset validates
scope before snapshot pop. The existing reset auto-start/NAT-off recovery,
router policy, time/AD readiness and lab-mode ordering are unchanged.

A read-only check against a deployed reference instance is available via:

```bash
python3 -m goad.course1_bound_lifecycle \
  --check-provider "$HOME/Documents/GOAD_NOMAD/workspace/<instance>/provider" \
  --action start --machine GOAD-WS01
```

A static plan's `BLOCKED_STATIC_PLAN_ONLY` value never authorizes a guest
operation. **Only the existing bound reference provider** may consume plan
ordering in its previously validated lifecycle. Any Course 1 manifest or
four-guest instance still fails closed. This integration deliberately does not
alter the VMware instance, launch any VM, or authorize Course 1 installation.
