# WSLPE #25: explicit, standalone-only MSI fixture preparation.
# SOURCE ONLY. Import has no filesystem side effects.
# This module never invokes Windows Installer, creates a privilege boundary,
# invokes repair, uninstalls a package, or resets unrelated resources.
Set-StrictMode -Version Latest

function Assert-Wslpe25ProtectedParent {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [switch]$RequireProtectedAcl
    )

    $item=Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if(-not $item.PSIsContainer -or
       (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
        throw "WSLPE25 refuses non-directory/reparse parent: $Path"
    }

    $acl=Get-Acl -LiteralPath $Path -ErrorAction Stop
    if($RequireProtectedAcl -and -not $acl.AreAccessRulesProtected) {
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
          [ValidateSet('Inspect','Prepare','Resume')]
          [string]$Action)

    $ErrorActionPreference='Stop'
    # Trusted library provenance is mandatory before importing executable code.
    $expectedLibrary='C:\ProgramData\KingdomsWSLPE45\lib'
    if(-not [string]::Equals(
        [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\'),
        $expectedLibrary,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'WSLPE25 module must run from the dedicated protected library'
    }
    Assert-Wslpe25ProtectedParent -Path 'C:\ProgramData\KingdomsWSLPE45' -RequireProtectedAcl
    Assert-Wslpe25ProtectedParent -Path $expectedLibrary -RequireProtectedAcl
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
    Assert-Wslpe25ProtectedParent -Path $root -RequireProtectedAcl
    # The fixtures parent may inherit only the protected root's safe ACL.
    Assert-Wslpe25ProtectedParent -Path $fixtures
    Assert-Wslpe45NoReparsePoints -Path $target

    # Enumerate the entry, not only its target. A dangling symlink or
    # preexisting foreign fixture must never be adopted.
    $existing=@(Get-ChildItem -LiteralPath $fixtures -Force -ErrorAction Stop |
        Where-Object {$_.Name -ceq $id})
    if($Action -eq 'Resume') {
        # Only recover our own *incomplete preparation* after the Windows
        # PowerShell 5.1 New-Item -LiteralPath parameter-binding failure.
        # Never adopt arbitrary directories, links, MSI registrations or
        # unexpected content. An ownership marker alone is insufficient
        # unless the inventory is exactly the interrupted create state.
        if($existing.Count -ne 1 -or
           -not $existing[0].PSIsContainer -or
           (($existing[0].Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw 'Resume requires exactly one ordinary existing fixture directory'
        }
        $null=Assert-Wslpe45OwnedFixture -Number 25 -Id $id
        Assert-Wslpe25ProtectedParent -Path $target -RequireProtectedAcl
        $remaining=@(Get-ChildItem -LiteralPath $target -Force -ErrorAction Stop)
        if($remaining.Count -ne 1 -or
           $remaining[0].Name -cne '.kingdoms-owned.json' -or
           $remaining[0].PSIsContainer -or
           (($remaining[0].Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw 'Resume refuses any unexpected or partially prepared fixture entry'
        }
        if(Test-Path -LiteralPath 'C:\Program Files\KingdomsWSLPE25') {
            throw 'Resume refuses already installed MSI payload'
        }
        $owned=$target
    } else {
        if($existing.Count -ne 0) {
            throw 'Prepare refuses an existing fixture; use verified Resume only'
        }
        # Create only a new owned fixture; do not adopt unrecognized state.
        $owned=New-Wslpe45OwnedFixture -Number 25 -Id $id
    }
    # The one intentionally learner-controlled primitive. The directory
    # and proof remain privileged. Learner may edit FILE DATA only, never
    # delete/replace the file, change its DACL, or supply a path.
    $request=Join-Path $owned 'repair-request.txt'
    if(Test-Path -LiteralPath $request){throw 'Refuse preexisting request'}
    $file=New-Item -Path $request -ItemType File -ErrorAction Stop
    Set-Content -LiteralPath $request -Value '1' -Encoding Ascii -NoNewline -ErrorAction Stop
    $learner=[Security.Principal.SecurityIdentifier]::new(
        (Assert-Wslpe45Identity).LearnerSid)
    $acl=Get-Acl -LiteralPath $request -ErrorAction Stop
    $rights=(
        [Security.AccessControl.FileSystemRights]::ReadData -bor
        [Security.AccessControl.FileSystemRights]::WriteData -bor
        [Security.AccessControl.FileSystemRights]::ReadAttributes -bor
        [Security.AccessControl.FileSystemRights]::ReadPermissions
    )
    $ace=[Security.AccessControl.FileSystemAccessRule]::new(
        $learner,$rights,
        [Security.AccessControl.InheritanceFlags]::None,
        [Security.AccessControl.PropagationFlags]::None,
        [Security.AccessControl.AccessControlType]::Allow)
    $acl.AddAccessRule($ace) | Out-Null
    Set-Acl -LiteralPath $request -AclObject $acl -ErrorAction Stop
    Assert-Wslpe25RepairFixture -Stage BeforeRepair
    if($Action -eq 'Resume') {
        Write-Output 'WSLPE25_FIXTURE_RESUMED=PASS'
    } else {
        Write-Output 'WSLPE25_FIXTURE_PREPARED=PASS'
    }
}

Export-ModuleMember -Function 'Invoke-Wslpe25FixturePreparation'
