"""Static acceptance for NORTH Topic 12 fixed SYSTEM command proof.

These tests check build output and lab implementation contracts. They do not
claim that a Windows VM executed the DLL or that the reader received output.
"""
import base64
import gzip
import hashlib
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / "ansible/roles/windows_lpe/files/dll_hijack"
ROLE = (ROOT / "ansible/roles/windows_lpe/tasks/techniques/service_dll_hijacking.yml").read_text()
DEFAULTS = (ROOT / "ansible/roles/windows_lpe/defaults/main.yml").read_text()
SOURCE = (FILES / "KingdomHelperProof.c").read_text()
VIEWER = (FILES / "KingdomDllProofViewer.ps1").read_text()
PACKAGE = (FILES / "KingdomHelperProof.dll.gz.b64").read_text()
DLL = gzip.decompress(base64.b64decode(PACKAGE.strip()))
SHA256 = "3a68f77286498a365fece9e53cda32417eb7294c63ef031be27a00ccb036b9d1"


def test_native_x64_dll_is_reviewed_and_has_export():
    assert DLL[:2] == b"MZ"
    pe = struct.unpack_from("<I", DLL, 0x3C)[0]
    assert DLL[pe:pe + 4] == b"PE\0\0"
    assert struct.unpack_from("<H", DLL, pe + 4)[0] == 0x8664
    assert b"KingdomDllProof\0" in DLL
    assert hashlib.sha256(DLL).hexdigest() == SHA256
    assert "whoami.exe".encode("utf-16le") in DLL
    assert b"CreateProcessW\0" in DLL


def test_native_proof_runs_only_fixed_read_only_commands():
    assert "system_context()" in SOURCE
    assert 'L"S-1-5-18"' in SOURCE
    assert 'L"WS01"' in SOURCE
    assert 'L"C:\\Windows\\System32\\whoami.exe"' not in SOURCE  # source has escaped C backslashes
    assert 'CreateProcessW(L"C:\\\\Windows\\\\System32\\\\whoami.exe"' in SOURCE
    assert 'L"/priv"' in SOURCE
    assert SOURCE.count("fixed_whoami(destination,") == 2
    assert "CreateProcessW" in SOURCE and "CREATE_NO_WINDOW" in SOURCE
    assert "KingdomsTopic12Proof" in SOURCE
    assert "WTSSendMessageW" not in SOURCE
    assert "DllMain(" not in SOURCE
    assert re.search(r"\bsystem\s*\(", SOURCE) is None
    assert "ShellExecute" not in SOURCE
    assert "cmd.exe" not in SOURCE.lower()
    assert "powershell.exe" not in SOURCE.lower()


def test_result_transport_is_local_read_only_and_ends():
    assert "NamedPipeServerStream" in VIEWER
    assert "PipeDirection]::In" in VIEWER
    assert "'S-1-5-18'" in VIEWER
    assert "WaitOne(150000)" in VIEWER
    assert "ReadToEnd()" in VIEWER
    assert "End of SYSTEM command proof" in VIEWER
    assert "Invoke-Expression" not in VIEWER
    assert "Start-Process" not in VIEWER
    assert "New-ScheduledTask" not in VIEWER
    assert "Set-ItemProperty" not in VIEWER


def test_service_trusts_only_the_expected_absolute_dll_path():
    assert 'LoadLibrary(@"$dll")' in ROLE
    assert 'GetProcAddress(library, "KingdomDllProof")' in ROLE
    assert "if (execute() != 0x4B120012) return;" in ROLE
    assert "File.AppendAllText" not in ROLE
    assert "KingdomDllProof.txt" not in ROLE
    assert "WTSSendMessageW" not in ROLE


def test_independent_system_task_is_read_only_to_students():
    assert "Workstation Component Health" in ROLE
    assert "Workstation Service Health" not in ROLE
    assert "KingdomBinarySvc" not in ROLE
    assert "D:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;GR;;;BU)" in ROLE
    assert "AllowDemandStart = $false" in ROLE
    assert "Repetition.Interval = 'PT1M'" in ROLE
    assert "principal=SYSTEM|interval=PT1M|service=KingdomDllSvc" in ROLE
    assert "ordinary user can unexpectedly start KingdomDllSvc directly" in ROLE


def test_apply_and_reset_include_only_topic12_student_fixture_and_viewer():
    assert "C:\\Users\\Public\\Documents\\KingdomHelper.dll" in ROLE
    assert "C:\\Users\\Public\\Documents\\KingdomDllProofViewer.ps1" in ROLE
    assert "src: dll_hijack/KingdomDllProofViewer.ps1" in ROLE
    assert "Topic 12 read-only terminal viewer is missing" in ROLE
    assert "Topic 12 terminal viewer still exists" in ROLE
    assert "native NORTH Topic 12 proof DLL is missing" in ROLE
    assert SHA256 in ROLE
    assert "if (Test-Path -LiteralPath $dll) { Remove-Item" in ROLE
    assert "WINDOWS_LPE_SERVICE_DLL_HIJACKING=VULNERABLE" in ROLE
    assert "WINDOWS_LPE_SERVICE_DLL_HIJACKING=CLEAN" in ROLE
    assert "display_name: Kingdoms DLL Loader Service" in DEFAULTS


def test_protected_service_directory_does_not_inherit_write():
    assert "$serviceAcl.SetAccessRuleProtection($true, $false)" in ROLE
    assert "Set-Acl -LiteralPath $serviceDir -AclObject $serviceAcl" in ROLE
    assert "S-1-5-18" in ROLE and "S-1-5-32-544" in ROLE
    assert "Sid = 'S-1-5-32-545'; Rights = [System.Security.AccessControl.FileSystemRights]::ReadAndExecute" in ROLE
    assert "InheritanceFlags]::None" in ROLE
    assert ROLE.index("Set-Acl -LiteralPath $serviceDir -AclObject $serviceAcl") < ROLE.index(
        "Add-Type -TypeDefinition $source"
    )
    assert "protected service executable directory must not be writable by ordinary users" in ROLE
