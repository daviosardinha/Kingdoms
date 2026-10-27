"""NORTH full cold-start direct-AD proof can close isolation without NAT.

Offline exercises of the real Bash functions, with no VMware or network calls.
The original GOAD and partial-start/mode-transition paths are not qualified.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "scripts/lab-mode.sh"
BASE = ROOT / "goad/provider/vagrant/vagrant.py"
NOMAD = ROOT / "goad/provider/vagrant/vmware_nomad.py"
KINGDOMS = ROOT / "goad/provider/vagrant/vmware_kingdoms.py"


def shell_function(name: str):
    source = LAB.read_text(encoding="utf-8")
    start = source.index(f"{name}() {{")
    end = source.index("\n}\n", start)
    return source[start:end + 2]


def replay(*, profile="NORTH", mode="exercise", persistent="FALSE",
           stopped=None):
    with tempfile.TemporaryDirectory() as td:
        Path(td, ".goad-nomad-mode").write_text(mode)
        stopped = stopped or ""
        source = """
set -euo pipefail
GOAD_LAB_PROFILE="__PROFILE__"
EXERCISE_VALIDATED_COLD_START=1
EXERCISE_ALLOW_STOPPED_MEMBERS=0
PROVIDER="__PROVIDER__"
WINDOWS_VMS=(GOAD-DC01 GOAD-DC02 GOAD-SRV02 GOAD-WS01)
DOMAIN_MEMBERS=(GOAD-SRV02 GOAD-WS01)
EXERCISE_DOMAIN_CONTROLLERS=(GOAD-DC02 GOAD-DC01)
vmx_for() { printf '/registered/%s.vmx\\n' "$1"; }
get_start_connected() { printf '%s\\n' '__PERSISTENT__'; }
is_running() { [[ "$1" != "/registered/__STOPPED__.vmx" ]]; }
ensure_vm_nat_state() { printf 'isolate:%s:%s:%s\\n' "$1" "$2" "$3"; }
prove_isolated_guest_ready() { echo 'FORBIDDEN DUPLICATE VAGRANT PROBE'; exit 41; }
fail() { printf 'BLOCKED:%s\\n' "$*" >&2; exit 42; }
__GUARD__
__CONFIGURE__
require_north_validated_cold_start
configure_windows_nat_exercise
"""
        source = (source.replace("__PROFILE__", profile)
                  .replace("__PROVIDER__", td)
                  .replace("__PERSISTENT__", persistent)
                  .replace("__STOPPED__", stopped)
                  .replace("__GUARD__", shell_function("require_north_validated_cold_start"))
                  .replace("__CONFIGURE__", shell_function("configure_windows_nat_exercise")))
        return subprocess.run(["bash", "-c", source],
                              capture_output=True, text=True,
                              timeout=6, check=False)


class VerifiedColdStartIsolationTests(unittest.TestCase):
    def test_four_authenticated_guests_isolate_without_duplicate_vagrant_probe(self):
        proc = replay()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for guest in ("GOAD-DC01", "GOAD-DC02", "GOAD-SRV02", "GOAD-WS01"):
            self.assertIn(f"isolate:{guest}:FALSE:disconnect", proc.stdout)
        self.assertEqual(proc.stdout.count("isolate:"), 4)
        self.assertNotIn("FORBIDDEN DUPLICATE VAGRANT PROBE", proc.stdout)

    def test_stopped_guest_is_not_accepted_as_previously_verified(self):
        proc = replay(stopped="GOAD-WS01")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("requires all previously verified guests running", proc.stderr)
        self.assertNotIn("isolate:", proc.stdout)

    def test_nonisolated_or_wrong_profile_never_claims_full_proof(self):
        for kwargs in (
            {"persistent": "TRUE"},
            {"profile": "GOAD"},
            {"mode": "provisioning"},
        ):
            with self.subTest(kwargs=kwargs):
                proc = replay(**kwargs)
                self.assertNotEqual(proc.returncode, 0)
                self.assertNotIn("isolate:", proc.stdout)

    def test_full_start_only_and_original_paths_preserved(self):
        provider = BASE.read_text()
        self.assertIn("self.lab_name == 'NORTH' and ready", provider)
        self.assertIn("vm_name is None and callable(start_existing)", provider)
        self.assertIn("'exercise', validated_cold_start=True", provider)
        self.assertIn("'exercise', allow_stopped_members=True", provider)
        self.assertIn("set_mode('exercise')", provider)
        mode = NOMAD.read_text()
        self.assertIn("args.append('--validated-cold-start')", mode)
        self.assertIn("or allow_stopped_members", mode)
        shim = KINGDOMS.read_text()
        self.assertIn("validated_cold_start=True", shim)

    def test_first_transition_from_provisioning_still_checks_legacy_readiness(self):
        source = LAB.read_text()
        exercise = source[source.index("enter_exercise_mode() {"):
                          source.index("enter_provisioning_mode() {")]
        self.assertIn("preflight_domain_health", exercise)
        self.assertIn("preflight_exercise_time_dependencies", exercise)
        self.assertIn("require_north_validated_cold_start", exercise)
        self.assertLess(exercise.index("require_north_validated_cold_start"),
                        exercise.index("apply_router_policy exercise"))
        self.assertIn("sudo bash ${ROUTES}", exercise)
        self.assertIn("configure_windows_nat_exercise", exercise)
        self.assertIn("verify_persistent_state FALSE", exercise)


if __name__ == "__main__":
    unittest.main()
