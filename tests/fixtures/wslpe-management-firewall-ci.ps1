# Executed over real WinRM only by the disposable hosted CI fixture account.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:USERNAME -cnotmatch '^wslpeci-[a-f0-9]{8}$' -or $env:COMPUTERNAME -eq 'WSLPE-WS01') {
    throw 'Expected disposable CI account'
}
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseInput(
    [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__SOURCE__')), [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Production script parse failed' }
foreach ($definition in $ast.FindAll({ param($node)
    $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -in @('Rule-Specs','Normalize-Values','Assert-Rule','Ensure-Rule')
}, $false)) { Invoke-Expression $definition.Extent.Text }
$Prefix = 'WSLPE-CI-' + [guid]::NewGuid().ToString('N') + '-'
$Group = $Prefix + 'firewall-test'
$nic = @(Get-NetAdapter | Where-Object { [string]$_.Status -eq 'Up' })[0]
$nics = @{'000C292FD75B'=$nic; '000C292FD765'=$nic; '000C292FD76F'=$nic}
$specs = Rule-Specs $nics
# CI does not have the lab's three NICs. Bind the fixture to its existing NIC,
# preserving all production addresses, ports, actions and profiles.
foreach ($spec in $specs) { $spec.InterfaceAlias = @($spec.InterfaceAlias | Select-Object -Unique) }
function New-FixtureRule($Spec, [string]$Suffix) {
    $params = @{}
    foreach ($key in $Spec.Keys) { if ($key -ne 'Suffix') { $params[$key] = $Spec[$key] } }
    New-NetFirewallRule @params -Name ($Prefix + $Suffix) -DisplayName ($Prefix + $Suffix) `
        -Group $Group -Enabled False -Direction Inbound -Protocol TCP -Profile Any -PolicyStore PersistentStore
}
try {
    # Reproduce the live failure with each old mixed IPv4/IPv6 address filter.
    foreach ($index in @(3,4)) {
        $old = $specs[$index].Clone()
        $key = if ($index -eq 3) { 'RemoteAddress' } else { 'LocalAddress' }
        $old[$key] = @($old[$key] | Where-Object { $_ -notin @('::/1','8000::/1') }) + @('::/0')
        $rejected = $false
        try { $null = New-FixtureRule $old ('Old-' + $index) }
        catch {
            if ($_.Exception.Message -notmatch 'address prefixes is invalid') { throw }
            $rejected = $true
        }
        if (-not $rejected) { throw 'Old IPv6 /0 did not reproduce the Windows rejection' }
    }
    Write-Output 'WSLPE_CI_OLD_IPV6_PREFIX=REPRODUCED'

    # Exact production ports and addresses must be accepted and retained by
    # NetSecurity. These rules stay disabled, so CI WinRM is never blocked.
    foreach ($spec in $specs) {
        $rule = New-FixtureRule $spec ('Disabled-' + $spec.Suffix)
        if ([string]$rule.Enabled -ne 'False') { throw 'Parsing fixture must remain disabled' }
        $filter = $rule | Get-NetFirewallAddressFilter
        if ((Normalize-Values $filter.LocalAddress) -cne (Normalize-Values $spec.LocalAddress) -or
            (Normalize-Values $filter.RemoteAddress) -cne (Normalize-Values $spec.RemoteAddress)) {
            throw ('Windows changed the address filter: ' + $spec.Suffix)
        }
    }
    Write-Output ('WSLPE_CI_FIREWALL_SPECS=' + (ConvertTo-Json -InputObject $specs -Depth 4 -Compress))

    # Exercise the actual Ensure/Assert functions, including resume after the
    # first three rules. Only the ports change to a reserved, loopback-only
    # fixture port; never enable blocks on the runner's 5985/5986 transports.
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try {
        $port = [string]$listener.LocalEndpoint.Port
        if ($port -in @('5985','5986')) { throw 'Unexpected fixture port' }
        foreach ($spec in $specs) { $spec.LocalPort = @($port) }
        foreach ($spec in $specs[0..2]) { Ensure-Rule $spec }
        foreach ($spec in $specs) { Ensure-Rule $spec }
        foreach ($spec in $specs) { Ensure-Rule $spec }
        $enabled = @(Get-NetFirewallRule -PolicyStore ActiveStore -Group $Group |
            Where-Object { [string]$_.Enabled -eq 'True' })
        if ($enabled.Count -ne 5) { throw 'Resume did not retain exactly five enabled fixture rules' }
        # Existing altered rules must fail validation instead of being replaced.
        $name = $Prefix + $specs[3].Suffix
        $null = Set-NetFirewallRule -PolicyStore PersistentStore -Name $name -RemoteAddress '192.0.2.1'
        $rejected = $false
        try { Ensure-Rule $specs[3] }
        catch {
            if ($_.Exception.Message -notlike 'Firewall filter mismatch:*') { throw }
            $rejected = $true
        }
        if (-not $rejected) { throw 'Existing altered rule was accepted or overwritten' }
    } finally { $listener.Stop() }
    Write-Output 'WSLPE_CI_FIREWALL_RESUME=PASS'
} finally {
    Get-NetFirewallRule -PolicyStore PersistentStore -Name ($Prefix + '*') -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule
    if (Get-NetFirewallRule -PolicyStore PersistentStore -Name ($Prefix + '*') -ErrorAction SilentlyContinue) {
        throw 'CI firewall cleanup failed'
    }
}
