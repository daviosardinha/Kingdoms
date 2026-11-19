#!/usr/bin/env bash
# Rebuild NORTH Topic 12's native x64 DLL with visible, non-shell proof.
# Requires clang-cl, lld-link and python3. Does not run Windows code.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/ansible/roles/windows_lpe/files/dll_hijack/KingdomHelperProof.c"
DST="$ROOT/ansible/roles/windows_lpe/files/dll_hijack/KingdomHelperProof.dll.gz.b64"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
for dep in clang-cl lld-link python3; do
  command -v "$dep" >/dev/null 2>&1 || { echo "Missing $dep" >&2; exit 1; }
done
cat > "$TMP/kernel32.def" <<'EOF'
LIBRARY kernel32.dll
EXPORTS
 GetComputerNameW
 lstrcmpiW
 GetCurrentProcess
 CloseHandle
 LocalFree
EOF
cat > "$TMP/advapi32.def" <<'EOF'
LIBRARY advapi32.dll
EXPORTS
 OpenProcessToken
 GetTokenInformation
 ConvertSidToStringSidW
EOF
cat > "$TMP/wtsapi32.def" <<'EOF'
LIBRARY wtsapi32.dll
EXPORTS
 WTSEnumerateSessionsW
 WTSQuerySessionInformationW
 WTSSendMessageW
 WTSFreeMemory
EOF
for lib in kernel32 advapi32 wtsapi32; do
  lld-link /nologo /dll /noentry /nodefaultlib /machine:x64 "/def:$TMP/$lib.def" "/out:$TMP/$lib.dll" "/implib:$TMP/$lib.lib"
done
clang-cl /nologo /c /GS- /Zl /O1 "/Fo:$TMP/KingdomHelperProof.obj" "$SRC"
lld-link /nologo /dll /noentry /nodefaultlib /Brepro /machine:x64 \
  "/out:$TMP/KingdomHelperProof.dll" "/implib:$TMP/KingdomHelperProof.lib" \
  /export:KingdomDllProof "$TMP/KingdomHelperProof.obj" "$TMP/kernel32.lib" "$TMP/advapi32.lib" "$TMP/wtsapi32.lib"
python3 - "$TMP/KingdomHelperProof.dll" "$DST" <<'PY'
import base64
import gzip
import hashlib
import pathlib
import sys
source = pathlib.Path(sys.argv[1]).read_bytes()
digest = hashlib.sha256(source).hexdigest()
expected = "cc3b582f9afd96e741a3110be556a8c4209afb48299963deb985f628f4215ba7"
if digest != expected:
    raise SystemExit(f"Unexpected proof DLL bytes: {digest}")
encoded = base64.b64encode(gzip.compress(source, mtime=0)).decode()
pathlib.Path(sys.argv[2]).write_text(encoded + "\n")
print(f"Rebuilt NORTH Topic 12 DLL with visible proof: SHA256 {digest}")
PY
