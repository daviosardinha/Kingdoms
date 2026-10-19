$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if($PSVersionTable.PSVersion.Major -ne 5){throw 'Native PS5.1 required'}
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $PWD 'ansible\files\wslpe45\WslpeComRegistration.psm1'),[ref]$tokens,[ref]$errors)
$functions=@($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -eq 'Invoke-Wslpe45RegAsmProcess'
},$true))
if(@($errors).Count -or $functions.Count -ne 1){throw 'Expected exact RegAsm helper'}
. ([scriptblock]::Create($functions[0].Extent.Text))
$directory=Join-Path $env:RUNNER_TEMP 'native process regression'
$null=New-Item -ItemType Directory -Path $directory
$exe=Join-Path $directory 'NativeStub.exe'
$assembly=Join-Path $directory 'sample fixture.dll'
[IO.File]::WriteAllText($assembly,'not an assembly; no RegAsm is executed')
$stub=@'
using System;
public static class NativeStub {
    public static int Main(string[] args) {
        if(args.Length != 3 || !args[0].EndsWith("sample fixture.dll") || args[2] != "/nologo") return 23;
        Console.Out.WriteLine("native stdout captured");
        Console.Error.WriteLine("RegAsm : warning RA0000 : unsigned /codebase test");
        return args[1] == "/codebase" ? 0 : 7;
    }
}
'@
Add-Type -TypeDefinition $stub -OutputAssembly $exe -OutputType ConsoleApplication
$Error.Clear()
$result=Invoke-Wslpe45RegAsmProcess -RegAsm $exe -Assembly $assembly -Operation '/codebase'
if($result.ExitCode -ne 0 -or $result.StdOut -notmatch 'stdout captured' -or
   $result.StdErr -notmatch 'warning RA0000' -or $Error.Count -ne 0) {
    throw 'Native warning incorrectly failed or diagnostics lost'
}
$caught=$null
try { $null=Invoke-Wslpe45RegAsmProcess -RegAsm $exe -Assembly $assembly -Operation '/unregister' }
catch { $caught=$_.Exception.Message }
if(-not $caught -or $caught -notmatch 'RegAsm exit 7' -or $caught -notmatch 'warning RA0000') {
    throw 'Native failure lost exit status or stderr'
}
$caught=$null
try { $null=Invoke-Wslpe45RegAsmProcess -RegAsm ($exe+'.missing') -Assembly $assembly -Operation '/codebase' }
catch { $caught=$_.Exception.Message }
if(-not $caught){throw 'Missing executable accepted'}
Write-Output '[PASS] PS5.1 native stderr/exit/path checks; no COM registration'
