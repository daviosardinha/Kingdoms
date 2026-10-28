# Real Windows WinRS acceptance on a disposable GitHub-hosted runner only.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or
    $env:KINGDOMS_TEST_NORTH_WINRS -ne '1' -or
    $env:COMPUTERNAME -in @('KINGSLANDING','WINTERFELL','CASTELBLACK','WS01','WSLPE-WS01')) {
    throw 'Only the explicitly enabled disposable Windows CI runner is permitted'
}
. "$PSScriptRoot\..\ansible\files\north-parent-winrs.ps1"
$checks = 0
function Check($Condition, $Message) {
    if (-not $Condition) { throw $Message }
    $script:checks++
}
$name = 'northci-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$secret = ConvertTo-SecureString ('Ci!42-' + [guid]::NewGuid().ToString('N')) -AsPlainText -Force
$credential = [PSCredential]::new($env:COMPUTERNAME + '\' + $name, $secret)
$policy = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'
$old = (Get-ItemProperty $policy).PSObject.Properties['LocalAccountTokenFilterPolicy']
$wasRunning = (Get-Service WinRM).Status -eq 'Running'
$listenerCreated = $false
$listenerRebound = $false
$originalThumbprint = $null
$originalHostname = $null
$cert = $null
$userCreated = $false
try {
    Start-Service WinRM
    $listeners = @(Get-ChildItem WSMan:\localhost\Listener | Where-Object {
        $_.Keys -contains 'Transport=HTTPS'
    })
    if ($listeners.Count -gt 1) { throw 'Ambiguous CI HTTPS listeners' }
    if ($listeners.Count -eq 1 -and
        (Get-Item ($listeners[0].PSPath + '\Port')).Value -ne '5986') {
        throw 'Existing CI HTTPS listener does not use 5986'
    }

    # The disposable hosted runner can ship a pre-existing EXPIRED localhost
    # certificate. Do not bypass expiration checks or touch production VMs.
    # Install a temporary currently-valid HTTPS listener certificate, and
    # restore the previous listener in the finally block.
    $cert = New-SelfSignedCertificate -DnsName 'localhost' `
        -CertStoreLocation Cert:\LocalMachine\My `
        -NotAfter ((Get-Date).AddDays(2))
    $selector = @{Address='*';Transport='HTTPS'}
    $newValues = @{Hostname='localhost';CertificateThumbprint=$cert.Thumbprint}
    if ($listeners.Count -eq 0) {
        $null = New-WSManInstance winrm/config/Listener `
            -SelectorSet $selector -ValueSet $newValues -ErrorAction Stop
        $listenerCreated = $true
    } else {
        $oldPath = $listeners[0].PSPath
        $originalThumbprint = [string](Get-Item ($oldPath + '\CertificateThumbprint')).Value
        $originalHostname = [string](Get-Item ($oldPath + '\Hostname')).Value
        $null = Set-WSManInstance winrm/config/Listener `
            -SelectorSet $selector -ValueSet $newValues -ErrorAction Stop
        $listenerRebound = $true
    }
    Restart-Service WinRM -Force -ErrorAction Stop
    $active = @(Get-ChildItem WSMan:\localhost\Listener | Where-Object {
        $_.Keys -contains 'Transport=HTTPS'
    })
    if ($active.Count -ne 1 -or
        (Get-Item ($active[0].PSPath + '\CertificateThumbprint')).Value -ne $cert.Thumbprint) {
        throw 'Disposable CI HTTPS listener failed to select fresh certificate'
    }
    Write-Output 'NORTH_CI_WINRS_TEMPORARY_TLS=PASS'
    $null = New-LocalUser -Name $name -Password $secret
    $userCreated = $true
    Add-LocalGroupMember -Group (Get-LocalGroup -SID S-1-5-32-544).Name -Member $name
    $null = New-ItemProperty $policy LocalAccountTokenFilterPolicy -PropertyType DWord -Value 1 -Force
    # No PSRP configuration or endpoint permissions are created or modified.
    function New-PSSession { throw 'PSRP is not the native provisioning transport' }
    Write-Output 'NORTH_CI_WINRS_STAGE=authenticated_create_shell'
    $marker = 'NORTH_CI_' + [guid]::NewGuid().ToString('N')
    $out = Invoke-NorthParentWinRS $credential "Write-Output '$marker'" 'https://localhost:5986/wsman'
    Check ($out.ExitCode -eq 0 -and $out.Stdout.Trim() -ceq $marker) 'Real WinRS command/output failed'
    $bad = [PSCredential]::new($credential.UserName, (ConvertTo-SecureString 'wrong-password' -AsPlainText -Force))
    $rejected = $false
    try { Invoke-NorthParentWinRS $bad "Write-Output '$marker'" 'https://localhost:5986/wsman' }
    catch { $rejected = $_.Exception.Message -like '*create shell failed*' }
    Check $rejected 'Invalid credentials must fail without a fallback'
    $out = Invoke-NorthParentWinRS $credential "throw 'fixture health failure'" 'https://localhost:5986/wsman'
    Check ($out.ExitCode -ne 0) 'Guest script failure was accepted'
    $script = Get-Content "$PSScriptRoot\..\ansible\files\north-parent-dc-health.ps1" -Raw
    $out = Invoke-NorthParentWinRS $credential $script 'https://localhost:5986/wsman'
    Check ($out.ExitCode -ne 0) 'Actual parent health proof must reject the CI host identity'
    foreach ($user in @('vagrant','SEVENKINGDOMS\vagrant','administrator@sevenkingdoms.local')) {
        $qualified = Get-NorthParentCredential ([PSCredential]::new($user, $secret))
        Check ($qualified.UserName -match '(?i)sevenkingdoms') 'Root credential qualification lost'
    }
    foreach ($user in @('NORTH\vagrant','vagrant@north.sevenkingdoms.local','.\vagrant')) {
        $rejected = $false
        try { Get-NorthParentCredential ([PSCredential]::new($user, $secret)) }
        catch { $rejected = $true }
        Check $rejected 'Foreign or ambiguous credential accepted'
    }
    Write-Output "NORTH_PARENT_WINRS_WINDOWS_TESTS=$checks PASS"
} finally {
    if ($listenerCreated) {
        Remove-WSManInstance winrm/config/Listener -SelectorSet @{Address='*';Transport='HTTPS'}
    }
    if ($listenerRebound) {
        # Do not make another real WinRS request while restoring the fixture.
        # This is safe only because the runner is disposable and gated above.
        $null = Set-WSManInstance winrm/config/Listener `
            -SelectorSet @{Address='*';Transport='HTTPS'} `
            -ValueSet @{Hostname=$originalHostname;CertificateThumbprint=$originalThumbprint}
    }
    if ($cert) { Remove-Item -LiteralPath $cert.PSPath }
    if ($userCreated) { Remove-LocalUser -Name $name }
    if ($old) { Set-ItemProperty $policy LocalAccountTokenFilterPolicy $old.Value }
    else { Remove-ItemProperty $policy LocalAccountTokenFilterPolicy -ErrorAction SilentlyContinue }
    if (-not $wasRunning) { Stop-Service WinRM }
}
