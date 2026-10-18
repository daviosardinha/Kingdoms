// Kingdoms WSLPE #38: bounded per-AppID DCOM LocalService fixture.
// SOURCE PROTOTYPE ONLY. No registration, ACL mutation or guest execution.
// Per-AppID LaunchPermission and an exact SCM LocalService are separately owned.
// This server deliberately omits *method* authorization after per-AppID COM
// activation. Its only possible privileged effect is a learner-chosen nonce
// in a fixed scenario-owned proof file (never a path, process, or command).
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <objbase.h>
#include <oaidl.h>
#include <oleauto.h>
#include <stdio.h>
#pragma comment(lib, "Ole32.lib")
#pragma comment(lib, "OleAut32.lib")
#pragma comment(lib, "Advapi32.lib")

static const GUID kKingdom38Clsid = {
    0x6ca0f9aa, 0x32c9, 0x4a81,
    {0xa3,0x74,0x38,0xe9,0x2c,0x15,0x66,0x11}
};
static const wchar_t* kService = L"Kingdom38ComSvc";
static const wchar_t* kProofFolder =
    L"C:\\ProgramData\\KingdomsWSLPE45\\fixtures\\dcom_server_launch_acl";
static const wchar_t* kProofPath =
    L"C:\\ProgramData\\KingdomsWSLPE45\\fixtures\\dcom_server_launch_acl\\dcom-proof.txt";
static HANDLE gStop = nullptr;
static SERVICE_STATUS_HANDLE gStatusHandle = nullptr;
static SERVICE_STATUS gStatus = {};

static long WriteBoundedProof(long nonce) {
    if (nonce <= 0 || nonce > 999999) return -1;
    const DWORD attributes = GetFileAttributesW(kProofFolder);
    if (attributes == INVALID_FILE_ATTRIBUTES ||
        !(attributes & FILE_ATTRIBUTE_DIRECTORY) ||
        (attributes & FILE_ATTRIBUTE_REPARSE_POINT)) return -2;
    HANDLE handle = CreateFileW(kProofPath, GENERIC_WRITE, 0, nullptr,
                                CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (handle == INVALID_HANDLE_VALUE) return -3;
    char marker[80] = {};
    const int size = sprintf_s(marker, sizeof(marker),
        "WSLPE38_DCOM_NONCE=%ld\r\n", nonce);
    DWORD written = 0;
    BOOL ok = size > 0 && WriteFile(handle, marker,
        static_cast<DWORD>(size), &written, nullptr);
    CloseHandle(handle);
    return ok && written == static_cast<DWORD>(size) ? 1 : -4;
}

class Kingdom38Dispatch final : public IDispatch {
    volatile LONG refs_ = 1;
public:
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID id, void** out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (IsEqualIID(id, IID_IUnknown) || IsEqualIID(id, IID_IDispatch)) {
            *out = static_cast<IDispatch*>(this);
            AddRef();
            return S_OK;
        }
        return E_NOINTERFACE;
    }
    ULONG STDMETHODCALLTYPE AddRef() override {
        return static_cast<ULONG>(InterlockedIncrement(&refs_));
    }
    ULONG STDMETHODCALLTYPE Release() override {
        LONG remaining = InterlockedDecrement(&refs_);
        if (remaining == 0) delete this;
        return static_cast<ULONG>(remaining);
    }
    HRESULT STDMETHODCALLTYPE GetTypeInfoCount(UINT* count) override {
        if (!count) return E_POINTER;
        *count = 0; return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetTypeInfo(UINT, LCID, ITypeInfo** out) override {
        if (out) *out = nullptr;
        return E_NOTIMPL;
    }
    HRESULT STDMETHODCALLTYPE GetIDsOfNames(REFIID id, LPOLESTR* names,
                              UINT count, LCID, DISPID* dispid) override {
        if (!IsEqualIID(id, IID_NULL) || count != 1 ||
            !names || !names[0] || !dispid) return DISP_E_UNKNOWNNAME;
        if (lstrcmpiW(names[0], L"Status") == 0) { *dispid=1; return S_OK; }
        if (lstrcmpiW(names[0], L"Proof") == 0) { *dispid=2; return S_OK; }
        return DISP_E_UNKNOWNNAME;
    }
    HRESULT STDMETHODCALLTYPE Invoke(DISPID id, REFIID iid, LCID, WORD flags,
                        DISPPARAMS* args, VARIANT* result,
                        EXCEPINFO*, UINT*) override {
        if (!IsEqualIID(iid, IID_NULL) || !(flags & DISPATCH_METHOD) ||
            !args || !result) return DISP_E_MEMBERNOTFOUND;
        VariantInit(result);
        result->vt = VT_I4;
        if (id == 1 && args->cArgs == 0) {
            result->lVal = 38;
            return S_OK;
        }
        if (id == 2 && args->cArgs == 1 && args->rgvarg &&
            args->rgvarg[0].vt == VT_I4) {
            result->lVal = WriteBoundedProof(args->rgvarg[0].lVal);
            return S_OK;
        }
        return DISP_E_BADPARAMCOUNT;
    }
};

class Kingdom38Factory final : public IClassFactory {
    volatile LONG refs_ = 1;
public:
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (IsEqualIID(iid, IID_IUnknown) || IsEqualIID(iid, IID_IClassFactory)) {
            *out = static_cast<IClassFactory*>(this); AddRef(); return S_OK;
        }
        return E_NOINTERFACE;
    }
    ULONG STDMETHODCALLTYPE AddRef() override {
        return static_cast<ULONG>(InterlockedIncrement(&refs_));
    }
    ULONG STDMETHODCALLTYPE Release() override {
        LONG remaining = InterlockedDecrement(&refs_);
        if (remaining == 0) delete this;
        return static_cast<ULONG>(remaining);
    }
    HRESULT STDMETHODCALLTYPE CreateInstance(IUnknown* outer, REFIID iid,
                                              void** result) override {
        if (!result) return E_POINTER;
        *result = nullptr;
        if (outer) return CLASS_E_NOAGGREGATION;
        Kingdom38Dispatch* instance = new (std::nothrow) Kingdom38Dispatch();
        if (!instance) return E_OUTOFMEMORY;
        HRESULT hr = instance->QueryInterface(iid, result);
        instance->Release();
        return hr;
    }
    HRESULT STDMETHODCALLTYPE LockServer(BOOL) override { return S_OK; }
};

static DWORD WINAPI ServiceControl(DWORD control, DWORD, void*, void*) {
    if (control == SERVICE_CONTROL_STOP && gStop) {
        gStatus.dwCurrentState = SERVICE_STOP_PENDING;
        gStatus.dwControlsAccepted = 0;
        SetServiceStatus(gStatusHandle, &gStatus);
        SetEvent(gStop);
        return NO_ERROR;
    }
    return ERROR_CALL_NOT_IMPLEMENTED;
}
static void WINAPI ServiceMain(DWORD, LPWSTR*) {
    gStatusHandle = RegisterServiceCtrlHandlerExW(kService, ServiceControl, nullptr);
    if (!gStatusHandle) return;
    gStatus.dwServiceType = SERVICE_WIN32_OWN_PROCESS;
    gStatus.dwCurrentState = SERVICE_START_PENDING;
    gStatus.dwWin32ExitCode = NO_ERROR;
    SetServiceStatus(gStatusHandle, &gStatus);
    gStop = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (!gStop) { gStatus.dwWin32ExitCode = ERROR_NOT_ENOUGH_MEMORY; goto done; }
    {
        HRESULT init = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
        if (FAILED(init)) { gStatus.dwWin32ExitCode = ERROR_INVALID_STATE; goto done; }
        HRESULT security = CoInitializeSecurity(nullptr, -1, nullptr, nullptr,
            RPC_C_AUTHN_LEVEL_PKT_INTEGRITY, RPC_C_IMP_LEVEL_IDENTIFY,
            nullptr, EOAC_NONE, nullptr);
        if (FAILED(security)) {
            gStatus.dwWin32ExitCode = ERROR_ACCESS_DENIED;
            CoUninitialize();
            goto done;
        }
        Kingdom38Factory* factory = new (std::nothrow) Kingdom38Factory();
        if (!factory) {
            gStatus.dwWin32ExitCode = ERROR_NOT_ENOUGH_MEMORY;
            CoUninitialize(); goto done;
        }
        DWORD cookie = 0;
        HRESULT registered = CoRegisterClassObject(kKingdom38Clsid,
            static_cast<IUnknown*>(factory), CLSCTX_LOCAL_SERVER,
            REGCLS_MULTIPLEUSE, &cookie);
        factory->Release();
        if (FAILED(registered)) {
            gStatus.dwWin32ExitCode = ERROR_ACCESS_DENIED;
            CoUninitialize(); goto done;
        }
        gStatus.dwCurrentState = SERVICE_RUNNING;
        gStatus.dwControlsAccepted = SERVICE_ACCEPT_STOP;
        SetServiceStatus(gStatusHandle, &gStatus);
        WaitForSingleObject(gStop, 12 * 60 * 1000);
        CoRevokeClassObject(cookie);
        CoUninitialize();
    }
done:
    if (gStop) { CloseHandle(gStop); gStop = nullptr; }
    gStatus.dwCurrentState = SERVICE_STOPPED;
    gStatus.dwControlsAccepted = 0;
    SetServiceStatus(gStatusHandle, &gStatus);
}
int wmain(int argc, wchar_t**) {
    if (argc != 1) return 2;
    SERVICE_TABLE_ENTRYW table[] = {
        { const_cast<LPWSTR>(kService), ServiceMain },
        { nullptr, nullptr }
    };
    return StartServiceCtrlDispatcherW(table) ? 0 : 3;
}
