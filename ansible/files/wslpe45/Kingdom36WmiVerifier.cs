// WSLPE #36: exact-local WMI consumer for method-authorization qualification.
// No remote target or caller-supplied namespace, path, executable or command.
// Source-only, never invoked in GitHub CI. Needs an independently approved
// owned provider/namespace registration before it can be tested.
using System;
using System.Management;

namespace KingdomsWSLPE45 {
    public static class Kingdom36LocalVerifier {
        public static int Main(string[] args) {
            bool statusOnly = args.Length == 1 && args[0] == "--status";
            bool proof = args.Length == 2 && args[0] == "--proof-nonce";
            if (!statusOnly && !proof) return 2;
            uint nonce = 0;
            if (proof && (!UInt32.TryParse(args[1], out nonce) ||
                          nonce == 0 || nonce > 999999)) return 2;

            try {
                ConnectionOptions options = new ConnectionOptions();
                options.Impersonation = ImpersonationLevel.Impersonate;
                options.Authentication = AuthenticationLevel.PacketIntegrity;
                ManagementScope scope = new ManagementScope(
                    @"\\.\root\KingdomsWSLPE45", options);
                scope.Connect();
                ObjectQuery query = new ObjectQuery(
                    "SELECT * FROM Kingdom36Maintenance WHERE Id='Kingdom36Local'");
                using (ManagementObjectSearcher search =
                       new ManagementObjectSearcher(scope, query)) {
                    ManagementObjectCollection collection = search.Get();
                    int count = 0;
                    foreach (ManagementObject instance in collection) {
                        using (instance) {
                            count++;
                            if (count > 1) return 5;
                            object[] methodArgs =
                                proof ? new object[] {nonce} : new object[0];
                            object reply = instance.InvokeMethod(
                                proof ? "Proof" : "Status", methodArgs);
                            if (reply == null) return 6;
                            Console.WriteLine("WSLPE36_LOCAL_METHOD=" +
                                (proof ? "PROOF" : "STATUS"));
                            Console.WriteLine("WSLPE36_LOCAL_METHOD_RETURN=" + reply);
                        }
                    }
                    return count == 1 ? 0 : 4;
                }
            } catch (ManagementException e) {
                Console.Error.WriteLine("WSLPE36_WMI_ERROR=" + e.ErrorCode);
                return 7;
            } catch (UnauthorizedAccessException) {
                Console.Error.WriteLine("WSLPE36_WMI_ACCESS_DENIED");
                return 8;
            }
        }
    }
}
