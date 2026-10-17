using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Principal;

[assembly: ComVisible(false)]

// Windows .NET Framework COM registration teaching sample. A dedicated
// 64-bit RegAsm CLSID and ProgId are created on WSLPE-WS01 only.
namespace Kingdoms45.Com
{
    [Guid("7E86DE4C-10F9-414B-82B5-07CB20264527")]
    [ProgId("Kingdoms45.ComServer")]
    [ComVisible(true)]
    [ClassInterface(ClassInterfaceType.AutoDual)]
    public sealed class Server
    {
        public void Proof()
        {
            const string path =
              @"C:\ProgramData\KingdomsWSLPE45\fixtures\com_clsid_registration_hijack\proof.txt";
            File.WriteAllText(path, "WSLPE45_COM_BASELINE=" +
                WindowsIdentity.GetCurrent().Name);
        }
    }
}
