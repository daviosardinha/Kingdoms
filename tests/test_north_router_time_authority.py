"""Source-only contracts for NORTH's isolated AD time hierarchy.

These tests do not touch VMware Workstation or the live NORTH instance.
"""
from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "ad/NORTH/providers/vmware/router/provision.sh"
PLAYBOOK = ROOT / "ansible/kingdoms-time-backoff.yml"
ROOT_PDC_ROLE = ROOT / "ansible/roles/kingdoms_time/root_pdc/tasks/main.yml"
TEMPLATE = ROOT / "template/provider/vmware/Vagrantfile"
LIFECYCLE = ROOT / "scripts/lab-mode.sh"


def test_router_provision_bash_parses():
    subprocess.run(["bash", "-n", str(ROUTER)], check=True)


def test_dc_readiness_closes_before_member_function():
    text = LIFECYCLE.read_text()
    dc = text.split("wait_domain_controller_ready() {", 1)[1].split(
        "\nwait_domain_member_ready() {", 1
    )[0]
    assert '(( basic_ready == 1 )) ||' in dc
    assert 'ensure_child_dc_time_ready "${vm}"' in dc
    assert 'echo "        [+] ${vm} AD runtime ready (${fqdn})"' in dc
    assert dc.rstrip().endswith("}")


def test_lifecycle_bash_parses_and_member_function_has_single_end():
    subprocess.run(["bash", "-n", str(LIFECYCLE)], check=True)
    s = LIFECYCLE.read_text()
    member = s.split("wait_domain_member_ready() {", 1)[1].split(
        "\npreflight_domain_health() {", 1
    )[0]
    assert member.count("did not regain domain identity readiness") == 1
    assert member.rstrip().endswith("}")


def test_router_only_listens_for_forest_root_pdc():
    s = ROUTER.read_text()
    assert "apt-get install -y --no-install-recommends nftables chrony" in s
    assert "bindaddress 10.4.20.1" in s
    assert "allow 10.4.20.10/32" in s
    assert "cmdport 0" in s
    assert "chronyc waitsync" in s
    assert "chronyc tracking" in s
    assert "10.4.20.1:123" in s
    assert "local stratum" not in s
    assert "allow 10.4.10.0/24" not in s
    assert "allow 10.4.99.0/24" not in s


def test_router_retains_isolated_forwarding_model():
    s = ROUTER.read_text()
    assert 'configure_lab_interface "NORTH"' in s
    assert 'configure_lab_interface "SEVENKINGDOMS"' in s
    assert 'configure_lab_interface "MANAGEMENT"' in s
    assert "net.ipv4.ip_forward = 1" in s
    exercise = (ROOT / "ad/NORTH/providers/vmware/router/nftables/exercise.nft").read_text()
    assert "policy drop;" in exercise
    assert "ip saddr 10.4.10.11 ip daddr 10.4.20.10" in exercise


def test_forest_root_role_runs_only_in_north():
    plays = yaml.safe_load(PLAYBOOK.read_text())
    root = plays[0]
    assert root["hosts"] == "parent_dc"
    assert root["roles"] == [
        {"role": "kingdoms_time/root_pdc", "when": "domain_name == 'NORTH'"}
    ]
    assert plays[1]["hosts"] == "server:workstation"
    assert plays[1]["roles"] == [{"role": "kingdoms_time/member"}]


def test_forest_root_identity_and_ntp_response_proven_before_modification():
    s = ROOT_PDC_ROLE.read_text()
    plays = yaml.safe_load(s)
    script = plays[0]["ansible.windows.win_powershell"]["script"]
    for token in (
        "Get-ADForest",
        "Get-ADDomain -Identity $forest.RootDomain",
        "kingslanding.sevenkingdoms.local",
        "$env:COMPUTERNAME -ine 'KINGSLANDING'",
        "w32tm.exe /stripchart /computer:10.4.20.1",
        "if ($LASTEXITCODE -ne 0)",
        "/syncfromflags:manual",
        "/reliable:yes",
        "Last Sync Error:",
        "$Ansible.Changed = $false",
    ):
        assert token in script
    assert script.index("w32tm.exe /stripchart") < script.index("w32tm.exe /config")


def test_north_new_windows_guests_use_windows_time():
    s = TEMPLATE.read_text()
    block = s.split("{% if lab_name == 'NORTH' %}", 1)[1].split("{% endif %}", 1)[0]
    assert 'if box[:os] == "windows"' in block
    assert 'v.vmx["tools.upgrade.policy"] = "manual"' in block
    assert 'v.vmx["tools.syncTime"] = "FALSE"' in block


def test_only_north_extends_member_time_convergence():
    s = LIFECYCLE.read_text()
    member = s.split("wait_domain_member_ready() {", 1)[1].split(
        "\npreflight_domain_health() {", 1
    )[0]
    assert "readonly AD_READINESS_TIMEOUT_SECONDS=300" in s
    assert "readonly AD_MEMBER_TIME_CONVERGENCE_TIMEOUT_SECONDS=600" in s
    assert '[[ "${GOAD_LAB_PROFILE}" == NORTH ]] && time_repair_threshold=18' in member
    assert 'time_repair_threshold=6' in member
    assert "consecutive_time_failures >= time_repair_threshold" in member
    assert 'readiness_deadline="${AD_MEMBER_TIME_CONVERGENCE_TIMEOUT_SECONDS}"' in member
    assert "KINGDOMS_MEMBER_TIME_REPAIR_FAILED\\|stage=rediscover" in member
    assert "time_repair_attempted=1" in member
    assert "did not regain domain identity readiness" in member
