"""Source-level guards for the NORTH Topic 10 interactive SYSTEM pilot.

These tests do not replace a live Windows apply/reboot/RDP/restore test.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (ROOT / "ansible/roles/windows_lpe/tasks/techniques/weak_service_registry_permissions.yml").read_text()
HELPER = (ROOT / "ansible/roles/windows_lpe/files/registry_shell/KingdomRegistryShell.cs").read_text()


def test_registry_acl_is_the_only_student_writable_control_point():
    assert "RegistryRights]::SetValue" in FIXTURE
    assert "Set-Acl -Path $regPath -AclObject $acl" in FIXTURE
    assert "sc.exe sdset" not in FIXTURE
    assert "StartupType Automatic" in FIXTURE
    assert "StartMode -ne 'Auto'" in FIXTURE


def test_helper_is_service_aware_and_lab_scoped():
    assert 'ServiceName = "KingdomRegistrySvc"' in HELPER
    assert 'Environment.MachineName.Equals("WS01"' in HELPER
    assert '"rickon.stark"' in HELPER
    assert '"NORTH"' in HELPER
    assert "WindowsIdentity.GetCurrent().IsSystem" in HELPER
    assert "CanHandleSessionChangeEvent = true" in HELPER
    assert "WTSEnumerateSessions" in HELPER
    assert "CreateProcessAsUser" in HELPER
    assert "SetTokenInformation" in HELPER
    assert "C:\\Windows\\System32\\cmd.exe" in HELPER
    assert "System.Net.Sockets" not in HELPER


def test_apply_validate_and_reset_manage_helper_lifecycle():
    assert "src: registry_shell/KingdomRegistryShell.cs" in FIXTURE
    assert "KingdomRegistryShell.exe" in FIXTURE
    assert "WINDOWS_LPE_TOPIC10_REGISTRY_SHELL_STAGED" in FIXTURE
    assert "Topic 10 service-aware helper missing" in FIXTURE
    assert "Topic 10 interactive helper still exists" in FIXTURE
    assert "Topic 10 helper source still exists" in FIXTURE
    assert "WINDOWS_LPE_WEAK_SERVICE_REGISTRY_PERMISSIONS=VULNERABLE" in FIXTURE
    assert "WINDOWS_LPE_WEAK_SERVICE_REGISTRY_PERMISSIONS=CLEAN" in FIXTURE
