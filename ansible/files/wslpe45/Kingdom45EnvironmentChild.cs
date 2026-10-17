using System;
using System.IO;
using System.Security.Principal;

public static class Kingdom45EnvironmentChild
{
    private static readonly string Root = @"__ROOT__";

    public static void Main()
    {
        // This child is fixed and trusted; the untrusted decision arrives
        // through the parent's inherited, learner-controlled environment.
        // No arbitrary command, DLL, executable path or system file is used.
        string job = Environment.GetEnvironmentVariable(
            "KINGDOMS_WSLPE45_CHILD_ACTION", EnvironmentVariableTarget.Process);
        if (!String.Equals(job, "PROOF", StringComparison.Ordinal))
            return;
        string output = Path.Combine(Root, "protected", "environment-proof.txt");
        File.WriteAllText(output,
            "WSLPE45_ENV_CHILD_PROOF=" + WindowsIdentity.GetCurrent().Name);
    }
}
