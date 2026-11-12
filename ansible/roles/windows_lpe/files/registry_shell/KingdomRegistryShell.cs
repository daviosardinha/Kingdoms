using System;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.ServiceProcess;
using System.Text;
using System.Threading;

// NORTH Topic 10 lab helper.
// Intentionally limited to the WS01 training machine, NORTH\rickon.stark,
// and the KingdomRegistrySvc service name. No network listener or self-installation.
internal sealed class KingdomRegistryShell : ServiceBase
{
    private readonly object gate = new object();
    private Thread retryThread;
    private volatile bool stopping;
    private bool launched;

    public KingdomRegistryShell()
    {
        ServiceName = "KingdomRegistrySvc";
        CanStop = true;
        CanHandleSessionChangeEvent = true;
    }

    protected override void OnStart(string[] args)
    {
        if (!Environment.MachineName.Equals("WS01", StringComparison.OrdinalIgnoreCase) ||
            !WindowsIdentity.GetCurrent().IsSystem)
            return;

        retryThread = new Thread(RetryUntilSessionAppears);
        retryThread.IsBackground = true;
        retryThread.Start();
    }

    protected override void OnStop()
    {
        stopping = true;
    }

    protected override void OnSessionChange(SessionChangeDescription change)
    {
        base.OnSessionChange(change);
        if (change.Reason == SessionChangeReason.SessionLogon ||
            change.Reason == SessionChangeReason.SessionUnlock ||
            change.Reason == SessionChangeReason.RemoteConnect)
            TryLaunch();
    }

    private void RetryUntilSessionAppears()
    {
        // Remain a normal service while waiting for Rickon's first RDP logon.
        // The session-change handler continues to work after this retry window.
        for (int i = 0; i < 360 && !stopping; i++)
        {
            TryLaunch();
            Thread.Sleep(5000);
        }
    }

    private void TryLaunch()
    {
        if (stopping)
            return;
        lock (gate)
        {
            if (launched || stopping)
                return;

            int sessionId = FindRickonSession();
            if (sessionId < 0)
                return;
            launched = StartSystemCmdInSession(sessionId);
        }
    }

    private static int FindRickonSession()
    {
        IntPtr list = IntPtr.Zero;
        int count = 0;
        if (!WTSEnumerateSessions(IntPtr.Zero, 0, 1, out list, out count))
            return -1;
        try
        {
            int stride = Marshal.SizeOf(typeof(WTS_SESSION_INFO));
            for (int i = 0; i < count; i++)
            {
                IntPtr item = new IntPtr(list.ToInt64() + (long)i * stride);
                WTS_SESSION_INFO info = (WTS_SESSION_INFO)Marshal.PtrToStructure(item, typeof(WTS_SESSION_INFO));
                if (info.State != 0) // WTSActive
                    continue;
                string user = ReadSessionString(info.SessionID, 5);   // WTSUserName
                string domain = ReadSessionString(info.SessionID, 7); // WTSDomainName
                if (user.Equals("rickon.stark", StringComparison.OrdinalIgnoreCase) &&
                    domain.Equals("NORTH", StringComparison.OrdinalIgnoreCase))
                    return info.SessionID;
            }
        }
        finally
        {
            WTSFreeMemory(list);
        }
        return -1;
    }

    private static string ReadSessionString(int sessionId, int property)
    {
        IntPtr value = IntPtr.Zero;
        int bytes = 0;
        if (!WTSQuerySessionInformation(IntPtr.Zero, sessionId, property, out value, out bytes))
            return String.Empty;
        try
        {
            return value == IntPtr.Zero ? String.Empty : (Marshal.PtrToStringUni(value) ?? String.Empty);
        }
        finally
        {
            if (value != IntPtr.Zero)
                WTSFreeMemory(value);
        }
    }

    private static bool EnablePrivilege(IntPtr token, string name)
    {
        LUID luid;
        if (!LookupPrivilegeValue(null, name, out luid))
            return false;
        TOKEN_PRIVILEGES privilege = new TOKEN_PRIVILEGES();
        privilege.PrivilegeCount = 1;
        privilege.Luid = luid;
        privilege.Attributes = 0x2; // SE_PRIVILEGE_ENABLED
        return AdjustTokenPrivileges(token, false, ref privilege, 0, IntPtr.Zero, IntPtr.Zero) &&
               Marshal.GetLastWin32Error() != 1300;
    }

    private static bool StartSystemCmdInSession(int sessionId)
    {
        IntPtr systemToken = IntPtr.Zero;
        IntPtr sessionToken = IntPtr.Zero;
        try
        {
            if (!OpenProcessToken(GetCurrentProcess(), 0xF01FF, out systemToken))
                return false;

            EnablePrivilege(systemToken, "SeTcbPrivilege");
            EnablePrivilege(systemToken, "SeAssignPrimaryTokenPrivilege");
            EnablePrivilege(systemToken, "SeIncreaseQuotaPrivilege");

            if (!DuplicateTokenEx(systemToken, 0xF01FF, IntPtr.Zero, 2, 1, out sessionToken))
                return false;
            if (!SetTokenInformation(sessionToken, 12, ref sessionId, sizeof(int)))
                return false;

            STARTUPINFO startup = new STARTUPINFO();
            startup.cb = Marshal.SizeOf(typeof(STARTUPINFO));
            startup.lpDesktop = @"winsta0\default";
            startup.dwFlags = 0x1; // STARTF_USESHOWWINDOW
            startup.wShowWindow = 5; // SW_SHOW

            PROCESS_INFORMATION process;
            string executable = @"C:\Windows\System32\cmd.exe";
            StringBuilder commandLine =
                new StringBuilder("\"" + executable + "\" /k title NORTH_KINGDOM_SYSTEM_SHELL");
            bool success = CreateProcessAsUser(
                sessionToken, executable, commandLine, IntPtr.Zero, IntPtr.Zero, false,
                0x10, IntPtr.Zero, @"C:\Windows\System32", ref startup, out process);
            if (!success)
                return false;

            CloseHandle(process.hThread);
            CloseHandle(process.hProcess);
            return true;
        }
        finally
        {
            if (sessionToken != IntPtr.Zero)
                CloseHandle(sessionToken);
            if (systemToken != IntPtr.Zero)
                CloseHandle(systemToken);
        }
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct WTS_SESSION_INFO
    {
        public int SessionID;
        [MarshalAs(UnmanagedType.LPWStr)]
        public string WinStationName;
        public int State;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct LUID { public uint LowPart; public int HighPart; }

    [StructLayout(LayoutKind.Sequential)]
    private struct TOKEN_PRIVILEGES
    {
        public int PrivilegeCount;
        public LUID Luid;
        public int Attributes;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct STARTUPINFO
    {
        public int cb;
        public string lpReserved;
        public string lpDesktop;
        public string lpTitle;
        public int dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars;
        public int dwFillAttribute, dwFlags;
        public short wShowWindow, cbReserved2;
        public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct PROCESS_INFORMATION
    {
        public IntPtr hProcess, hThread;
        public int dwProcessId, dwThreadId;
    }

    [DllImport("wtsapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool WTSEnumerateSessions(
        IntPtr server, int reserved, int version, out IntPtr sessions, out int count);

    [DllImport("wtsapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool WTSQuerySessionInformation(
        IntPtr server, int session, int property, out IntPtr buffer, out int bytes);

    [DllImport("wtsapi32.dll")]
    private static extern void WTSFreeMemory(IntPtr memory);

    [DllImport("kernel32.dll")]
    private static extern IntPtr GetCurrentProcess();

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool OpenProcessToken(IntPtr process, int access, out IntPtr token);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool DuplicateTokenEx(
        IntPtr token, int access, IntPtr attributes, int impersonationLevel, int tokenType, out IntPtr duplicate);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetTokenInformation(IntPtr token, int infoClass, ref int info, int size);

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool LookupPrivilegeValue(string system, string name, out LUID luid);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool AdjustTokenPrivileges(
        IntPtr token, [MarshalAs(UnmanagedType.Bool)] bool disableAll,
        ref TOKEN_PRIVILEGES privileges, int bufferLength, IntPtr previousState, IntPtr returnLength);

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CreateProcessAsUser(
        IntPtr token, string application, StringBuilder commandLine, IntPtr processAttributes,
        IntPtr threadAttributes, [MarshalAs(UnmanagedType.Bool)] bool inheritHandles,
        int creationFlags, IntPtr environment, string currentDirectory,
        ref STARTUPINFO startup, out PROCESS_INFORMATION process);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CloseHandle(IntPtr handle);

    public static void Main()
    {
        ServiceBase.Run(new KingdomRegistryShell());
    }
}
