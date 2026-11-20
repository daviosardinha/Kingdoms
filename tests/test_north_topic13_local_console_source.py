"""Static contracts for NORTH Topic 13 local-only interactive SYSTEM proof.

These checks enforce file and source scope. They do not claim that the pipe
handshake, terminal I/O or cleanup were validated on a real Windows WS01.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROLE = (ROOT / "ansible/roles/windows_lpe/tasks/techniques/path_search_order_hijacking.yml").read_text()
DIR = ROOT / "ansible/roles/windows_lpe/files/path_search"
HELPER = (DIR / "KingdomPathShell.cs").read_text()
VIEWER = (DIR / "KingdomPathConsole.ps1").read_text()
TOPIC12 = (ROOT / "ansible/roles/windows_lpe/tasks/techniques/service_dll_hijacking.yml").read_text()


def test_new_fixture_is_separate_from_prior_course_helpers():
    for f in ("KingdomPathShell.cs", "KingdomPathConsole.ps1"):
        assert (DIR / f).is_file()
    assert "KingdomProof.exe" not in HELPER
    assert "KingdomDllProofViewer.ps1" not in HELPER
    assert "KingdomsTopic12Proof" not in HELPER
    assert "KingdomsTopic13Console" in HELPER
    assert "KingdomsTopic13Console" in VIEWER
    assert "KingdomPathShell.exe" in ROLE
    assert "KingdomPathConsole.ps1" in ROLE
    assert "src: path_search/KingdomPathShell.cs" in ROLE
    assert "src: path_search/KingdomPathConsole.ps1" in ROLE


def test_local_only_authenticated_duplex_channel():
    assert "NamedPipeClientStream" in HELPER
    assert "NamedPipeServerStream" in VIEWER
    assert "PipeDirection.InOut" in HELPER and "PipeDirection.InOut" in VIEWER
    assert 'new NamedPipeClientStream(\n                ".", PipeName' in HELPER
    assert "TokenImpersonationLevel.Impersonation" in HELPER
    assert "GetImpersonationUserName()" in VIEWER
    assert '"KINGDOMS_TOPIC13_HELLO"' in HELPER
    assert '"KINGDOMS_TOPIC13_APPROVED"' in HELPER
    assert '"KINGDOMS_TOPIC13_HELLO"' in VIEWER
    assert '"KINGDOMS_TOPIC13_APPROVED"' in VIEWER
    assert 'new SecurityIdentifier("S-1-5-18")' in VIEWER
    assert 'clientSid.Value != "S-1-5-18"' in VIEWER
    assert "PipeAccessRights.FullControl" in VIEWER
    for forbidden in ("TcpClient", "TcpListener", "Socket(", "HttpClient", "WebRequest", "WebClient", "Invoke-WebRequest", "Invoke-RestMethod", "System.Net."):
        assert forbidden not in HELPER
        assert forbidden not in VIEWER


def test_limited_lifetime_persistent_system_process():
    assert 'identity.User.Value != "S-1-5-18"' in HELPER
    assert 'Path.Combine(Environment.SystemDirectory, "cmd.exe")' in HELPER
    assert 'cmd.StartInfo.Arguments = "/Q /D"' in HELPER
    assert "cmd.StartInfo.RedirectStandardInput = true;" in HELPER
    assert "cmd.StartInfo.RedirectStandardOutput = true;" in HELPER
    assert "cmd.StartInfo.RedirectStandardError = true;" in HELPER
    assert "SessionTimeoutMs = 600000" in HELPER
    assert "cmd.Kill()" in HELPER
    assert '"::kingdom-close::"' in HELPER and '"::kingdom-close::"' in VIEWER
    assert "ConnectionTimeoutMs = 150000" in VIEWER
    assert "viewer" not in HELPER.lower().split("using")[0]  # no reverse install dependency


def test_apply_only_installs_and_reset_only_removes_topic13_artifacts():
    assert "Stage Topic 13 local SYSTEM console helper source" in ROLE
    assert "Compile the Topic 13 local command helper without running it" in ROLE
    assert "Publish the Topic 13 local pipe viewer for Rickon" in ROLE
    assert "NORTH_TOPIC13_LOCAL_HELPER=READY" in ROLE
    assert "Topic 13 local command fixture missing" in ROLE
    assert "Topic 13 local command fixture was not removed" in ROLE
    assert "C:\\Users\\Public\\Documents\\KingdomProof.exe" not in ROLE
    assert "C:\\Users\\Public\\Documents\\KingdomDllProofViewer.ps1" not in ROLE
    assert "Remove-Item -LiteralPath $root -Recurse -Force" in ROLE
    assert "WINDOWS_LPE_PATH_SEARCH_ORDER_HIJACKING=VULNERABLE" in ROLE
    assert "WINDOWS_LPE_PATH_SEARCH_ORDER_HIJACKING=CLEAN" in ROLE


def test_topic12_unchanged_source_contract():
    assert "KingdomDllProofViewer.ps1" in TOPIC12
    assert "Workstation Component Health" in TOPIC12
    assert "$serviceAcl.SetAccessRuleProtection($true, $false)" in TOPIC12
