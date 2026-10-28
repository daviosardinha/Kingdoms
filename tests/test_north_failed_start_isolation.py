"""NORTH failed-start isolation may tolerate stopped, already-isolated members.

Unit-only: no VMware, network, privilege, or real guests are touched.
"""
import ast
import subprocess
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
MODE = ROOT / "scripts/lab-mode.sh"
NOMAD = ROOT / "goad/provider/vagrant/vmware_nomad.py"
BASE = ROOT / "goad/provider/vagrant/vagrant.py"


def exercise_function():
    text = MODE.read_text()
    return (text.split("configure_windows_nat_exercise() {", 1)[1]
                .split("\n}\n", 1)[0])


def run_mock_exercise(allow, persistent="FALSE", inventory_ok=True):
    body = exercise_function()
    source = """
set -euo pipefail
EXERCISE_ALLOW_STOPPED_MEMBERS=__ALLOW__
DOMAIN_MEMBERS=(GOAD-SRV02 GOAD-WS01)
EXERCISE_DOMAIN_CONTROLLERS=(GOAD-DC02 GOAD-DC01)
vmx_for() { echo "/registered/$1.vmx"; }
get_start_connected() { echo "__PERSISTENT__"; }
ensure_vm_nat_state() { echo "nat:$1:$2:$3"; }
prove_isolated_guest_ready() { echo "ready:$1:$2"; }
fail() { echo "blocked:$*" >&2; exit 1; }
vmrun() {
    __RETURN__
    printf "Total running VMs: 4\\n"
    printf "/registered/GOAD-SRV02.vmx\\n"
    printf "/registered/GOAD-DC02.vmx\\n"
    printf "/registered/GOAD-DC01.vmx\\n"
}
configure_windows_nat_exercise() {
__BODY__
}
configure_windows_nat_exercise
"""
    source = (source.replace("__ALLOW__", "1" if allow else "0")
              .replace("__PERSISTENT__", persistent)
              .replace("__RETURN__", ":" if inventory_ok else "return 1")
              .replace("__BODY__", body))
    return subprocess.run(
        ["bash", "-c", source], text=True, capture_output=True,
        timeout=10, check=False,
    )


class OfflineRestorationTests(TestCase):
    def test_only_failed_start_explicit_mode_allows_stopped_member(self):
        out = run_mock_exercise(True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("[SKIP] GOAD-WS01 powered off", out.stdout)
        self.assertIn("ready:GOAD-SRV02:member", out.stdout)
        self.assertNotIn("ready:GOAD-WS01:member", out.stdout)
        self.assertIn("ready:GOAD-DC01:dc", out.stdout)
        self.assertIn("ready:GOAD-DC02:dc", out.stdout)

    def test_normal_exercise_keeps_authentication_requirement(self):
        out = run_mock_exercise(False)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("ready:GOAD-WS01:member", out.stdout)
        self.assertNotIn("[SKIP]", out.stdout)

    def test_nonisolated_stopped_member_cannot_be_skipped(self):
        out = run_mock_exercise(True, persistent="TRUE")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("offline skip requires persistent NAT isolation", out.stderr)

    def test_unknown_vmware_power_state_blocks_offline_skip(self):
        out = run_mock_exercise(True, inventory_ok=False)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("VMware power inventory unavailable", out.stderr)

    def test_flag_requires_north_and_existing_exercise_record(self):
        text = MODE.read_text()
        gate = text.split('if [[ "$#" -eq 2 ]]; then', 1)[1].split(
            'case "${1:-status}" in', 1)[0]
        self.assertIn('"${GOAD_LAB_PROFILE}" == NORTH', gate)
        self.assertIn('== exercise', gate)
        self.assertIn('EXERCISE_ALLOW_STOPPED_MEMBERS=1', gate)
        self.assertIn('--allow-stopped-members', gate)

    def test_failed_start_only_passes_exemption_not_normal_start(self):
        text = BASE.read_text()
        start = text.split("def start(self, vm_name=None):", 1)[1].split(
            "\n    def stop(self):", 1
        )[0]
        self.assertIn("ready = False", start)
        self.assertIn("self.lab_name == 'NORTH' and not ready", start)
        self.assertIn("allow_stopped_members=True", start)
        self.assertIn("set_mode('exercise')", start)

    def test_mode_controller_rejects_foreign_or_unknown_instance(self):
        text = NOMAD.read_text()
        tree = ast.parse(text)
        method = next(n for n in ast.walk(tree)
                      if isinstance(n, ast.FunctionDef)
                      and n.name == "set_runtime_mode")
        namespace = {"Log": Mock(), "subprocess": Mock()}
        exec(compile(ast.Module(body=[method], type_ignores=[]),
                     str(NOMAD), "exec"), namespace)
        controller = namespace["set_runtime_mode"]
        p = Mock()
        p.is_goad_nomad_segmented.return_value = True
        p._script.return_value = "/safe/mode.sh"
        p._provider_env.return_value = {"GOAD_LAB_PROFILE": "NORTH"}
        p.get_runtime_mode.return_value = "exercise"
        p.lab_name = "NORTH"
        namespace["subprocess"].run.return_value.returncode = 0
        self.assertTrue(controller(p, "exercise", allow_stopped_members=True))
        namespace["subprocess"].run.assert_called_once_with(
            ["bash", "/safe/mode.sh", "exercise", "--allow-stopped-members"],
            env=p._provider_env.return_value, check=False,
        )
        namespace["subprocess"].run.reset_mock()
        p.lab_name = "GOAD"
        self.assertFalse(controller(p, "exercise", allow_stopped_members=True))
        namespace["subprocess"].run.assert_not_called()
        p.lab_name = "NORTH"
        p.get_runtime_mode.return_value = "unknown"
        self.assertFalse(controller(p, "exercise", allow_stopped_members=True))
        namespace["subprocess"].run.assert_not_called()
        p.get_runtime_mode.return_value = "exercise"
        self.assertFalse(controller(p, "provisioning", allow_stopped_members=True))
        namespace["subprocess"].run.assert_not_called()


if __name__ == "__main__":
    main()
