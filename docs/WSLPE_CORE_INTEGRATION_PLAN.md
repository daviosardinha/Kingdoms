# WSLPE: reuse the Kingdoms core, not a parallel installer

**Decision:** Build `WSLPE` as a **first-class Kingdoms lab recipe and independent instance** managed by the existing Kingdoms operator console, lab manager, provider factory, workspace isolation, Ansible provisioner and source gates. **Do not make a separate ad-hoc Vagrant project the authoritative installation path.** The existing NORTH deployment remains untouched during WSLPE development.

## Lab versus extension

- `WSLPE`: a new independent lab/profile with one Windows guest, local standard learner account and no Active Directory dependencies. This is the correct isolation boundary for a standalone Windows LPE course and later cloud image.
- An extension adds machine(s) or provisioning to an *existing* instance. It is **not** a replacement for the independent WSLPE lab. A future extension may reuse the same Windows LPE role to add an optional profile to other Kingdoms labs, but NORTH currently already seeds the original 20 through its own Ansible playbook.
- `NORTH`: Course 1's current deployed domain-joined lab, including its working WS01. Preserve it until the independent WSLPE profile is fully proven.

The working course identifier remains `windows-lpe` for the operator menu; the concrete lab identifier is **`WSLPE`**. The learner receives access only to a vulnerable guest, never the operator console.

## Existing source that must be reused

| Component | Already exists | WSLPE integration task |
| --- | --- | --- |
| Operator entry point | `./goad.sh`, `goad_nomad.py` | Route `windows-lpe` selection to a separate `WSLPE` instance through existing lab/instance management |
| Lab discovery | `goad/labs.py`, `goad/goadpath.py` | Add a WSLPE lab recipe in the existing lab-discovery layout. Path label `ad/` is a **legacy repository layout**, not a requirement that WSLPE use AD |
| Instances | `goad/lab_manager.py`, `goad/instance.py` | Create a dedicated WSLPE workspace instance with its own Vagrant state, VM identity, provider inventory and lifecycle |
| Provider | `goad/provider/provider_factory.py`, `goad/provider/vagrant/vmware_kingdoms_profile.py` | Reuse the existing VMware/Vagrant provider non-NORTH path. Prove it works for one Windows guest without using NORTH router/network policy |
| Existing 20 scenarios | `ansible/roles/windows_lpe/` | Keep the role and per-technique apply/validate/reset untouched until tested against a local learner |
| Existing installer | `ansible/ws01-lpe-install.yml` | Extract/reuse its `full-lpe` role invocation in a WSLPE-specific playbook; feed a local learner name/password, not Rickon's domain values |
| Provisioning | `goad/provisioner/ansible/ansible.py`, `playbooks.yml` | Add a separate `WSLPE` playbook sequence. It must **not** execute `build.yml`, domain membership, AD data, trusts or NORTH's WS01 foothold configuration without independently proving those tasks are local-only |
| Regression | `scripts/validate-windows-lpe-framework-source.sh` | Preserve existing 20-scenario source contract and add WSLPE instance, domain-free provisioning and per-scenario runtime gates |

The existing provider factory selects the profiled Kingdoms VMware provider for the `vmware` provider. The profiled and segmented paths special-case the historical `GOAD` lab and otherwise delegate to the common VMware provider. This makes reuse promising, **not already validated**. Test non-NORTH guest creation and WinRM inventory carefully.

## Instance and guest identity

- Lab identifier: `WSLPE`
- Proposed guest name: `WSLPE-WS01` (exact identifier subject to provider-template checks)
- Exactly one Windows guest from the already installed pinned `mayfly/windows10` `2024.01.06` box
- Local standard learner (identity set through Ansible vars); privileged training fixtures remain local to this guest
- One standalone VMware instance with unique Vagrant state/VMX and no connections to NORTH segmented networks
- Operator management during provisioning is allowed, but exploit demonstrations must remain local-only and work without DCs or any other vulnerable machine
- Never alter existing NORTH `GOAD-WS01` or its live networking, inventory, scheduler or credentials

## Engineering milestones

1. **Legacy state review.** Operator-side read-only inspection of `courses/windows-lpe/standalone/.vagrant` and global VMware state before retiring the experimental bootstrap. Do not delete state or assume it is empty. No untracked VM may be adopted silently by a new WSLPE instance.
2. **Native lab recipe.** Add `WSLPE` to the original Kingdoms lab-discovery structure with a single VMware Windows guest definition and inventory. Ensure the provider can build the instance without domain controllers, segmented routers or NORTH preflights.
3. **Unified operator flow.** In `./goad.sh`, `courses` → `select_course windows-lpe` → `install` must select/manage a WSLPE **instance** through the existing lab manager. Do not bypass its workspace, provider and provisioning contract with a separate `vagrant up`. Keep NORTH behavior unchanged when selected.
4. **Local Windows foundation.** Create only the local standard learner, provisioner identity and guest readiness checks first. Verify build, non-domain membership, UAC, Defender and Firewall, WinRM management boundary and unique VMware NICs. Do not apply vulnerabilities until the base is proven.
5. **Existing 20.** Reuse the `windows_lpe` role and `full-lpe` selection through a WSLPE-specific playbook with a local learner account. Test each scenario's apply/validate/low-privileged exploit/reset/reapply behavior. The existing NORTH role defaults still contain some target-specific local fixture names that need a **separate, evidenced compatibility audit**.
6. **Next 15.** Add the approved 15 scenarios as candidate techniques to the **same role**, not a second implementation, and require reproducible local-only exploitation and rollback before promotion.
7. **NORTH integration.** Only after WSLPE passes all 35 and regression: use the same shared role on the existing NORTH WS01 with its domain learner adapter and verify Phase 00–03 invariants and the full 35-scenario lifecycle.

## Invariants

- **One Kingdoms core**, two independent lab instances, one shared LPE scenario engine.
- Separate course identity from lab instance identity. No learner gets control-plane access.
- WSLPE must not require AD, DCs, LDAP, domain DNS, remote shares, another target or NORTH's router.
- Source tests are not equivalent to a guest exploit success. Every real escalation result needs evidence.
- No normal deployment is allowed to claim `WSLPE=READY` or `windows-lpe=available` before provisioning and scenario gates pass.
- No destructive cleanup or merging of unfinished experimental VM state without operator review.

## Superseded prototype

`courses/windows-lpe/standalone/Vagrantfile` and `kingdoms/windows_lpe_vmware.py` were previously created as a separate VMware bootstrap. They are **not** the final WSLPE installation architecture. Treat the direct boot code as an engineering prototype only. Its standalone machine was reported `not created` by the operator's last Vagrant status, but it also has unexplained Vagrant state and its previous `course-vm-create` run failed. **Do not retry direct guest creation, delete Vagrant state, or continue evolving the parallel bootstrap.** Use the native Kingdoms instance path after migration and regression.

Do not rename/remove historical paths, source-gate labels or legacy lab `GOAD` identifiers by bulk replacement. Those are internal backward-compatibility constraints; the operator-facing project, course and WSLPE lab branding stays Kingdoms.
