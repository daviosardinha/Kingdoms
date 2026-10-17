using System;
using System.Diagnostics;
using System.IO;
using System.ServiceProcess;

// Explicit lab-only elevated consumer. Tokens replaced at build time by the
// exact standalone fixture module. Do not compile/deploy on any other host.
public sealed class Kingdom45ServiceConsumer : ServiceBase
{
    private static readonly string Mode = "__MODE__";
    private static readonly string Root = @"__ROOT__";

    public Kingdom45ServiceConsumer()
    {
        ServiceName = "__SERVICE__";
        CanStop = true;
        AutoLog = false;
    }

    protected override void OnStart(string[] args)
    {
        string inbox = Path.Combine(Root, "inbox");
        string request = Path.Combine(inbox, "request.txt");
        if (!File.Exists(request))
            return;

        try
        {
            string supplied = File.ReadAllText(request).Trim();
            if (supplied.Length == 0 || supplied.Length > 256)
                return;

            ProcessStartInfo child;
            if (Mode == "privileged_service_config_injection")
            {
                // The flaw: concatenating an untrusted configuration field
                // into a privileged command interpreter invocation.
                child = new ProcessStartInfo("cmd.exe", "/d /c echo BASELINE " + supplied);
            }
            else if (Mode == "privileged_updater_hijack")
            {
                // The flaw: accepting a locally supplied unsigned executable
                // package path as a trusted offline update. The path remains
                // inside our owned inbox for the training exercise.
                string path = Path.GetFullPath(Path.Combine(inbox, supplied));
                string prefix = Path.GetFullPath(inbox).TrimEnd('\\') + "\\";
                if (!path.StartsWith(prefix, StringComparison.OrdinalIgnoreCase) ||
                    !path.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) ||
                    !File.Exists(path))
                    return;
                child = new ProcessStartInfo(path);
            }
            else if (Mode == "privileged_argument_injection")
            {
                // The flaw: command argument reaches cmd.exe rather than a
                // direct Process.Start with a strongly typed argument vector.
                child = new ProcessStartInfo("cmd.exe",
                    "/d /c \"C:\\Windows\\System32\\whoami.exe\" " + supplied);
            }
            else
            {
                return;
            }

            child.UseShellExecute = false;
            child.CreateNoWindow = true;
            child.WorkingDirectory = inbox;
            using (Process process = Process.Start(child))
            {
                if (process != null)
                    process.WaitForExit(5000);
            }
        }
        catch
        {
            // No external process or registry manipulation on failure.
            // Runtime validation must independently distinguish a blocked
            // consumer from a successful learner-side privilege boundary.
        }
    }

    protected override void OnStop() { }

    public static void Main()
    {
        ServiceBase.Run(new Kingdom45ServiceConsumer());
    }
}
