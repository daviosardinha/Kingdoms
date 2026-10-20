#!/usr/bin/env bash
# Read-only diagnosis of the forest-root PDC time source and the WINTERFELL -> KINGSLANDING NTP path.
set -uo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
ANSIBLE_PLAYBOOK="${ANSIBLE_PLAYBOOK:-$HOME/.goad/.venv/bin/ansible-playbook}"
# Override both inventory paths when diagnosing an installed NORTH instance.
# Defaults intentionally preserve the established full GOAD diagnostic.
DATA_INVENTORY="${KINGDOMS_DIAG_DATA_INVENTORY:-$ROOT/ad/GOAD/data/inventory}"
PROVIDER_INVENTORY="${KINGDOMS_DIAG_PROVIDER_INVENTORY:-$ROOT/ad/GOAD/providers/vmware/inventory}"
TMP="$(mktemp /tmp/kingdoms-root-time.XXXXXX.yml)"
trap 'rm -f "$TMP"' EXIT

cat >"$TMP" <<'YAML'
---
- name: Diagnose forest-root time authority without changing state
  hosts: dc01:dc02
  gather_facts: false

  tasks:
    - name: Collect root-PDC and parent-time-path evidence
      ansible.windows.win_powershell:
        script: |
          $ErrorActionPreference = 'Continue'

          function Emit-Command {
              param(
                  [Parameter(Mandatory=$true)][string]$Name,
                  [Parameter(Mandatory=$true)][scriptblock]$Command
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

          Write-Output ("HOST|NAME={0}|TIME={1:o}" -f $env:COMPUTERNAME,(Get-Date))

          try {
              Import-Module ActiveDirectory -ErrorAction Stop
              $root = Get-ADDomain -Identity 'sevenkingdoms.local' -ErrorAction Stop
              Write-Output ("AD|ROOT_DOMAIN={0}|PDC={1}|RID={2}|INFRA={3}" -f $root.DNSRoot,$root.PDCEmulator,$root.RIDMaster,$root.InfrastructureMaster)
          }
          catch {
              Write-Output ("AD|ROOT_DOMAIN_QUERY_FAILED={0}" -f $_.Exception.Message)
          }

          foreach ($svcName in 'W32Time','Netlogon','Kdc','NTDS') {
              try {
                  $svc = Get-Service -Name $svcName -ErrorAction Stop
                  $cim = Get-CimInstance Win32_Service -Filter "Name='$svcName'"
                  Write-Output ("SERVICE|NAME={0}|STATE={1}|STARTMODE={2}" -f $svcName,$svc.Status,$cim.StartMode)
              }
              catch {
                  Write-Output ("SERVICE|NAME={0}|ERROR={1}" -f $svcName,$_.Exception.Message)
              }
          }

          Emit-Command 'ROOT_DSGETDC_GENERIC' { nltest.exe /dsgetdc:sevenkingdoms.local /force }
          Emit-Command 'ROOT_DSGETDC_PDC' { nltest.exe /dsgetdc:sevenkingdoms.local /pdc /force }
          Emit-Command 'ROOT_DSGETDC_TIMESERV' { nltest.exe /dsgetdc:sevenkingdoms.local /timeserv /force }
          Emit-Command 'ROOT_DSGETDC_GTIMESERV' { nltest.exe /dsgetdc:sevenkingdoms.local /gtimeserv /force }

          Emit-Command 'W32TM_SOURCE' { w32tm.exe /query /source }
          Emit-Command 'W32TM_STATUS' { w32tm.exe /query /status /verbose }
          Emit-Command 'W32TM_CONFIGURATION' { w32tm.exe /query /configuration }
          Emit-Command 'W32TM_PEERS' { w32tm.exe /query /peers }

          try {
              $cfg = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\W32Time\Config' -ErrorAction Stop
              Write-Output ("REGISTRY|CONFIG|ANNOUNCEFLAGS={0}|LOCALCLOCKDISPERSION={1}" -f $cfg.AnnounceFlags,$cfg.LocalClockDispersion)
          }
          catch {
              Write-Output ("REGISTRY|CONFIG|ERROR={0}" -f $_.Exception.Message)
          }

          try {
              $params = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\W32Time\Parameters' -ErrorAction Stop
              Write-Output ("REGISTRY|PARAMETERS|TYPE={0}|NTPSERVER={1}" -f $params.Type,$params.NtpServer)
          }
          catch {
              Write-Output ("REGISTRY|PARAMETERS|ERROR={0}" -f $_.Exception.Message)
          }

          try {
              $server = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\W32Time\TimeProviders\NtpServer' -ErrorAction Stop
              Write-Output ("REGISTRY|NTP_SERVER_PROVIDER|ENABLED={0}" -f $server.Enabled)
          }
          catch {
              Write-Output ("REGISTRY|NTP_SERVER_PROVIDER|ERROR={0}" -f $_.Exception.Message)
          }

          if ($env:COMPUTERNAME -ieq 'KINGSLANDING') {
              Emit-Command 'DCDIAG_ADVERTISING' { dcdiag.exe /test:advertising /s:kingslanding /v }
          }

          if ($env:COMPUTERNAME -ieq 'WINTERFELL') {
              Emit-Command 'STRIPCHART_KINGSLANDING' { w32tm.exe /stripchart /computer:kingslanding.sevenkingdoms.local /samples:5 /dataonly }
          }

          Write-Output '===== TIME SERVICE EVENTS ====='
          Get-WinEvent -FilterHashtable @{
              LogName='System'
              ProviderName='Microsoft-Windows-Time-Service'
              StartTime=(Get-Date).AddHours(-2)
          } -ErrorAction SilentlyContinue |
              Sort-Object TimeCreated |
              Select-Object -Last 50 |
              ForEach-Object {
                  $msg = ($_.Message -replace "\r",' ' -replace "\n",' ')
                  Write-Output ("TIME_EVENT|TIME={0:o}|ID={1}|LEVEL={2}|MESSAGE={3}" -f $_.TimeCreated,$_.Id,$_.LevelDisplayName,$msg)
              }

          Write-Output 'KINGDOMS_FOREST_ROOT_TIME_DIAGNOSTIC_COMPLETE=True'
      changed_when: false
      register: diag

    - name: Emit complete forest-root time diagnostic
      ansible.builtin.debug:
        var: diag.output
      changed_when: false
YAML

cd "$ROOT" || exit 1

ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
timeout 360 "$ANSIBLE_PLAYBOOK" \
  -i "$DATA_INVENTORY" \
  -i "$PROVIDER_INVENTORY" \
  "$TMP"
