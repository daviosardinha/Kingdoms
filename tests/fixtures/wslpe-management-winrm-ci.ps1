# Only the disposable GitHub-hosted Windows CI runner may use this fixture.
[CmdletBinding()]
param([ValidateSet('Setup','Cleanup')][string]$Mode, [string]$StatePath)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
    $env:KINGDOMS_TEST_LOOPBACK_WINRM -cne '1' -or $env:COMPUTERNAME -eq 'WSLPE-WS01') {
    throw 'This fixture is restricted to disposable hosted CI'
}
$user = $env:KINGDOMS_CI_WINRM_USER
if ($user -cnotmatch '^wslpeci-[a-f0-9]{8}$') { throw 'Invalid CI fixture account' }
$policy = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'
if ($Mode -eq 'Cleanup') {
    if (-not (Test-Path -LiteralPath $StatePath)) { return }
    $state = Get-Content -Raw -LiteralPath $StatePath | ConvertFrom-Json
    if ($state.User -cne $user) { throw 'CI fixture state mismatch' }
    if (Get-LocalUser -Name $user -ErrorAction SilentlyContinue) { Remove-LocalUser -Name $user }
    if ($state.Listener) { Remove-Item -LiteralPath $state.Listener -Recurse -Force }
    if ($state.TokenPresent) {
        Set-ItemProperty -Path $policy -Name LocalAccountTokenFilterPolicy -Value $state.TokenValue -Type DWord
    } else {
        Remove-ItemProperty -Path $policy -Name LocalAccountTokenFilterPolicy -ErrorAction SilentlyContinue
    }
    if (-not $state.ServiceRunning) { Stop-Service WinRM }
    return
}
if (Get-LocalUser -Name $user -ErrorAction SilentlyContinue) { throw 'CI account already exists' }
$token = (Get-ItemProperty -Path $policy).PSObject.Properties['LocalAccountTokenFilterPolicy']
$state = [pscustomobject]@{
    User=$user; ServiceRunning=((Get-Service WinRM).Status -eq 'Running'); Listener=''
    TokenPresent=($null -ne $token); TokenValue=$(if ($token) { [int]$token.Value } else { 0 })
}
$state | ConvertTo-Json | Set-Content -LiteralPath $StatePath -Encoding UTF8
Start-Service WinRM
$http = @(Get-ChildItem WSMan:\localhost\Listener | Where-Object {
    @($_.Keys) -contains 'Transport=HTTP'
})
if (-not $http.Count) {
    $listener = New-Item -Path WSMan:\localhost\Listener -Transport HTTP -Address 'IP:127.0.0.1' -Port 5985
    $state.Listener = $listener.PSPath
    $state | ConvertTo-Json | Set-Content -LiteralPath $StatePath -Encoding UTF8
}
# NTLM message encryption is required. No firewall rule, Basic or plaintext.
Set-Item WSMan:\localhost\Service\Auth\Basic -Value $false
Set-Item WSMan:\localhost\Service\AllowUnencrypted -Value $false
Set-Item WSMan:\localhost\Service\Auth\Negotiate -Value $true
Set-ItemProperty -Path $policy -Name LocalAccountTokenFilterPolicy -Value 1 -Type DWord
$password = ConvertTo-SecureString $env:KINGDOMS_CI_WINRM_PASSWORD -AsPlainText -Force
$null = New-LocalUser -Name $user -Password $password
Add-LocalGroupMember -Group (Get-LocalGroup -SID 'S-1-5-32-544').Name -Member $user
Write-Output 'WSLPE_CI_WINRM_READY'
