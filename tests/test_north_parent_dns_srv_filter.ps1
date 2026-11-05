# Offline, read-only regression for NORTH root-PDC DNS SRV answer selection.
# Avoids DNS/network calls, AD configuration, secrets, or guest changes.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$health = Join-Path $PSScriptRoot '..\ansible\files\north-parent-dc-health.ps1'
$tokens = $null
$parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile(
    $health, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -ne 0) {
    throw ('Root-PDC health script has {0} parsing errors' -f $parseErrors.Count)
}
$found = @($ast.FindAll({
    param($node)
    $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Get-NorthParentLdapSrvMatches'
}, $true))
if ($found.Count -ne 1) { throw 'Expected exactly one SRV record selector' }
. ([scriptblock]::Create($found[0].Extent.Text))

# A normal DNS reply may contain answer and additional-section records.
# The original script raised InvalidOperation on .NameTarget.TrimEnd() when
# processing A/AAAA records that do not have NameTarget.
$records = @(
    [pscustomobject]@{Type='A'; IPAddress='10.4.20.10'},
    [pscustomobject]@{Type='AAAA'; IPAddress='fe80::1'},
    [pscustomobject]@{Type='SRV'; NameTarget=$null},
    [pscustomobject]@{Type='SRV'; NameTarget='other.sevenkingdoms.local.'},
    [pscustomobject]@{Type='SRV'; NameTarget='KINGSLANDING.sevenkingdoms.local.'}
)
$selected = @(Get-NorthParentLdapSrvMatches -Answers $records)
if ($selected.Count -ne 1 -or
    $selected[0].NameTarget -cne 'KINGSLANDING.sevenkingdoms.local.') {
    throw 'Expected one exact case-insensitive root PDC SRV target'
}
$missing = @(Get-NorthParentLdapSrvMatches -Answers @(
    [pscustomobject]@{Type='A'; IPAddress='10.4.20.10'},
    [pscustomobject]@{Type='SRV'; NameTarget='other.sevenkingdoms.local'}
))
if ($missing.Count -ne 0) {
    throw 'Foreign SRV or unrelated records must not satisfy PDC health'
}
$empty = @(Get-NorthParentLdapSrvMatches -Answers @())
if ($empty.Count -ne 0) {
    throw 'Empty DNS answers must not satisfy PDC health'
}

Write-Output 'NORTH_PARENT_DNS_SRV_FILTER=PASS mixed=1 missing=1 empty=1'
