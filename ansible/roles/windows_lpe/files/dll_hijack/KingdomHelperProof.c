/* NORTH Topic 12: native x64 DLL with a visible, non-shell SYSTEM proof.
 * Loads only through the lab-specific KingdomDllSvc exported-function contract.
 * No command execution, token duplication, persistence, or network activity.
 * The service's execution token is checked before showing a message in
 * NORTH\rickon.stark's active RDP session.
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
typedef struct { void *Sid; DWORD Attributes; } SID_AND_ATTRIBUTES;
typedef struct { SID_AND_ATTRIBUTES User; } TOKEN_USER;
typedef struct { DWORD SessionId; LPWSTR WinStationName; int State; } WTS_SESSION_INFOW;

#define DLL __declspec(dllimport)
DLL BOOL __stdcall GetComputerNameW(LPWSTR, DWORD *);
DLL int __stdcall lstrcmpiW(LPCWSTR, LPCWSTR);
DLL HANDLE __stdcall GetCurrentProcess(void);
DLL BOOL __stdcall CloseHandle(HANDLE);
DLL HLOCAL __stdcall LocalFree(HLOCAL);
DLL BOOL __stdcall OpenProcessToken(HANDLE, DWORD, HANDLE *);
DLL BOOL __stdcall GetTokenInformation(HANDLE, int, LPVOID, DWORD, DWORD *);
DLL BOOL __stdcall ConvertSidToStringSidW(void *, LPWSTR *);
DLL BOOL __stdcall WTSEnumerateSessionsW(HANDLE, DWORD, DWORD, WTS_SESSION_INFOW **, DWORD *);
DLL BOOL __stdcall WTSQuerySessionInformationW(HANDLE, DWORD, int, LPWSTR *, DWORD *);
DLL BOOL __stdcall WTSSendMessageW(HANDLE, DWORD, LPWSTR, DWORD, LPWSTR, DWORD,
                                   DWORD, DWORD, DWORD *, BOOL);
DLL void __stdcall WTSFreeMemory(LPVOID);

#define TOKEN_QUERY 0x0008u
#define WTS_ACTIVE 0
#define WTS_USER_NAME 5
#define WTS_DOMAIN_NAME 7

static int process_is_system(void)
{
    HANDLE token = (HANDLE)0;
    BYTE buffer[512];
    DWORD size = 0;
    LPWSTR sid = (LPWSTR)0;
    int result = 0;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) return 0;
    if (GetTokenInformation(token, 1, buffer, sizeof(buffer), &size) &&
        ConvertSidToStringSidW(((TOKEN_USER *)buffer)->User.Sid, &sid)) {
        result = (lstrcmpiW(sid, L"S-1-5-18") == 0);
        LocalFree((HLOCAL)sid);
    }
    CloseHandle(token);
    return result;
}

/* For this specific training lab, a separate native DLL supplies
 * immediate user-visible evidence. This never opens a shell. */
__declspec(dllexport) int __cdecl KingdomDllProof(void)
{
    WCHAR computer[64];
    DWORD size = 64, count = 0, i;
    WTS_SESSION_INFOW *sessions = (WTS_SESSION_INFOW *)0;
    int delivered = 0;
    static WCHAR title[] = L"NORTH | DLL Hijacking proof";
    static WCHAR message[] = L"KingdomHelper.dll was loaded by KingdomDllSvc running as NT AUTHORITY\\SYSTEM. This is a code-execution proof, not a SYSTEM CMD.";

    if (!GetComputerNameW(computer, &size) ||
        lstrcmpiW(computer, L"WS01") != 0 || !process_is_system())
        return 0;

    if (!WTSEnumerateSessionsW((HANDLE)0, 0, 1, &sessions, &count)) return 0;
    for (i = 0; i < count; ++i) {
        LPWSTR user = (LPWSTR)0, domain = (LPWSTR)0;
        DWORD user_size = 0, domain_size = 0, response = 0;
        BOOL user_ok, domain_ok;
        if (sessions[i].State != WTS_ACTIVE) continue;
        user_ok = WTSQuerySessionInformationW((HANDLE)0, sessions[i].SessionId,
                                               WTS_USER_NAME, &user, &user_size);
        domain_ok = WTSQuerySessionInformationW((HANDLE)0, sessions[i].SessionId,
                                                 WTS_DOMAIN_NAME, &domain, &domain_size);
        if (user_ok && domain_ok && user && domain &&
            lstrcmpiW(user, L"rickon.stark") == 0 &&
            lstrcmpiW(domain, L"NORTH") == 0) {
            delivered = WTSSendMessageW((HANDLE)0, sessions[i].SessionId,
                                        title, sizeof(title), message, sizeof(message),
                                        0x40u, 10, &response, 0);
        }
        if (user) WTSFreeMemory(user);
        if (domain) WTSFreeMemory(domain);
        if (delivered) break;
    }
    if (sessions) WTSFreeMemory(sessions);
    return delivered ? 0x4B120012 : 0;
}
