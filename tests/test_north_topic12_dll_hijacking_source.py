"""Static source checks for NORTH Topic 12. No VM or service execution is performed."""
import base64
import gzip
import hashlib
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROLE = (ROOT / "ansible/roles/windows_lpe/tasks/techniques/service_dll_hijacking.yml").read_text()
DEFAULTS = (ROOT / "ansible/roles/windows_lpe/defaults/main.yml").read_text()
PROOF_SOURCE = (ROOT / "ansible/roles/windows_lpe/files/dll_hijack/KingdomHelperProof.c").read_text()
PACKAGED = (ROOT / "ansible/roles/windows_lpe/files/dll_hijack/KingdomHelperProof.dll.gz.b64").read_text()
PROOF_BYTES = gzip.decompress(base64.b64decode(PACKAGED.strip()))


def test_proof_is_native_x64_dll_with_only_benign_export():
    assert PROOF_BYTES[:2] == b"MZ"
    pe_offset = struct.unpack_from("<I", PROOF_BYTES, 0x3C)[0]
    assert PROOF_BYTES[pe_offset:pe_offset + 4] == b"PE\0\0"
    assert struct.unpack_from("<H", PROOF_BYTES, pe_offset + 4)[0] == 0x8664
    assert b"KingdomDllProof\0" in PROOF_BYTES
    assert hashlib.sha256(PROOF_BYTES).hexdigest() == (
        "cc3b582f9afd96e741a3110be556a8c4209afb48299963deb985f628f4215ba7"
    )
    assert "return delivered ? 0x4B120012 : 0;" in PROOF_SOURCE
    assert "WTSSendMessageW" in PROOF_SOURCE
    assert "S-1-5-18" in PROOF_SOURCE
    assert "rickon.stark" in PROOF_SOURCE
    assert "WS01" in PROOF_SOURCE
    assert "system(" not in PROOF_SOURCE
    assert "CreateProcess" not in PROOF_SOURCE
    assert "DllMain(" not in PROOF_SOURCE


def test_service_only_calls_explicit_library_path_and_proves_execution():
    assert "LoadLibrary(@\"$dll\")" in ROLE
    assert "GetProcAddress(library, \"KingdomDllProof\")" in ROLE
    assert "if (execute() != 0x4B120012) return;" in ROLE
    assert "execute() != 0x4B120012" in ROLE
    assert "KingdomDllProof.txt" not in ROLE
    assert "File.AppendAllText" not in ROLE


def test_trigger_is_separate_from_topic07_and_not_student_writable():
    assert "Workstation Component Health" in ROLE
    assert "Workstation Service Health" not in ROLE
    assert "KingdomBinarySvc" not in ROLE
    assert "D:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;GR;;;BU)" in ROLE
    assert "AllowDemandStart = $false" in ROLE
    assert "Repetition.Interval = 'PT1M'" in ROLE
    assert "principal=SYSTEM|interval=PT1M|service=KingdomDllSvc" in ROLE
    assert "ordinary user can unexpectedly start KingdomDllSvc directly" in ROLE


def test_vulnerable_apply_stages_proof_but_not_target_dll():
    assert "C:\\Users\\Public\\Documents\\KingdomHelper.dll" in ROLE
    assert "if (Test-Path -LiteralPath $dll) { Remove-Item" in ROLE
    assert "native NORTH Topic 12 proof DLL is missing" in ROLE
    assert "protected service executable directory must not be writable" in ROLE
    assert "WINDOWS_LPE_SERVICE_DLL_HIJACKING=VULNERABLE" in ROLE
    assert "display_name: Kingdoms DLL Loader Service" in DEFAULTS


def test_reset_removes_only_topic12_service_task_and_fixture():
    assert "Unregister-ScheduledTask -TaskName $taskName" in ROLE
    assert "Topic 12 maintenance task still exists" in ROLE
    assert "Topic 12 proof DLL fixture still exists" in ROLE
    assert "WINDOWS_LPE_SERVICE_DLL_HIJACKING=CLEAN" in ROLE

def test_protected_service_directory_does_not_inherit_write_access():
    # WS01's parent training tree may be broadly writable. The private
    # service executable and proof log must not inherit those permissions.
    assert "$serviceAcl.SetAccessRuleProtection($true, $false)" in ROLE
    assert "Set-Acl -LiteralPath $serviceDir -AclObject $serviceAcl" in ROLE
    assert "S-1-5-18" in ROLE
    assert "S-1-5-32-544" in ROLE
    assert "S-1-5-32-545" in ROLE
    assert "Rights = [System.Security.AccessControl.FileSystemRights]::ReadAndExecute" in ROLE
    assert "InheritanceFlags]::None" in ROLE
    assert ROLE.index("Set-Acl -LiteralPath $serviceDir -AclObject $serviceAcl") < ROLE.index(
        "Add-Type -TypeDefinition $source"
    )
    assert "protected service executable directory must not be writable by ordinary users" in ROLE
