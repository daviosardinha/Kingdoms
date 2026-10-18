// WSLPE #36: dedicated managed WMI method-provider proof of concept.
// Source only. Provider registration, unique namespace ACLs, service
// identity and exact owned teardown must be independently implemented.
using System;
using System.IO;
using System.Reflection;
using System.Threading;
using System.Security.Principal;
using System.Management.Instrumentation;

[assembly: WmiConfiguration(@"root\KingdomsWSLPE45", HostingModel = ManagementHostingModel.Decoupled)]

namespace KingdomsWSLPE45 {
    [InstrumentationClass(InstrumentationType.Instance)]
    public sealed class Kingdom36Maintenance : Instance {
        [ManagementKey]
        public string Id { get; set; }

        public Kingdom36Maintenance() {
            Id = "Kingdom36Local";
        }

        [ManagementTask]
        public string Status() {
            return "WSLPE45_WMI36_STATUS";
        }

        [ManagementTask]
        public string Proof(uint nonce) {
            // Deliberately flawed per-method authorization: an authenticated
            // local standard user with WMI method access can request that the
            // privileged host write an attacker-selected nonce. This remains
            // strictly bounded to a fixed owned destination (no path/command).
            if (nonce == 0 || nonce > 999999) {
                throw new ArgumentOutOfRangeException("nonce");
            }
            const string folder =
                @"C:\ProgramData\KingdomsWSLPE45\fixtures\wmi_privileged_provider_authorization";
            DirectoryInfo item = new DirectoryInfo(folder);
            if (!item.Exists || (item.Attributes & FileAttributes.ReparsePoint) != 0) {
                throw new DirectoryNotFoundException("Exact owned fixture absent or linked");
            }
            string proof = Path.Combine(folder, "wmi-provider-proof.txt");
            byte[] contents = System.Text.Encoding.ASCII.GetBytes(
                "WSLPE45_WMI36_NONCE=" + nonce.ToString() + "\r\n");
            using (FileStream output = new FileStream(
                proof, FileMode.CreateNew, FileAccess.Write, FileShare.None)) {
                output.Write(contents, 0, contents.Length);
            }
            return "WSLPE45_WMI36_PROOF";
        }
    }

    public static class Kingdom36ProviderHost {
        public static int Main(string[] args) {
            if (args.Length != 1 || args[0] != "--serve-local-provider") return 2;
            // This standalone lab service must be hosted as LocalSystem.
            // Otherwise a learner could run a private copy and forge a proof.
            if (!String.Equals(Environment.MachineName, "WSLPE-WS01",
                               StringComparison.OrdinalIgnoreCase)) return 3;
            using (WindowsIdentity identity = WindowsIdentity.GetCurrent()) {
                if (identity == null || !identity.IsSystem) return 4;
            }
            // Decoupled provider lifetime is finite and cleans only its own
            // assembly and exact instance. Never modify root WMI ACLs here.
            Assembly ownAssembly = Assembly.GetExecutingAssembly();
            Kingdom36Maintenance instance = new Kingdom36Maintenance();
            bool registered = false;
            bool published = false;
            try {
                Instrumentation.RegisterAssembly(ownAssembly);
                registered = true;
                Instrumentation.Publish(instance);
                published = true;
                using (var stop = new ManualResetEvent(false)) {
                    stop.WaitOne(TimeSpan.FromMinutes(30));
                }
                return 0;
            } finally {
                if (published) Instrumentation.Revoke(instance);
                if (registered) InstrumentationManager.UnregisterAssembly(ownAssembly);
            }
        }
    }
}
