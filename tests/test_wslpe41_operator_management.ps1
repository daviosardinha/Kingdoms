# Executable PowerShell source/behavior tests. Windows cmdlets are mocks here.
$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot '..\scripts\wslpe41-operator-management.ps1'
$tokens = $null
$parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($source, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
foreach ($definition in $ast.FindAll({ param($node)
    $node -is [Management.Automation.Language.FunctionDefinitionAst]
}, $false)) { Invoke-Expression $definition.Extent.Text }
$Prefix = 'Kingdoms-WSLPE41-bf5369-'
$Group = 'Kingdoms WSLPE41 operator bf5369'
$script:checks = 0
function Check([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
    $script:checks++
}
function Get-Item { param($LiteralPath) [pscustomobject]@{Value=$script:wsValue} }
$script:wsValue = 'false'
Check (-not (Get-WSBool 'mock')) 'WSMan string false must not become true'
$script:wsValue = 'true'
Check (Get-WSBool 'mock') 'WSMan string true'
$nics = @{
    '000C292FD75B'=[pscustomobject]@{Name='NAT'}
    '000C292FD765'=[pscustomobject]@{Name='Learner'}
    '000C292FD76F'=[pscustomobject]@{Name='Management'}
}
$specs = Rule-Specs $nics
Check ($specs.Count -eq 5) 'Five bounded management rules'
Check ($specs[0].RemoteAddress[0] -eq '172.28.233.254') 'Sole allowed operator source'
Check ($specs[1].LocalPort[0] -eq '5985' -and $specs[1].InterfaceAlias[0] -eq 'Any') 'HTTP blocked on every NIC'
Check ((Normalize-Values $specs[2].InterfaceAlias) -eq 'Learner,NAT') 'HTTPS blocked on NAT and learner'
Check ($specs[3].RemoteAddress -contains '::/0') 'No IPv6 source bypass'
Check ($specs[4].LocalAddress -contains '::/0') 'No IPv6 destination bypass'

function Get-NetFirewallRule {
    param($PolicyStore, $Name)
    [pscustomobject]@{Enabled='True'; Direction='Inbound'; Action=$script:spec.Action;
        Profile='Any'; Group=$Group}
}
function Get-NetFirewallPortFilter {
    param([Parameter(ValueFromPipeline)]$InputObject)
    [pscustomobject]@{Protocol='TCP'; LocalPort=$script:spec.LocalPort; RemotePort=$script:remotePort}
}
function Get-NetFirewallAddressFilter {
    param([Parameter(ValueFromPipeline)]$InputObject)
    [pscustomobject]@{LocalAddress=$script:spec.LocalAddress; RemoteAddress=$script:remoteAddress}
}
function Get-NetFirewallInterfaceFilter {
    param([Parameter(ValueFromPipeline)]$InputObject)
    [pscustomobject]@{InterfaceAlias=$script:spec.InterfaceAlias}
}
function Get-NetFirewallApplicationFilter {
    param([Parameter(ValueFromPipeline)]$InputObject)
    [pscustomobject]@{Program=$script:program}
}
function Get-NetFirewallServiceFilter {
    param([Parameter(ValueFromPipeline)]$InputObject)
    [pscustomobject]@{Service='Any'}
}
foreach ($script:spec in $specs) {
    $script:remotePort='Any'
    $script:program='Any'
    $script:remoteAddress=$script:spec.RemoteAddress
    Assert-Rule $script:spec
    $script:checks++
    foreach ($tamper in @('port','program','source')) {
        $script:remotePort='Any'; $script:program='Any'; $script:remoteAddress=$script:spec.RemoteAddress
        switch ($tamper) {
            port { $script:remotePort='1' }
            program { $script:program='C:\unrelated.exe' }
            source { $script:remoteAddress=@('192.0.2.1') }
        }
        $blocked=$false
        try { Assert-Rule $script:spec } catch { $blocked=$true }
        Check $blocked ('Altered rule must fail: ' + $tamper)
    }
}
Write-Output "WSLPE_OPERATOR_POWERSHELL_SOURCE_TESTS=$script:checks PASS (mock cmdlets; no Windows acceptance)"
