# Kingdoms foundation — mandatory inheritance contract

**Kingdoms is the authoritative product, configuration base, and engineering
source. GOAD is the historical origin of the fork, NOT a source to pull into
NORTH or any future Kingdoms lab.**

The live reference environment still has the compatibility names
\`ad/GOAD\`, \`GOAD-DC01\`, \`GOAD-ROUTER\`, \`goad.sh\`, and
\`GOAD_NOMAD\`. These names do **not** imply that upstream GOAD
configuration may overwrite Kingdoms-patched settings or provisioning.

## Protected baseline

The reusable foundation is the **current committed Kingdoms repository**,
including the tested, patched versions of:

- VMware provider lifecycle and guest process safety: bounded Vagrant calls,
  timeout cleanup that preserves vmware-vmx, running-instance collision checks,
  explicit machine readiness, and controlled router-first startup.
- Active Directory readiness: parent/child DC ordering, DNS/WinRM readiness,
  domain-member and trust checks, child-domain time-authority validation, and
  validated network-mode transitions.
- Provisioning security and reliability: noninteractive sudo gates,
  deterministic address/MAC/adapter handling, VMware Tools/WinRM recovery,
  inventory consistency, isolated router management and temporary host routes.
- Network isolation: segmented VMware vmnets, provisioning-only NAT and host
  routes, exercise-mode NAT shutdown and deny-by-default router forwarding.
- Provenance and diagnostics: immutable Git source gate, install-phase timing,
  structured regressions, fail-closed instance binding, and repeatable rollback.

Do not blindly copy the GOAD six-VM lifecycle into NORTH: it contains the
**reference topology**, not Course 1's reduced scope. Likewise do not copy
upstream GOAD's permissive/default network, inventory, credential, Vagrant,
Ansible or router behavior into any new course.

## Required implementation path

1. **Select the Kingdoms foundation**: every native course
   \`ad/<LAB>/course.json\` must declare
   \`"kingdoms_foundation": "kingdoms-foundation-v1"\`.
   An absent/mismatched foundation fails closed.
2. **Verify foundation protections**: the authoritative
   \`goad.kingdoms_foundation.validate_foundation()\` checks source sentinels
   in the patched Kingdoms provider, router, Vagrant and lifecycle code.
   Derived preview generators refuse to operate if a protected fix vanishes.
3. **Apply only course-specific differences**: NORTH has FOUR Windows VMs
   (DC01/DC02/SRV02/WS01), NO ESSOS trust/forest/network, and its own router,
   proposed isolated VMware subnet/MAC identities, SQL KINGDOMS2 fixture, and
   Phase 03 interactive poisoning/relay behavior. Do not lose the patched
   **shared** reliability and security mechanisms to achieve that reduction.
4. **Prove parity**: after the course runtime provider is implemented,
   run the Kingdoms regression suite **and** new course-scoped tests for
   install, restart, stop, mode transition, rollback, Ansible/AD, SQL,
   and each relevant attack path. No course inherits release status merely
   because an earlier provider succeeded.
5. **Keep one operator control plane**: native \`./goad.sh\`,
   \`labs\`, \`set_lab NORTH\`, \`install\`, \`start\`, \`stop\`, \`status\`,
   \`validate\`, with independently bound installed instances.

## Source location during the transition

Today, the source renderer reads the already **Kingdoms-patched** reference
recipe under \`ad/GOAD\` (a legacy compatibility name). The function
\`reference_recipe()\` makes that explicit, and the foundation validation
runs **before** reading any recipe data. It must never read an external
GOAD checkout or introduce an upstream GOAD fallback.

Before NORTH is approved for installation, extract the reusable (non-
topology-specific) Kingdoms templates/contracts into a course-neutral
foundation so future courses don't have to derive from \`ad/GOAD\`.
Any such extraction must show byte/behavior parity with the validated
Kingdoms reference, not reset to upstream defaults. The existing
reference recipe is **not deleted or rewritten** during this work.

## Merge rules

Reject PRs that silently:

- replace Kingdoms-patched provider/lifecycle code with stock GOAD;
- reintroduce 6-VM assumptions, ESSOS or vmnet10/20/30/99 into NORTH;
- weaken fail-closed source, instance, runtime, route and VM safety checks;
- remove course-independent protections to simplify a new profile;
- merge incomplete NORTH into an activated provider;
- overwrite the installed reference \`workspace\`, snapshots, adapters or
  network configuration.

The \`validate_foundation\` check is an **early regression guard**, not a
complete semantic proof. Its source sentinels cannot guarantee that a
function works correctly after internal rewrites; existing source,
failure-injection and disposable runtime regressions remain mandatory.

**NORTH remains PREVIEW_ONLY_NOT_INSTALLABLE.** No changes to the live
reference guests/VMware networking are performed by this contract.

## Provider-neutral contract versus VMware implementation

`kingdoms-foundation-v1` is the shared **Kingdoms** course foundation ID,
not a statement that all future courses must run on VMware. The current
protective checks cover the mature VMware implementation in this repository;
future Ludus and other providers must implement equivalent behaviors through
the provider-neutral lifecycle, network and rollback contracts, with their own
end-to-end release tests. A native course declares the common Kingdoms base
and advertises only its independently accepted provider(s).
