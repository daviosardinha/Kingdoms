#!/usr/bin/env python3
"""One-time private Ansible runtime preparation for existing WSLPE41 VMware guest.

--prepare writes ONLY the fresh instance's private Ansible inputs; no guest or
host networking changes. --verify reruns exact live operator HTTPS, private
inventory, fixture proof and real Ansible win_ping using the pinned TLS leaf.
No scenario or account is installed by this program.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kingdoms.wslpe41_install_flow import InstallBlocked
from kingdoms.wslpe41_operator_management import ManagementBlocked
from kingdoms.wslpe41_provided_runtime import prepare, load_existing
from kingdoms.wslpe41_stage_executor import _environment, _guest, _inventory
from kingdoms.wslpe41_operator_auth import authenticate_native_operator


@contextmanager
def scoped_secrets(context, operator, learner):
    names = (
        "KINGDOMS_WSLPE_INSTANCE_ID", "KINGDOMS_WSLPE_OPERATOR_PASSWORD",
        "KINGDOMS_WSLPE_LEARNER_PASSWORD", "KINGDOMS_WSLPE_FIXTURE_VARS_FILE",
    )
    original = {key: os.environ.get(key) for key in names}
    try:
        os.environ.update({
            names[0]: context.identity.instance_id, names[1]: operator,
            names[2]: learner, names[3]: str(context.private_vars),
        })
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.prepare:
            print("[SCOPE] One existing registered bf5369-wslpe-vmware only", flush=True)
            print("[WRITE] Private instance inventory, certificate anchor and fixture secrets ONLY", flush=True)
            prepare()
        context, operator, learner = load_existing()
        with scoped_secrets(context, operator, learner):
            _guest(context)
            _inventory(context, _environment(context))
            print("[PASS] Instance-owned private inventory, vars and pinned TLS certificate", flush=True)
            if not authenticate_native_operator(context):
                raise InstallBlocked("Ansible operator authentication did not pass")
            print("[PASS] Exact operator Ansible win_ping over verified HTTPS/5986", flush=True)
            print("[PASS] WSLPE41_PROVIDED_RUNTIME_READY", flush=True)
        print("[NOT INSTALLED] No 41-scenario guest mutation executed", flush=True)
        return 0
    except (InstallBlocked, ManagementBlocked, ValueError, OSError) as exc:
        # A delegated library exception may contain a secret in its text;
        # never print arbitrary stderr, inventory contents or passwords.
        print(f"[BLOCKED] Provided Ansible runtime: {type(exc).__name__}", flush=True)
        print("[PRESERVED] No automatic regeneration, recovery or retry", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
