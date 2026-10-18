// WSLPE #25: bounded Windows Installer repair custom action source.
// Source-only: this DLL is never installed merely by being built.
// The per-machine MSI authoring, privilege tests and owned uninstall are
// separate mandatory gates before this may become a candidate.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <msi.h>
#include <msiquery.h>
#include <stdio.h>
#pragma comment(lib, "msi.lib")

extern "C" __declspec(dllexport) UINT __stdcall Kingdom25Repair(MSIHANDLE session) {
    // No shell, no command execution, no caller-selected absolute paths.
    // CustomActionData must be explicitly set by an installed MSI.
    WCHAR data[64] = {};
    DWORD length = static_cast<DWORD>(64);
    UINT result = MsiGetPropertyW(session, L"CustomActionData", data, &length);
    if (result != ERROR_SUCCESS || lstrcmpW(data, L"WSLPE25-REPAIR") != 0) {
        return ERROR_INSTALL_FAILURE;
    }
    // Bounded learner control: only a six-digit nonce in one existing,
    // fixed, administrator-created request file. No path/command injection.
    const WCHAR* root =
        L"C:\\ProgramData\\KingdomsWSLPE45\\fixtures\\msi_repair_custom_action";
    const DWORD rootAttr = GetFileAttributesW(root);
    if (rootAttr == INVALID_FILE_ATTRIBUTES ||
        !(rootAttr & FILE_ATTRIBUTE_DIRECTORY) ||
        (rootAttr & FILE_ATTRIBUTE_REPARSE_POINT)) return ERROR_INSTALL_FAILURE;

    WCHAR request[MAX_PATH] = {};
    WCHAR proof[MAX_PATH] = {};
    if (swprintf_s(request, MAX_PATH, L"%s\\repair-request.txt", root) < 0 ||
        swprintf_s(proof, MAX_PATH, L"%s\\repair-proof.txt", root) < 0)
        return ERROR_INSTALL_FAILURE;

    HANDLE source = CreateFileW(request, GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING,
        FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
    if (source == INVALID_HANDLE_VALUE) return ERROR_INSTALL_FAILURE;
    BY_HANDLE_FILE_INFORMATION attributes = {};
    LARGE_INTEGER count = {};
    BOOL safe = GetFileInformationByHandle(source, &attributes) &&
        !(attributes.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) &&
        !(attributes.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) &&
        GetFileSizeEx(source, &count) && count.QuadPart >= 1 &&
        count.QuadPart <= 6;
    char requestBytes[7] = {};
    DWORD read = 0;
    if (safe) safe = ReadFile(source, requestBytes,
        static_cast<DWORD>(count.QuadPart), &read, nullptr) &&
        read == static_cast<DWORD>(count.QuadPart);
    CloseHandle(source);
    if (!safe) return ERROR_INSTALL_FAILURE;

    unsigned long nonce = 0;
    for (DWORD i = 0; i < read; ++i) {
        if (requestBytes[i] < '0' || requestBytes[i] > '9')
            return ERROR_INSTALL_FAILURE;
        nonce = nonce * 10 + static_cast<unsigned long>(requestBytes[i] - '0');
    }
    if (nonce == 0 || nonce > 999999) return ERROR_INSTALL_FAILURE;

    // No overwrite, even if a prior run produced a marker. Only the
    // administrator-owned reset may clear the original proof object.
    HANDLE handle = CreateFileW(proof, GENERIC_WRITE, 0, nullptr,
                                CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (handle == INVALID_HANDLE_VALUE) return ERROR_INSTALL_FAILURE;
    char marker[64] = {};
    const int markerLength = sprintf_s(marker, sizeof(marker),
        "WSLPE45_MSI_REPAIR_NONCE=%lu\r\n", nonce);
    DWORD written = 0;
    BOOL ok = markerLength > 0 && WriteFile(handle, marker,
        static_cast<DWORD>(markerLength), &written, nullptr);
    CloseHandle(handle);
    return ok && written == static_cast<DWORD>(markerLength) ?
        ERROR_SUCCESS : ERROR_INSTALL_FAILURE;
}
