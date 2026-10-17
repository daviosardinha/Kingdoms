"""Mock/source-only regression: WSLPE must not retire Vagrant before release.

NORTH provider stays untouched. No Windows/VMware/Ansible calls.
"""
from pathlib import Path
from types import SimpleNamespace
import unittest

from tests.test_kingdoms_course_registry import OperatorConsole, StubLog

ROOT=Path(__file__).resolve().parents[1]

class VagrantRetirementPolicyTests(unittest.TestCase):
    def setUp(self):
        self.console=OperatorConsole.__new__(OperatorConsole)
        self.console.legacy_calls=[]
        self.active={"lab":"WSLPE","instance":SimpleNamespace(lab_name="WSLPE")}
        self.console.lab_manager=SimpleNamespace(
            get_current_lab_name=lambda:self.active["lab"],
            get_current_instance=lambda:self.active["instance"],
            is_lab_exist=lambda l:l in {"GOAD","WSLPE"},
            set_lab=lambda l:self.active.__setitem__("lab",l),
        )
        self.console._selected_course="windows-lpe"
        StubLog.output=[]

    def test_wslpe_direct_call_refuses_disabling_bootstrap(self):
        self.assertIs(self.console.do_disable_vagrant(""),False)
        self.assertIn("Refusing disable"," ".join(str(v) for _,v in StubLog.output))

    def test_loaded_wslpe_guard_survives_course_selection_change(self):
        self.console._selected_course="north"
        self.active["lab"]="GOAD"
        self.assertIs(self.console.do_disable_vagrant(""),False)

    def test_unloaded_wslpe_lab_also_blocked(self):
        self.active["instance"]=None
        self.assertIs(self.console.do_disable_vagrant(""),False)

    def test_wslpe_console_rejects_legacy_disable_command(self):
        self.assertFalse(self.console.onecmd("disable_vagrant"))
        self.assertEqual(self.console.legacy_calls,[])

    def test_upstream_issue_pattern_is_not_reintroduced_in_student_release(self):
        installed=(
            ROOT/"goad/provider/vagrant/vmware_kingdoms.py"
        ).read_text(encoding="utf-8")
        self.assertIn("def _start_existing_instance",installed)
        self.assertIn("['vmrun', '-T', 'ws', 'start', vmx, 'nogui']",installed)
        self.assertIn("no Vagrant NAT discovery",installed)

        wslpe=(ROOT/"kingdoms/wslpe_resume.py").read_text(encoding="utf-8")
        self.assertIn("instance.get_status() != PROVIDED",wslpe)
        self.assertIn('["up", GUEST, "--no-provision"]',wslpe)
        # Because WSLPE's development-resume still authenticates through
        # Vagrant, it MUST stay blocked from early retirement.
        console=(ROOT/"goad_nomad.py").read_text(encoding="utf-8")
        self.assertIn("def do_disable_vagrant(self, arg=''):",console)
        self.assertIn("post-release start/reset have not been accepted",console)

if __name__=="__main__":
    unittest.main()
