# Execute the real Prepare body against a saved prior transaction in a temp dir.
# Registry, network and account cmdlets are mocks; files and hashes are real.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$source = Join-Path $PSScriptRoot '..\scripts\wslpe41-operator-management.ps1'
$legacy = Join-Path $PSScriptRoot 'fixtures\wslpe-management-before-public-profile.ps1'
if ((Get-FileHash -LiteralPath $legacy -Algorithm SHA256).Hash.ToLowerInvariant() -cne
    'edd8a6935fb8715c14d482e52b530694c818885767dcd1e4b372dc4b2bb8367b') {
    throw 'Frozen recovery fixture bytes changed; check Git line-ending conversion'
}
$tokens=$null; $errors=$null
$ast = [Management.Automation.Language.Parser]::ParseFile($source, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
foreach ($definition in $ast.FindAll({ param($node)
    $node -is [Management.Automation.Language.FunctionDefinitionAst]
}, $false)) { Invoke-Expression $definition.Extent.Text }
$prepare = @($ast.FindAll({ param($node)
    $node -is [Management.Automation.Language.IfStatementAst] -and
    $node.Clauses[0].Item1.Extent.Text -ceq '$Mode -eq ''Prepare'''
}, $false))[0].Clauses[0].Item2.Extent.Text
$prepare = [scriptblock]::Create($prepare.Substring(1, $prepare.Length - 2))
$folder = Join-Path ([IO.Path]::GetTempPath()) ('wslpe-recovery-' + [guid]::NewGuid().ToString('N'))
$null = [IO.Directory]::CreateDirectory($folder)
$StatePath = Join-Path $folder 'state.clixml'
$ScriptPath = Join-Path $folder 'management.ps1'
$PreviousScriptPath = Join-Path $folder 'management.before-public-profile.ps1'
$PendingScriptPath = Join-Path $folder 'management.pending.ps1'
$Instance='bf5369-wslpe-vmware'; $Prefix='Kingdoms-WSLPE41-bf5369-'
$Policy='mock-uac-policy'; $Nonce='a'*32
$Certificate=[pscustomobject]@{Thumbprint='unchanged-certificate'}
$Nics=@{
    '000C292FD76F'=[pscustomobject]@{Name='Management'}
    '000C292FD75B'=[pscustomobject]@{Name='NAT'}
    '000C292FD765'=[pscustomobject]@{Name='Learner'}
}
$SourceBase64=[Convert]::ToBase64String([IO.File]::ReadAllBytes($source))
$script:checks=0
function Check([bool]$ok, [string]$message) {
    if (-not $ok) { throw $message }; $script:checks++
}
function Protect-Folder {}
function Get-Certificate { return $Certificate }
function Get-LocalUser { [CmdletBinding()]param($Name) return $script:operator }
function Get-NetFirewallRule { [CmdletBinding()]param($Name) return $script:rules }
function Set-Item { throw 'Native WSMan write must never run on Public/unidentified networks' }
function Get-Item {
    param($LiteralPath)
    if ($LiteralPath -like '*\Auth\Negotiate') { return [pscustomobject]@{Value='true'} }
    return [pscustomobject]@{Value=$(if ($script:policyFailure) {'true'} else {'false'})}
}
function Get-ItemProperty {
    param($LiteralPath,$Path)
    if ($Path -eq $Policy) { return [pscustomobject]@{LocalAccountTokenFilterPolicy=0} }
    [pscustomobject]@{AllowBasic=1; UnrelatedPolicy=42}
}
function Test-Path {
    param($LiteralPath, $PathType)
    if ($LiteralPath -like 'HKLM:*') { return $true }
    return Microsoft.PowerShell.Management\Test-Path -LiteralPath $LiteralPath
}
function New-Item { throw 'An existing policy key must not be recreated' }
function New-ItemProperty {
    param($LiteralPath, $Name, $PropertyType, $Value, [switch]$Force)
    $saved=Import-Clixml -LiteralPath $StatePath
    Check ($null -ne $saved.PSObject.Properties['WinRMPolicyBefore']) 'Journal before policy mutation'
    Check ($LiteralPath -eq 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WinRM\Service' -and
        $Name -in @('AllowBasic','AllowUnencryptedTraffic') -and $Value -eq 0 -and
        $PropertyType -eq 'DWord' -and $Force) 'Only secure service policy values may change'
    $script:events += $Name
}
function Set-ItemProperty { param($Path,$Name,$Type,$Value) $script:events += 'token-policy' }
function Ensure-Rule {
    param($Spec)
    Check ($Spec.Suffix -ceq 'HTTPS-Allow' -and $Spec.RemoteAddress[0] -ceq '172.28.233.254') 'Only narrow HTTPS allow during Prepare'
    $script:events += 'HTTPS-Allow'
}
function Reset-Fixture {
    [IO.File]::WriteAllBytes($ScriptPath, [IO.File]::ReadAllBytes($legacy))
    foreach ($path in @($PreviousScriptPath,$PendingScriptPath)) { if ([IO.File]::Exists($path)) { [IO.File]::Delete($path) } }
    $script:state=[pscustomobject]@{
        Instance=$Instance; Certificate=$Certificate.Thumbprint; Phase='prepared'; Nonce=$Nonce
        ConsoleNonce=''; Basic=$true; AllowUnencrypted=$true
        TokenPolicyPresent=$true; TokenPolicy=0
    }
    $script:state | Export-Clixml -LiteralPath $StatePath
    $script:operator=$null; $script:rules=@(); $script:events=@(); $script:policyFailure=$false
}
try {
    Reset-Fixture
    $output=@(& $prepare)
    Check ($output -contains 'WSLPE_OPERATOR_PREPARED=PASS') 'Interrupted Prepare must resume'
    Check ([Convert]::ToBase64String([IO.File]::ReadAllBytes($ScriptPath)) -ceq $SourceBase64) 'Recovery uses corrected source'
    Check ([Convert]::ToBase64String([IO.File]::ReadAllBytes($PreviousScriptPath)) -ceq
        [Convert]::ToBase64String([IO.File]::ReadAllBytes($legacy))) 'Original recovery source preserved byte for byte'
    $saved=Import-Clixml -LiteralPath $StatePath
    Check ($saved.Nonce -ceq $Nonce -and $saved.Certificate -ceq $Certificate.Thumbprint -and
        $saved.TokenPolicy -eq 0 -and $saved.Basic -and $saved.AllowUnencrypted) 'Original recovery facts retained'
    Check ($saved.WinRMPolicyBefore.AllowBasic.Present -and $saved.WinRMPolicyBefore.AllowBasic.Value -eq 1 -and
        -not $saved.WinRMPolicyBefore.AllowUnencryptedTraffic.Present) 'Original policy presence and values journaled'
    Check ($script:events[-1] -ceq 'HTTPS-Allow') 'Narrow allow follows effective security proof'
    $backup=[Convert]::ToBase64String([IO.File]::ReadAllBytes($PreviousScriptPath))
    $null = & $prepare
    Check ([Convert]::ToBase64String([IO.File]::ReadAllBytes($PreviousScriptPath)) -ceq $backup) 'Repeat Prepare retains original backup'

    foreach ($case in @('nonce','source','phase','console','account','rules','backup','pending','certificate')) {
        Reset-Fixture
        switch ($case) {
            nonce { $script:state.Nonce='b'*32 }
            source { [IO.File]::AppendAllText($ScriptPath, '# changed') }
            phase { $script:state.Phase='hardened' }
            console { $script:state.ConsoleNonce=$Nonce }
            account { $script:operator=[pscustomobject]@{Name='kingdom.operator'} }
            rules { $script:rules=@([pscustomobject]@{Name='existing'}) }
            backup { [IO.File]::WriteAllText($PreviousScriptPath, 'existing') }
            pending { [IO.File]::WriteAllText($PendingScriptPath, 'different') }
            certificate { $script:state.Certificate='changed' }
        }
        $script:state | Export-Clixml -LiteralPath $StatePath
        $before=[Convert]::ToBase64String([IO.File]::ReadAllBytes($ScriptPath))
        $failed=$false
        try { $null = & $prepare } catch { $failed=$true }
        Check $failed ('Unsafe resume must fail: ' + $case)
        Check ($script:events.Count -eq 0 -and
            [Convert]::ToBase64String([IO.File]::ReadAllBytes($ScriptPath)) -ceq $before) ('No mutation on mismatch: ' + $case)
    }
    Reset-Fixture
    [IO.File]::WriteAllBytes($PendingScriptPath, [Convert]::FromBase64String($SourceBase64))
    $null = & $prepare
    Check ([IO.File]::Exists($PreviousScriptPath)) 'Interrupted staging resumes with original backup'
    Reset-Fixture
    $script:policyFailure=$true
    $failed=$false
    try { $null = & $prepare } catch { $failed=$_.Exception.Message -like 'WinRM secure policy is not effective:*' }
    Check $failed 'Ineffective policy must fail'
    Check ($script:events -notcontains 'HTTPS-Allow') 'Ineffective policy must not open management firewall'
    Reset-Fixture
    [IO.File]::Delete($StatePath)
    [IO.File]::Delete($ScriptPath)
    $output=@(& $prepare)
    Check ($output -contains 'WSLPE_OPERATOR_PREPARED=PASS' -and
        -not [IO.File]::Exists($PreviousScriptPath)) 'Fresh Prepare installs current recovery without a migration'
    Write-Output "WSLPE_OPERATOR_RECOVERY_TESTS=$script:checks PASS (mock Windows; real recovery files)"
} finally { [IO.Directory]::Delete($folder, $true) }
