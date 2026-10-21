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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="print the single 41-scenario manifest (default)")
    mode.add_argument("--execute", action="store_true", help="not yet enabled: requires proven fresh-native runner")
    mode.add_argument("--host-plan", action="store_true",
                      help="read-only VMware/host/VPN/native instance subnet discovery")
    mode.add_argument("--native-status", action="store_true",
                      help="read-only proof of an existing native WSLPE VMX registration")
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
