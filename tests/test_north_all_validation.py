"""Guard the NORTH installed-instance one-shot acceptance against cross-lab changes."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate-north-all.sh"


def test_shell_syntax():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_wrong_or_missing_target_fails_before_any_network_action():
    for args in ([], ["PURPLE"], ["34a864-north-vmware"]):
        done = subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True)
        assert done.returncode == 2, done.stdout + done.stderr


def test_instance_and_mode_are_exact_north_only():
    code = SCRIPT.read_text()
    for marker in (
        "^[a-f0-9]{6}-north-vmware$",
        'PROVIDER="$ROOT/workspace/$INSTANCE/provider"',
        "ad/NORTH/data/inventory",
        "GOAD_LAB_PROFILE=NORTH",
        "KINGDOMS_PHASE02_PROFILE=NORTH",
        "KINGDOMS_PHASE03_PROFILE=NORTH",
        '"$(cat "$MODE_FILE")" == exercise',
        "flock -n 9",
    ):
        assert marker in code


def test_validate_all_existing_contracts_and_two_sided_runtime():
    code = SCRIPT.read_text()
    for marker in (
        "verify-test-source.sh",
        "validate-goad-kingdoms-install-source.sh",
        "tests/test_north_*.py tests/test_course1_*.py",
        "validate-phase01.py",
        "validate-phase02-readiness.sh",
        "validate-phase03-readiness.sh",
        "ansible/phase03-$spec-preflight.yml",
        "rbcd shadow adidns webdav-shortcut",
        "course1-phase04-acceptance.sh",
        "PHASE04_LPE_ACTIVE_ACCEPTANCE=PASS",
        "NORTH_RUNTIME_ACCEPTANCE=PASS",
        "north-runtime-before",
        "north-runtime-after",
        "summary.json",
        "NORTH_ALL_READINESS=",
        "PHASE03_ACTIVE_ATTACK_CHAINS=NOT_TESTED",
        "PHASE04_RICKON_TO_SYSTEM_EXPLOIT=NOT_TESTED",
    ):
        assert marker in code
    assert code.index("north-runtime-before") < code.index("phase01-anonymous-and-http")
    assert code.index("phase04-full-20-lpe") < code.index("north-runtime-after")


def test_active_exploit_and_lifecycle_commands_are_not_in_orchestrator():
    code = SCRIPT.read_text()
    for forbidden in (
        "vagrant destroy", "vagrant up", "vmrun -T ws stop", "vmrun -T ws start",
        "Reset-ComputerMachinePassword", "nltest /sc_reset",
        "ntlmrelayx -t ", "responder -I ", "mitm6 -d",
        "windows_lpe_action=apply", "windows_lpe_action=reset",
        "--run-http-ldaps", "lab-mode.sh exercise",
    ):
        assert forbidden not in code
    assert "--confirm-transient-right" in code
    assert "failure=$((failure + 1))" in code
