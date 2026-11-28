"""NORTH WS01 NAT contrast guard is source-only; never touches a real VM."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "probe-north-ws01-nat-dependency.sh"


def test_script_parses_without_execution():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_probe_is_only_for_exact_north_ws01_and_restores_runtime_nat():
    s = SCRIPT.read_text()
    assert "workspace/\${instance}/provider" in s
    assert "GOAD-WS01/vmware_desktop/id" in s
    assert "vmrun -T ws list | grep -Fxq" in s
    assert "ethernet0\\.startConnected" in s
    assert '"exercise"' in s
    assert "trap cleanup EXIT" in s
    assert "trap 'exit 130' INT" in s
    assert "trap 'exit 143' TERM" in s
    assert s.count("connectNamedDevice") == 1
    assert s.count("disconnectNamedDevice") >= 3
    assert "NORTH_WS01_ISOLATED_BEFORE" in s
    assert "NORTH_WS01_NAT_CONNECTED" in s
    assert "NORTH_WS01_ISOLATED_AFTER" in s
    assert "Test-ComputerSecureChannel -Server $dc" in s
    assert "ansible.windows.win_shell" in s


def test_probe_cannot_destroy_or_reconfigure_the_lab():
    s = SCRIPT.read_text()
    for forbidden in (
        "Reset-ComputerMachinePassword", "Test-ComputerSecureChannel -Repair",
        "nltest.exe /sc_reset", "vagrant destroy", "vagrant up",
        "shutdown.exe", "Restart-Computer", "Set-NetRoute",
        "Set-DnsClientServerAddress", "Remove-ADComputer",
        "GOAD-LAB", "PURPLE-WS01",
    ):
        assert forbidden not in s
