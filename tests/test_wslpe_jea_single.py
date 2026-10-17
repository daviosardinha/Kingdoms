"""JEA #30 fail-closed PS5.1 remote lifecycle regression; zero guest actions."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/wslpe-jea-single.py"
PLAY = ROOT / "ansible/wslpe45/jea_role_capability_misconfig.yml"
SPEC = importlib.util.spec_from_file_location("wslpe_jea_single_gate", SCRIPT)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

class JeaSingleGateTests(unittest.TestCase):
    def test_source_plan_never_contacts_guest_or_hypervisor(self):
        with patch.object(sys, "argv", [str(SCRIPT)]):
            self.assertEqual(MOD.main(), 0)

    def test_apply_refused_even_with_recovery_approved(self):
        for flags in (["--apply"], ["--recovery-rehearsed"],
                      ["--apply", "--recovery-rehearsed"]):
            with self.subTest(flags=flags), patch.object(sys, "argv", [str(SCRIPT), *flags]):
                self.assertEqual(MOD.main(), 2)

    def test_remote_playbook_blocks_apply_and_reset_before_windows(self):
        plays = yaml.safe_load(PLAY.read_text(encoding="utf-8"))
        self.assertEqual([p["hosts"] for p in plays], ["localhost", "wslpe"])
        pre = plays[1]["pre_tasks"]
        self.assertIn("ansible.builtin.fail", pre[0])
        self.assertEqual(pre[0]["when"],
                         "(wslpe_45_action | default('')) in ['apply', 'reset']")
        self.assertEqual(pre[1]["changed_when"], False)
        self.assertIn("win_powershell", next(iter(
            k for k in pre[1] if k.startswith("ansible.windows."))))
        self.assertIn("NoServiceRestart", pre[0]["ansible.builtin.fail"]["msg"])

    def test_source_plan_enforces_remote_guard(self):
        self.assertEqual(MOD.local_candidate()["number"], 30)
        original = PLAY.read_text(encoding="utf-8")
        try:
            # Read-only mock: do not mutate files to test the failing path.
            with patch.object(MOD, "local_candidate",
                              side_effect=ValueError("Missing remote guard")), \
                 patch.object(sys, "argv", [str(SCRIPT)]):
                self.assertEqual(MOD.main(), 2)
        finally:
            self.assertEqual(PLAY.read_text(encoding="utf-8"), original)

    def test_no_implicit_winrm_ansible_or_north_actions(self):
        script = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("subprocess.run(", "ansible-playbook", "Start-Service",
                          "Restart-Service", "revertToSnapshot", "vmrun",
                          "disable_vagrant", "GOAD-WS01", "10.4.10.31"):
            self.assertNotIn(forbidden, script)
        self.assertIn("[BLOCKED] PowerShell 5.1 JEA registration", script)

if __name__ == "__main__":
    unittest.main()
