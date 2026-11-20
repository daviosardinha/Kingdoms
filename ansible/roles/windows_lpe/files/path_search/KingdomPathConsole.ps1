# NORTH Topic 13. Rickon's local view of the SYSTEM command process.
# Named pipe only. No sockets, C2, remote callbacks, or token impersonation.
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if ($identity.User.Value -eq 'S-1-5-18') {
    throw 'Run the Topic 13 console as Rickon, not as SYSTEM.'
}
$source = @'
using System;
using System.IO;
using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using System.Threading;

public static class KingdomPathConsole
{
    private const string PipeName = "KingdomsTopic13Console";
    private const int ConnectionTimeoutMs = 150000;

    private static void ReadOutput(StreamReader reader)
    {
        char[] block = new char[1024];
        try
        {
            int n;
            while ((n = reader.Read(block, 0, block.Length)) > 0)
            {
                Console.Out.Write(block, 0, n);
                Console.Out.Flush();
            }
        }
        catch (IOException) { }
        catch (ObjectDisposedException) { }
    }

    public static void Run()
    {
        SecurityIdentifier user = WindowsIdentity.GetCurrent().User;
        SecurityIdentifier system = new SecurityIdentifier("S-1-5-18");

        PipeSecurity security = new PipeSecurity();
        security.AddAccessRule(new PipeAccessRule(
            user, PipeAccessRights.FullControl, AccessControlType.Allow));
        security.AddAccessRule(new PipeAccessRule(
            system, PipeAccessRights.FullControl, AccessControlType.Allow));

        using (NamedPipeServerStream pipe = new NamedPipeServerStream(
            PipeName, PipeDirection.InOut, 1, PipeTransmissionMode.Byte,
            PipeOptions.Asynchronous, 4096, 4096, security))
        {
            Console.WriteLine("Viewer runs as: " + WindowsIdentity.GetCurrent().Name);
            Console.WriteLine("Waiting for the Topic 13 service helper (local pipe only)...");
            IAsyncResult pending = pipe.BeginWaitForConnection(null, null);
            try
            {
                if (!pending.AsyncWaitHandle.WaitOne(ConnectionTimeoutMs))
                {
                    throw new TimeoutException("No Topic 13 helper connected in 150 seconds.");
                }
                pipe.EndWaitForConnection(pending);
            }
            finally { pending.AsyncWaitHandle.Close(); }

            using (StreamReader reader = new StreamReader(
                pipe, new UTF8Encoding(false), true, 1024, true))
            using (StreamWriter writer = new StreamWriter(
                pipe, new UTF8Encoding(false), 1024, true))
            {
                // The client must write first. This allows Windows to expose
                // the client's actual identity, rather than trusting a string
                // that an unprivileged process could claim to be SYSTEM.
                string greeting = reader.ReadLine();
                if (greeting != "KINGDOMS_TOPIC13_HELLO")
                    throw new UnauthorizedAccessException("Unrecognized local pipe client.");

                string clientName = pipe.GetImpersonationUserName();
                if (String.IsNullOrEmpty(clientName))
                    throw new UnauthorizedAccessException("Cannot verify the pipe client identity.");

                SecurityIdentifier clientSid = (SecurityIdentifier)
                    new NTAccount(clientName).Translate(typeof(SecurityIdentifier));
                if (clientSid.Value != "S-1-5-18")
                    throw new UnauthorizedAccessException("Pipe client is not LocalSystem.");

                writer.AutoFlush = true;
                writer.WriteLine("KINGDOMS_TOPIC13_APPROVED");

                Console.WriteLine("Verified local pipe client: NT AUTHORITY\\SYSTEM");
                Console.WriteLine("Type 'whoami' to verify live execution, or /quit to disconnect.");
                Thread output = new Thread(() => ReadOutput(reader));
                output.IsBackground = true;
                output.Start();

                try
                {
                    string command;
                    while (true)
                    {
                        Console.Write("SYSTEM> ");
                        command = Console.ReadLine();
                        if (command == null || command.Trim().Equals("/quit", StringComparison.OrdinalIgnoreCase))
                        {
                            writer.WriteLine("::kingdom-close::");
                            break;
                        }
                        writer.WriteLine(command);
                    }
                }
                catch (IOException) { }
                catch (ObjectDisposedException) { }
            }
        }
        Console.WriteLine("Topic 13 local command channel closed.");
    }
}
'@
Add-Type -TypeDefinition $source -Language CSharp -ReferencedAssemblies 'System.dll', 'System.Core.dll' -ErrorAction Stop
[KingdomPathConsole]::Run()
