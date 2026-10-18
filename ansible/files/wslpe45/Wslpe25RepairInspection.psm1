# WSLPE #25: read-only inspection of the existing, dedicated MSI fixture.
# SOURCE ONLY. Importing this file never changes the guest. This module
# cannot create a fixture, install an MSI, trigger repair, or reset a package.
Set-StrictMode -Version Latest

function Assert-Wslpe25RepairFixture {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [ValidateSet('BeforeRepair','AfterRepair')]
        [string]$Stage
    )

    $ErrorActionPreference='Stop'
    $shared=Join-Path $PSScriptRoot 'WslpeFixture.psm1'
    if(-not (Test-Path -LiteralPath $shared -PathType Leaf)) {
        throw 'Dedicated WSLPE fixture ownership library is missing'
    }
    Import-Module -Name $shared -Force -ErrorAction Stop

    $identity=Assert-Wslpe45Identity
    $id='msi_repair_custom_action'
    $root=Assert-Wslpe45OwnedFixture -Number 25 -Id $id
    Assert-Wslpe45NoReparsePoints -Path $root

    # The two fixture ancestors must not be replaceable by standard users.
    # This verifies current ACL evidence; it is not an atomic filesystem
    # security guarantee and does not authorize installation or repair.
    $ancestors=@(
        'C:\ProgramData\KingdomsWSLPE45',
        'C:\ProgramData\KingdomsWSLPE45\fixtures',
        $root
    )
    $dangerous=[int][Security.AccessControl.FileSystemRights]::Write -bor
               [int][Security.AccessControl.FileSystemRights]::Delete -bor
               [int][Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor
               [int][Security.AccessControl.FileSystemRights]::ChangePermissions -bor
               [int][Security.AccessControl.FileSystemRights]::TakeOwnership
    foreach($path in $ancestors) {
        $item=Get-Item -LiteralPath $path -Force -ErrorAction Stop
        if(-not $item.PSIsContainer -or
           (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw "Unexpected directory or reparse point: $path"
        }

        $acl=Get-Acl -LiteralPath $path -ErrorAction Stop
        if($path -ceq $root -and -not $acl.AreAccessRulesProtected) {
            throw 'Dedicated MSI fixture must have protected access rules'
        }

        try {
            $ownerSid=([Security.Principal.NTAccount]::new(
                $acl.Owner)).Translate([Security.Principal.SecurityIdentifier]).Value
        } catch {
            throw "Cannot independently resolve fixture directory owner: $path"
        }
        if($ownerSid -eq $identity.LearnerSid) {
            throw "Non-administrator learner owns protected MSI path: $path"
        }

        $entries=$acl.GetAccessRules(
            $true,$true,[Security.Principal.SecurityIdentifier])
        foreach($entry in $entries) {
            if($entry.AccessControlType -ne
               [Security.AccessControl.AccessControlType]::Allow) { continue }
            $sid=$entry.IdentityReference.Value
            if($sid -in @('S-1-5-18','S-1-5-32-544')) { continue }
            if(([int]$entry.FileSystemRights -band $dangerous) -ne 0) {
                throw "Unexpected write-capable ACL entry for $sid at $path"
            }
        }
    }

    # Enumerate the directory itself: a broken symlink must not appear
    # absent merely because its target does not exist.
    $matches=@(Get-ChildItem -LiteralPath $root -Force -ErrorAction Stop |
        Where-Object { $_.Name -ceq 'repair-proof.txt' })
    if($Stage -eq 'BeforeRepair') {
        if($matches.Count -ne 0) {
            throw 'Existing proof object must not be overwritten or adopted'
        }
    } else {
        if($matches.Count -ne 1 -or $matches[0].PSIsContainer -or
           (($matches[0].Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw 'Expected exactly one regular MSI repair proof file'
        }
        $observed=Get-Content -LiteralPath $matches[0].FullName -Raw -ErrorAction Stop
        if($observed -cne "WSLPE45_MSI_REPAIR_ACTION_INVOKED`r`n") {
            throw 'Unexpected MSI repair marker bytes'
        }
    }

    Write-Output ('WSLPE25_FIXTURE_INSPECT={0}:PASS' -f $Stage)
}

Export-ModuleMember -Function 'Assert-Wslpe25RepairFixture'
