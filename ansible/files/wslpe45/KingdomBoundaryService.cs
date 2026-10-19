using System;
using System.IO;
using System.IO.Pipes;
using System.Net;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Security.AccessControl;
using System.Security.Principal;
using System.ServiceProcess;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

// Native, Windows-10-specific, isolated test service for four DIFFERENT
// trust-boundary errors. Source is compiled under WSLPE-WS01 only.
// The only privileged side effect is a file inside this owned fixture.
public sealed class Kingdom45BoundaryService : ServiceBase
{
    private static readonly string Mode = "__MODE__";
    private static readonly string Root = @"__ROOT__";
    private static readonly string ServiceId = "__SERVICE__";
    private Thread worker;
    private volatile bool stopping;
    private HttpListener listener;

    public Kingdom45BoundaryService()
    {
        ServiceName = ServiceId;
        CanStop = true;
        AutoLog = false;
    }

    protected override void OnStart(string[] args)
    {
        stopping = false;
        worker = new Thread(Run);
        worker.IsBackground = true;
        worker.Name = ServiceId + "-worker";
        worker.Start();
    }

    protected override void OnStop()
    {
        stopping = true;
        if (listener != null)
        {
            try { listener.Stop(); listener.Close(); } catch { }
        }
        if (worker != null && worker.IsAlive)
            worker.Join(3000);
    }

    private static string Protected(string name)
    {
        // No caller-controlled output paths, registry, command execution,
        // or untrusted-system-file writes.
        return Path.Combine(Root, "protected", name);
    }

    private static void Proof(string reason)
    {
        File.WriteAllText(Protected("proof.txt"),
            "WSLPE45_" + reason + "=" + WindowsIdentity.GetCurrent().Name);
    }

    private void Run()
    {
        if (Mode == "named_pipe_authorization")
            PipeLoop();
        else if (Mode == "privileged_loopback_http_authz")
            HttpLoop();
        else if (Mode == "privileged_file_toctou")
            RaceLoop();
        else if (Mode == "privileged_backup_restore_api")
            RestoreLoop();
        else if (Mode == "ntfs_link_redirection")
            LinkProof();
        else if (Mode == "elevated_plugin_signature_bypass")
            PluginProof();
    }

    private void PipeLoop()
    {
        // The bug is authorization: any local Users-group account may ask
        // this SYSTEM service to perform its protected marker operation.
        PipeSecurity acl = new PipeSecurity();
        SecurityIdentifier users = new SecurityIdentifier(
            WellKnownSidType.BuiltinUsersSid, null);
        acl.AddAccessRule(new PipeAccessRule(
            users, PipeAccessRights.ReadWrite, AccessControlType.Allow));
        while (!stopping)
        {
            try
            {
                using (NamedPipeServerStream pipe = new NamedPipeServerStream(
                    "Kingdom45Pipe29", PipeDirection.InOut, 1,
                    PipeTransmissionMode.Byte, PipeOptions.Asynchronous,
                    1024, 1024, acl))
                {
                    pipe.WaitForConnection();
                    using (StreamReader reader = new StreamReader(
                        pipe, Encoding.ASCII, false, 256, true))
                    using (StreamWriter writer = new StreamWriter(
                        pipe, Encoding.ASCII, 256, true))
                    {
                        // PipeStream does not support Stream.ReadTimeout.
                        var read = reader.ReadLineAsync();
                        if (Task.WhenAny(read, Task.Delay(3000)).GetAwaiter().GetResult() != read)
                        {
                            read.ContinueWith(t => t.Exception.Handle(error => true),
                                TaskContinuationOptions.OnlyOnFaulted);
                            continue;
                        }
                        string request = read.GetAwaiter().GetResult();
                        if (String.Equals(request, "PROOF", StringComparison.Ordinal))
                        {
                            Proof("PIPE");
                            writer.WriteLine("OK");
                        }
                        else writer.WriteLine("DENIED");
                        writer.Flush();
                    }
                }
            }
            catch (IOException) { }
            catch (InvalidOperationException) { if (stopping) return; }
        }
    }

    private void HttpLoop()
    {
        // Loopback-only binding. The bug is "localhost is trusted", so no
        // application authorization is checked for ordinary local clients.
        listener = new HttpListener();
        listener.Prefixes.Add("http://127.0.0.1:45939/");
        listener.AuthenticationSchemes = AuthenticationSchemes.Anonymous;
        try
        {
            listener.Start();
            while (!stopping)
            {
                HttpListenerContext context;
                try { context = listener.GetContext(); }
                catch (HttpListenerException) { if (stopping) return; else continue; }
                bool allowed = context.Request.HttpMethod == "POST" &&
                    context.Request.Url.AbsolutePath == "/proof" &&
                    IPAddress.IsLoopback(context.Request.RemoteEndPoint.Address);
                if (allowed) Proof("HTTP");
                context.Response.StatusCode = allowed ? 200 : 404;
                context.Response.ContentLength64 = 0;
                context.Response.Close();
            }
        }
        finally { if (listener != null) listener.Close(); }
    }

    private void RaceLoop()
    {
        string input = Path.Combine(Root, "inbox", "request.txt");
        string signal = Path.Combine(Root, "inbox", "ready.flag");
        string done = Path.Combine(Root, "protected", "done.flag");
        while (!stopping)
        {
            try
            {
                if (!File.Exists(done) && File.Exists(input) &&
                    String.Equals(File.ReadAllText(input).Trim(), "ARM",
                                  StringComparison.Ordinal))
                {
                    // TOCTOU: after this successful validation the learner
                    // can replace the content before the privileged use.
                    File.WriteAllText(signal, "VALIDATED");
                    Thread.Sleep(1600);
                    string consumed = File.ReadAllText(input).Trim();
                    if (consumed == "PROOF")
                    {
                        Proof("RACE");
                        File.WriteAllText(done, "DONE");
                    }
                }
            }
            catch (IOException) { }
            Thread.Sleep(250);
        }
    }

    private void RestoreLoop()
    {
        string request = Path.Combine(Root, "inbox", "restore.request");
        string snapshot = Path.Combine(Root, "inbox", "backup.txt");
        string done = Path.Combine(Root, "protected", "done.flag");
        while (!stopping)
        {
            try
            {
                if (!File.Exists(done) && File.Exists(request) &&
                    File.ReadAllText(request).Trim() == "RESTORE" &&
                    File.Exists(snapshot))
                {
                    // The flaw: application-level restore authorization is
                    // absent. Users can supply an owned snapshot that an
                    // elevated service writes into a protected application file.
                    string supplied = File.ReadAllText(snapshot).Trim();
                    if (supplied.Length > 0 && supplied.Length <= 128)
                    {
                        File.WriteAllText(Protected("restored.txt"), supplied);
                        Proof("RESTORE");
                        File.WriteAllText(done, "DONE");
                    }
                }
            }
            catch (IOException) { }
            Thread.Sleep(400);
        }
    }

    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    private static extern uint GetFinalPathNameByHandle(
        IntPtr hFile, StringBuilder filename, uint capacity, uint flags);

    private void LinkProof()
    {
        // Vulnerable use: SYSTEM follows a learner-created NTFS junction
        // from the inbox to a protected file in this private lab.
        // Containment: open an existing file only, verify its FINAL path via
        // the already-open handle, then write through that SAME handle.
        // No creation or writing outside this exact fixture is permitted.
        string alias = Path.Combine(Root, "inbox", "link", "proof.txt");
        string expected = "\\\\?\\" + Path.GetFullPath(
            Path.Combine(Root, "protected", "proof.txt"));
        try
        {
            using (FileStream stream = new FileStream(
                alias, FileMode.Open, FileAccess.Write, FileShare.None))
            {
                StringBuilder resolved = new StringBuilder(1024);
                uint length = GetFinalPathNameByHandle(
                    stream.SafeFileHandle.DangerousGetHandle(),
                    resolved, (uint)resolved.Capacity, 0);
                if (length == 0 || length >= resolved.Capacity ||
                    !String.Equals(resolved.ToString(), expected,
                                   StringComparison.OrdinalIgnoreCase))
                    return;
                byte[] proof = Encoding.ASCII.GetBytes(
                    "WSLPE45_NTFS_LINK_PROOF=" +
                    WindowsIdentity.GetCurrent().Name);
                stream.SetLength(0);
                stream.Write(proof, 0, proof.Length);
                stream.Flush(true);
            }
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }

    private void PluginProof()
    {
        // Intentionally defective trust decision: a learner-writable
        // manifest string is treated as a cryptographic signature verdict.
        // All component files and the proof sink are owned by this lab.
        string inbox = Path.Combine(Root, "inbox");
        string manifest = Path.Combine(inbox, "manifest.txt");
        string assemblyPath = Path.Combine(inbox, "Kingdom45Plugin.dll");
        try
        {
            if (!File.Exists(manifest) || !File.Exists(assemblyPath) ||
                File.ReadAllText(manifest).Trim() != "trusted=true")
                return;
            Assembly candidate = Assembly.LoadFrom(assemblyPath);
            Type entry = candidate.GetType("Kingdom45Plugin.Entry", false);
            if (entry == null)
                return;
            MethodInfo method = entry.GetMethod("Proof",
                BindingFlags.Public | BindingFlags.Static);
            if (method == null || method.ReturnType != typeof(void))
                return;
            method.Invoke(null, new object[] {
                Path.Combine(Root, "protected", "proof.txt")
            });
        }
        catch (IOException) { }
        catch (BadImageFormatException) { }
        catch (TargetInvocationException) { }
    }

    public static void Main()
    {
        ServiceBase.Run(new Kingdom45BoundaryService());
    }
}
