// WSLPE #40: owned, localhost-only Windows RPC authentication/authorization lab.
// Source-only; the batch does not start or install this server.
// The intended bug is a missing per-method privilege check after caller
// authentication. The only effect is a caller-chosen nonce written to an
// existing, protected, scenario-owned proof file (CREATE_NEW, no replacement).
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <rpc.h>
#include <rpcdce.h>
#include <stdio.h>
#include <stdlib.h>
#include <vector>
#include "Kingdom40LocalRpc.h"
#pragma comment(lib, "Rpcrt4.lib")

extern "C" void* __RPC_USER midl_user_allocate(size_t n) { return malloc(n); }
extern "C" void __RPC_USER midl_user_free(void* p) { free(p); }

static const wchar_t* kEndpoint = L"KingdomsWSLPE40";
static const wchar_t* kFixture =
    L"C:\\ProgramData\\KingdomsWSLPE45\\fixtures\\custom_rpc_authorization";
static const wchar_t* kProof =
    L"C:\\ProgramData\\KingdomsWSLPE45\\fixtures\\custom_rpc_authorization\\rpc-proof.txt";

static bool IsExactLocalLearner(handle_t binding) {
    // This checks who called, but intentionally fails to check if a standard
    // user is authorized for the privileged proof operation.
    RPC_STATUS status = RpcImpersonateClient(binding);
    if (status != RPC_S_OK) return false;
    bool matched = false;
    HANDLE token = nullptr;
    if (OpenThreadToken(GetCurrentThread(), TOKEN_QUERY, TRUE, &token)) {
        DWORD required = 0;
        GetTokenInformation(token, TokenUser, nullptr, 0, &required);
        if (required > 0 && required <= 4096) {
            std::vector<BYTE> details(required);
            if (GetTokenInformation(token, TokenUser, details.data(),
                                    required, &required)) {
                BYTE learnerSid[SECURITY_MAX_SID_SIZE] = {};
                DWORD learnerLength = sizeof(learnerSid);
                wchar_t authority[256] = {};
                DWORD authorityLength = 256;
                SID_NAME_USE usage = SidTypeUnknown;
                if (LookupAccountNameW(nullptr, L"WSLPE-WS01\\lpe.trainee",
                                       learnerSid, &learnerLength,
                                       authority, &authorityLength, &usage)) {
                    const auto* user =
                        reinterpret_cast<TOKEN_USER*>(details.data());
                    matched = EqualSid(user->User.Sid, learnerSid) != 0;
                }
            }
        }
        CloseHandle(token);
    }
    RpcRevertToSelf();
    return matched;
}

void Kingdom40Status(handle_t binding, long* result) {
    if (!result) return;
    *result = IsExactLocalLearner(binding) ? 40 : -1;
}

void Kingdom40OwnedProof(handle_t binding, unsigned long nonce, long* result) {
    if (!result) return;
    *result = -1;
    if (!IsExactLocalLearner(binding) || nonce == 0 || nonce > 999999) return;

    // No root creation or caller-controlled paths. The owned fixture must
    // already exist with protected parent ACLs; guest validation is separate.
    DWORD attributes = GetFileAttributesW(kFixture);
    if (attributes == INVALID_FILE_ATTRIBUTES ||
        (attributes & FILE_ATTRIBUTE_DIRECTORY) == 0 ||
        (attributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0) return;

    HANDLE proof = CreateFileW(kProof, GENERIC_WRITE, 0, nullptr, CREATE_NEW,
                              FILE_ATTRIBUTE_NORMAL, nullptr);
    if (proof == INVALID_HANDLE_VALUE) return;
    char output[80] = {};
    const int count = sprintf_s(output, sizeof(output),
                                "WSLPE40_LOCAL_RPC_NONCE=%lu\r\n", nonce);
    DWORD written = 0;
    const BOOL ok = count > 0 &&
        WriteFile(proof, output, static_cast<DWORD>(count), &written, nullptr);
    CloseHandle(proof);
    *result = ok && written == static_cast<DWORD>(count) ? 1 : -2;
}

int wmain(int argc, wchar_t** argv) {
    if (argc != 2 || wcscmp(argv[1], L"--serve-local-only") != 0) return 2;
    RPC_STATUS rc = RpcServerUseProtseqEpW(
        reinterpret_cast<RPC_WSTR>(const_cast<wchar_t*>(L"ncalrpc")),
        RPC_C_PROTSEQ_MAX_REQS_DEFAULT,
        reinterpret_cast<RPC_WSTR>(const_cast<wchar_t*>(kEndpoint)), nullptr);
    if (rc != RPC_S_OK) return 3;
    rc = RpcServerRegisterAuthInfoW(nullptr, RPC_C_AUTHN_WINNT, nullptr, nullptr);
    if (rc != RPC_S_OK) return 4;
    rc = RpcServerRegisterIf2(Kingdom40LocalRpc_v1_0_s_ifspec, nullptr, nullptr,
                              RPC_IF_ALLOW_LOCAL_ONLY | RPC_IF_ALLOW_SECURE_ONLY,
                              8, static_cast<unsigned>(-1), nullptr);
    if (rc != RPC_S_OK) return 5;
    // FALSE is essential: synchronous/TRUE listen never reaches the
    // bounded host lifetime or owned cleanup without an external stop.
    rc = RpcServerListen(1, 8, FALSE);
    if (rc != RPC_S_OK) return 6;
    // Finite guest-console session, not an installed service.
    Sleep(12 * 60 * 1000);
    const RPC_STATUS stopped = RpcMgmtStopServerListening(nullptr);
    const RPC_STATUS unregistered =
        RpcServerUnregisterIf(Kingdom40LocalRpc_v1_0_s_ifspec, nullptr, TRUE);
    return (stopped == RPC_S_OK && unregistered == RPC_S_OK) ? 0 : 7;
}
