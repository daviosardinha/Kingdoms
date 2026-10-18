# WSLPE #25: explicit, standalone-only MSI fixture preparation.
# SOURCE ONLY. Import has no filesystem side effects.
# This module never invokes Windows Installer, creates a privilege boundary,
# invokes repair, uninstalls a package, or resets unrelated resources.
Set-StrictMode -Version Latest

function Assert-Wslpe25ProtectedParent {
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)][string]$Path)

    $item=Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if(-not $item.PSIsContainer -or
       (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
        throw "WSLPE25 refuses non-directory/reparse parent: $Path"
    }

    $acl=Get-Acl -LiteralPath $Path -ErrorAction Stop
    if(-not $acl.AreAccessRulesProtected) {
        throw "WSLPE25 requires a protected fixture parent ACL: $Path"
    }

    $ownerSid=$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    $adminGroup=Get-LocalGroup -SID 'S-1-5-32-544' -ErrorAction Stop
    $memberSids=@(Get-LocalGroupMember -Group $adminGroup.Name -ErrorAction Stop |
        ForEach-Object {$_.SID.Value})
    if($ownerSid -notin @('S-1-5-18','S-1-5-32-544') -and
       $ownerSid -notin $memberSids) {
        throw "WSLPE25 refuses non-administrator parent owner: $Path"
    }

    $writeMask=(
        [int][Security.AccessControl.FileSystemRights]::Write -bor
        [int][Security.AccessControl.FileSystemRights]::Delete -bor
        [int][Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor
        [int][Security.AccessControl.FileSystemRights]::ChangePermissions -bor
        [int][Security.AccessControl.FileSystemRights]::TakeOwnership
    )
    foreach($entry in $acl.GetAccessRules(
        $true,$true,[Security.Principal.SecurityIdentifier])) {
        if($entry.AccessControlType -ne
           [Security.AccessControl.AccessControlType]::Allow) {continue}
        $sid=$entry.IdentityReference.Value
        if($sid -in @('S-1-5-18','S-1-5-32-544') -or
           $sid -in $memberSids) {continue}
        if(([int]$entry.FileSystemRights -band $writeMask) -ne 0) {
            throw "WSLPE25 refuses writable parent ACE ($sid): $Path"
        }
    }
}

function Invoke-Wslpe25FixturePreparation {
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)]
          [ValidateSet('Inspect','Prepare')]
          [string]$Action)

    $ErrorActionPreference='Stop'
    $fixtureLibrary=Join-Path $PSScriptRoot 'WslpeFixture.psm1'
    $inspector=Join-Path $PSScriptRoot 'Wslpe25RepairInspection.psm1'
    foreach($source in @($fixtureLibrary,$inspector)) {
        if(-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "WSLPE25 required local source is absent: $source"
        }
        $sourceItem=Get-Item -LiteralPath $source -Force -ErrorAction Stop
        if(($sourceItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'WSLPE25 refuses reparse-point module source'
        }
    }
    Import-Module -Name $fixtureLibrary -Force -ErrorAction Stop
    Import-Module -Name $inspector -Force -ErrorAction Stop
    $null=Assert-Wslpe45Identity

    if($Action -eq 'Inspect') {
        Assert-Wslpe25RepairFixture -Stage BeforeRepair
        return
    }

    $principal=[Security.Principal.WindowsPrincipal]::new(
        [Security.Principal.WindowsIdentity]::GetCurrent())
    if(-not $principal.IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'WSLPE25 preparation requires an elevated local administrator'
    }

    $root='C:\ProgramData\KingdomsWSLPE45'
    $fixtures=Join-Path $root 'fixtures'
    $id='msi_repair_custom_action'
    $target=Get-Wslpe45FixturePath -Id $id

    # Parent creation is deliberately out of scope. It must have been
    # performed and locked down by the already reviewed WSLPE bootstrap.
    foreach($parent in @($root,$fixtures)) {
        Assert-Wslpe25ProtectedParent -Path $parent
    }
    Assert-Wslpe45NoReparsePoints -Path $target

    # Enumerate the entry, not only its target. A dangling symlink or
    # preexisting foreign fixture must never be adopted.
    $existing=@(Get-ChildItem -LiteralPath $fixtures -Force -ErrorAction Stop |
        Where-Object {$_.Name -ceq $id})
    if($existing.Count -ne 0) {
        throw 'WSLPE25 refuses to adopt an existing fixture entry'
    }

    # Shared helper is authoritative for identity, creation and marker.
    # If a subsequent verification fails, preserve evidence and stop;
    # never delete an object whose ownership is in doubt.
    $null=New-Wslpe45OwnedFixture -Number 25 -Id $id
    Assert-Wslpe25RepairFixture -Stage BeforeRepair
    Write-Output 'WSLPE25_FIXTURE_PREPARED=PASS'
}

Export-ModuleMember -Function 'Invoke-Wslpe25FixturePreparation'
