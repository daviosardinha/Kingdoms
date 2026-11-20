"""NORTH Topic 13 interactive RDP proof source contracts.

These are source-only checks. They do not establish Windows compile success,
Rickon's interactive desktop outcome, or the safety of reset/reapply.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROLE = (ROOT / "ansible/roles/windows_lpe/tasks/techniques/path_search_order_hijacking.yml").read_text()
RDP_SOURCE = (ROOT / "ansible/roles/windows_lpe/files/config_shell/KingdomConfigShell.cs").read_text()
TOPIC11_SOURCE_PATH = ROOT / "ansible/roles/windows_lpe/files/config_shell/KingdomConfigShell.cs"
TOPIC12_ROLE = (ROOT / "ansible/roles/windows_lpe/tasks/techniques/service_dll_hijacking.yml").read_text()


def test_topic13_reuses_proven_repo_source_not_topic11_installed_executable():
    assert TOPIC11_SOURCE_PATH.is_file()
    assert "src: config_shell/KingdomConfigShell.cs" in ROLE
    assert "dest: 'C:\\Kingdom LPE\\Path Search\\Service\\KingdomPathShell.cs'" in ROLE
    assert "KingdomConfigShell.exe" not in ROLE
    assert "KingdomProof.exe" not in ROLE
    assert "KingdomDllProofViewer.ps1" not in ROLE


def test_separate_compiled_binary_and_window_identity():
    assert "Compile dedicated Topic 13 interactive RDP helper without executing it" in ROLE
    assert "$text = $text.Replace('KingdomConfigShell', 'KingdomPathShell')" in ROLE
    assert "$text = $text.Replace('NORTH_KINGDOM_CONFIG_SYSTEM_SHELL', 'NORTH_KINGDOM_PATH_SYSTEM_SHELL')" in ROLE
    assert "Add-Type -TypeDefinition $text -Language CSharp -OutputAssembly $temporary -OutputType WindowsApplication" in ROLE
    assert "$fixture = 'C:\\Users\\Public\\Documents\\KingdomPathShell.exe'" in ROLE
    assert "NORTH_TOPIC13_INTERACTIVE_RDP_HELPER=READY" in ROLE
    assert ROLE.index("Stage proven Windows RDP session helper source") < ROLE.index(
        "Compile dedicated Topic 13 interactive RDP helper"
    )


def test_original_helper_uses_scoped_system_rdp_session_mechanism():
    assert "Environment.MachineName.Equals(\"WS01\"" in RDP_SOURCE
    assert "WindowsIdentity.GetCurrent().IsSystem" in RDP_SOURCE
    assert 'user.Equals("rickon.stark"' in RDP_SOURCE
    assert 'domain.Equals("NORTH"' in RDP_SOURCE
    assert "FindRickonSession()" in RDP_SOURCE
    assert "StartSystemCmdInSession(session)" in RDP_SOURCE
    assert "CreateProcessAsUser(" in RDP_SOURCE
    assert 'startup.lpDesktop = @"winsta0\\default";' in RDP_SOURCE
    assert "NORTH_KINGDOM_CONFIG_SYSTEM_SHELL" in RDP_SOURCE


def test_no_named_pipe_viewer_or_network_code_added_to_topic13():
    assert "KingdomPathConsole.ps1" not in ROLE
    assert "KingdomsTopic13Console" not in ROLE
    assert "NamedPipe" not in ROLE
    assert not (ROOT / "ansible/roles/windows_lpe/files/path_search/KingdomPathConsole.ps1").exists()
    assert not (ROOT / "ansible/roles/windows_lpe/files/path_search/KingdomPathShell.cs").exists()
    for forbidden in ("TcpClient", "TcpListener", "Socket(", "HttpClient", "WebClient", "WebRequest"):
        assert forbidden not in RDP_SOURCE


def test_apply_and_reset_are_isolated_to_topic13_artifact():
    assert "when: windows_lpe_action == 'apply'" in ROLE
    assert "when: windows_lpe_action == 'reset'" in ROLE
    assert "Remove-Item -LiteralPath $root -Recurse -Force" in ROLE
    assert "C:\\Users\\Public\\Documents\\KingdomPathShell.exe" in ROLE
    assert "Topic 13 local command fixture missing" in ROLE
    assert "Topic 13 local command fixture was not removed" in ROLE
    assert "WINDOWS_LPE_PATH_SEARCH_ORDER_HIJACKING=RESET" in ROLE
    assert "WINDOWS_LPE_PATH_SEARCH_ORDER_HIJACKING=CLEAN" in ROLE


def test_earlier_topic12_contract_remains():
    assert "KingdomDllProofViewer.ps1" in TOPIC12_ROLE
    assert "$serviceAcl.SetAccessRuleProtection($true, $false)" in TOPIC12_ROLE
