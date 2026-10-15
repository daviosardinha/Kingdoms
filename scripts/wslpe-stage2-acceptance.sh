#!/usr/bin/env bash
# Kingdoms WSLPE: one read-only operator Stage 2 acceptance command.
# Does not create VMs, provision accounts, change networks, or run exploits.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$HOME/.goad/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo '[BLOCKED] Existing Kingdoms Python virtual environment missing' >&2
  exit 1
fi

echo 'KINGDOMS WSLPE | STAGE 2 RUNTIME GATE'
echo '[CHECK] Stage 2 mock and parser regression tests'
"$PYTHON" -m unittest discover \
  -s "$ROOT/tests" -p 'test_wslpe_stage2_inspect.py' -v

echo '[CHECK] Native WSLPE VMX, VMware adapters, management WinRM and Windows baseline'
"$PYTHON" "$ROOT/scripts/wslpe-stage2-inspect.py" --show-adapters

echo '[PASS] WSLPE Stage 2 read-only Windows baseline and checks passed'
echo '[NOT VERIFIED] Complete VMware network isolation or learner/scenario acceptance'
