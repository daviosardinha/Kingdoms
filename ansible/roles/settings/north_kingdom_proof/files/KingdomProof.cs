using System;
using System.IO;
using System.Security.Principal;

// Harmless execution-context proof used by NORTH Windows service exercises.
// No child process, credentials, network traffic or Windows configuration changes.
public static class KingdomProof
{
    public static void Main()
    {
        string output = @"C:\Users\Public\Documents\KingdomProofs\execution-proof.txt";
        Directory.CreateDirectory(Path.GetDirectoryName(output));
        File.AppendAllText(
            output,
            DateTime.UtcNow.ToString("o") + " | " +
            WindowsIdentity.GetCurrent().Name + Environment.NewLine
        );
    }
}
