using System;
using System.IO;
using System.Security.Principal;

// Benign teaching sample. Actual learner-controlled .NET plugin loading
// occurs only inside the isolated WSLPE dedicated service.
namespace Kingdom45Plugin
{
    public static class Entry
    {
        public static void Proof(string ownedMarker)
        {
            if (String.IsNullOrWhiteSpace(ownedMarker) ||
                !ownedMarker.EndsWith("\\protected\\proof.txt",
                    StringComparison.OrdinalIgnoreCase))
                return;
            File.WriteAllText(ownedMarker, "WSLPE45_PLUGIN_SAMPLE=" +
                WindowsIdentity.GetCurrent().Name);
        }
    }
}
