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
# The earlier implementation incorrectly required an XML <ShellId> element.
# This fixture contains only the documented wsman:Selector Name=ShellId.
if ($checks -ne 5) { throw "Expected five EPR parser cases, got $checks" }
Write-Output "NORTH_PARENT_WINRS_EPR_TESTS=$checks PASS"
