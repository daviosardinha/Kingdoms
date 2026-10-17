# Original LSA account-right API comes from the proven standalone rights adapter.
# New rights are assigned only on exact workgroup WSLPE-WS01, never NORTH.
Set-StrictMode -Version Latest

function Invoke-Wslpe45LsaRight {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [ValidateSet('setakeownership_privilege','serestore_privilege','sedebug_privilege')]
        [string]$Id,
        [Parameter(Mandatory=$true)]
        [ValidateSet('apply','validate','reset')]
        [string]$Action,
        [Parameter(Mandatory=$true)]
        [ValidateSet('apply','vulnerable','reset','clean','reapply','revulnerable')]
        [string]$Stage
    )
    $ErrorActionPreference = 'Stop'
    Import-Module 'C:\ProgramData\KingdomsWSLPE45\lib\WslpeFixture.psm1' -Force -ErrorAction Stop
    $who = Assert-Wslpe45Identity
    $definition = @{
        setakeownership_privilege = @{ number=31; right='SeTakeOwnershipPrivilege' }
        serestore_privilege = @{ number=32; right='SeRestorePrivilege' }
        sedebug_privilege = @{ number=33; right='SeDebugPrivilege' }
    }[$Id]
    if ($null -eq $definition) { throw 'Unknown local-account privilege' }
    $number = [int]$definition.number
    $right = [string]$definition.right
    $root = Get-Wslpe45FixturePath -Id $Id
    $artifact = Join-Path $root 'protected-evidence.txt'
    $serviceName = 'Kingdom45DebugTarget'
    $serviceBinary = Join-Path $root 'Kingdom45DebugTarget.exe'
    $sid = $who.LearnerSid

    if (-not ('WslpeDirectAccountRights' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Principal;
public static class WslpeDirectAccountRights {
    [StructLayout(LayoutKind.Sequential)]
    struct LSA_OBJECT_ATTRIBUTES {
        public int Length;
        public IntPtr RootDirectory;
        public IntPtr ObjectName;
        public uint Attributes;
        public IntPtr SecurityDescriptor;
        public IntPtr SecurityQualityOfService;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct LSA_UNICODE_STRING {
        public ushort Length;
        public ushort MaximumLength;
        public IntPtr Buffer;
    }
    const uint LOOKUP_NAMES = 0x00000800;
    const uint CREATE_ACCOUNT = 0x00000010;
    [DllImport("advapi32.dll", ExactSpelling=true)]
    static extern uint LsaOpenPolicy(IntPtr host,
        ref LSA_OBJECT_ATTRIBUTES attrs, uint access, out IntPtr policy);
    [DllImport("advapi32.dll", ExactSpelling=true)]
    static extern uint LsaEnumerateAccountRights(IntPtr policy,
        IntPtr accountSid, out IntPtr rights, out uint count);
    [DllImport("advapi32.dll", ExactSpelling=true)]
    static extern uint LsaAddAccountRights(IntPtr policy,
        IntPtr accountSid, [In] LSA_UNICODE_STRING[] rights, uint count);
    [DllImport("advapi32.dll", ExactSpelling=true)]
    static extern uint LsaRemoveAccountRights(IntPtr policy,
        IntPtr accountSid, bool allRights, [In] LSA_UNICODE_STRING[] rights, uint count);
    [DllImport("advapi32.dll", ExactSpelling=true)]
    static extern uint LsaNtStatusToWinError(uint status);
    [DllImport("advapi32.dll", ExactSpelling=true)]
    static extern uint LsaClose(IntPtr policy);
    [DllImport("advapi32.dll", ExactSpelling=true)]
    static extern uint LsaFreeMemory(IntPtr buffer);

    static void EnsureSuccess(uint code, string stage) {
        if (code != 0)
            throw new Win32Exception((int)LsaNtStatusToWinError(code),
                "WSLPE LSA " + stage + " failed");
    }
    static IntPtr AllocateSid(string text) {
        var sid = new SecurityIdentifier(text);
        var bytes = new byte[sid.BinaryLength];
        sid.GetBinaryForm(bytes, 0);
        var ptr = Marshal.AllocHGlobal(bytes.Length);
        Marshal.Copy(bytes, 0, ptr, bytes.Length);
        return ptr;
    }
    static IntPtr Open(uint access) {
        var attrs = new LSA_OBJECT_ATTRIBUTES();
        attrs.Length = Marshal.SizeOf(typeof(LSA_OBJECT_ATTRIBUTES));
        IntPtr policy;
        EnsureSuccess(LsaOpenPolicy(IntPtr.Zero, ref attrs, access, out policy), "open");
        return policy;
    }
    public static bool HasRight(string sid, string wantedRight) {
        IntPtr sidPtr = IntPtr.Zero, policy = IntPtr.Zero, rightBuffer = IntPtr.Zero;
        try {
            sidPtr = AllocateSid(sid);
            policy = Open(LOOKUP_NAMES);
            uint count = 0;
            uint status = LsaEnumerateAccountRights(policy, sidPtr, out rightBuffer, out count);
            if (status != 0) {
                uint error = LsaNtStatusToWinError(status);
                if (error == 2) return false; // Account has no direct rights.
                EnsureSuccess(status, "enumeration");
            }
            int size = Marshal.SizeOf(typeof(LSA_UNICODE_STRING));
            for (uint i = 0; i < count; i++) {
                var right = (LSA_UNICODE_STRING)Marshal.PtrToStructure(
                    IntPtr.Add(rightBuffer, checked((int)i * size)),
                    typeof(LSA_UNICODE_STRING));
                string value = Marshal.PtrToStringUni(right.Buffer, right.Length / 2);
                if (String.Equals(value, wantedRight, StringComparison.OrdinalIgnoreCase))
                    return true;
            }
            return false;
        } finally {
            if (rightBuffer != IntPtr.Zero) LsaFreeMemory(rightBuffer);
            if (policy != IntPtr.Zero) LsaClose(policy);
            if (sidPtr != IntPtr.Zero) Marshal.FreeHGlobal(sidPtr);
        }
    }
    public static void Change(string sid, string rightName, bool remove) {
        IntPtr sidPtr = IntPtr.Zero, policy = IntPtr.Zero, rightPtr = IntPtr.Zero;
        try {
            sidPtr = AllocateSid(sid);
            policy = Open(LOOKUP_NAMES | CREATE_ACCOUNT);
            rightPtr = Marshal.StringToHGlobalUni(rightName);
            var right = new LSA_UNICODE_STRING {
                Buffer = rightPtr,
                Length = checked((ushort)(rightName.Length * 2)),
                MaximumLength = checked((ushort)((rightName.Length + 1) * 2))
            };
            uint status = remove
                ? LsaRemoveAccountRights(policy, sidPtr, false, new [] {right}, 1)
                : LsaAddAccountRights(policy, sidPtr, new [] {right}, 1);
            EnsureSuccess(status, remove ? "remove" : "add");
        } finally {
            if (rightPtr != IntPtr.Zero) Marshal.FreeHGlobal(rightPtr);
            if (policy != IntPtr.Zero) LsaClose(policy);
            if (sidPtr != IntPtr.Zero) Marshal.FreeHGlobal(sidPtr);
        }
    }
}
'@ -Language CSharp -ErrorAction Stop
    }
    $hasRight=[WslpeDirectAccountRights]::HasRight($sid,$right)
    $service=Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($Action -eq 'apply') {
        if($hasRight) { throw 'Original local-account right already exists; refusing overwrite' }
        if($Id -eq 'sedebug_privilege' -and $service) {
            throw 'Refusing pre-existing debug-target service'
        }
        $root=New-Wslpe45OwnedFixture -Number $number -Id $Id
        # Entire new fixture tree uses SYSTEM/Administrators ACL from
        # WslpeFixture; do not expose write access through filesystem inheritance.
        Set-Content -LiteralPath $artifact -Value "KINGDOMS_WSLPE45_PROTECTED_$right" -Encoding Ascii -ErrorAction Stop

        if($Id -eq 'sedebug_privilege') {
            $serviceCode=@'
using System;
using System.ServiceProcess;
public sealed class Kingdom45DebugTarget : ServiceBase {
    public Kingdom45DebugTarget(){ ServiceName="Kingdom45DebugTarget"; CanStop=true; }
    protected override void OnStart(string[] args){}
    protected override void OnStop(){}
    public static void Main(){ ServiceBase.Run(new Kingdom45DebugTarget()); }
}
'@
            Add-Type -TypeDefinition $serviceCode -Language CSharp -ReferencedAssemblies 'System.ServiceProcess.dll' -OutputAssembly $serviceBinary -OutputType WindowsApplication -ErrorAction Stop
            New-Service -Name $serviceName -BinaryPathName ('"{0}"' -f $serviceBinary) -DisplayName 'WSLPE Standalone SeDebug Proof Target' -StartupType Manual -ErrorAction Stop | Out-Null
            Start-Service -Name $serviceName -ErrorAction Stop
            $process=Get-CimInstance Win32_Service -Filter "Name='$serviceName'" -ErrorAction Stop
            if(-not $process -or $process.ProcessId -eq 0 -or $process.StartName -ne 'LocalSystem') {
                throw 'The dedicated SYSTEM debug service did not start'
            }
        }
        [WslpeDirectAccountRights]::Change($sid,$right,$false)
        if(-not [WslpeDirectAccountRights]::HasRight($sid,$right)) {
            throw 'Direct local-account LSA right assignment did not persist'
        }
        Write-Output ('WSLPE45_LSA_GRANTED=' + $right)
    }
    elseif($Action -eq 'reset') {
        $root=Assert-Wslpe45OwnedFixture -Number $number -Id $Id
        if ($Id -eq 'sedebug_privilege') {
            $existing=Get-CimInstance Win32_Service -Filter "Name='$serviceName'" -ErrorAction Stop
            if(-not $existing -or -not ([string]$existing.PathName).Trim('"').Equals($serviceBinary,[StringComparison]::OrdinalIgnoreCase)) {
                throw 'Refusing to remove service that is not exactly owned'
            }
            if($existing.State -eq 'Running') {
                Stop-Service -Name $serviceName -ErrorAction Stop
            }
            $response=& sc.exe delete $serviceName 2>&1
            if($LASTEXITCODE -ne 0) { throw "Scoped debug service removal failed: $response" }
            for($i=0;$i -lt 20;$i++) {
                if(-not (Get-Service -Name $serviceName -ErrorAction SilentlyContinue)) { break }
                Start-Sleep -Milliseconds 500
            }
            if(Get-Service -Name $serviceName -ErrorAction SilentlyContinue) {
                throw 'Dedicated debug service still exists after delete'
            }
        }
        if($hasRight) {
            [WslpeDirectAccountRights]::Change($sid,$right,$true)
        }
        if([WslpeDirectAccountRights]::HasRight($sid,$right)) {
            throw 'Cannot clear direct account privilege during reset'
        }
        Remove-Wslpe45OwnedFixture -Number $number -Id $Id
        Write-Output ('WSLPE45_LSA_REMOVED=' + $right)
    }
    elseif($Stage -eq 'clean') {
        if($hasRight -or (Test-Path -LiteralPath $root) -or
            ($Id -eq 'sedebug_privilege' -and $service)) {
            throw 'Local account LSA privilege fixture not cleaned'
        }
        Write-Output ('WSLPE45_LSA_CLEAN=' + $right)
    }
    else {
        $root=Assert-Wslpe45OwnedFixture -Number $number -Id $Id
        if(-not $hasRight -or -not (Test-Path -LiteralPath $artifact -PathType Leaf)) {
            throw 'Local-account right or protected evidence target missing'
        }
        if($Id -eq 'sedebug_privilege') {
            $target=Get-CimInstance Win32_Service -Filter "Name='$serviceName'" -ErrorAction Stop
            if(-not $target -or $target.StartName -ne 'LocalSystem' -or
                $target.State -ne 'Running' -or $target.ProcessId -eq 0) {
                throw 'Dedicated non-PPL SYSTEM debug target not available'
            }
        }
        # A new learner logon is required after applying LSA rights.
        # This check proves direct policy configuration only, never actual
        # low-privilege token enablement or exploitation.
        Write-Output ('WSLPE45_LSA_VULNERABLE_CONFIGURATION=' + $right)
    }
    Write-Output ('WSLPE45_BATCH_STAGE=' + $Id + ':' + $Stage + ':PASS')
}
Export-ModuleMember -Function 'Invoke-Wslpe45LsaRight'
