"""NORTH uses the patched Kingdoms Ansible install pipeline, not upstream default."""
import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "playbooks.yml"
PHASE01 = ROOT / "ansible/phase01.yml"


class NativeNorthAnsiblePlanTests(unittest.TestCase):
    def load(self):
        return yaml.safe_load(LAYOUT.read_text(encoding="utf-8"))

    def test_north_has_explicit_native_kingdoms_plan_not_default(self):
        plans = self.load()
        self.assertIn("NORTH", plans)
        self.assertIn("GOAD", plans)
        self.assertNotEqual(plans["NORTH"], plans["default"])
        expected = [p for p in plans["GOAD"] if p != "ad-trusts.yml"]
        self.assertEqual(plans["NORTH"], expected)

    def test_north_preserves_forest_child_ws01_health_and_lpe(self):
        stages = self.load()["NORTH"]
        for item in (
            "build.yml", "ad-servers.yml", "ad-parent_domain.yml",
            "ad-child_domain.yml", "ad-members.yml", "kingdoms-time-backoff.yml",
            "ws01.yml", "kingdoms-health.yml", "phase01.yml",
            "ws01-lpe-install.yml", "kingdoms-health-final.yml",
        ):
            self.assertIn(item, stages)
            self.assertTrue((ROOT / "ansible" / item).is_file())
        self.assertLess(stages.index("ad-child_domain.yml"), stages.index("ad-members.yml"))
        self.assertLess(stages.index("ad-data.yml"), stages.index("ws01.yml"))
        self.assertLess(stages.index("kingdoms-health.yml"), stages.index("phase01.yml"))
        self.assertLess(stages.index("ws01-lpe-install.yml"),
                        stages.index("kingdoms-health-final.yml"))
        self.assertNotIn("ad-trusts.yml", stages)

    def test_native_ansible_provider_resolves_the_north_list(self):
        from goad.provisioner.ansible.ansible import Ansible
        controller = object.__new__(Ansible)
        self.assertEqual(controller.get_playbook_list("NORTH"),
                         self.load()["NORTH"])

    def test_phase01_resolves_correct_selected_kingdoms_data(self):
        txt = PHASE01.read_text(encoding="utf-8")
        self.assertIn("domain_name in ['GOAD', 'NORTH']", txt)
        self.assertIn('../ad/{{ domain_name }}/data/config.json', txt)
        self.assertNotIn('file: ../ad/GOAD/data/config.json', txt)
        self.assertIn("hosts: dc02:srv02", txt)
        data = yaml.safe_load(txt)
        self.assertEqual(len(data), 3)

    def test_north_removes_external_essos_but_retains_child(self):
        import json
        lab = json.loads((ROOT / "ad/NORTH/data/config.json").read_text())["lab"]
        self.assertEqual(set(lab["domains"]),
                         {"sevenkingdoms.local", "north.sevenkingdoms.local"})
        self.assertEqual(set(lab["hosts"]), {"dc01", "dc02", "srv02", "ws01"})
        self.assertEqual(lab["domains"]["sevenkingdoms.local"]["trust"], "")
        self.assertNotIn("ad-trusts.yml", self.load()["NORTH"])

    def test_reference_kingdoms_recipe_has_not_lost_essos(self):
        goad = self.load()["GOAD"]
        self.assertIn("ad-trusts.yml", goad)
        self.assertIn("phase01.yml", goad)
        self.assertIn("kingdoms-health-final.yml", goad)


if __name__ == "__main__":
    unittest.main()
