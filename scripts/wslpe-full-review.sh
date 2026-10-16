#!/usr/bin/env bash
# One command for ALL currently available WSLPE P1-C pre-change reviews.
# No VM lifecycle, packet probes to NORTH, firewall writes, guest mutations.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
PY="$HOME/.goad/.venv/bin/python"
ANSIBLE="$HOME/.goad/.venv/bin/ansible-playbook"
[[ -x "$PY" && -x "$ANSIBLE" ]] || {
    echo '[BLOCKED] Missing existing Kingdoms GOAD Python/Ansible environment'
    exit 1
}
cd "$ROOT"
export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"
export ANSIBLE_ROLES_PATH="$ROOT/ansible/roles"

echo 'KINGDOMS WSLPE | CONSOLIDATED READ-ONLY REVIEW'
echo 'No changes to NORTH, Windows, VMware, Linux routes or nftables'

echo '===== SOURCE REGRESSION GATES ====='
"$PY" -m py_compile \
    scripts/wslpe-p1c-batch-review.py \
    scripts/wslpe-p1c-isolation-plan.py
"$PY" -m unittest -v \
    tests.test_wslpe_p1c_batch_review \
    tests.test_wslpe_isolation_policy \
    tests.test_wslpe_p1c_topology_audit \
    tests.test_wslpe_access_audit \
    tests.test_wslpe_https_auth_audit

echo '===== READ-ONLY PRIVILEGED FIREWALL EVIDENCE ====='
echo 'sudo is used only for nft --check/list, ss inventory, and iptables-save.'
sudo -v || { echo '[BLOCKED] Read-only firewall evidence requires sudo'; exit 1; }

echo '===== WSLPE COMPLETE P1-C REVIEW ====='
"$PY" scripts/wslpe-p1c-batch-review.py \
    --expected-thumbprint C773EC26D02940F559FE715B83628FEDAE2AA92D

echo '[NO CHANGES] Full read-only P1-C review completed'
