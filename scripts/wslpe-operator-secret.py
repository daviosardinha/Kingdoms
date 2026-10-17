#!/usr/bin/env python3
"""Private local WSLPE operator credential preparation (NO guest mutation)."""
from __future__ import annotations
import argparse
import importlib.util
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kingdoms.wslpe_operator_credentials import operator_secret
STAGE=ROOT/"scripts/wslpe-stage2-inspect.py"

def exact_native_id() -> str:
    spec=importlib.util.spec_from_file_location("wslpe_operator_stage2",STAGE)
    if spec is None or spec.loader is None:
        raise ValueError("WSLPE instance helper not available")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    identity,meta=mod.find_instance(mod.WORKSPACE)
    vmx=mod.locate_registered_vm(identity)
    if meta.get("lab")!="WSLPE" or meta.get("provider")!="vmware":
        raise ValueError("Not the canonical WSLPE VM")
    if (vmx.is_symlink() or not vmx.resolve(strict=True).is_relative_to(
            mod.WORKSPACE.resolve())):
        raise ValueError("WSLPE VMX escapes dedicated workspace")
    return meta["id"]

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare",action="store_true",
                        help="create private per-instance operator secret, but do not change Windows")
    args=parser.parse_args()
    print("KINGDOMS WSLPE | DEDICATED OPERATOR CREDENTIAL PREPARATION")
    print("[NO GUEST CHANGES] No Windows account, WinRM, VMware or NORTH mutation")
    try:
        ident=exact_native_id()
        print(f"[SCOPE] Exact registered WSLPE instance: {ident}")
        if not args.prepare:
            print("[PLAN ONLY] Use --prepare to generate a private credential once")
            return 0
        operator_secret(ident,prepare=True)
    except Exception as exc:
        print(f"[BLOCKED] {type(exc).__name__}; no guest changes")
        return 1
    print("[PASS] Private operator secret prepared/reused; never printed")
    print("[NOT DEPLOYED] Windows account absent until separately approved provisioning")
    print("[NO RELEASE] vagrant stays enabled pending independent authenticated HTTPS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
