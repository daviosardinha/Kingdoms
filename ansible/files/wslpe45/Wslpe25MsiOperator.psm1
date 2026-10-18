# WSLPE #25: locally approved Windows Installer lifecycle, source-only.
# Import has no side effects. NOT called by Ansible, CI, or batch operator.
Set-StrictMode -Version Latest

function Read-Wslpe25MsiProperty {
    param($Database, [string]$Name)
    if($Name -notin @('ProductCode','ProductName','Manufacturer','ProductVersion','ALLUSERS')) {
        throw 'Unrecognized MSI identity property'
    }
    $tick=[char]96
    $sql=("SELECT {0}Value{0} FROM {0}Property{0} WHERE {0}Property{0} = '{1}'" -f $tick,$Name)
    $view=$Database.OpenView($sql)
    try {
        $null=$view.Execute()
        $record=$view.Fetch()
        if($null -eq $record){throw "Missing MSI property: $Name"}
        return [string]$record.StringData(1)
    } finally {
        $null=$view.Close()
    }
}

function Get-Wslpe25MsiIdentity {
    [CmdletBinding()]
    param()
    $path='C:\ProgramData\KingdomsWSLPE45\lib\Kingdom25Repair.msi'
    $item=Get-Item -LiteralPath $path -Force -ErrorAction Stop
    if($item.PSIsContainer -or (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)){
        throw 'Refusing missing, directory or reparse-point MSI'
    }
    $installer=New-Object -ComObject WindowsInstaller.Installer
    $database=$installer.OpenDatabase($path,0)
    $code=Read-Wslpe25MsiProperty $database 'ProductCode'
    $guid=[guid]::Empty
    if(-not [guid]::TryParse($code,[ref]$guid) -or $guid -eq [guid]::Empty){
        throw 'Unusable native MSI ProductCode'
    }
    $expected=@{
        ProductName='Kingdoms WSLPE25 Repair Fixture'
        Manufacturer='Nomad Kingdom'
        ProductVersion='0.1.0'
        ALLUSERS='1'
    }
    foreach($name in @('ProductName','Manufacturer','ProductVersion','ALLUSERS')){
        if((Read-Wslpe25MsiProperty $database $name) -cne $expected[$name]){
            throw "MSI $name did not match dedicated package identity"
        }
    }
    [pscustomobject]@{
        ProductCode=$code
        Sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash
        Path=$path
    }
}

# Deterministic recovery dispatch. No installer, account, or file I/O.
# Windows CI exercises positive and negative transitions independently.
function Get-Wslpe25RecoveryDecision {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$LedgerStatus,
        [Parameter(Mandatory=$true)][int]$ProductState,
        [Parameter(Mandatory=$true)][bool]$OwnedAndMatching,
        [Parameter(Mandatory=$true)][bool]$UnexpectedEntries
    )
    if(-not $OwnedAndMatching -or $UnexpectedEntries -or
       $LedgerStatus -cne 'install-attempted'){
        return 'BLOCK'
    }
    if($ProductState -eq 5){return 'UNINSTALL_EXACT_PRODUCT'}
    if($ProductState -eq -1){return 'CLEAN_OWNED_FIXTURE_ONLY'}
    return 'BLOCK'
}

function Invoke-Wslpe25MsiOperator {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [ValidateSet('Inspect','Install','Uninstall','Recover')][string]$Action,
        [string]$ExpectedSha256,
        [string]$Approval
    )
    $ErrorActionPreference='Stop'
    $lib='C:\ProgramData\KingdomsWSLPE45\lib'
    if(-not [string]::Equals(
        [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\'),
        $lib,[StringComparison]::OrdinalIgnoreCase)){
        throw 'Module must be imported from the exact WSLPE protected library'
    }
    foreach($module in @('WslpeFixture.psm1','Wslpe25RepairInspection.psm1',
                        'Wslpe25RepairPreparation.psm1')){
        $full=Join-Path $lib $module
        $item=Get-Item -LiteralPath $full -Force -ErrorAction Stop
        if($item.PSIsContainer -or (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)){
            throw 'WSLPE25 requires ordinary owned module files'
        }
    }
    Import-Module (Join-Path $lib 'WslpeFixture.psm1') -Force -ErrorAction Stop
    Import-Module (Join-Path $lib 'Wslpe25RepairPreparation.psm1') -Force -ErrorAction Stop
    Import-Module (Join-Path $lib 'Wslpe25RepairInspection.psm1') -Force -ErrorAction Stop
    $who=Assert-Wslpe45Identity
    Assert-Wslpe25ProtectedParent -Path 'C:\ProgramData\KingdomsWSLPE45' -RequireProtectedAcl
    Assert-Wslpe25ProtectedParent -Path $lib -RequireProtectedAcl
    $pkg=Get-Wslpe25MsiIdentity
    $installer=New-Object -ComObject WindowsInstaller.Installer
    $state=[int]$installer.ProductState($pkg.ProductCode)
    $root='C:\ProgramData\KingdomsWSLPE45\fixtures\msi_repair_custom_action'
    $ledger=Join-Path $root 'msi-product-ownership.json'

    if($Action -eq 'Inspect'){
        Write-Output ('WSLPE25_PRODUCT_CODE=' + $pkg.ProductCode)
        Write-Output ('WSLPE25_MSI_SHA256=' + $pkg.Sha256)
        Write-Output ('WSLPE25_PRODUCT_STATE=' + $state)
        Write-Output ('WSLPE25_LEDGER_PRESENT=' + [bool](Test-Path -LiteralPath $ledger -PathType Leaf))
        return
    }
    $principal=[Security.Principal.WindowsPrincipal]::new(
        [Security.Principal.WindowsIdentity]::GetCurrent())
    if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
        throw 'Install/uninstall requires elevated local administrator'
    }
    if($env:SESSIONNAME -cne 'Console'){
        throw 'Install/uninstall must run from the interactive VMware Windows console'
    }
    $requiredApproval=switch($Action){
        'Install' {'INSTALL WSLPE25'}
        'Uninstall' {'UNINSTALL WSLPE25'}
        'Recover' {'RECOVER WSLPE25'}
    }
    if($Approval -cne $requiredApproval){throw 'Exact local operator approval required'}
    $null=Assert-Wslpe45OwnedFixture -Number 25 -Id 'msi_repair_custom_action'
    Assert-Wslpe45NoReparsePoints -Path $root
    $entries=@(Get-ChildItem -LiteralPath $root -Force -ErrorAction Stop |
        Where-Object {$_.Name -ceq 'msi-product-ownership.json'})

    if($Action -eq 'Install'){
        if($ExpectedSha256 -cnotmatch '^[0-9A-Fa-f]{64}$' -or
           $pkg.Sha256 -cne $ExpectedSha256.ToUpperInvariant()){
            throw 'MSI hash differs from operator-approved build digest'
        }
        if($state -ne -1 -or $entries.Count -ne 0){
            throw 'Refuse an already registered MSI or existing ledger'
        }
        Assert-Wslpe25RepairFixture -Stage BeforeRepair
        if(Test-Path -LiteralPath 'C:\Program Files\KingdomsWSLPE25'){
            throw 'Refuse existing Program Files destination'
        }
        $manifest=[ordered]@{
            schema='kingdoms.wslpe25.msi-product-owner.v1'
            machine='WSLPE-WS01'
            learner_sid=$who.LearnerSid
            product_code=$pkg.ProductCode
            msi_sha256=$pkg.Sha256
            status='install-attempted'
        }
        $bytes=[Text.Encoding]::UTF8.GetBytes(($manifest|ConvertTo-Json -Compress))
        $stream=[IO.File]::Open($ledger,[IO.FileMode]::CreateNew,
            [IO.FileAccess]::Write,[IO.FileShare]::None)
        try{$stream.Write($bytes,0,$bytes.Length)}finally{$stream.Dispose()}

        $argsText=('/i "{0}" /qn /norestart REBOOT=ReallySuppress' -f $pkg.Path)
        $process=Start-Process -FilePath "$env:windir\System32\msiexec.exe" -ArgumentList $argsText -Wait -PassThru
        if($process.ExitCode -ne 0){
            throw "MSI install returned code $($process.ExitCode); retain recovery ledger"
        }
        if([int]$installer.ProductState($pkg.ProductCode) -ne 5){
            throw 'MSI did not register in installed state; retain ledger'
        }
        $manifest.status='installed'
        ($manifest|ConvertTo-Json -Compress) | Set-Content -LiteralPath $ledger -Encoding UTF8 -ErrorAction Stop
        Write-Output 'WSLPE25_MSI_INSTALLED=PASS'
        return
    }

    if($Action -eq 'Recover' -and
       ($ExpectedSha256 -cnotmatch '^[0-9A-Fa-f]{64}
       (($entries[0].Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)){
        throw 'Uninstall requires exactly one regular owned ledger'
    }
    $owner=Get-Content -LiteralPath $ledger -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    if($owner.schema -cne 'kingdoms.wslpe25.msi-product-owner.v1' -or
       $owner.machine -cne 'WSLPE-WS01' -or
       $owner.learner_sid -cne $who.LearnerSid -or
       $owner.product_code -cne $pkg.ProductCode -or
       $owner.msi_sha256 -cne $pkg.Sha256 -or
       ($Action -eq 'Uninstall' -and $owner.status -cne 'installed') -or
       ($Action -eq 'Recover' -and $owner.status -cne 'install-attempted')){
        throw 'Refuse mismatched MSI ownership or lifecycle ledger'
    }
    # Check the *whole* fixture inventory before any installer mutation,
    # never silently adopt unexpected objects in our dedicated directory.
    $allowed=@('.kingdoms-owned.json','msi-product-ownership.json','repair-proof.txt')
    $unexpected=$false
    foreach($entry in @(Get-ChildItem -LiteralPath $root -Force -ErrorAction Stop)){
        if($entry.PSIsContainer -or $entry.Name -cnotin $allowed -or
           (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)){
            $unexpected=$true
        }
    }
    if($unexpected){throw 'Unexpected object in owned MSI fixture; preserve for review'}
    if($Action -eq 'Recover'){
        $decision=Get-Wslpe25RecoveryDecision -LedgerStatus $owner.status `
            -ProductState $state -OwnedAndMatching $true -UnexpectedEntries $unexpected
        if($decision -eq 'BLOCK'){
            throw 'Recovery blocked by unknown registration or ledger state'
        }
    } else {
        if($state -ne 5){throw 'Owned uninstall requires an installed product'}
        $decision='UNINSTALL_EXACT_PRODUCT'
    }
    if($decision -eq 'UNINSTALL_EXACT_PRODUCT'){
        # Native removal is permitted only for this exact ProductCode.
        $argsText=('/x {0} /qn /norestart REBOOT=ReallySuppress' -f $pkg.ProductCode)
        $process=Start-Process -FilePath "$env:windir\System32\msiexec.exe" -ArgumentList $argsText -Wait -PassThru
        if($process.ExitCode -ne 0){throw "Exact MSI uninstall failed ($($process.ExitCode)); keep ledger"}
        if([int]$installer.ProductState($pkg.ProductCode) -ne -1){
            throw 'MSI still registered after uninstall; retain recovery evidence'
        }
    }
    if(Test-Path -LiteralPath 'C:\Program Files\KingdomsWSLPE25'){
        throw 'MSI destination not absent; keep ownership evidence'
    }
    # Refuse recursive teardown if anything outside our exact bounded
    # fixture file contract has appeared since installation.
    foreach($entry in @(Get-ChildItem -LiteralPath $root -Force -ErrorAction Stop)){
        if($entry.PSIsContainer -or $entry.Name -cnotin $allowed -or
           (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)){
            throw 'Unexpected MSI fixture entry after removal; preserve for review'
        }
    }
    if(Test-Path -LiteralPath (Join-Path $root 'repair-proof.txt')){
        Assert-Wslpe25RepairFixture -Stage AfterRepair
    }
    Remove-Wslpe45OwnedFixture -Number 25 -Id 'msi_repair_custom_action'
    if($Action -eq 'Recover'){
        Write-Output 'WSLPE25_MSI_EXPLICIT_RECOVERY=PASS'
    } else {
        Write-Output 'WSLPE25_MSI_UNINSTALLED_AND_FIXTURE_REMOVED=PASS'
    }
}

Export-ModuleMember -Function @('Invoke-Wslpe25MsiOperator','Get-Wslpe25RecoveryDecision')
 -or
        $pkg.Sha256 -cne $ExpectedSha256.ToUpperInvariant())){
        throw 'Recovery requires the exact approved MSI digest'
    }
    if($entries.Count -ne 1 -or $entries[0].PSIsContainer -or
       (($entries[0].Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)){
        throw 'Uninstall requires exactly one regular owned ledger'
    }
    $owner=Get-Content -LiteralPath $ledger -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    if($owner.schema -cne 'kingdoms.wslpe25.msi-product-owner.v1' -or
       $owner.machine -cne 'WSLPE-WS01' -or
       $owner.learner_sid -cne $who.LearnerSid -or
       $owner.product_code -cne $pkg.ProductCode -or
       $owner.msi_sha256 -cne $pkg.Sha256 -or
       $owner.status -cne 'installed' -or $state -ne 5){
        throw 'Refuse to remove an unowned, changed or unregistered product'
    }
    $argsText=('/x {0} /qn /norestart REBOOT=ReallySuppress' -f $pkg.ProductCode)
    $process=Start-Process -FilePath "$env:windir\System32\msiexec.exe" -ArgumentList $argsText -Wait -PassThru
    if($process.ExitCode -ne 0){throw "MSI uninstall code $($process.ExitCode); retain ledger"}
    if([int]$installer.ProductState($pkg.ProductCode) -ne -1){
        throw 'MSI still registered after uninstall; retain fixture'
    }
    if(Test-Path -LiteralPath 'C:\Program Files\KingdomsWSLPE25'){
        throw 'MSI payload directory still present; retain fixture for review'
    }
    # Refuse recursive teardown if anything outside our exact bounded
    # fixture file contract has appeared since installation.
    $allowed=@('.kingdoms-owned.json','msi-product-ownership.json','repair-proof.txt')
    foreach($entry in @(Get-ChildItem -LiteralPath $root -Force -ErrorAction Stop)){
        if($entry.PSIsContainer -or $entry.Name -cnotin $allowed -or
           (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)){
            throw 'Unexpected MSI fixture entry; preserve it for manual review'
        }
    }
    if(Test-Path -LiteralPath (Join-Path $root 'repair-proof.txt')){
        Assert-Wslpe25RepairFixture -Stage AfterRepair
    }
    Remove-Wslpe45OwnedFixture -Number 25 -Id 'msi_repair_custom_action'
    Write-Output 'WSLPE25_MSI_UNINSTALLED_AND_FIXTURE_REMOVED=PASS'
}

Export-ModuleMember -Function 'Invoke-Wslpe25MsiOperator'
