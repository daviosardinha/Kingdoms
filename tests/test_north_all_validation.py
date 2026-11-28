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
        'PHASE02_RDP_BOT_MODE="$RDP_MODE"',
        "RDP_BOT_CONTRACT=",
        "KINGDOMS_PHASE03_PROFILE=NORTH",
        '"$(cat "$MODE_FILE")" == exercise',
        "flock -n 9",
    ):
        assert marker in code


def test_validate_all_existing_contracts_and_two_sided_runtime():
    code = SCRIPT.read_text()
    for marker in (
        "verify-test-source.sh",
        "KINGDOMS_SOURCE_TEST_PYTHON",
        "north-course1-full-source",
        "validate-course1.sh --skip-host",
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
        "PHASE03_FIXTURE_EXPLOITABILITY=NOT_PROVEN_BY_INSPECTION",
        "PHASE03_RBCD_SELF_CAN_WRITE=",
        "PHASE03_SHADOW_PREFLIGHT_COMPLETE=True",
        "PHASE03_ADIDNS_PREFLIGHT_COMPLETE=True",
        "PHASE03_WEBDAV_PREFLIGHT_COMPLETE=True",
        "PHASE03_ACTIVE_ATTACK_CHAINS=NOT_TESTED",
        "PHASE04_RICKON_TO_SYSTEM_EXPLOIT=NOT_TESTED",
    ):
        assert marker in code
    assert code.index("north-course1-full-source") < code.index("north-runtime-before")
    assert code.index("north-runtime-before") < code.index("phase01-anonymous-and-http")
    assert code.index("phase04-full-20-lpe") < code.index("north-runtime-after")
    assert code.count("for spec in rbcd shadow adidns webdav-shortcut; do") == 1
    assert code.count("run_stage phase04-full-20-lpe") == 1
    assert code.count("run_stage north-runtime-after") == 1



def test_rdp_mode_is_explicit_and_defaults_to_actual_legacy_install():
    code = SCRIPT.read_text()
    assert "RDP_MODE=legacy" in code
    assert "--rdp-mode legacy|headless" in code
    assert '"$3" == --rdp-mode' in code
    assert '"$4" == legacy || "$4" == headless' in code
    assert 'PHASE02_RDP_BOT_MODE="$RDP_MODE"' in code
    bad = subprocess.run(
        ["bash", str(SCRIPT), "34a864-north-vmware",
         "--confirm-transient-right", "--rdp-mode", "unverified"],
        capture_output=True, text=True,
    )
    assert bad.returncode == 2

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


def test_host_python_is_pinned_before_ansible_venv_path():
    code = SCRIPT.read_text()
    capture = 'HOST_PYTEST_PYTHON="$(command -v python3)"'
    path_mutation = 'export PATH="$HOME/.goad/.venv/bin:$PATH"'
    use = '"$HOST_PYTEST_PYTHON" -m pytest -q tests/test_north_*.py tests/test_course1_*.py'
    assert capture in code
    assert path_mutation in code
    assert use in code
    assert code.index(capture) < code.index(path_mutation) < code.index(use)
    assert "bash -c 'python3 -m pytest" not in code
