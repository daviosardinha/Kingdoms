# Offline PS5.1 regression tests: execute only the pure decision function.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$tokens=$null; $errors=$null
$path=Join-Path $env:RUNNER_TEMP 'wslpe21-ps\deploy21-preflight1.ps1'
$ast=[System.Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors)
if(@($errors).Count) { throw 'Preflight syntax errors' }
$functions=@($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -eq 'Assert-Wslpe21RpcObservation'
},$true))
if($functions.Count -ne 1) { throw 'Expected one pure RPC decision function' }
. ([scriptblock]::Create($functions[0].Extent.Text))
$expected='C:\ProgramData\KingdomsWSLPE45\lib\Kingdom40LocalRpcServer.exe'
$admin='S-1-5-21-111-222-333-500'
function New-Observation {
    return @{Count=1;ImagePath=$expected;CommandLine=('"'+$expected+'" --serve-local-only');
        OwnerSid=$admin;OwnedFixture=$true;NetworkEndpointCount=0}
}
function Assert-Accepted {
    param([hashtable]$Record,[string]$ExpectedState)
    $state=Assert-Wslpe21RpcObservation -Observation $Record -AllowedOwnerSids @('S-1-5-18',$admin)
    if($state -cne $ExpectedState) { throw "Wrong coexistence decision: $state" }
}
function Assert-Rejected {
    param([hashtable]$Record,[string]$Reason)
    $caught=$null
    try { $null=Assert-Wslpe21RpcObservation -Observation $Record -AllowedOwnerSids @('S-1-5-18',$admin) }
    catch { $caught=$_.Exception.Message }
    if(-not $caught -or $caught -notlike "*$Reason*") { throw "Expected rejection: $Reason; observed: $caught" }
}
Assert-Accepted @{Count=0} 'ABSENT'
Assert-Accepted (New-Observation) 'OWNED_LOCAL_HOST'
$record=New-Observation; $record.CommandLine=$expected+' --serve-local-only'
Assert-Accepted $record 'OWNED_LOCAL_HOST'
$record=New-Observation; $record.OwnerSid='S-1-5-18'
Assert-Accepted $record 'OWNED_LOCAL_HOST'
$record=New-Observation; $record.Count=2
Assert-Rejected $record 'Ambiguous'
$record=New-Observation; $record.ImagePath='C:\Temp\Kingdom40LocalRpcServer.exe'
Assert-Rejected $record 'image path'
$record=New-Observation; $record.CommandLine+=' --extra'
Assert-Rejected $record 'arguments'
$record=New-Observation; $record.CommandLine=$null
Assert-Rejected $record 'arguments'
$record=New-Observation; $record.OwnerSid='S-1-5-21-111-222-333-1001'
Assert-Rejected $record 'owner'
$record=New-Observation; $record.OwnerSid=$null
Assert-Rejected $record 'owner'
$record=New-Observation; $record.OwnedFixture=$false
Assert-Rejected $record 'owned fixture'
$record=New-Observation; $record.NetworkEndpointCount=1
Assert-Rejected $record 'network endpoints'
$record=New-Observation; $record.NetworkEndpointCount=$null
Assert-Rejected $record 'network endpoints'
Write-Output '[PASS] 13 RPC coexistence decisions in native PS5.1; no guest access'
