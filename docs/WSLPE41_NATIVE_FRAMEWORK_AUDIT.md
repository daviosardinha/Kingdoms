# WSLPE41 native framework boundary audit

Status: source audit only; no Windows guest acceptance has been executed.

## Authoritative infrastructure lifecycle

`goad/lab_manager.py` owns instance selection, creation and registration.
`kingdoms/wslpe_stage1.py:bootstrap_native_wslpe` validates WSLPE-only
settings and calls `manager.create_instance()`, then the native VMware
`provider.install()`. The provider-generated Vagrantfile and
`.vagrant/machines/WSLPE-WS01/vmware_desktop/id` are authoritative
registration inputs. The resulting native status is PROVIDED, **not READY**.

No WSLPE41 module may independently implement Vagrant/VMware creation,
destroy, networking ownership, lifecycle, credentials or guest-console
management. Existing KINGDOMS/NORTH provider behavior is unchanged.

## PR #44 module ownership

| Module | Permitted responsibility | Boundary |
| --- | --- | --- |
| `wslpe41_fresh_contract` | 41 scenario IDs, exclusions and ordering | Keep |
| `wslpe41_stage_commands` | Map scenario/stage to existing Ansible sources | Keep |
| `wslpe41_install_flow` | One 83-stage journal and evidence contract | Keep; no VM lifecycle |
| `wslpe41_runtime_proof` | Verify exact stage observations | Keep |
| `wslpe41_stage_executor` | Execute existing Ansible stage against registered guest | Keep internal |
| `wslpe41_foundation_executor` | Invoke existing WSLPE Ansible foundations | Keep internal |
| `wslpe41_native_stage_runner` | Adapt validated provider-backed transports to journal | Keep internal |
| `wslpe41_native_identity` | Read-only Vagrant/VMX registration verification | Keep; not fresh proof |
| `wslpe41_host_preflight` | Read-only collision evidence | Keep; no VMnet creation |
| `wslpe41_network_auto` | Candidate subnet selection only | Do not treat as allocation |
| `wslpe41_native_stage1_bridge` | Call existing native Stage 1, return bound identity | Internal only; no alternate boot |
| `wslpe41_native_foundation_handoff` | Sequence existing Ansible foundations and required checks | Refactor to native provider-backed probes; not a management subsystem |
| `scripts/wslpe41-install.py` | Read-only plan/status interface | Keep `--execute` locked |

## Verified gaps / release blockers

1. Native Stage 1 only proves VMX registration and running inventory. It
   does not prove dedicated VMnet isolation, guest freshness or Windows state.
2. Foundation callbacks are **interfaces**, not implementations of actual
   VMware-console recovery, operator authentication or trusted HTTPS.
   Passing an injected callback is not itself independent evidence.
3. `run_foundation_stage(operator)` creates a principal but explicitly
   returns `operator_authenticated=False`; operator authentication must
   be checked separately with the intended account.
4. `install_41` has a fail-closed journal and 83-stage source mapping but
   is not connected to an authorized production native lifecycle.
5. Two independent clean installs with 41/41 configuration checks and
   learner exploitation verification are outstanding.

## Integration rule

The native KINGDOMS manager/provider must supply lifecycle and transport
capabilities. WSLPE41 supplies only guest configuration, scenario sequencing
and verification. No new VMware provider, Vagrant CLI lifecycle wrapper,
network manager, Windows account manager or generic credential subsystem.

Do not enable `--execute` or merge PR #44 until the provider-backed
transport, isolation and fresh-install acceptance evidence exists.
