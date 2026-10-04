#!/usr/bin/env bash
# Trigger DHCPv6 renewal on WS01 over the existing trusted management path,
# then show only new mitm6 / observer evidence produced by that action.
set -uo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
PLAYBOOK="$ROOT/ansible/phase03-trigger-ws01-renew6.yml"
DATA_INVENTORY="$ROOT/ad/GOAD/data/inventory"
PROVIDER_INVENTORY="$ROOT/ad/GOAD/providers/vmware/inventory"
MITM6_LOG="${MITM6_LOG:-/tmp/kingdoms-mitm6.log}"
HTTP_LOG="${HTTP_LOG:-/tmp/kingdoms-wpad-http.log}"
IFACE="${IFACE:-vmnet10}"
PCAP="${PCAP:-/tmp/kingdoms-wpad.pcap}"
WS01_V4="${WS01_V4:-10.4.10.31}"
WS01_MAC="${WS01_MAC:-00:50:56:20:10:31}"
ATTACKER_V6="${ATTACKER_V6:-fe80::250:56ff:fec0:a}"
WPAD_WAIT_SECONDS="${WPAD_WAIT_SECONDS:-360}"
WPAD_POLL_SECONDS="${WPAD_POLL_SECONDS:-10}"

find_ansible_playbook() {
  local c
  for c in \
    "$(command -v ansible-playbook 2>/dev/null || true)" \
    "$ROOT/.venv/bin/ansible-playbook" \
    "$ROOT/venv/bin/ansible-playbook" \
    "$HOME/.goad/.venv/bin/ansible-playbook" \
    "$HOME/.local/bin/ansible-playbook"; do
    [[ -n "$c" && -x "$c" ]] || continue
    printf '%s\n' "$c"
    return 0
  done
  return 1
}

cd "$ROOT" || exit 1

pgrep -af '(^|[ /])mitm6([ ]|$)' >/dev/null || {
  echo 'FAIL: scoped mitm6 is not running' >&2
  exit 1
}

[[ -f "$PLAYBOOK" ]] || {
  echo "FAIL: missing playbook: $PLAYBOOK" >&2
  exit 1
}

[[ -f "$MITM6_LOG" ]] || {
  echo "FAIL: mitm6 log missing: $MITM6_LOG" >&2
  exit 1
}

[[ -f "$HTTP_LOG" ]] || {
  echo "FAIL: WPAD HTTP observer log missing: $HTTP_LOG" >&2
  echo 'Start scripts/phase03/diagnostics/start-wpad-observers.sh before triggering WS01.' >&2
  exit 1
}

sudo ss -H -lntp 2>/dev/null | grep -Eq ':80[[:space:]]' || {
  echo 'FAIL: WPAD HTTP observer is not listening on TCP/80' >&2
  exit 1
}

pgrep -af "tcpdump[ ].*-i[ ]+${IFACE}[ ].*-w[ ]+${PCAP//./[.]}" >/dev/null || {
  echo 'FAIL: WPAD packet capture is not running' >&2
  exit 1
}

mitm6_before="$(wc -l < "$MITM6_LOG")"
http_before="$(wc -l < "$HTTP_LOG")"

echo '===== BASELINE ====='
printf 'mitm6 lines: %s\nHTTP lines : %s\n' "$mitm6_before" "$http_before"

ANSIBLE_PLAYBOOK="$(find_ansible_playbook || true)"
[[ -n "$ANSIBLE_PLAYBOOK" ]] || {
  echo 'FAIL: ansible-playbook not found' >&2
  exit 1
}

echo
echo '===== TRIGGER WS01 DHCPV6 RENEWAL ====='
ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
"$ANSIBLE_PLAYBOOK" \
  -i "$DATA_INVENTORY" \
  -i "$PROVIDER_INVENTORY" \
  "$PLAYBOOK" || exit 1

echo
echo "===== WAIT FOR AUTOMATIC WPAD DISCOVERY ====="
echo "INFO: Windows WPAD discovery is asynchronous."
echo "INFO: polling every ${WPAD_POLL_SECONDS}s for up to ${WPAD_WAIT_SECONDS}s; the 15-minute safety watchdog remains authoritative."

elapsed=0
wpad_seen=0
http_seen=0

while (( elapsed <= WPAD_WAIT_SECONDS )); do
  if [[ -r "$PCAP" ]]; then
    if (( wpad_seen == 0 )) && tshark -r "$PCAP"       -Y "eth.src == $WS01_MAC && ipv6.dst == $ATTACKER_V6 && dns.qry.name contains \"wpad\""       -T fields -e frame.number 2>/dev/null | grep -q .; then
      wpad_seen=1
      echo "[+] WPAD DNS query observed after ${elapsed}s"
    fi

    if (( http_seen == 0 )) && tshark -r "$PCAP"       -Y "ip.src == $WS01_V4 && http.request.method == \"GET\" && http.request.uri == \"/wpad.dat\""       -T fields -e frame.number 2>/dev/null | grep -q .; then
      http_seen=1
      echo "[+] GET /wpad.dat observed after ${elapsed}s"
    fi
  fi

  if (( wpad_seen == 1 && http_seen == 1 )); then
    echo "PHASE03_WPAD_AUTODISCOVERY_OBSERVED=True"
    break
  fi

  if (( elapsed >= WPAD_WAIT_SECONDS )); then
    break
  fi

  if (( elapsed == 0 || elapsed % 30 == 0 )); then
    echo "INFO: still waiting for Windows WPAD discovery... elapsed=${elapsed}s"
  fi

  sleep "$WPAD_POLL_SECONDS"
  elapsed=$((elapsed + WPAD_POLL_SECONDS))
done

echo
echo '===== NEW MITM6 OUTPUT ====='
tail -n "+$((mitm6_before + 1))" "$MITM6_LOG" 2>/dev/null || true

echo
echo '===== NEW HTTP OUTPUT ====='
tail -n "+$((http_before + 1))" "$HTTP_LOG" 2>/dev/null || true

if (( wpad_seen == 0 || http_seen == 0 )); then
  echo "WARN: automatic WPAD DNS/PAC evidence was not complete within ${WPAD_WAIT_SECONDS}s." >&2
  echo 'WARN: leave the exercise armed only if you are still observing it; complete-wpad-exercise.sh remains the final validator and rollback gate.' >&2
else
  echo "PASS: automatic WPAD DNS and PAC retrieval observed in the live capture"
fi

