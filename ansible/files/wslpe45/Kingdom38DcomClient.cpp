// WSLPE #38: learner's fixed-local DCOM IDispatch verifier.
// Source-only. No remote host, registry path or arbitrary object identifier.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <objbase.h>
#include <oaidl.h>
#include <oleauto.h>
#include <stdio.h>
#include <stdlib.h>
#pragma comment(lib, "Ole32.lib")
#pragma comment(lib, "OleAut32.lib")

static const GUID kKingdom38Clsid = {
    0x6ca0f9aa,0x32c9,0x4a81,{0xa3,0x74,0x38,0xe9,0x2c,0x15,0x66,0x11}
};

int wmain(int argc, wchar_t** argv) {
    const bool status = argc == 2 && wcscmp(argv[1],L"--status") == 0;
    const bool proof = argc == 3 && wcscmp(argv[1],L"--proof-nonce") == 0;
    if (!status && !proof) return 2;
    long nonce = 0;
    if (proof) {
        wchar_t* tail = nullptr;
        nonce = wcstol(argv[2], &tail, 10);
        if (!tail || *tail || nonce < 1 || nonce > 999999) return 2;
    }
    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(hr)) return 3;
    IDispatch* server = nullptr;
    hr = CoCreateInstance(kKingdom38Clsid, nullptr, CLSCTX_LOCAL_SERVER,
                          IID_IDispatch, reinterpret_cast<void**>(&server));
    if (FAILED(hr) || !server) { CoUninitialize(); return 4; }
    hr = CoSetProxyBlanket(server, RPC_C_AUTHN_WINNT, RPC_C_AUTHZ_NONE,
                           nullptr, RPC_C_AUTHN_LEVEL_PKT_INTEGRITY,
                           RPC_C_IMP_LEVEL_IDENTIFY, nullptr, EOAC_NONE);
    if (FAILED(hr)) { server->Release(); CoUninitialize(); return 5; }
    LPOLESTR method = const_cast<LPOLESTR>(proof ? L"Proof" : L"Status");
    DISPID id = 0;
    hr = server->GetIDsOfNames(IID_NULL,&method,1,LOCALE_USER_DEFAULT,&id);
    if (FAILED(hr)) { server->Release(); CoUninitialize(); return 6; }
    VARIANTARG request;
    VariantInit(&request);
    request.vt = VT_I4;
    request.lVal = nonce;
    DISPPARAMS params = {};
    params.cArgs = proof ? 1 : 0;
    params.rgvarg = proof ? &request : nullptr;
    VARIANT response;
    VariantInit(&response);
    hr = server->Invoke(id,IID_NULL,LOCALE_USER_DEFAULT,DISPATCH_METHOD,
                         &params,&response,nullptr,nullptr);
    bool accepted = SUCCEEDED(hr) && response.vt == VT_I4 &&
                    response.lVal == (proof ? 1 : 38);
    if (SUCCEEDED(hr) && response.vt == VT_I4) {
        printf("WSLPE38_DCOM_%s=%ld\n", proof ? "PROOF" : "STATUS", response.lVal);
    }
    VariantClear(&response);
    server->Release();
    CoUninitialize();
    return accepted ? 0 : 7;
}
