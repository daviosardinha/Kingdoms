# Offline regression for Microsoft WSMan Session.Create EPR shell selectors.
# Uses only in-memory XML; no WinRM, accounts, certificates, or VM changes.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. "$PSScriptRoot\..\ansible\files\north-parent-winrs.ps1"

$guid = 'uuid:C443F44F-28E4-486F-A5A1-12745F90CF5A'
function New-ResponseXml([string]$name, [string]$value) {
    $xml = @"
<wst:ResourceCreated xmlns:wst="http://schemas.xmlsoap.org/ws/2004/09/transfer" xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:wsman="http://schemas.dmtf.org/wbem/wsman/1/wsman.xsd">
  <wsa:Address>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</wsa:Address>
  <wsa:ReferenceParameters>
    <wsman:ResourceURI>http://schemas.microsoft.com/wbem/wsman/1/windows/shell/cmd</wsman:ResourceURI>
    <wsman:SelectorSet><wsman:Selector Name="$name">$value</wsman:Selector></wsman:SelectorSet>
  </wsa:ReferenceParameters>
</wst:ResourceCreated>
"@
    return [xml]$xml
}
$checks = 0
foreach ($case in @('ShellId', 'ShellID', 'shellid')) {
    $response = New-ResponseXml $case $guid
    $observed = Get-NorthParentWinRSShellGuid $response
    if ($observed -cne $guid) {
        throw "WinRS EPR selector $case did not return the expected GUID"
    }
    $checks++
}
foreach ($invalid in @(
    (New-ResponseXml 'OtherSelector' $guid),
    (New-ResponseXml 'ShellId' 'not-a-valid-guid')
)) {
    $rejected = $false
    try { $null = Get-NorthParentWinRSShellGuid $invalid }
    catch { $rejected = $true }
    if (-not $rejected) { throw 'Invalid WinRS EPR selector was accepted' }
    $checks++
}
# Parent health proof must remain fail-closed on a nonzero remote exit or
# a forged/prefixed marker, while accepting the observed CLIXML progress prefix.
$marker = 'NORTH_PARENT_DC_AD_HEALTH=PASS host=KINGSLANDING'
$clixml = '<Objs Version="1.1.0.1"><Obj S="progress" /></Objs>'
$cases = @(
    @{ ExitCode = 0; Stdout = $marker; Accepted = $true; Count = 1 },
    @{ ExitCode = 0; Stdout = $clixml + $marker; Accepted = $true; Count = 1 },
    @{ ExitCode = 1; Stdout = $clixml + $marker; Accepted = $false; Count = 1 },
    @{ ExitCode = 0; Stdout = 'UNEXPECTED' + $marker; Accepted = $false; Count = 0 },
    @{ ExitCode = 0; Stdout = ''; Accepted = $false; Count = 0 },
    @{ ExitCode = 0; Stdout = $marker + "`n" + $marker; Accepted = $false; Count = 2 }
)
foreach ($case in $cases) {
    $result = [pscustomobject]@{
        ExitCode = $case.ExitCode
        Stdout = $case.Stdout
        StderrBytes = 0
    }
    $observed = Get-NorthParentHealthProofStatus $result
    if ($observed.Accepted -ne $case.Accepted -or
        $observed.MarkerCount -ne $case.Count -or
        $observed.ExitCode -ne $case.ExitCode) {
        throw 'WinRS parent proof accepted unexpected marker or failed expected CLIXML case'
    }
    $checks++
}
# The earlier implementation incorrectly required an XML <ShellId> element.
# This fixture contains only the documented wsman:Selector Name=ShellId.
if ($checks -ne 11) { throw "Expected eleven offline WinRS parser/proof cases, got $checks" }
Write-Output "NORTH_PARENT_WINRS_EPR_TESTS=$checks PASS"
