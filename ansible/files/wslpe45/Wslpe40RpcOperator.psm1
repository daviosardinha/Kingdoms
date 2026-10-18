# WSLPE #40: isolated native RPC fixture lifecycle.
# Source-only. Import does nothing. No guest or batch execution.
Set-StrictMode -Version Latest

function Invoke-Wslpe40RpcOperator {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [ValidateSet('Inspect','Prepare','Reset')][string]$Action,
        [ValidateSet('BeforeProof','AfterProof')][string]$Stage='BeforeProof',
        [ValidateRange(1,999999)][uint32]$ExpectedNonce=1,
        [string]$Approval
    )
    $ErrorActionPreference='Stop'
    $lib='C:\ProgramData\KingdomsWSLPE45\lib'
    if(-not [string]::Equals(
        [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\'),
        $lib,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'RPC operator must originate from the exact WSLPE protected library'
    }
    foreach($path in @('C:\ProgramData\KingdomsWSLPE45',$lib)) {
        $item=Get-Item -LiteralPath $path -Force -ErrorAction Stop
        if(-not $item.PSIsContainer -or
           (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw 'Unexpected WSLPE library directory or linked ancestor'
        }
        $acl=Get-Acl -LiteralPath $path -ErrorAction Stop
        if(-not $acl.AreAccessRulesProtected) {
            throw 'RPC source path must have protected access rules'
        }
    }
    $fixtureLibrary=Join-Path $lib 'WslpeFixture.psm1'
    $moduleFile=Get-Item -LiteralPath $fixtureLibrary -Force -ErrorAction Stop
    if($moduleFile.PSIsContainer -or
       (($moduleFile.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
        throw 'RPC operator refuses linked fixture library'
    }
    Import-Module $fixtureLibrary -Force -ErrorAction Stop
    $null=Assert-Wslpe45Identity
    $id='custom_rpc_authorization'
    $root='C:\ProgramData\KingdomsWSLPE45\fixtures\custom_rpc_authorization'
    $proof=Join-Path $root 'rpc-proof.txt'

    if($Action -ne 'Inspect') {
        $principal=[Security.Principal.WindowsPrincipal]::new(
            [Security.Principal.WindowsIdentity]::GetCurrent())
        if(-not $principal.IsInRole(
            [Security.Principal.WindowsBuiltInRole]::Administrator)) {
            throw 'RPC fixture mutation requires elevated local administrator'
        }
        if($env:SESSIONNAME -cne 'Console') {
            throw 'RPC fixture mutation requires the local guest console'
        }
        $phrase=if($Action -eq 'Prepare') {'PREPARE WSLPE40'} else {'RESET WSLPE40'}
        if($Approval -cne $phrase) {
            throw 'RPC fixture requires exact operator approval'
        }
    }
    if($Action -eq 'Prepare') {
        $fixtures=Split-Path -Path $root -Parent
        if(-not (Test-Path -LiteralPath $fixtures -PathType Container)) {
            throw 'Missing protected WSLPE fixtures parent'
        }
        if(@(Get-ChildItem -LiteralPath $fixtures -Force -ErrorAction Stop |
            Where-Object {$_.Name -ceq $id}).Count -ne 0) {
            throw 'Refuse existing RPC fixture or linked entry'
        }
        $null=New-Wslpe45OwnedFixture -Number 40 -Id $id
        Write-Output 'WSLPE40_RPC_PREPARED=PASS'
        return
    }

    $null=Assert-Wslpe45OwnedFixture -Number 40 -Id $id
    Assert-Wslpe45NoReparsePoints -Path $root
    $allowed=@('.kingdoms-owned.json','rpc-proof.txt')
    $entries=@(Get-ChildItem -LiteralPath $root -Force -ErrorAction Stop)
    foreach($entry in $entries) {
        if($entry.PSIsContainer -or $entry.Name -cnotin $allowed -or
           (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw 'Unexpected object in bounded RPC fixture'
        }
    }
    if($Action -eq 'Inspect') {
        $matches=@($entries | Where-Object {$_.Name -ceq 'rpc-proof.txt'})
        if($Stage -eq 'BeforeProof' -and $matches.Count -ne 0) {
            throw 'RPC proof must not exist before learner action'
        }
        if($Stage -eq 'AfterProof') {
            if($matches.Count -ne 1) {
                throw 'Expected one RPC proof after learner action'
            }
            $observed=Get-Content -LiteralPath $proof -Raw -ErrorAction Stop
            $expected=('WSLPE40_LOCAL_RPC_NONCE={0}' -f $ExpectedNonce) +
                [char]13 + [char]10
            if($observed -cne $expected) {
                throw 'RPC proof content did not match expected learner nonce'
            }
        }
        Write-Output ('WSLPE40_RPC_INSPECT_{0}=PASS' -f $Stage)
        return
    }
    # Never terminate an arbitrary PID. The host must have stopped itself.
    $running=@(Get-CimInstance Win32_Process -Filter
        "Name = 'Kingdom40LocalRpcServer.exe'" -ErrorAction Stop)
    if($running.Count -ne 0) {
        throw 'Refuse RPC reset while native host process exists'
    }
    Remove-Wslpe45OwnedFixture -Number 40 -Id $id
    Write-Output 'WSLPE40_RPC_RESET=PASS'
}

Export-ModuleMember -Function 'Invoke-Wslpe40RpcOperator'
