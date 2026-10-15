# WSLPE Windows networking lifecycle

**Operator-only development contract. Not yet learner-ready.** This is a WSLPE-specific extraction of the Windows NIC lifecycle semantics already demonstrated by NORTH, rather than an invocation of NORTH's routing, AD or domain services.

## What we confirmed

The independent native WSLPE instance has booted to Kingdoms status `PROVIDED`. Stage 2 fixture tests passed, but the actual bootstrap WinRM guest TCP/5985 forward was observed on host TCP/2210 **listening on 0.0.0.0**. Running as root, `ss` and `lsof` both identified the owner as **vmnet-nat**, not the Python/Kingdoms console. The Vagrantfile's `host_ip: 127.0.0.1` cannot by itself be accepted as security evidence because the **actual daemon socket** is wildcard-bound.

NORTH already has a proven two-phase pattern:

- **Provisioning**: VMware Ethernet0 NAT attached for controlled Vagrant/WinRM bootstrap while Ethernet1 carries the exercise network.
- **Exercise**: Ethernet0 persistently disconnected, Windows guest managed through its trusted exercise interface. NORTH verifies `ethernet0.startConnected=FALSE`, the appropriate dedicated Ethernet1 VMnet, and direct Windows services after transition.
- **Rollback/restore**: preserve the mode contract instead of blindly invoking Vagrant `up` or reconnecting management NAT.

Source references: `scripts/lab-mode.sh`, `scripts/validate-ws01-runtime.sh`, `scripts/validate-network-segmentation-runtime.sh`, and `goad/provider/vagrant/vmware_kingdoms.py`.

**Do not call those NORTH scripts with WSLPE.** They assume a router, AD infrastructure, and fixed NORTH-owned VMnets. WSLPE must be an isolated one-guest implementation using the same **invariants**, not the entire NORTH lifecycle implementation.

## New WSLPE-only compensating management-port guard

New operator-only files:

- `kingdoms/wslpe_winrm_guard.py`: pure rule/owner validation of a dedicated nftables input chain, matching exactly one dynamically discovered WinRM forwarded TCP port.
- `scripts/wslpe-winrm-firewall.py`: **read-only by default**. Its `--apply --confirm-port <current-port>` is an explicit **privileged host firewall mutation**, scoped to the WSLPE port. It checks the native instance and running VM registration, proves the port's current socket is owned by `vmnet-nat`, refuses to overwrite another existing nftables table, and verifies the result after applying.
- `scripts/wslpe-stage2-inspect.py`: continues to demand loopback management isolation. Because the NAT daemon may genuinely bind `0.0.0.0`, it may instead accept the **exact runtime nftables input/drop JSON rule plus privileged owner proof** as an explicitly labeled *compensating control*. It never describes a wildcard-bound socket as loopback-bound.
- `tests/test_wslpe_winrm_guard.py` and expanded `tests/test_wslpe_stage2_inspect.py`: exercise malicious/incorrect firewall JSON, wrong ports, wrong ownership and no-guard failure behavior.

The rule created by the guarded command is in its **own** `inet kingdoms_wslpe_winrm` table, with one input hook and:

```text
meta iifname != "lo" tcp dport <actual_WSLPE_host_port> drop
```

This is not a firewall flush, a Vagrant reload, or a VMware NAT restart. It does **not** rewrite vmnet8 or touch a NORTH guest. The nftables rule is **runtime-only**. It may disappear after a host reboot, at which point the checker must fail closed. A subsequent course release must define and verify the rule's lifecycle/persistence, a clean removal path, and an independent remote-reachability test. A stage-2 pass does **not** by itself mean the guest is safe for learner access.

### Operator troubleshooting: separate Python and Vagrant contexts

The operator's first consolidated test run used Kali's system `python3` (Python 3.14), which cannot import `ansible_runner` from Kingdoms' established dependencies. **The 82 tests did not all pass**: 81 passed and one test module could not import. Run all WSLPE tests through **`$HOME/.goad/.venv/bin/python`** instead. Output printed by mocked firewall tests, including simulated `[PASS] ... DROP verified`, is **not live host firewall evidence**.

The initial `sudo "$HOME/.goad/.venv/bin/python" scripts/wslpe-winrm-firewall.py` audit also failed during `vagrant port WSLPE-WS01`. The first implementation ran Vagrant as root, so it could see a **different Vagrant home/plugin context** from the operator who registered the instance. The updated WSLPE inspector now delegates **only** the read-only `vagrant port` call back to the verified owner of the native WSLPE instance directory when the firewall audit itself is root. It requires `SUDO_UID` to match that directory's non-root owner, uses `sudo -H -u <verified-owner> -- vagrant port`, and leaves `nft` and privileged `ss` checks as root. It neither changes ownership nor copies/restores Vagrant registration state, and it refuses arbitrary identity mismatches.

Preferred next checks:

```bash
cd "$HOME/kingdoms-lpe-standalone"
git fetch origin && git merge --ff-only origin/feature/windows-lpe-standalone-foundation
"$HOME/.goad/.venv/bin/python" -m unittest discover -s tests -p 'test_wslpe_*.py' -q
sudo "$HOME/.goad/.venv/bin/python" scripts/wslpe-winrm-firewall.py
```

The read-only audit is expected to return `[BLOCKED]` while no WSLPE-specific guard exists. Only once the revised tests pass and the live audit confirms the exact WSLPE forwarded port and its current `vmnet-nat` ownership should the operator approve the **explicit one-port nftables mutation**. Never infer that a mocked unit-test message configured the firewall. In particular, do not run `vagrant up`, modify NORTH, `chmod` the instance directory, or clear/reset Vagrant's state to fix this symptom.

### First bounded operator check

After pulling and running the new source tests, **audit** the real WSLPE host port using the existing native instance (the operator's current port was TCP/2210):

```bash
cd "$HOME/kingdoms-lpe-standalone"
"$HOME/.goad/.venv/bin/python" -m unittest discover -s tests -p 'test_wslpe_winrm_guard.py' -v
"$HOME/.goad/.venv/bin/python" -m unittest discover -s tests -p 'test_wslpe_nic_contract.py' -v
sudo "$HOME/.goad/.venv/bin/python" scripts/wslpe-winrm-firewall.py
```

The audit intentionally exits nonzero when the protective rule is absent. **Only when the audit proves that TCP/2210 still belongs to WSLPE's vmnet-nat and the operator approves a one-port change**, execute:

```bash
sudo "$HOME/.goad/.venv/bin/python" scripts/wslpe-winrm-firewall.py --apply --confirm-port 2210
```

**Never copy the 2210 port number to another host without first discovering that host's actual WSLPE forward.** No change is allowed for an ambiguous instance, changed listener owner, an already present foreign rule/table or a mismatch in the explicit confirmation.

If successful, verify actual Windows guest state and the exercise NIC. The following checks **do not change any VM or networking state**:

```bash
sudo -v
bash scripts/wslpe-stage2-acceptance.sh
python3 scripts/wslpe-exercise-network-preflight.py
```

The Windows baseline and exercise NIC checks are separate. The exercise-network preflight intentionally fails if Vagrant's generated private network did not map to a **dedicated, unshared** host-only VMware vmnet, if its configured subnet is not the WSLPE instance subnet, or if there is no matching host interface. **Do not fix that by moving WSLPE onto vmnet8 or a NORTH VMnet.**

## Latest live Stage 2 evidence: firewall profile ambiguity

The operator confirmed **90/90 WSLPE regression tests PASS** and successfully applied the WSLPE-specific temporary nftables protection for guest WinRM TCP/5985 forwarded to host TCP/2210. The subsequent live acceptance confirmed the exact VMX, registered WSLPE instance, VMware NAT and dedicated `vmnet2` exercise interfaces, `172.28.231.31/24` guest IP, no AD join, enabled UAC, and running Defender. The exercise NIC's actual VMware subnet matches `172.28.231.0/24`. NORTH remained untouched.

The live Windows audit reported **7 PASS / 1 FAIL**. The sole failing assertion was `All Windows firewall profiles enabled`. **This is not yet proof a profile is disabled:** `Get-NetFirewallProfile` may serialize its `Enabled` CIM/GpoBoolean property as strings such as `"True"` or `"False"`, whereas the initial Python evaluator required literal JSON boolean `true` for every profile.

The read-only inspector now prints the exact Domain, Private and Public `Enabled` values and JSON data types, together with active interface network classifications. It accepts only explicit boolean `true` or the string `"True"` and still rejects `false`, `"False"`, `NotConfigured`, missing profiles, duplicates and unknown values. The future WSLPE learner foundation uses the same explicit `[string]$_.Enabled -eq 'True'` semantics. Additional mocked regression cases exercise all these inputs.

**Next operator command, read-only:**

```bash
cd "$HOME/kingdoms-lpe-standalone"
git fetch origin && git merge --ff-only origin/feature/windows-lpe-standalone-foundation
bash scripts/wslpe-network-acceptance.sh
```

This will rerun the source tests and the live Windows/firewall + dedicated NIC checks. Record the `[INFO] Windows Firewall` lines and the final Stage 2 summary. **Do not run `Set-NetFirewallProfile` or change Windows settings based on an unevidenced type mismatch.** If any actual profile is disabled, assess the source Vagrant image and scenario prerequisites before making an explicit WSLPE-only change. The firewall host guard is not reboot-persistent and guest-to-host isolation, direct HTTPS WinRM and learner access remain unverified.

## New blocker: registered WSLPE VMX not in the running VMware inventory

The operator reran the combined read-only WSLPE network acceptance after the firewall profile reporting update. The Stage 2 tests passed **25/25**, but **all three** live runtime checks stopped at `Exact registered WSLPE VMX is not uniquely running`, before reaching WinRM, Windows Firewall or the exercise NIC. Prior evidence had confirmed this native VMX running, so the immediate question is whether VMware has powered it off, ceased reporting it, or the registered Vagrant VMX path no longer matches the actual running file. **Do not conclude that Windows Firewall is still failing.** No change to NORTH was reported.

A single new operator-only diagnostic identifies the exact reason without starting, destroying or reloading VMs:

```bash
cd "$HOME/kingdoms-lpe-standalone"
git fetch origin && git merge --ff-only origin/feature/windows-lpe-standalone-foundation
"$HOME/.goad/.venv/bin/python" -m unittest discover \
  -s tests -p 'test_wslpe_vm_state_diagnose.py' -v
"$HOME/.goad/.venv/bin/python" scripts/wslpe-vm-state-diagnose.py
```

The script checks the WSLPE native `instance.json`, the read-only `.vagrant/machines/WSLPE-WS01/vmware_desktop/id` registration path, and the actual output of `vmrun -T ws list` plus `vagrant status WSLPE-WS01` from the **existing operator** Vagrant project. It distinguishes a stopped/non-listed guest, an altered VMX path and an ambiguous duplicate. It performs **no host or Windows mutations** and deliberately exits nonzero when the VM is not proven running. No automatic reboot or state repair may be attempted before examining this evidence. The newly committed diagnostic and fixture tests are awaiting operator execution.

## Planned WSLPE-specific exercise handoff, NOT IMPLEMENTED YET

We must validate the following gates before disconnecting WSLPE's NAT adapter:

1. Prove `ethernet0` is the current NAT provisioning adapter and `ethernet1` is a **separate dedicated host-only vmnet**, not vmnet1, vmnet8, or vmnet10/20/30/99. `kingdoms/wslpe_nic_contract.py` and `scripts/wslpe-exercise-network-preflight.py` encode this requirement without changing the guest.
2. Validate that the actual dedicated host-only vmnet and the Windows guest match the native instance's configured private /24, and ensure no other guest uses that exercise segment.
3. Verify an independent, authenticated **direct WinRM HTTPS management path** to the WSLPE exercise IP from the trusted operator host. Do not disconnect NAT first and hope for recovery.
4. Implement a WSLPE-specific bounded mode transition that disconnects NAT for this exact VMX, persists `ethernet0.startConnected=FALSE` safely, verifies Ethernet1 remained present and the Windows machine remains reachable, and fails closed with a WSLPE-only rollback plan. **Do not invoke NORTH's lab-mode script.**
5. Prove wildcard NAT forwarding is no longer reachable from untrusted interfaces after guest isolation. A disconnected guest NIC alone is not proof that the host NAT daemon has retired its listener.
6. Only then proceed to non-admin local learner provisioning, the original 20 LPE scenarios, and the additional 15 planned scenarios.

**No automatic exercise-mode cutover is enabled in this revision.** This is deliberate: the current guest NIC-to-vmnet mapping and direct WinRM path have not yet been observed. We must inspect them before making irreversible or potentially disruptive guest changes.

For future clean VMware hosts, network IDs and the private prefix are discovered per host. For a future VPS/AWS implementation, only the learner/lab contract is shared; it requires a provider-specific virtual NIC and access adapter, not VMware vmnet names.
