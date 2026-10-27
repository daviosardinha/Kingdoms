# KINGDOMS / NORTH / Mayfly GOAD lifecycle parity review

**Date:** 2026-10-27  
**Scope:** Source-only inspection, NORTH installed VMware startup failure after PURPLE coexistence acceptance. **No production, host, guest, or VMware state changed by this review.**

## What was compared

1. Mayfly's original GOAD repository: `Orange-Cyberdefense/GOAD`, `main`, `goad/provider/vagrant/vagrant.py`.
2. KINGDOMS `main`: `daviosardinha/Kingdoms`, known-good operator baseline, including `goad/provider/vagrant/{vagrant,vmware_nomad,vmware_kingdoms}.py`.
3. NORTH candidate source: `fix/installed-member-w32time-cold-start-recovery` and downstream coexistence changes on `fix/north-purple-owned-vagrant-forwarding`.

These are **source versions**, not claims that the currently installed VMs were freshly regression-tested here.

## Source comparison

| Property | Upstream GOAD (Mayfly) | KINGDOMS main | NORTH development |
|---|---|---|---|
| Full start | `vagrant up` | Segmented instance lifecycle, exact VMX, dependencies, router and exercise restoration | Reuses same provider, plus NORTH-specific network and time changes |
| Stop | `vagrant halt` | Scoped bounded VMware guest handling for segmented labs | Same host provider but some different stopped-member/failed-start semantics |
| AD readiness | Primarily provisioning-dependent | DC service, SYSVOL/NETLOGON, Locator, TIMESERV, expected parent source | Same, plus verbose W32Time **five exact regex states** for DC02 |
| Parent time-source identity | Not a standalone installed-start gate | Requires `w32tm /query /source` matches `kingslanding.sevenkingdoms.local` | Same |
| Member time | Basic AD deployment dependencies | Requires member secure channel, Netlogon, parent source | Adds bounded member NT5DS recovery following sustained time-only pending |
| Failed-start exercise isolation | Not an upstream concept | Normal exercise transition | Adds `allow_stopped_members=True` for still-isolated, powered-off members |

## Live evidence — 2026-10-27

- NORTH instance: `0da0a9-north-vmware` (installed/exercise).
- First blocker: vmnet8 NAT added 2200/2201/2202 for PURPLE-WS01. Explicit, identity-bound registration passed without VMware network writes.
- Startup then passed: segmented preflight, router SSH/policy, router owner route, GOAD-DC01 authenticated readiness, GOAD-DC02 direct authenticated WinRM.
- DC02 failure after 300s: `W32Time child-domain time server is not yet signed, synchronized and advertising` and `time_repair_attempted=False`. Since the message comes **after** service/share/DC locator/TIMESERV/source checks, the last sampled response had already passed those earlier checks.
- Failure cleanup raised a separate `TypeError`: VMware provider method `set_runtime_mode` did not accept the NORTH-only `allow_stopped_members=True` argument. This was fixed on the downstream coexistence branch with an exact regression test.
- The trace cannot prove whether DC02's actual time status was healthy: the script threw a single generic message and discarded the individual `w32tm /query /status /verbose` fields.

## Why the extra DC02 gate was a reliability regression

The added five `-match` patterns required *exact* English verbose strings for:
`State Machine: 2 (Sync)`, `Time Source Flags: 8 (SignatureAuthenticated...)`,
`Server Role: 64 (Time Service)`, `Last Sync Error: 0 (...)`,
and `Leap Indicator: 0 (...)`.

These are Windows Time **diagnostic display fields**, not a stable API for readiness across OS builds, languages, bit flags or transient startup states. Even when all established AD and parent-source checks pass, one differing string blocks all NORTH members for the entire 300-second startup budget.

The KINGDOMS `main` DC02 startup contract already requires:
1. NTDS, DNS, ADWS, Netlogon, KDC and W32Time services running;
2. SYSVOL and NETLOGON published;
3. DC Locator and `/timeserv` discovery;
4. exact `kingslanding.sevenkingdoms.local` W32Time selected source.

Microsoft documents AD time hierarchy and domain-time authentication, and separately presents `w32tm /query /status /verbose` as diagnostic output:
- https://learn.microsoft.com/en-us/windows-server/networking/windows-time-service/how-the-windows-time-service-works
- https://learn.microsoft.com/en-us/windows-server/networking/windows-time-service/Windows-Time-Service-Tools-and-Settings

**Recommendation implemented on this branch:** Restore precisely that successful KINGDOMS DC readiness contract, including expected parent source, rather than requiring exact verbose W32Time display text on the startup critical path. Strict member secure-channel and expected domain-time readiness **remain** prerequisites. Do not add alternate public NTP servers or disable NTP security.

This does **not** prove that DC02's time configuration is good. A DC can appear in Locator while not yet being fully synchronized. Collect independent read-only evidence using `scripts/diagnostics/north-installed-time-evidence.py --target winterfell`, and keep real time failures visible rather than re-labeling them as successful.

## Code and acceptance gates

- NORTH-owned NAT coexistence remains behind explicit root-only instance-bound registration; unknown VMnet changes remain blocked.
- Failed-start isolation `allow_stopped_members=True` is allowed only for already recorded NORTH exercise mode, and preserves normal strict isolation in all other cases.
- Restored DC02 readiness uses the **KINGDOMS main** AD/Locator/TIMESERV/W32Time source checks, not a new abbreviated approximation.
- DC02 strict display-status regex stays in optional diagnostics, not the blocking startup probe.
- Strict member `Test-ComputerSecureChannel`, `nltest /sc_query`, expected time source and optional bounded member repair remain unchanged.
- No restart, `w32tm /resync`, trust reset, new NAT routes, or guest writes are part of the source repair.
- Source regression tests must pass; Windows runner certificate failure is separate infrastructure debt.
- Live gate: verify immutable NORTH owner, run installed NORTH `start`, confirm all intended guests running and verified, exercise-mode restored, and no PURPLE guest/network changes.
- If the unchanged member time checks fail, gather exact W32Time evidence. Do **not** silently weaken them.

## Deferred cleanup

- Unify the segmented power/state control plane across installed lab instances without changing Vagrant identities or VMware networks.
- Add machine-readable W32Time diagnostics (e.g., captured command output, independent health reporting) and avoid matching localized verbose human-readable labels in critical lifecycle code.
- Validate NORTH **stop + cold-start twice** and preserved exercises before merging the parity change into its parent branch; do not treat source tests as full VM acceptance.
