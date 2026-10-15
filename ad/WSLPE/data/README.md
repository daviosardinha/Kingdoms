# WSLPE lab recipe (Kingdoms core)

This folder is intentionally under the existing `ad/` lab-discovery path for compatibility. **WSLPE itself has no AD dependency.**

WSLPE is a **first-class Kingdoms lab**, not an extension of NORTH. The existing instance manager creates its own workspace and Vagrant state. Its single guest is `WSLPE-WS01`, pinned to the same Windows 10 image version as the existing NORTH workstation.

- The instance range `{{ip_range}}.31` must be inspected against the operator's real host networks before VM creation. Using the default 192.168.56.x range is **not an automatic collision clearance**.
- The provider inventory is intentionally one Windows workstation only.
- The initial Ansible run reads `data/inventory` and the rendered provider inventory. The post-Vagrant `data/inventory_disable_vagrant` is a separate lifecycle artifact. Both inventories must contain the WSLPE local Windows host group.
- The `inventory_disable_vagrant` file currently holds *bootstrap* Vagrant credentials for management and will need to be replaced with a dedicated operator-only identity before learner access is released.
- No domain join, DC, router, domain GPO or cross-host service is part of WSLPE.
- No VMware vmnet index is fixed in the native WSLPE recipe. This workstation's management NAT may be vmnet8, but future VMware hosts must discover their available networks. Non-VMware VPS/cloud installations will need a provider-specific adapter. See `docs/WSLPE_NETWORK_PORTABILITY.md`.
- The lab is discoverable, and an operator-confirmed **Stage 1 guest-only boot** is now available through the private Kingdoms console. Keep the course registry marked `development` until Windows/network isolation, learner provisioning, the original 20 scenarios and the 15 additional scenarios pass their separate acceptance gates. This is not a completed course installation.
- Learners receive the vulnerable guest only, not Kingdoms source or provider control.

See `docs/WSLPE_CORE_INTEGRATION_PLAN.md` for the implementation and acceptance contract.
