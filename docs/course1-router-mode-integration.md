# NORTH router / host routing — provider integration

The existing Kingdoms `GoadNomadVmwareProvider` now resolves router/firewall
source files from the current lab rather than assuming the GOAD reference.
Its `_script` selector keeps the original `scripts/router-ssh.sh` and
`scripts/provisioning-routes.sh` for GOAD, but resolves the isolated NORTH
helpers under `scripts/course1` for NORTH.

NORTH-specific configuration:
- `ad/NORTH/providers/vmware/router/nftables/provisioning.nft`: temporary
  provisioning forwarding for Windows/AD bootstrap.
- `ad/NORTH/providers/vmware/router/nftables/exercise.nft`: deny-by-default
  forwarding, permitting the two parent/child domain controller endpoints
  `10.41.20.10` ↔ `10.41.10.11` (dynamic RPC required by AD).
- `scripts/course1/provisioning-routes.sh`: only the temporary
  `10.41.20.0/24 via 10.41.10.1 dev vmnet11` host route. Requires the
  independent NORTH host-address helper and refuses to replace/remove foreign
  routes; does not touch `10.4.x` routes.
- `scripts/course1/router-ssh.sh`: SSH to `10.41.99.1` only when bound
  through `GOAD_PROVIDER_DIR` to a NORTH Vagrant instance that declares all
  three NORTH vmnets and has its own router Vagrant machine/key. Rejects GOAD.

**Not yet deployable:** The provider still checks
`segmented_install_enabled=False` for NORTH, and retains the working
`GOAD` segmented runtime guard. No new route, nftables policy or guest is
applied by the offline checks. The per-instance four-guest NAT/AD readiness
mode controller and integration with full install are still unfinished.

The reference Kingdoms networking, original installed workspace and
`main` checkout must remain untouched. Source/loop regression tests cover
shell parsing, single-parent-route identity, policy boundaries, SSH wrong-
instance refusal and preservation of the existing GOAD dispatch.

## Reusing the existing lifecycle controller

The common `scripts/lab-mode.sh` now supports an explicit
`KINGDOMS_VMWARE_LAB` identity propagated from the provider's
`_provider_env()`. Default/reference GOAD still has six Windows guests,
three DCs, two domain members plus WS01 and four network zones. NORTH
selects two DCs, CASTELBLACK, WS01 and the three independent networks.
Both share the existing patched NT5DS/directory readiness and reversible
Windows NAT transition functions—this is not a forked mode controller.

The read-only `--describe-profile` argument exposes the selected rosters and
helper paths for regression tests. NORTH always requires an explicit Vagrant
instance provider; it refuses auto-discovery and mismatched vmnet identities,
and the existing read-only `course1_instance_binding` continues rejecting all
reduced instances before any runtime mutation. This has NOT authorized NORTH
install, provisioning or exercise mode.

Remaining work includes an approved per-instance NORTH binding, safe provider
install/start/stop routing, actual WinRM/AD readiness and full guest runtime
acceptance. Do not use the common controller to operate an unreleased NORTH lab.
