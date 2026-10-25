"""NORTH audited installer failures and one-shot recovery policy tests."""
import json
from pathlib import Path
import stat
import subprocess
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import unittest
from goad.course1_install_diagnostics import emit, recovery_policy
from tests.test_north_tools_transition import isolated_method

RUNNER=Path(__file__).resolve().parents[1]/"scripts/north-install-observed.sh"

class NorthDiagnosticPolicyTests(unittest.TestCase):
    def test_journal_does_not_accept_arbitrary_secret_or_error_payload(self):
        with TemporaryDirectory() as tmp:
            provider=Path(tmp)/"c0ffee-north-vmware"/"provider"
            provider.mkdir(parents=True)
            f=emit(provider,machine="GOAD-WS01",phase="post-ws01-eval",
                   signature="VMTOOLS_PARTIAL_PERSISTENT",result="blocked")
            self.assertEqual(stat.S_IMODE(f.stat().st_mode),0o600)
            j=json.loads(f.read_text())
            self.assertEqual(j["policy"],"manual_review")
            self.assertEqual(j["instance"],"c0ffee-north-vmware")
            self.assertNotIn("stdout",j)
            with self.assertRaises(ValueError):
                emit(provider,machine="GOAD-WS01",phase="post-ws01-eval",
                     signature="password=abc",result="blocked")
            self.assertEqual(len(f.read_text().splitlines()),1)

    def test_explicit_allowed_actions(self):
        self.assertEqual(recovery_policy("VMTOOLS_MISSING"),"one_shot_original_tools_install")
        self.assertEqual(recovery_policy("VMTOOLS_PARTIAL"),"read_only_wait")
        self.assertEqual(recovery_policy("VMTOOLS_PARTIAL_PERSISTENT"),"manual_review")
        self.assertEqual(recovery_policy("VMTOOLS_WS01_SIGNED_IDLE_ORPHAN"),"one_shot_original_tools_install")
        with self.assertRaises(KeyError):
            recovery_policy("unknown")

    def test_symlinked_journal_is_rejected(self):
        with TemporaryDirectory() as tmp:
            provider=Path(tmp)/"abcdef-north-vmware"/"provider"
            provider.mkdir(parents=True)
            victim=Path(tmp)/"victim"
            victim.write_text("safe")
            (provider.parent/".north-install-recovery.jsonl").symlink_to(victim)
            with self.assertRaises(OSError):
                emit(provider,machine="GOAD-WS01",phase="post-ws01-eval",
                     signature="VMTOOLS_MISSING",result="observed")
            self.assertEqual(victim.read_text(),"safe")

    def test_persistent_partial_never_installs(self):
        with TemporaryDirectory() as tmp:
            provider=Path(tmp)/"123abc-north-vmware"/"provider"
            provider.mkdir(parents=True)
            guest=Mock(lab_name="NORTH",path=str(provider))
            guest.lab_name="NORTH"
            guest.path=str(provider)
            guest._winrm_forwarded_port.return_value=2203
            guest._wait_winrm_ready.return_value=True
            gate=isolated_method("_north_tools_transition_gate",logger=Mock())
            with patch("goad.course1_tools_transition.inspect_owned_guest_tools",
                       return_value=("/owned/guest.vmx","partial")) as inventory, \
                 patch("goad.course1_tools_transition.prove_idle_signed_original_ws01_orphan", return_value=False), \
                 patch("time.sleep") as pause:
                self.assertFalse(gate(guest,"GOAD-WS01","post-ws01-eval"))
            self.assertEqual(inventory.call_count,4)
            self.assertEqual(pause.call_count,3)
            guest._install_vmware_tools.assert_not_called()
            j=(provider.parent/".north-install-recovery.jsonl").read_text()
            self.assertIn("VMTOOLS_PARTIAL_PERSISTENT",j)

    def test_supervisor_log_failure_is_not_silent(self):
        r=subprocess.run(["bash","-n",str(RUNNER)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        r=subprocess.run(["bash",str(RUNNER)],capture_output=True,text=True)
        self.assertEqual(r.returncode,2)
        text=RUNNER.read_text()
        self.assertIn("umask 077",text)
        self.assertIn("installer.log",text)
        self.assertIn("STATUSES=",text)
        self.assertIn("STATUSES[1]",text)
        self.assertNotIn("-t destroy",text)

if __name__=="__main__":
    unittest.main()
