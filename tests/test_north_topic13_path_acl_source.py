"""Static guardrails for NORTH Topic 13 PATH search-order isolation.

These tests do not replace Windows ACL/effective-access or cross-topic runtime
regression checks. Only exact-technique WS01 validation can complete those gates.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROLE = (ROOT / "ansible/roles/windows_lpe/tasks/techniques/path_search_order_hijacking.yml").read_text()
DEFAULTS = (ROOT / "ansible/roles/windows_lpe/defaults/main.yml").read_text()
TOPIC12 = (ROOT / "ansible/roles/windows_lpe/tasks/techniques/service_dll_hijacking.yml").read_text()


def test_topic13_stays_within_its_own_directory_and_service():
    assert "root: 'C:\\Kingdom LPE\\Path Search'" in DEFAULTS
    assert "service_name: KingdomPathSvc" in DEFAULTS
    assert "Set-Acl -LiteralPath $Path -AclObject $acl" in ROLE
    assert "Set-Acl -LiteralPath $sharedParent" not in ROLE
    assert "Set-Acl -LiteralPath 'C:\\Kingdom LPE'" not in ROLE
    assert "icacls C:\\" not in ROLE
    assert "Remove-Item -LiteralPath $root -Recurse -Force" in ROLE
    assert "WINDOWS_LPE_PATH_SEARCH_ORDER_HIJACKING=RESET" in ROLE


def test_parent_acl_is_not_inherited_by_topic13():
    assert "$acl.SetAccessRuleProtection($true, $false)" in ROLE
    assert "$acl.RemoveAccessRuleSpecific($oldRule)" in ROLE
    assert "Get-Acl -LiteralPath $Path" in ROLE
    assert "Set-Topic13DirectoryAcl -Path $root -UsersRights" in ROLE
    assert "Set-Topic13DirectoryAcl -Path $serviceDir -UsersRights" in ROLE
    assert "Set-Topic13DirectoryAcl -Path $protectedDir -UsersRights" in ROLE
    assert "Set-Topic13DirectoryAcl -Path $writableDir -UsersRights" in ROLE
    assert ROLE.index("Set-Topic13DirectoryAcl -Path $root -UsersRights") < ROLE.index(
        "New-Item -ItemType Directory -Path $serviceDir"
    )
    assert ROLE.index("Set-Topic13DirectoryAcl -Path $serviceDir -UsersRights") < ROLE.index(
        "Add-Type"
    )


def test_intended_access_is_read_only_except_userbin():
    assert "Sid = 'S-1-5-18'; Rights = [System.Security.AccessControl.FileSystemRights]::FullControl" in ROLE
    assert "Sid = 'S-1-5-32-544'; Rights = [System.Security.AccessControl.FileSystemRights]::FullControl" in ROLE
    assert "Sid = 'S-1-5-32-545'; Rights = $UsersRights" in ROLE
    assert ROLE.count("Set-Topic13DirectoryAcl -Path") == 4
    assert ROLE.count("::ReadAndExecute)") >= 3
    assert "Set-Topic13DirectoryAcl -Path $writableDir -UsersRights ([System.Security.AccessControl.FileSystemRights]::Modify)" in ROLE


def test_validation_rejects_all_unprivileged_write_not_just_users():
    assert "Assert-ProtectedTopic13Path" in ROLE
    assert "foreach ($protectedPath in @($root, $serviceDir, $protectedDir, $exe, $protectedHelper))" in ROLE
    assert "AreAccessRulesProtected" in ROLE
    assert "DeleteSubdirectoriesAndFiles" in ROLE
    assert "Shared parent grants DELETE_CHILD" in ROLE
    assert "throw 'BUILTIN\\Users cannot create the intended PATH preemption file'" in ROLE
    assert "WINDOWS_LPE_PATH_SEARCH_ORDER_HIJACKING=VULNERABLE" in ROLE


def test_service_start_and_original_helper_contract_remain():
    assert 'psi.FileName = "$helperName";' in ROLE
    assert "psi.UseShellExecute = false;" in ROLE
    assert "Process.Start(psi);" in ROLE
    assert "New-Service" in ROLE
    assert "(A;;RPWP;;;BU)" in ROLE
    assert "if ($rights -match 'DC')" in ROLE
    assert "protected fallback helper missing" in ROLE


def test_topic12_still_has_its_own_directory_isolation_contract():
    assert "$serviceAcl.SetAccessRuleProtection($true, $false)" in TOPIC12
    assert "Set-Acl -LiteralPath $serviceDir -AclObject $serviceAcl" in TOPIC12
