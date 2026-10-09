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
