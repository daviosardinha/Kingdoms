#!/usr/bin/env python3
"""KINGDOMS WSLPE: one future native fresh installation of all 41 scenarios.

Source-plan only until the new-guest provider/management/JEA runner is wired
and proven on two clean VMware instances. --execute fails before any writes.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kingdoms.wslpe41_fresh_contract import fresh_scenario_manifest


def provided_plan() -> int:
    """One read-only live handoff for the existing, already managed fresh VM.

    This NEVER creates/re-provisions a guest or creates a 41-install journal.
    It deliberately does not upgrade --execute into an unsafe installer.
    """
    from kingdoms.wslpe41_operator_management import (
        ManagementBlocked, exact_target, run as management_verify,
    )
    from kingdoms.wslpe41_stage_commands import one_install_invocations

    try:
        target = exact_target()
        if target.instance.name != "bf5369-wslpe-vmware":
            raise ManagementBlocked("Provided instance identity mismatch")
        proofs = []
        management_verify(apply=False, report=proofs.append)
        if not any(line.startswith("[PASS] WSLPE_OPERATOR_MANAGEMENT=PASS")
                   for line in proofs):
            raise ManagementBlocked("Fresh operator HTTPS handoff has no live proof")

        # In secure operation, the learner's vmnet3 IP is an exercise target
        # and is NOT the WinRM management transport. Existing stage plans
        # still parameterize Windows scenarios using the learner address.
        guest = "172.28.232.31"
        operator = "172.28.233.31"
        inventory = target.instance / "ansible" / "inventory.yml"
        private_vars = target.instance / "ansible" / "private-vars.yml"
        ansible = Path.home() / ".goad/.venv/bin/ansible-playbook"
        stages = one_install_invocations(
            ansible=ansible, inventory=inventory, varsfile=private_vars,
            expected_address=guest, instance_id=target.instance.name,
            management_address=operator,
        )
        if (len(stages) != 83 or len(set(stage.number for stage in stages)) != 41
                or len([stage for stage in stages if stage.transport == "guest_console"]) != 1):
            raise ManagementBlocked("Canonical 41/83 stage mapping has drifted")
        print("[PASS] Existing fresh VMware instance uniquely identified")
        print("[PASS] Existing kingdom.operator live TLS/policy/isolation re-verified")
        print(f"[PASS] WSLPE41_PROVIDED_STAGE_MAP=41 scenarios / {len(stages)} stages")
        print(f"[LEARNER TARGET] {guest} (vmnet3; never WinRM transport)")
        print(f"[OPERATOR TRANSPORT] {operator}:5986 (vmnet4; pinned TLS required)")
        for label, path, private in (
            ("Ansible executable", ansible, False),
            ("Secure native inventory", inventory, False),
            ("Private fixture vars", private_vars, True),
        ):
            if (not path.is_file() or path.is_symlink()
                    or (private and path.stat().st_mode & 0o077)):
                print(f"[PENDING] {label}: exact instance-owned runtime input missing or unsafe")
            else:
                print(f"[EXISTS] {label}; effective contents not yet attested")
        print("[PENDING] Bind dedicated operator HTTPS, private secrets and exact inventory")
        print("[PENDING] Independent VMware-console JEA #30 activation and WinRM recovery")
        print("[NOT EXECUTED] No scenario, VM, account, firewall, route or journal changes")
        print("[NOT AUTHORIZED] --execute is still blocked until runtime acceptance")
        return 0
    except (ManagementBlocked, OSError, ValueError, RuntimeError) as exc:
        print(f"[BLOCKED] Existing WSLPE41 installer handoff: {type(exc).__name__}")
        print("[NO CHANGES] No VM, guest, Ansible or scenario mutations")
        return 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="print the single 41-scenario manifest (default)")
    mode.add_argument("--execute", action="store_true", help="not yet enabled: requires proven fresh-native runner")
    mode.add_argument("--host-plan", action="store_true",
                      help="read-only VMware/host/VPN/native instance subnet discovery")
    mode.add_argument("--native-status", action="store_true",
                      help="read-only proof of an existing native WSLPE VMX registration")
    mode.add_argument("--provided-plan", action="store_true",
                      help="read-only 41/83 stage and live operator handoff for the existing fresh guest")
    parser.add_argument("--workspace", action="append", default=None,
                        help="additional native Kingdoms workspace to inspect (repeatable; host-plan only)")
    parser.add_argument("--instance-dir", default=None,
                        help="exact native WSLPE instance directory (native-status only)")
    args = parser.parse_args(argv)
    if args.workspace and not args.host_plan:
        parser.error("--workspace is only meaningful with --host-plan")
    if bool(args.instance_dir) != bool(args.native_status):
        parser.error("--instance-dir is required only with --native-status")
    scenarios = fresh_scenario_manifest()
    print("KINGDOMS | WSLPE41 | ONE FRESH INSTALLATION")
    print("[SCOPE] Exactly 41 scenarios, one ordered installer, one journal, one guest")
    print("[EXCLUDED] Historical IDs 25,36,38,40 are not part of this course")
    if args.provided_plan:
        return provided_plan()
    if args.execute:
        print("[BLOCKED] No production fresh-native runner is wired yet.")
        print("[BLOCKED] Guest creation, learner/operator bootstrap, per-scenario execution,")
        print("          out-of-band JEA #30 activation and second clean-build proof remain required.")
        print("[SAFETY] No VMware, Windows, Ansible or network changes were made.")
        return 2
    if args.native_status:
        from kingdoms.wslpe41_host_preflight import HostEvidenceBlocked, read_only_command
        from kingdoms.wslpe41_native_identity import inspect_native_registration
        try:
            output = read_only_command("vmrun", "-T", "ws", "list")
            instance = Path(args.instance_dir).expanduser().absolute()
            registration = inspect_native_registration(instance, output)
        except (HostEvidenceBlocked, OSError) as exc:
            print(f"[BLOCKED] Native WSLPE registration: {exc}")
            return 2
        print(f"[NATIVE PROVIDED] {registration.instance_id}")
        print(f"[SUBNET] {registration.subnet}")
        print(f"[GUEST ADDRESS] {registration.guest_address}")
        print("[NOT PROVEN] This is NOT fresh-guest, operator-management or 41/41 validation.")
        print("[SAFETY] Read-only; no VMware or guest changes.")
        return 0
    if args.host_plan:
        from kingdoms.wslpe41_host_preflight import HostEvidenceBlocked, host_plan
        repo = Path(__file__).resolve().parents[1]
        workspaces = [repo / "workspace"]
        for extra in args.workspace or []:
            path = Path(extra).expanduser().absolute()
            if not path.is_dir() or path.is_symlink():
                print("[BLOCKED] Additional native workspace missing or unsafe.")
                return 2
            workspaces.append(path)
        try:
            plan = host_plan(workspaces=tuple(workspaces))
        except (HostEvidenceBlocked, OSError) as exc:
            print(f"[BLOCKED] Read-only host network preflight: {exc}")
            return 2
        print(f"[HOST CANDIDATE] {plan.subnet}")
        print(f"[GUEST ADDRESS] {plan.guest_address}")
        print(f"[EXISTING VMWARE RUNNING GUESTS] {plan.running_vm_count} (not stopped)")
        print(f"[NATIVE INSTANCES] {plan.registered_instance_count} across {plan.workspace_count} inspected workspaces")
        print("[SAFETY] Candidate only; not proof of global VM registration or actual vmnet isolation.")
        print("[SAFETY] No VMware, Windows, Ansible, guest or host configuration changes.")
        return 0
    for i, scenario in enumerate(scenarios, 1):
        channel = "independent guest console" if scenario.execution_channel == "out_of_band_jea_activation" else "Ansible"
        print(f"  {i:02d}/41  #{scenario.number:02d}  {scenario.identifier}  [{channel}]")
    print("[PLAN ONLY] 41/41 is a source manifest, not a deployed machine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
