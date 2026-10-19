# Compile source only; exercise the pipe denial/timeout paths without services.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if($PSVersionTable.PSVersion.Major -ne 5){throw 'Native PS5.1 required'}
$out=Join-Path $env:RUNNER_TEMP 'remaining-native'
$null=New-Item -ItemType Directory -Path $out
$files=@(
    @('KingdomBoundaryService.cs','WindowsApplication',@('System.ServiceProcess.dll','System.Core.dll')),
    @('KingdomTraversalService.cs','WindowsApplication',@('System.ServiceProcess.dll')),
    @('KingdomServiceConsumer.cs','WindowsApplication',@('System.ServiceProcess.dll')),
    @('Kingdom45EnvironmentChild.cs','ConsoleApplication',@()),
    @('Kingdom45Plugin.cs','Library',@()),
    @('Kingdom45WmiWake.cs','ConsoleApplication',@()),
    @('Kingdom45ComServer.cs','Library',@())
)
foreach($spec in $files) {
    $code=Get-Content (Join-Path 'ansible/files/wslpe45' $spec[0]) -Raw
    $params=@{TypeDefinition=$code;Language='CSharp';OutputType=$spec[1];
        OutputAssembly=(Join-Path $out ($spec[0]+'.dll'));ErrorAction='Stop'}
    if($spec[2].Count){$params.ReferencedAssemblies=$spec[2]}
    Add-Type @params
}
foreach($module in @('WslpeLsaRights.psm1','WslpeRegistryTrust.psm1')) {
    $tokens=$null; $errors=$null
    $ast=[System.Management.Automation.Language.Parser]::ParseFile(
        (Join-Path $PWD ('ansible/files/wslpe45/'+$module)),[ref]$tokens,[ref]$errors)
    $blocks=@($ast.FindAll({
        param($node)
        ($node -is [System.Management.Automation.Language.StringConstantExpressionAst] -or
         $node -is [System.Management.Automation.Language.ExpandableStringExpressionAst]) -and
        $node.Value -match '^using System;'
    },$true))
    if($blocks.Count -ne $(if($module -eq 'WslpeLsaRights.psm1'){2}else{3})) {throw 'Inline CSharp coverage changed'}
    for($i=0;$i -lt $blocks.Count;$i++) {
        Add-Type -TypeDefinition $blocks[$i].Value -Language CSharp -ReferencedAssemblies 'System.ServiceProcess.dll' -OutputType Library -OutputAssembly (Join-Path $out ($module+$i+'.dll')) -ErrorAction Stop
    }
}
$boundary=Get-Content 'ansible/files/wslpe45/KingdomBoundaryService.cs' -Raw
$boundary=$boundary.Replace('Kingdom45Pipe29','Kingdom45Pipe29SourceCI')
$harness=@'
public static class PipeRegression {
    public static void Check(bool sendLine) {
        var server = new Kingdom45BoundaryService();
        var flags = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic;
        var stop = typeof(Kingdom45BoundaryService).GetField("stopping", flags);
        var loop = typeof(Kingdom45BoundaryService).GetMethod("PipeLoop", flags);
        System.Exception failure = null;
        var worker = new System.Threading.Thread(() => {
            try { loop.Invoke(server, null); } catch(System.Exception error) { failure = error; }
        });
        worker.IsBackground = true;
        worker.Start();
        using(var client = new System.IO.Pipes.NamedPipeClientStream(".", "Kingdom45Pipe29SourceCI",
            System.IO.Pipes.PipeDirection.InOut, System.IO.Pipes.PipeOptions.Asynchronous)) {
            client.Connect(5000);
            stop.SetValue(server, true);
            if(sendLine) {
                using(var writer = new System.IO.StreamWriter(client, System.Text.Encoding.ASCII, 256, true))
                using(var reader = new System.IO.StreamReader(client, System.Text.Encoding.ASCII, false, 256, true)) {
                    writer.WriteLine("STATUS"); writer.Flush();
                    var read = reader.ReadLineAsync();
                    if(!read.Wait(5000) || read.Result != "DENIED")
                        throw new System.Exception("Pipe denial path failed");
                }
            }
            if(!worker.Join(6000)) throw new System.Exception("Pipe read did not time out");
        }
        if(failure != null) throw new System.Exception("Pipe worker failed", failure);
        server.Dispose();
    }
}
'@
$boundary=$boundary.Replace('Kingdom45BoundaryService','Kingdom45BoundaryServiceCI')
$harness=$harness.Replace('Kingdom45BoundaryService','Kingdom45BoundaryServiceCI')
Add-Type -TypeDefinition ($boundary+[Environment]::NewLine+$harness) -ReferencedAssemblies @('System.ServiceProcess.dll','System.Core.dll')
[PipeRegression]::Check($true)
[PipeRegression]::Check($false)
Write-Output '[PASS] 12 CSharp sources compiled; pipe denial/timeout passed; no guest deployment'
