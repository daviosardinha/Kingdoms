# WSLPE #30: out-of-band Windows PowerShell 5.1 JEA endpoint lifecycle.
# Import has NO effects; invoke ONLY from elevated VMware Workstation console.
Set-StrictMode -Version Latest

function Assert-Wslpe45JeaConsole {
    [CmdletBinding()]param()
    $ErrorActionPreference='Stop'
    if ($PSVersionTable.PSVersion.Major -ne 5 -or
        $PSVersionTable.PSEdition -ne 'Desktop') {
        throw 'WSLPE JEA console runner requires Windows PowerShell 5.1 Desktop'
    }
    if (Get-Variable PSSenderInfo -ErrorAction SilentlyContinue) {
        throw 'WSLPE JEA registration cannot run from a remote PowerShell session'
    }
    if ($env:SESSIONNAME -cne 'Console' -or
        [Diagnostics.Process]::GetCurrentProcess().SessionId -eq 0) {
        throw 'WSLPE JEA registration requires the interactive VMware guest console'
    }
    $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
    $principal=New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Elevated local administrator token required'
    }
    Import-Module 'C:\ProgramData\KingdomsWSLPE45\lib\WslpeFixture.psm1' -Force -ErrorAction Stop
    $null=Assert-Wslpe45Identity
    $service=Get-Service WinRM -ErrorAction Stop
    if ($service.Status -ne 'Running') {
        throw 'WinRM must be running before JEA lifecycle begins; inspect manually'
    }
}

function Restore-Wslpe45WinrmAfterLocalJea {
    [CmdletBinding()]param()
    $ErrorActionPreference='Stop'
    # Registration on PowerShell 5.1 can stop its own WinRM transport,
    # despite -NoServiceRestart. This routine is local, never WinRM-hosted.
    for ($i=0; $i -lt 45; $i++) {
        $svc=Get-Service WinRM -ErrorAction Stop
        if ($svc.Status -eq 'Running') { break }
        if ($svc.Status -eq 'Stopped') {
            Start-Service WinRM -ErrorAction Stop
        }
        Start-Sleep -Seconds 1
    }
    if ((Get-Service WinRM -ErrorAction Stop).Status -ne 'Running') {
        throw 'WinRM did not recover locally; investigate from VMware console'
    }
    # Do not alter any machine-wide listener/certificate/firewall settings.
    $https=@(Get-NetTCPConnection -LocalPort 5986 -State Listen -ErrorAction SilentlyContinue)
    if ($https.Count -lt 1) { throw 'WinRM running but HTTPS/5986 is not listening' }
    Write-Output 'WSLPE45_JEA_WINRM_LOCAL_RECOVERY=PASS'
}

function Invoke-Wslpe45JeaLocal {
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)]
          [ValidateSet('Inspect','Apply','Reset')][string]$Action)
    $ErrorActionPreference='Stop'
    Assert-Wslpe45JeaConsole
    $root='C:\ProgramData\KingdomsWSLPE45\fixtures\jea_role_capability_misconfig'
    $marker='C:\Program Files\WindowsPowerShell\Modules\Kingdoms45JEA\.kingdoms45-owner.txt'
    $endpoint=@(Get-PSSessionConfiguration -Name Kingdoms45JEA -ErrorAction SilentlyContinue)
    if ($Action -eq 'Inspect') {
        $owner='ABSENT'
        if (Test-Path -LiteralPath $marker -PathType Leaf) {
            $owner=(Get-Content -LiteralPath $marker -Raw -ErrorAction Stop).Trim()
        }
        if ($endpoint.Count -gt 1) { throw 'Multiple JEA endpoints found' }
        if ($endpoint.Count -eq 1 -and $owner -cne 'WSLPE45:30:jea_role_capability_misconfig') {
            throw 'JEA present without exact module ownership marker'
        }
        Write-Output ('WSLPE45_JEA_ENDPOINT_COUNT='+$endpoint.Count)
        Write-Output ('WSLPE45_JEA_OWNER='+$owner)
        Write-Output 'WSLPE45_JEA_LOCAL_INSPECTION=PASS'
        return
    }
    if ($Action -eq 'Apply') {
        if ($endpoint.Count -ne 0 -or (Test-Path -LiteralPath $root) -or
            (Test-Path -LiteralPath (Split-Path -Path $marker -Parent))) {
            throw 'JEA already present or partial state; do not reapply'
        }
    } elseif ($Action -eq 'Reset') {
        if ($endpoint.Count -ne 1 -or
            -not (Test-Path -LiteralPath $marker -PathType Leaf) -or
            (Get-Content -LiteralPath $marker -Raw -ErrorAction Stop).Trim() -cne
                'WSLPE45:30:jea_role_capability_misconfig') {
            throw 'JEA ownership or registration does not match; refusing reset'
        }
        $null=Assert-Wslpe45OwnedFixture -Number 30 -Id 'jea_role_capability_misconfig'
    }
    $stage=if ($Action -eq 'Apply') {'apply'} else {'reset'}
    $errorDuringOperation=$null
    $errorDuringRecovery=$null
    try {
        Import-Module 'C:\ProgramData\KingdomsWSLPE45\lib\WslpeJea.psm1' -Force -ErrorAction Stop
        $output=@(Invoke-Wslpe45Jea -Action $stage -Stage $stage)
        $expected='WSLPE45_BATCH_STAGE=jea_role_capability_misconfig:'+$stage+':PASS'
        if (@($output | Where-Object {$_ -ceq $expected}).Count -ne 1) {
            throw 'JEA lifecycle did not emit expected owned completion marker'
        }
    } catch {
        $errorDuringOperation=$_
    } finally {
        try { Restore-Wslpe45WinrmAfterLocalJea }
        catch { $errorDuringRecovery=$_ }
    }
    if ($errorDuringRecovery) {
        throw ('WinRM local recovery failed: '+$errorDuringRecovery.Exception.Message)
    }
    if ($errorDuringOperation) {
        throw ('JEA lifecycle failed or is partial: '+$errorDuringOperation.Exception.Message)
    }
    Write-Output ('WSLPE45_JEA_LOCAL_'+$Action.ToUpperInvariant()+'=PASS')
    Write-Output 'WSLPE45_JEA_HTTPS_REMOTE_PROOF=PENDING'
}
Export-ModuleMember -Function Invoke-Wslpe45JeaLocal
