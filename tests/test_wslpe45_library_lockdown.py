"""Library ACL must be hardened before source deployment in every candidate."""
from pathlib import Path
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]
LOCK=ROOT/"ansible/wslpe45/lockdown-library.yml"
CANDIDATES=(
    "scheduled_task_definition_acl","scm_create_service_acl",
    "privileged_service_config_injection","privileged_updater_hijack",
    "ifeo_debugger_acl_hijack","app_paths_registry_hijack",
    "setakeownership_privilege","serestore_privilege","sedebug_privilege",
    "traversal","privileged_argument_injection",
)

class LibraryLockdownTests(unittest.TestCase):
    def test_acl_does_not_allow_learner_overwrite_elevated_scripts(self):
        tasks=yaml.safe_load(LOCK.read_text())
        self.assertEqual(len(tasks),1)
        code=tasks[0]["ansible.windows.win_powershell"]["script"]
        for value in ("WSLPE-WS01","PartOfDomain","KingdomsWSLPE45",
                      "S-1-5-32-545","ReadAndExecute",
                      "S-1-5-18","S-1-5-32-544",
                      "SetAccessRuleProtection($true,$false)",
                      "Set-Acl -LiteralPath $path",
                      "Shared library remains writable"):
            self.assertIn(value,code)
        self.assertNotIn("10.4.10.31",code)
        self.assertNotIn("GOAD-WS01",code)
        self.assertEqual(tasks[0]["when"],"wslpe_45_action == 'apply'")

    def test_library_hardening_precedes_every_shared_source_copy(self):
        for name in CANDIDATES:
            with self.subTest(technique=name):
                path=ROOT/f"ansible/wslpe45/{name}.yml"
                plays=yaml.safe_load(path.read_text())
                self.assertEqual([p["hosts"] for p in plays],["localhost","wslpe"])
                tasks=plays[1]["tasks"]
                imports=[(i,x) for i,x in enumerate(tasks)
                         if x.get("ansible.builtin.import_tasks")=="lockdown-library.yml"]
                self.assertEqual(len(imports),1)
                location=imports[0][0]
                self.assertTrue(any("ansible.windows.win_file" in x for x in tasks[:location]))
                self.assertTrue(any("ansible.windows.win_copy" in x for x in tasks[location+1:]))
                self.assertFalse(any("ansible.windows.win_copy" in x for x in tasks[:location]))

if __name__=="__main__":
    unittest.main()
