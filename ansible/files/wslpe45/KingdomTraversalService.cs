using System;
using System.IO;
using System.ServiceProcess;
using System.Security.Principal;

// Dedicated, intentionally vulnerable WSLPE-WS01 path traversal fixture.
// Does not run arbitrary commands or write outside the lab-owned fixture.
// Lab operation demonstrates SYSTEM writing an otherwise protected file.
public sealed class KingdomWslpe45TraversalService : ServiceBase
{
    private const string Fixture =
        @"C:\ProgramData\KingdomsWSLPE45\fixtures\privileged_path_traversal_write";

    public KingdomWslpe45TraversalService()
    {
        ServiceName = "KingdomWslpe45TraversalSvc";
        CanStop = true;
        AutoLog = false;
    }

    protected override void OnStart(string[] args)
    {
        string inbox = Path.Combine(Fixture, "inbox");
        string request = Path.Combine(inbox, "request.txt");
        string allowedProof = Path.GetFullPath(
            Path.Combine(Fixture, "protected", "proof.txt"));
        if (!File.Exists(request))
            return;

        try
        {
            string name = File.ReadAllText(request).Trim();
            if (name.Length == 0 || name.Length > 120)
                return;

            // The flaw: normal behavior should have constrained name to inbox.
            // Intentionally permit ".." to reach the protected sibling, while
            // confining the *entire* effect to an exact lab-owned marker path.
            string destination = Path.GetFullPath(Path.Combine(inbox, name));
            if (!String.Equals(destination, allowedProof,
                               StringComparison.OrdinalIgnoreCase))
                return;

            string principal = WindowsIdentity.GetCurrent().Name;
            File.WriteAllText(destination, "WSLPE45_TRAVERSAL_PROOF=" + principal);
        }
        catch
        {
            // No retries, external file writes or process spawning on errors.
        }
    }

    protected override void OnStop()
    {
    }

    public static void Main()
    {
        ServiceBase.Run(new KingdomWslpe45TraversalService());
    }
}
