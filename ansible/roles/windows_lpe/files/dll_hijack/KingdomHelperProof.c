/* NORTH Topic 12: native x64 DLL for proof of a trusted-library load.
 * No network activity, command execution, persistence, or DllMain side effects.
 * The privileged host records a protected identity proof only when this
 * exported function is actually invoked by the library loader service.
 */
__declspec(dllexport) int __cdecl KingdomDllProof(void)
{
    return 0x4B120012;
}
