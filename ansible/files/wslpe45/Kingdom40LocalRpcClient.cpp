// WSLPE #40: explicit local-only RPC learner verifier. No remote target option.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <rpc.h>
#include <rpcdce.h>
#include <stdio.h>
#include <stdlib.h>
#include "Kingdom40LocalRpc.h"
#pragma comment(lib, "Rpcrt4.lib")

extern "C" void* __RPC_USER midl_user_allocate(size_t n) { return malloc(n); }
extern "C" void __RPC_USER midl_user_free(void* p) { free(p); }

int wmain(int argc, wchar_t** argv) {
    if (argc != 2 && argc != 3) return 2;
    const bool statusOnly = argc == 2 && wcscmp(argv[1], L"--status") == 0;
    const bool proof = argc == 3 && wcscmp(argv[1], L"--proof-nonce") == 0;
    if (!statusOnly && !proof) return 2;
    unsigned long nonce = 0;
    if (proof) {
        wchar_t* remaining = nullptr;
        nonce = wcstoul(argv[2], &remaining, 10);
        if (!remaining || *remaining != 0 || nonce == 0 || nonce > 999999) return 2;
    }

    RPC_WSTR text = nullptr;
    RPC_STATUS rc = RpcStringBindingComposeW(
        nullptr,
        reinterpret_cast<RPC_WSTR>(const_cast<wchar_t*>(L"ncalrpc")), nullptr,
        reinterpret_cast<RPC_WSTR>(const_cast<wchar_t*>(L"KingdomsWSLPE40")),
        nullptr, &text);
    if (rc != RPC_S_OK) return 3;

    handle_t binding = nullptr;
    rc = RpcBindingFromStringBindingW(text, &binding);
    RpcStringFreeW(&text);
    if (rc != RPC_S_OK || !binding) return 4;

    rc = RpcBindingSetAuthInfoW(binding, nullptr, RPC_C_AUTHN_LEVEL_PKT_INTEGRITY,
                                RPC_C_AUTHN_WINNT, nullptr, RPC_C_AUTHZ_NONE);
    if (rc != RPC_S_OK) { RpcBindingFree(&binding); return 5; }

    long value = -1;
    bool completed = false;
    RpcTryExcept {
        if (statusOnly) Kingdom40Status(binding, &value);
        else Kingdom40OwnedProof(binding, nonce, &value);
        completed = true;
    }
    RpcExcept(1) { completed = false; }
    RpcEndExcept;

    RpcBindingFree(&binding);
    if (!completed) return 6;
    printf("WSLPE40_RPC_%s=%ld\n", statusOnly ? "STATUS" : "PROOF", value);
    return (statusOnly && value == 40) || (proof && value == 1) ? 0 : 7;
}
