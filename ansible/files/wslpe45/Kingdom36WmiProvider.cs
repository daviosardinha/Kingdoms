// WSLPE #36: dedicated managed WMI method-provider proof of concept.
// Source only. Provider registration, unique namespace ACLs, service
// identity and exact owned teardown must be independently implemented.
using System;
using System.IO;
using System.Reflection;
using System.Threading;
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
        public string Proof() {
            // Strictly bounded teaching proof; no user-provided paths,
            // command execution, or access to unrelated WMI namespaces.
            const string folder =
                @"C:\ProgramData\KingdomsWSLPE45\fixtures\wmi_privileged_provider_authorization";
            if (!Directory.Exists(folder)) {
                throw new DirectoryNotFoundException("Exact owned fixture absent");
            }
            string proof = Path.Combine(folder, "wmi-provider-proof.txt");
            File.WriteAllText(proof, "WSLPE45_WMI36_PROVIDER_INVOKED");
            return "WSLPE45_WMI36_PROOF";
        }
    }

    public static class Kingdom36ProviderHost {
        public static int Main(string[] args) {
            if (args.Length != 1 || args[0] != "--serve-local-provider") return 2;
            Instrumentation.RegisterAssembly(Assembly.GetExecutingAssembly());
            Instrumentation.Publish(new Kingdom36Maintenance());
            using (var stop = new ManualResetEvent(false)) {
                stop.WaitOne(TimeSpan.FromMinutes(30));
            }
            return 0;
        }
    }
}
