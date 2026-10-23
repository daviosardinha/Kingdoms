"""Source contract: WSLPE41 foundation evidence is emitted only after Windows role success."""
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "ansible/wslpe-lpe-test.yml"


class FoundationStageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PLAYBOOK.read_text(encoding="utf-8")
        cls.plays = yaml.safe_load(cls.source)

    def test_existing_role_preserved_with_fresh_only_post_role_gate(self):
        self.assertEqual(len(self.plays), 2)
        guest = self.plays[1]
        self.assertEqual(guest["hosts"], "wslpe")
        self.assertEqual(guest["roles"][0]["role"], "windows_lpe")
        tasks = guest["post_tasks"]
        self.assertEqual(len(tasks), 3)
        for task in tasks:
            self.assertEqual(task["when"], "wslpe41_fresh_run | default(false) | bool")
        self.assertIn("ansible.windows.win_powershell", tasks[0])
        self.assertIn("WSLPE41_POST_ROLE_GUEST=PASS",
                      tasks[0]["ansible.windows.win_powershell"]["script"])
        self.assertIn("wslpe41_windows_stage_proof.output == ['WSLPE41_POST_ROLE_GUEST=PASS']",
                      tasks[1]["ansible.builtin.assert"]["that"])
        self.assertEqual(tasks[2]["ansible.builtin.debug"]["msg"],
                         "WSLPE41_STAGE={{ wslpe_techniques[0] }}:{{ wslpe41_stage_label }}:PASS")

    def test_mutation_preflight_checks_https_guest_and_instance(self):
        tasks = self.plays[0]["tasks"]
        fresh = next(task for task in tasks if task["name"].startswith("Restrict the unified fresh"))
        self.assertEqual(fresh["when"], "wslpe41_fresh_run | default(false) | bool")
        rules = "\n".join(fresh["ansible.builtin.assert"]["that"])
        for required in (
            "groups.get('wslpe', []) == ['ws01']",
            "groups.get('windows_lpe_standalone', []) == ['ws01']",
            "(groups.get('domain', []) | length) == 0",
            "(groups.get('dc', []) | length) == 0",
            "hostvars['ws01']['ansible_host'] == wslpe41_expected_address",
            "hostvars['ws01']['ansible_port'] | int == 5986",
            "hostvars['ws01']['ansible_winrm_scheme'] == 'https'",
            "hostvars['ws01']['ansible_winrm_server_cert_validation'] == 'validate'",
            "lookup('env', 'KINGDOMS_WSLPE_INSTANCE_ID')",
            "wslpe41_stage_label == ('apply' if wslpe_action == 'apply' else 'vulnerable')",
        ):
            self.assertIn(required, rules)
        self.assertLess(tasks.index(fresh), next(
            i for i, task in enumerate(tasks)
            if task["name"].startswith("Refuse source-visible fixture credentials")
        ))

    def test_no_new_windows_lpe_shared_role_changes_needed(self):
        # The first 20 still run through their original playbook/role;
        # the new proof is a conditional post-task in this standalone harness.
        self.assertIn("windows_lpe_action", self.plays[1]["roles"][0]["vars"])
        self.assertIn("wslpe41_fresh_run | default(false) | bool", self.source)


if __name__ == "__main__":
    unittest.main()
