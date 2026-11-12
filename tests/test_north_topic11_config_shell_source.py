"""Source checks for NORTH Topic 11. These are not Windows runtime tests."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROLE = (ROOT / "ansible/roles/windows_lpe/tasks/techniques/insecure_service_registry.yml").read_text()
HELPER = (ROOT / "ansible/roles/windows_lpe/files/config_shell/KingdomConfigShell.cs").read_text()


def test_attack_surface_is_the_application_helper_path():
    assert "if ($valueName -ne 'HelperPath')" in ROLE
    assert "RegistryRights]::SetValue" in ROLE
    assert "RegistryValueKind]::String" in ROLE
    assert "SOFTWARE\\GOAD Kingdoms" in ROLE
    assert "sc.exe sdset $name $sddl" in ROLE
    assert "(A;;RPWP;;;BU)" in ROLE
    assert "StartupType Manual" in ROLE
    assert "service startup mode=" in ROLE
    assert "BUILTIN\\Users start and stop rights" in ROLE


def test_standalone_helper_is_scoped_and_uses_system_session_token():
    assert "internal static class KingdomConfigShell" in HELPER
    assert 'MachineName.Equals("WS01"' in HELPER
    assert "WindowsIdentity.GetCurrent().IsSystem" in HELPER
    assert '"rickon.stark"' in HELPER
    assert '"NORTH"' in HELPER
    assert "WTSEnumerateSessions" in HELPER
    assert "CreateProcessAsUser" in HELPER
    assert "SetTokenInformation" in HELPER
    assert "C:\\Windows\\System32\\cmd.exe" in HELPER
    assert "NORTH_KINGDOM_CONFIG_SYSTEM_SHELL" in HELPER
    assert "ServiceBase.Run" not in HELPER
    assert "System.Net" not in HELPER


def test_apply_and_reset_manage_stage_without_overwriting_original_helper():
    assert "src: config_shell/KingdomConfigShell.cs" in ROLE
    assert "KingdomConfigShell.exe" in ROLE
    assert "WINDOWS_LPE_TOPIC11_CONFIG_SHELL_STAGED" in ROLE
    assert "Topic 11 standalone SYSTEM helper missing" in ROLE
    assert "Topic 11 interactive helper still exists" in ROLE
    assert "Topic 11 interactive helper source still exists" in ROLE
    assert "WINDOWS_LPE_INSECURE_SERVICE_REGISTRY=VULNERABLE" in ROLE
    assert "WINDOWS_LPE_INSECURE_SERVICE_REGISTRY=CLEAN" in ROLE
