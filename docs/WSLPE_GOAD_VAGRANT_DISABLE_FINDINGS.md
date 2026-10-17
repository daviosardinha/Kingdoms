# GOAD issue #284 — Vagrant bootstrap retirement and Kingdoms

**Reviewed 2026-10-17. Source-only safety action. No VM changes.**

## Verified upstream finding

The original report from daviosardinha is [Orange-Cyberdefense/GOAD issue #284](https://github.com/Orange-Cyberdefense/GOAD/issues/284), "NHA - Disable vagrant Issue - WinRM username: vagrant", opened 2024-10-21. It remains **OPEN**, with no merged fix linked in the issue. The GOAD maintainer confirmed the problem and the workaround of leaving vagrant enabled.

Current upstream main @ 992307adf944b934a3b76a2f56a637104c54b805 (inspected 2026-10-17):
- goad/provider/vagrant/vagrant.py implements start as Vagrant up and stop as Vagrant halt, which can invoke its Windows WinRM communicator.
- ansible/disable_vagrant.yml still disables the Windows vagrant account; ansible/roles/disable_user/tasks/main.yml uses account_disabled: true.
- The upstream NHA inventory_disable_vagrant moves Ansible to domain administrator credentials, but this **does not change Vagrant's own communicator credentials**.
- Therefore there is **no upstream fixed implementation to cherry-pick**. The open issue and provider code do not prove a successful post-disable VM boot.

## Kingdoms architecture: retain proven split

- Fresh installs and ALL development/provisioning, including WSLPE: **retain vagrant** and Vagrant/Ansible communicator until configuration and scenario acceptance finish.
- Existing installed NORTH lifecycle already provides the right model: goad/provider/vagrant/vmware_kingdoms.py uses exact registered VMX paths, vmrun power-on/shutdown and independent WinRM readiness, rather than invoking Vagrant up against a disabled login. Preserve this source unchanged and do not touch NORTH VMs.
- WSLPE remains development-only (PROVIDED). Its kingdom/wslpe_resume.py (actual path: kingdoms/wslpe_resume.py) intentionally calls Vagrant up WSLPE-WS01 --no-provision with a temporary direct WinRM override. The default vagrant login MUST remain usable until that path is retired.
- A WSLPE-scoped guard in goad_nomad.py refuses the legacy do_disable_vagrant command, even when invoked directly instead of through the interactive command filter. Other GOAD/NORTH console behavior is unchanged.

## Future WSLPE student-ready cutover (NOT YET IMPLEMENTED/AUTHORIZED)

1. Finish and live-verify all 45 exercises; prove credentials are per-instance, learner remains nonadmin, security boundary and intended credential discovery paths work, and finalize independent recovery.
2. Create and authenticate a replacement operator administrator over pinned HTTPS. Update only WSLPE provisioning and management inventory so it no longer depends on vagrant. Keep the WinRM service and unrelated sessions untouched.
3. Implement and validate a separate **post-release** WSLPE lifecycle that boots/stops/resets only the exact registered WSLPE VMware guest, with VMware vmrun and a captured fully vulnerable baseline snapshot; no Vagrant up/halt/reprovision, no automatic retry, no fallback to vagrant login. The development resume remains Vagrant-based while the lab is not released.
4. Require two independent readiness indicators: validated course release and verified guest state/identity. Do not trust generic READY status by itself; the shared GOAD console may mark READY after general Ansible provisioning, before secure handoff.
5. After a reviewed, testable rollback and an explicit final release approval, disable vagrant from the replacement operator context. Prove the known bootstrap password no longer authenticates and the VMware-only start/stop/reset + operator HTTPS access still work; fail closed if any check fails.
6. Only then capture/finalize the KINGDOMS-WSLPE-READY baseline and permit learner access. Fresh installs always enter the original Vagrant bootstrap flow and repeat release gates.

The current KINGDOMS-WSLPE-PRE-JEA snapshot is a development recovery point and still contains the original vagrant account.

## Current evidence / decision

**PASS:** upstream issue and current provider confirmed; NORTH installed runtime uses vmrun; WSLPE early-disable safeguard and mock regression added.

**BLOCKED:** upstream issue unresolved; WSLPE post-release VMware-only lifecycle not implemented, vagrant still enabled, all 45 live validation incomplete. Absolutely no automatic disable_vagrant, shared NORTH role modification or guest changes from this source checkpoint.
