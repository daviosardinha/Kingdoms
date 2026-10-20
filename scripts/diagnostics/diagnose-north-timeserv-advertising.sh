#!/usr/bin/env bash
# Read-only comparison of NORTH time-service advertising from WINTERFELL and CASTELBLACK.
set -uo pipefail

ROOT="${ROOT:-$HOME/Documents/GOAD_NOMAD}"
ANSIBLE_PLAYBOOK="${ANSIBLE_PLAYBOOK:-$HOME/.goad/.venv/bin/ansible-playbook}"
# Override both inventory paths when diagnosing an installed NORTH instance.
# Defaults intentionally preserve the established full GOAD diagnostic.
DATA_INVENTORY="${KINGDOMS_DIAG_DATA_INVENTORY:-$ROOT/ad/GOAD/data/inventory}"
PROVIDER_INVENTORY="${KINGDOMS_DIAG_PROVIDER_INVENTORY:-$ROOT/ad/GOAD/providers/vmware/inventory}"
TMP="$(mktemp /tmp/kingdoms-north-timeserv.XXXXXX.yml)"
trap 'rm -f "$TMP"' EXIT

cat >"$TMP" <<'YAML'
---
- name: Diagnose NORTH time-service advertising without changing state
  hosts: dc02:srv02
  gather_facts: false
  tasks:
    - name: Collect NORTH time-service and DC Locator evidence
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

          $computer = Get-CimInstance Win32_ComputerSystem
          Write-Output ("IDENTITY|DOMAIN={0}|PART_OF_DOMAIN={1}" -f $computer.Domain,$computer.PartOfDomain)

          foreach ($svcName in 'W32Time','Netlogon','Kdc','NTDS') {
              try {
                  $svc = Get-Service -Name $svcName -ErrorAction Stop
                  $cim = Get-CimInstance Win32_Service -Filter "Name='$svcName'"
                  Write-Output ("SERVICE|NAME={0}|STATE={1}|STARTMODE={2}" -f $svcName,$svc.Status,$cim.StartMode)
              }
              catch {
                  Write-Output ("SERVICE|NAME={0}|ABSENT_OR_ERROR={1}" -f $svcName,$_.Exception.Message)
              }
          }

          Emit-Command 'DSGETDC_GENERIC' { nltest.exe /dsgetdc:north.sevenkingdoms.local /force }
          Emit-Command 'DSGETDC_TIMESERV' { nltest.exe /dsgetdc:north.sevenkingdoms.local /timeserv /force }
          Emit-Command 'DSGETDC_GTIMESERV' { nltest.exe /dsgetdc:north.sevenkingdoms.local /gtimeserv /force }
          Emit-Command 'SC_QUERY' { nltest.exe /sc_query:north.sevenkingdoms.local }

          Emit-Command 'W32TM_SOURCE' { w32tm.exe /query /source }
          Emit-Command 'W32TM_STATUS' { w32tm.exe /query /status /verbose }
          Emit-Command 'W32TM_CONFIGURATION' { w32tm.exe /query /configuration }
          Emit-Command 'W32TM_PEERS' { w32tm.exe /query /peers }
          Emit-Command 'W32TM_MONITOR' { w32tm.exe /monitor /domain:north.sevenkingdoms.local }

          try {
              $cfg = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\W32Time\Config' -ErrorAction Stop
              Write-Output ("REGISTRY|CONFIG|ANNOUNCEFLAGS={0}" -f $cfg.AnnounceFlags)
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
              $ntpServer = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\W32Time\TimeProviders\NtpServer' -ErrorAction Stop
              Write-Output ("REGISTRY|NTP_SERVER_PROVIDER|ENABLED={0}" -f $ntpServer.Enabled)
          }
          catch {
              Write-Output ("REGISTRY|NTP_SERVER_PROVIDER|ERROR={0}" -f $_.Exception.Message)
          }

          if ($env:COMPUTERNAME -ieq 'WINTERFELL') {
              Emit-Command 'DCDIAG_ADVERTISING' { dcdiag.exe /test:advertising /s:winterfell /v }
          }

          Write-Output '===== TIME SERVICE EVENTS ====='
          Get-WinEvent -FilterHashtable @{
              LogName='System'
              ProviderName='Microsoft-Windows-Time-Service'
              StartTime=(Get-Date).AddHours(-2)
          } -ErrorAction SilentlyContinue |
              Sort-Object TimeCreated |
              Select-Object -Last 40 |
              ForEach-Object {
                  $msg = ($_.Message -replace "\r",' ' -replace "\n",' ')
                  Write-Output ("TIME_EVENT|TIME={0:o}|ID={1}|LEVEL={2}|MESSAGE={3}" -f $_.TimeCreated,$_.Id,$_.LevelDisplayName,$msg)
              }

          Write-Output '===== NETLOGON EVENTS ====='
          Get-WinEvent -FilterHashtable @{
              LogName='System'
              ProviderName='NETLOGON'
              StartTime=(Get-Date).AddHours(-2)
          } -ErrorAction SilentlyContinue |
              Sort-Object TimeCreated |
              Select-Object -Last 30 |
              ForEach-Object {
                  $msg = ($_.Message -replace "\r",' ' -replace "\n",' ')
                  Write-Output ("NETLOGON_EVENT|TIME={0:o}|ID={1}|LEVEL={2}|MESSAGE={3}" -f $_.TimeCreated,$_.Id,$_.LevelDisplayName,$msg)
              }

          Write-Output 'KINGDOMS_NORTH_TIMESERV_DIAGNOSTIC_COMPLETE=True'
      changed_when: false
      register: diag

    - name: Emit complete NORTH time-service diagnostic
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
