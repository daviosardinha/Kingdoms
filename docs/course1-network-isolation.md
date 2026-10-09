# Kingdoms Course 1 — same-host network isolation contract

Status: source-only network planning. Four-VM deployment remains blocked.

## Why this is needed

The reduced Course 1 preview still inherits the reference Kingdoms VMware
vmnets, static MAC identities, router interfaces, and IPv4 subnets. An isolated
workspace directory cannot prevent layer-2 collisions or ambiguous host routes.

The network contract module goad/course1_network_plan.py reads the canonical
reference Vagrantfile AND router provisioning shell script. It establishes the
network identities of the six-VM reference Kingdoms deployment, including
the router-only MANAGEMENT subnet.

## Non-deployable proposal rules

- Exactly four Windows guests and one router.
- NORTH, SEVENKINGDOMS, MANAGEMENT, and an ESSOS_TRANSITION adapter zone.
- Each zone uses a unique vmnet, non-overlapping /24 subnet, and valid gateway.
- Every guest/router MAC is unicast, unique, and different from reference MACs.
- Parent DC remains in SEVENKINGDOMS; child DC, SRV02 and WS01 remain in NORTH.
- No reference vmnet or reference IPv4 subnet may be reused.
- The manifest state must be PROPOSED_NOT_DEPLOYABLE.

ESSOS_TRANSITION exists only because the legacy router has a third lab NIC.
It does not add an ESSOS AD domain or an ESSOS Windows guest to Course 1.
Removing that NIC needs a separate router PCI/slot regression.

A proposal can be checked offline with:

    python3 -m goad.course1_network_plan --check-proposal /absolute/path/plan.json

Even a clean static proposal has NOT been surveyed against the VMware host:
host_networks_surveyed=false and deployment_authorized=false. The sample
vmnet numbers in unit tests are synthetic, not recommendations for the host.

## Single validation entry point

Run the existing script after syncing Git:

    cd "$HOME/kingdoms-course1-src" && git pull --ff-only && bash scripts/course1/validate-course1.sh

The runner now checks that the CURRENT four-VM preview remains unsafe to
co-host with the reference Kingdoms instance (shared vmnet/MAC/IP identity).
This is an expected-failure safety assertion, not a deployment green light.

## Next release gates

1. Obtain a READ-ONLY inventory of real VMware vmnets, host routes, virtual
   interfaces and running VM identities; do not provision VMnets or alter NICs.
2. Allocate genuinely free network identities and validate host route selection.
3. Render profile-specific router, VMware guest adapters, inventory addresses
   and instance manifest; fail closed when any source or runtime mapping differs.
4. Prove a disposable reduced deployment, including NORTH attacker L2 traffic,
   parent/child AD, WinRM, NT5DS, reset, SQL and Phase 03 regressions.
5. Keep PR #30 a draft until all live release gates pass.

GitHub is the engineering source of truth; no Notion curriculum edits.
