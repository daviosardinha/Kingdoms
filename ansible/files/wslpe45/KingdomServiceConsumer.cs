using System;
using System.Diagnostics;
using System.IO;
using System.ServiceProcess;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

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

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern uint GetFinalPathNameByHandle(
        SafeFileHandle handle, StringBuilder path, uint length, uint flags);

    private static string StageOpenedUpdate(string path, string prefix)
    {
        // Pin the opened bytes against replacement/write, resolve the actual
        // handle, then copy into the admin-owned root. Process.Start must never
        // reopen a learner-controlled path after a containment check.
        using (FileStream input = new FileStream(path, FileMode.Open,
                                                FileAccess.Read, FileShare.Read))
        {
            StringBuilder finalName = new StringBuilder(32768);
            uint size = GetFinalPathNameByHandle(input.SafeFileHandle, finalName,
                                                (uint)finalName.Capacity, 0);
            if (size == 0 || size >= finalName.Capacity)
                throw new IOException("Cannot resolve opened update object");
            string resolved = finalName.ToString();
            if (!resolved.StartsWith(@"\\?\", StringComparison.Ordinal))
                throw new IOException("Unexpected final path namespace");
            resolved = resolved.Substring(4);
            if (!resolved.StartsWith(prefix, StringComparison.OrdinalIgnoreCase) ||
                !String.Equals(resolved, path, StringComparison.OrdinalIgnoreCase))
                throw new IOException("Opened update escaped the owned inbox");
            string staged = Path.Combine(Root, "update-" + Guid.NewGuid().ToString("N") + ".exe");
            using (FileStream output = new FileStream(staged, FileMode.CreateNew,
                                                     FileAccess.Write, FileShare.None))
            {
                input.CopyTo(output);
                output.Flush(true);
            }
            return staged;
        }
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

                // Path.GetFullPath does not resolve Windows junctions,
                // symbolic links or other reparse-point redirections.
                // Reject any such component before selecting the candidate.
                // The opened-object check and protected copy below also close
                // the check-to-execution path replacement window.
                string trustedInbox = Path.GetFullPath(inbox).TrimEnd('\\');
                string cursor = path;
                bool reachedInbox = false;
                while (cursor != null)
                {
                    FileAttributes attributes = File.GetAttributes(cursor);
                    if ((attributes & FileAttributes.ReparsePoint) != 0)
                        return;
                    if (String.Equals(cursor, trustedInbox,
                                      StringComparison.OrdinalIgnoreCase))
                    {
                        reachedInbox = true;
                        break;
                    }
                    cursor = Path.GetDirectoryName(cursor);
                }
                if (!reachedInbox)
                    return;
                path = StageOpenedUpdate(path, prefix);
                child = new ProcessStartInfo(path);
            }
            else if (Mode == "privileged_child_environment_trust")
            {
                // Lab-specific environment trust mistake. The privileged
                // parent forwards learner-controlled data into a fixed child.
                // The child may only create a lab-owned proof marker.
                string trustedChild = Path.Combine(Root, "Kingdom45EnvironmentChild.exe");
                if (!File.Exists(trustedChild))
                    return;
                child = new ProcessStartInfo(trustedChild);
                child.EnvironmentVariables["KINGDOMS_WSLPE45_CHILD_ACTION"] = supplied;
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
