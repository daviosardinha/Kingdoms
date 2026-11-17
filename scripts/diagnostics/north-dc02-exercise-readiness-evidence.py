#!/usr/bin/env python3
"""Read-only replay of NORTH's EXACT exercise-mode DC02 time-readiness probe.

Does not change AD, W32Time, Windows guest power, NAT, router, or host routes.
Runs precisely the PowerShell probe embedded in scripts/lab-mode.sh, using the
same NORTH direct-NTLM helper as exercise mode, but exposes stdout, stderr,
return code and elapsed time instead of hiding everything as reason=transport.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "scripts" / "lab-mode.sh"
HELPER = ROOT / "scripts" / "north-exercise-winrm.py"
DOMAIN = "north.sevenkingdoms.local"
PARENT = "kingslanding.sevenkingdoms.local"


def exact_probe() -> str:
    source = LAB.read_text(encoding="utf-8")
    start = source.index("ensure_child_dc_time_ready() {")
    end = source.index("\nwait_domain_controller_ready() {", start)
    part = source[start:end]
    match = re.search(
        r'probe_script="\$\(cat <<POWERSHELL\n(.*?)\nPOWERSHELL\n\)"',
        part,
        flags=re.S,
    )
    if not match:
        raise ValueError("NORTH DC02 exercise PowerShell probe source not found")
    script = match.group(1).replace(r"\$", "$")
    script = script.replace("${domain}", DOMAIN)
    script = script.replace("${parent_server}", PARENT)
    if "${" in script or len(script.encode("utf-8")) > 5000:
        raise ValueError("Unresolved or oversized exercise PowerShell probe")
    required = (
        "KINGDOMS_DC_TIME_READY|",
        "KINGDOMS_DC_TIME_NOT_READY|",
        "w32tm.exe /query /source",
        f"/dsgetdc:{DOMAIN}",
        "/timeserv /force",
    )
    if not all(marker in script for marker in required):
        raise ValueError("Exercise time-readiness contract not recognized")
    return script


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", type=Path, required=True)
    args = parser.parse_args()
    if not args.provider.is_absolute() or args.provider.is_symlink():
        parser.error("Provide the exact absolute installed NORTH provider path")
    # Load and run the existing, strict ownership validation before any network.
    import importlib.util
    spec = importlib.util.spec_from_file_location("north_direct", HELPER)
    if spec is None or spec.loader is None:
        raise SystemExit("[BLOCKED] Direct NORTH WinRM helper unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        module.validate_provider(str(args.provider))
        script = exact_probe()
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"[BLOCKED] {exc}", file=sys.stderr)
        return 2
    print("[INFO] Replaying exact NORTH/DC02 exercise time probe read-only", flush=True)
    print(f"[INFO] script_bytes={len(script.encode('utf-8'))} endpoint=10.4.10.11:5986", flush=True)
    start = time.monotonic()
    try:
        outcome = subprocess.run(
            [
                sys.executable, str(HELPER), "--machine", "GOAD-DC02",
                "--provider", str(args.provider), "--timeout", "75",
            ],
            input=script,
            text=True,
            capture_output=True,
            timeout=85,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        print(f"[FAIL] helper process exceeded 85s: {type(exc).__name__}")
        return 1
    elapsed = round(time.monotonic() - start, 2)
    print(f"[EVIDENCE] elapsed_seconds={elapsed} returncode={outcome.returncode}", flush=True)
    print("=== STDOUT ===", flush=True)
    print(outcome.stdout[:4000], flush=True)
    print("=== STDERR ===", flush=True)
    print(outcome.stderr[:4000], flush=True)
    markers = re.findall(
        r"KINGDOMS_DC_TIME_(?:READY|NOT_READY)\|[^\r\n]*", outcome.stdout
    )
    print(f"[EVIDENCE] marker={markers[-1] if markers else '<missing>'}", flush=True)
    if outcome.returncode == 0 and markers and markers[-1].startswith("KINGDOMS_DC_TIME_READY|"):
        print("[PASS] Exact exercise DC02 read-only probe accepted")
        return 0
    print("[FAIL] Exact exercise DC02 probe did not produce an accepted readiness marker")
    return 1


if __name__ == "__main__":
    sys.exit(main())
