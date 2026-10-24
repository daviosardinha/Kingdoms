#!/usr/bin/env bash
# Read-only diagnosis for the recurring CASTELBLACK / SRV02 domain-time startup failure.
set -uo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
ANSIBLE_PLAYBOOK="${ANSIBLE_PLAYBOOK:-$HOME/.goad/.venv/bin/ansible-playbook}"
# Override both inventory paths when diagnosing an installed NORTH instance.
# Defaults intentionally preserve the established full GOAD diagnostic.
DATA_INVENTORY="${KINGDOMS_DIAG_DATA_INVENTORY:-$ROOT/ad/GOAD/data/inventory}"
PROVIDER_INVENTORY="${KINGDOMS_DIAG_PROVIDER_INVENTORY:-$ROOT/ad/GOAD/providers/vmware/inventory}"
TMP="$(mktemp /tmp/kingdoms-srv02-time.XXXXXX.yml)"
trap 'rm -f "$TMP"' EXIT

[[ -x "$ANSIBLE_PLAYBOOK" ]] || {
  echo "FAIL: ansible-playbook not executable: $ANSIBLE_PLAYBOOK" >&2
  exit 1
}

cat >"$TMP" <<'YAML'
---
- name: Diagnose CASTELBLACK domain time without changing state
  hosts: srv02
  gather_facts: false
  tasks:
    - name: Collect read-only identity and W32Time evidence
      ansible.windows.win_powershell:
        script: |
          $ErrorActionPreference = 'Continue'

          function Emit-Command {
              param(
                  [string]$Name,
                  [scriptblock]$Command
              )
              $global:LASTEXITCODE = 0
              try {
                  $value = & $Command 2>&1 | Out-String
                  $rc = $LASTEXITCODE
                  if ($null -eq $rc) { $rc = 0 }
                  $safe = (($value -replace "\r",' ' -replace "\n",' ; ').Trim())
                  if (-not $safe) { $safe = '<empty>' }
                  Write-Output ("CMD|NAME={0}|RC={1}|OUT={2}" -f $Name,$rc,$safe)
              }
              catch {
                  Write-Output ("CMD|NAME={0}|EXCEPTION={1}" -f $Name,$_.Exception.Message)
              }
          }

          $computer = Get-CimInstance Win32_ComputerSystem
          Write-Output ("IDENTITY|HOST={0}|DOMAIN={1}|PART_OF_DOMAIN={2}" -f $env:COMPUTERNAME,$computer.Domain,$computer.PartOfDomain)

          try {
              Resolve-DnsName 'winterfell.north.sevenkingdoms.local' -ErrorAction Stop | Out-Null
              Write-Output 'DNS|WINTERFELL=PASS'
          }
          catch {
              Write-Output ("DNS|WINTERFELL=FAIL|ERROR={0}" -f $_.Exception.Message)
          }

          try {
              $secure = Test-ComputerSecureChannel -Server 'winterfell.north.sevenkingdoms.local' -ErrorAction Stop
              Write-Output ("SECURE_CHANNEL|HEALTHY={0}" -f $secure)
          }
          catch {
              Write-Output ("SECURE_CHANNEL|ERROR={0}" -f $_.Exception.Message)
          }

          try {
              $account = New-Object System.Security.Principal.NTAccount('NORTH','administrator')
              $sid = $account.Translate([System.Security.Principal.SecurityIdentifier])
              Write-Output ("ACCOUNT_TRANSLATION|PASS|SID={0}" -f $sid.Value)
          }
          catch {
              Write-Output ("ACCOUNT_TRANSLATION|FAIL|ERROR={0}" -f $_.Exception.Message)
          }

          foreach ($svcName in 'W32Time','Netlogon') {
              try {
                  $svc = Get-Service -Name $svcName -ErrorAction Stop
                  $cim = Get-CimInstance Win32_Service -Filter "Name='$svcName'"
                  Write-Output ("SERVICE|NAME={0}|STATE={1}|STARTMODE={2}" -f $svcName,$svc.Status,$cim.StartMode)
              }
              catch {
                  Write-Output ("SERVICE|NAME={0}|ERROR={1}" -f $svcName,$_.Exception.Message)
              }
          }

          Emit-Command 'W32TM_SOURCE' { w32tm.exe /query /source }
          Emit-Command 'W32TM_STATUS' { w32tm.exe /query /status /verbose }
          Emit-Command 'W32TM_CONFIGURATION' { w32tm.exe /query /configuration }
          Emit-Command 'W32TM_PEERS' { w32tm.exe /query /peers }
          Emit-Command 'NLTEST_DSGETDC' { nltest.exe /dsgetdc:north.sevenkingdoms.local /force }
          Emit-Command 'NLTEST_SC_QUERY' { nltest.exe /sc_query:north.sevenkingdoms.local }
          Emit-Command 'W32TM_STRIPCHART_DC' { w32tm.exe /stripchart /computer:winterfell.north.sevenkingdoms.local /samples:3 /dataonly }

          try {
              $params = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\W32Time\Parameters' -ErrorAction Stop
              Write-Output ("REGISTRY|TYPE={0}|NTPSERVER={1}" -f $params.Type,$params.NtpServer)
          }
          catch {
              Write-Output ("REGISTRY|ERROR={0}" -f $_.Exception.Message)
          }

          Write-Output '===== RECENT TIME-SERVICE EVENTS ====='
          Get-WinEvent -FilterHashtable @{
              LogName='System'
              ProviderName='Microsoft-Windows-Time-Service'
              StartTime=(Get-Date).AddHours(-2)
          } -ErrorAction SilentlyContinue |
              Sort-Object TimeCreated |
              Select-Object -Last 30 |
              ForEach-Object {
                  $msg = ($_.Message -replace "\r",' ' -replace "\n",' ')
                  Write-Output ("TIME_EVENT|TIME={0:o}|ID={1}|LEVEL={2}|MESSAGE={3}" -f $_.TimeCreated,$_.Id,$_.LevelDisplayName,$msg)
              }

          Write-Output 'KINGDOMS_SRV02_TIME_DIAGNOSTIC_COMPLETE=True'
      changed_when: false
      register: diag

    - name: Emit diagnostic
      ansible.builtin.debug:
        var: diag.output
      changed_when: false
YAML

cd "$ROOT" || exit 1
ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
timeout 300 "$ANSIBLE_PLAYBOOK" \
  -i "$DATA_INVENTORY" \
  -i "$PROVIDER_INVENTORY" \
  "$TMP"
