// WSLPE #25: bounded Windows Installer repair custom action source.
// Source-only: this DLL is never installed merely by being built.
// The per-machine MSI authoring, privilege tests and owned uninstall are
// separate mandatory gates before this may become a candidate.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <msi.h>
#include <msiquery.h>
#pragma comment(lib, "msi.lib")

extern "C" __declspec(dllexport) UINT __stdcall Kingdom25Repair(MSIHANDLE session) {
    // No shell, no command execution, no caller-selected absolute paths.
    // CustomActionData must be explicitly set by an installed MSI.
    WCHAR data[64] = {};
    DWORD length = static_cast<DWORD>(_countof(data));
    UINT result = MsiGetPropertyW(session, L"CustomActionData", data, &length);
    if (result != ERROR_SUCCESS || lstrcmpW(data, L"WSLPE25-REPAIR") != 0) {
        return ERROR_INSTALL_FAILURE;
    }
    const WCHAR* root = L"C:\\ProgramData\\KingdomsWSLPE45\\fixtures\\msi_repair_custom_action";
    WCHAR proof[MAX_PATH] = {};
    if (swprintf_s(proof, _countof(proof), L"%s\\repair-proof.txt", root) < 0) {
        return ERROR_INSTALL_FAILURE;
    }
    // This marker is bounded to this fixture. A later Windows-native
    // installation contract must verify ACL ownership and reject reparse
    // points before invoking this custom action.
    HANDLE handle = CreateFileW(proof, GENERIC_WRITE, 0, nullptr,
                                CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (handle == INVALID_HANDLE_VALUE) return ERROR_INSTALL_FAILURE;
    const char marker[] = "WSLPE45_MSI_REPAIR_ACTION_INVOKED\r\n";
    DWORD written = 0;
    BOOL ok = WriteFile(handle, marker, sizeof(marker) - 1, &written, nullptr);
    CloseHandle(handle);
    return ok && written == sizeof(marker) - 1 ? ERROR_SUCCESS : ERROR_INSTALL_FAILURE;
}
