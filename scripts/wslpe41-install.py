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
    args = parser.parse_args(argv)
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
    for i, scenario in enumerate(scenarios, 1):
        channel = "independent guest console" if scenario.execution_channel == "out_of_band_jea_activation" else "Ansible"
        print(f"  {i:02d}/41  #{scenario.number:02d}  {scenario.identifier}  [{channel}]")
    print("[PLAN ONLY] 41/41 is a source manifest, not a deployed machine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
