#!/usr/bin/env bash
# Rebuild NORTH Topic 12's fixed-command native x64 proof DLL.
# Requires clang-cl, lld-link and Python 3. No Windows guest needed.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/ansible/roles/windows_lpe/files/dll_hijack/KingdomHelperProof.c"
DST="$ROOT/ansible/roles/windows_lpe/files/dll_hijack/KingdomHelperProof.dll.gz.b64"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
for dep in clang-cl lld-link python3; do
  command -v "$dep" >/dev/null || { echo "Missing $dep" >&2; exit 1; }
done
cat > "$TMP/kernel32.def" <<'DEF'
LIBRARY kernel32.dll
EXPORTS
 GetComputerNameW
 lstrcmpiW
 GetCurrentProcess
 CloseHandle
 LocalFree
 CreateFileW
 CreatePipe
 SetHandleInformation
 CreateProcessW
 ReadFile
 WriteFile
 WaitForSingleObject
 GetExitCodeProcess
 FlushFileBuffers
DEF
cat > "$TMP/advapi32.def" <<'DEF'
LIBRARY advapi32.dll
EXPORTS
 OpenProcessToken
 GetTokenInformation
 ConvertSidToStringSidW
DEF
for lib in kernel32 advapi32; do
  lld-link /nologo /dll /noentry /nodefaultlib /machine:x64 \
    "/def:$TMP/$lib.def" "/out:$TMP/$lib.dll" "/implib:$TMP/$lib.lib"
done
clang-cl /nologo /c /GS- /Zl /O1 "/Fo:$TMP/KingdomHelperProof.obj" "$SRC"
lld-link /nologo /dll /noentry /nodefaultlib /Brepro /machine:x64 \
  "/out:$TMP/KingdomHelperProof.dll" "/implib:$TMP/KingdomHelperProof.lib" \
  /export:KingdomDllProof "$TMP/KingdomHelperProof.obj" \
  "$TMP/kernel32.lib" "$TMP/advapi32.lib"
python3 - "$TMP/KingdomHelperProof.dll" "$DST" <<'PY'
import base64
import gzip
import hashlib
import pathlib
import sys
binary = pathlib.Path(sys.argv[1]).read_bytes()
digest = hashlib.sha256(binary).hexdigest()
expected = "3a68f77286498a365fece9e53cda32417eb7294c63ef031be27a00ccb036b9d1"
if digest != expected:
    raise SystemExit("Native DLL does not match the reviewed x64 proof: " + digest)
packed = base64.b64encode(gzip.compress(binary, mtime=0)).decode("ascii")
pathlib.Path(sys.argv[2]).write_text(packed + "\n")
print("NORTH Topic 12 DLL built: SHA256 " + digest)
PY
