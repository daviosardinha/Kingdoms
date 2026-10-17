# Native PowerShell JEA teaching fixture. No import-time effects.
Set-StrictMode -Version Latest
function Invoke-Wslpe45Jea {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][ValidateSet('apply','validate','reset')][string]$Action,
        [Parameter(Mandatory=$true)][ValidateSet('apply','vulnerable','reset','clean','reapply','revulnerable')][string]$Stage
    )
    $ErrorActionPreference='Stop'
    Import-Module 'C:\ProgramData\KingdomsWSLPE45\lib\WslpeFixture.psm1' -Force -ErrorAction Stop
    $who=Assert-Wslpe45Identity
    $id='jea_role_capability_misconfig'
    $root=Get-Wslpe45FixturePath -Id $id
    $name='Kingdoms45JEA'
    $moduleDir=Join-Path $env:ProgramFiles 'WindowsPowerShell\Modules\Kingdoms45JEA'
    $roles=Join-Path $moduleDir 'RoleCapabilities'
    $moduleFile=Join-Path $moduleDir 'Kingdoms45JEA.psm1'
    $manifest=Join-Path $moduleDir 'Kingdoms45JEA.psd1'
    $role=Join-Path $roles 'Kingdoms45Role.psrc'
    $config=Join-Path $root 'Kingdoms45JEA.pssc'
    $marker=Join-Path $moduleDir '.kingdoms45-owner.txt'
    $existing=Get-PSSessionConfiguration -Name $name -ErrorAction SilentlyContinue
    if($Action -eq 'apply'){
        if($existing -or (Test-Path -LiteralPath $moduleDir)){throw 'Refusing preexisting JEA endpoint or module'}
        $root=New-Wslpe45OwnedFixture -Number 30 -Id $id
        New-Item -Path $roles -ItemType Directory -ErrorAction Stop | Out-Null
        $acl=(Get-Acl -LiteralPath $moduleDir -ErrorAction Stop).Access
        foreach($ace in $acl){
            $sid=$null
            try{$sid=$ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value}catch{}
            if($sid -eq $who.LearnerSid -and $ace.AccessControlType -eq 'Allow' -and ($ace.FileSystemRights -band [Security.AccessControl.FileSystemRights]::WriteData)){
                throw 'JEA privileged source is learner-writable'
            }
        }
        Set-Content -LiteralPath $marker -Value 'WSLPE45:30:jea_role_capability_misconfig' -Encoding Ascii -ErrorAction Stop
        $functionCode=@'
function Invoke-Kingdoms45Maintenance {
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)][ValidateSet('Status','Proof')][string]$Operation)
    if($Operation -eq 'Status'){ return 'WSLPE45_JEA_STATUS' }
    $file='C:\ProgramData\KingdomsWSLPE45\fixtures\jea_role_capability_misconfig\proof.txt'
    [IO.File]::WriteAllText($file,'WSLPE45_JEA_PROOF='+[Security.Principal.WindowsIdentity]::GetCurrent().Name)
    return 'WSLPE45_JEA_PROOF_WRITTEN'
}
Export-ModuleMember -Function Invoke-Kingdoms45Maintenance
'@
        Set-Content -LiteralPath $moduleFile -Value $functionCode -Encoding UTF8 -ErrorAction Stop
        New-ModuleManifest -Path $manifest -RootModule 'Kingdoms45JEA.psm1' -ModuleVersion '1.0.0' -FunctionsToExport 'Invoke-Kingdoms45Maintenance' -ErrorAction Stop | Out-Null
        New-PSRoleCapabilityFile -Path $role -VisibleFunctions 'Invoke-Kingdoms45Maintenance' -ErrorAction Stop
        $principal='WSLPE-WS01\lpe.trainee'
        $definitions=@{ $principal = @{ RoleCapabilities = @('Kingdoms45Role') } }
        New-PSSessionConfigurationFile -Path $config -SessionType RestrictedRemoteServer -RunAsVirtualAccount -RoleDefinitions $definitions -ErrorAction Stop
        if(-not (Test-PSSessionConfigurationFile -Path $config -ErrorAction Stop)){throw 'JEA configuration validation failed'}
        Register-PSSessionConfiguration -Name $name -Path $config -NoServiceRestart -Force -ErrorAction Stop | Out-Null
        Write-Output 'WSLPE45_JEA_REGISTERED_WITHOUT_WINRM_RESTART'
    }
    elseif($Action -eq 'reset'){
        $root=Assert-Wslpe45OwnedFixture -Number 30 -Id $id
        if(-not (Test-Path -LiteralPath $marker -PathType Leaf) -or (Get-Content -LiteralPath $marker -Raw -ErrorAction Stop).Trim() -cne 'WSLPE45:30:jea_role_capability_misconfig'){
            throw 'JEA module owner marker invalid; refusing cleanup'
        }
        if(-not $existing){throw 'Dedicated JEA endpoint missing'}
        Unregister-PSSessionConfiguration -Name $name -NoServiceRestart -Force -ErrorAction Stop
        if(Get-PSSessionConfiguration -Name $name -ErrorAction SilentlyContinue){throw 'JEA endpoint still registered'}
        foreach($path in @($moduleDir,$roles)){
            if(([IO.File]::GetAttributes($path) -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'JEA module reparse point detected'}
        }
        Remove-Item -LiteralPath $moduleDir -Recurse -Force -ErrorAction Stop
        Remove-Wslpe45OwnedFixture -Number 30 -Id $id
        Write-Output 'WSLPE45_JEA_UNREGISTERED_WITHOUT_WINRM_RESTART'
    }
    elseif($Stage -eq 'clean'){
        if($existing -or (Test-Path -LiteralPath $moduleDir) -or (Test-Path -LiteralPath $root)){throw 'JEA fixture not clean'}
        Write-Output 'WSLPE45_JEA_CLEAN'
    }
    else{
        $root=Assert-Wslpe45OwnedFixture -Number 30 -Id $id
        if(-not $existing -or -not (Test-Path -LiteralPath $manifest -PathType Leaf) -or -not (Test-Path -LiteralPath $role -PathType Leaf) -or -not (Test-Path -LiteralPath $config -PathType Leaf)){
            throw 'JEA endpoint or role missing'
        }
        if((Get-Content -LiteralPath $config -Raw) -notmatch 'RunAsVirtualAccount'){throw 'JEA virtual account not configured'}
        Write-Output 'WSLPE45_JEA_CONFIGURATION_PRESENT_NOT_EXECUTION_PROOF'
    }
    Write-Output ('WSLPE45_BATCH_STAGE='+$id+':'+$Stage+':PASS')
}
Export-ModuleMember -Function Invoke-Wslpe45Jea
