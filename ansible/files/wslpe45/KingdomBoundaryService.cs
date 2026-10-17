using System;
using System.IO;
using System.IO.Pipes;
using System.Net;
using System.Security.AccessControl;
using System.Security.Principal;
using System.ServiceProcess;
using System.Text;
using System.Threading;

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
                    PipeTransmissionMode.Byte, PipeOptions.None,
                    1024, 1024, acl))
                {
                    pipe.WaitForConnection();
                    pipe.ReadTimeout = 3000;
                    using (StreamReader reader = new StreamReader(
                        pipe, Encoding.ASCII, false, 256, true))
                    using (StreamWriter writer = new StreamWriter(
                        pipe, Encoding.ASCII, 256, true))
                    {
                        string request = reader.ReadLine();
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

    public static void Main()
    {
        ServiceBase.Run(new Kingdom45BoundaryService());
    }
}
