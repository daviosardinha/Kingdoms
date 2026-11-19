#!/usr/bin/env bash
# Rebuild the harmless native x64 NORTH Topic 12 proof DLL on a developer host.
# Requires clang-cl, lld-link and python3. Does not run Windows code.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT}/ansible/roles/windows_lpe/files/dll_hijack/KingdomHelperProof.c"
DST="${ROOT}/ansible/roles/windows_lpe/files/dll_hijack/KingdomHelperProof.dll.gz.b64"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

for dep in clang-cl lld-link python3; do
  command -v "${dep}" >/dev/null 2>&1 || { echo "Missing ${dep}" >&2; exit 1; }
done

clang-cl /nologo /c /GS- /Zl /O1 "/Fo:${TMP}/KingdomHelperProof.obj" "${SRC}"
lld-link /nologo /dll /noentry /nodefaultlib /Brepro /machine:x64 \
  "/out:${TMP}/KingdomHelperProof.dll" \
  "/implib:${TMP}/KingdomHelperProof.lib" \
  /export:KingdomDllProof "${TMP}/KingdomHelperProof.obj"

python3 - "${TMP}/KingdomHelperProof.dll" "${DST}" <<'PY'
import base64
import gzip
import hashlib
import pathlib
import sys

source = pathlib.Path(sys.argv[1]).read_bytes()
digest = hashlib.sha256(source).hexdigest()
expected = "2c377de8c7674d23725dbe6142d247dfb50afd662b430695deee2edd81b1ab45"
if digest != expected:
    raise SystemExit(f"Unexpected proof DLL bytes: {digest}")
encoded = base64.b64encode(gzip.compress(source, mtime=0)).decode()
pathlib.Path(sys.argv[2]).write_text(encoded + "\n")
print(f"Rebuilt reproducible NORTH Topic 12 proof DLL: SHA256 {digest}")
PY
