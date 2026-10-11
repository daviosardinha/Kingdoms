"""NORTH must use Kingdoms' full Ansible cadence minus retired Essos trust."""
import ast
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import yaml

ROOT = Path(__file__).resolve().parents[1]


def get_existing_playbook_method(manifest):
    source = (ROOT / "goad/provisioner/ansible/ansible.py").read_text()
    tree = ast.parse(source)
    cls = next(x for x in tree.body if isinstance(x, ast.ClassDef)
               and x.name == "Ansible")
    method = next(x for x in cls.body if isinstance(x, ast.FunctionDef)
                  and x.name == "get_playbook_list")
    scope = {
        "os": os, "yaml": yaml, "Log": Mock(),
        "GoadPath": SimpleNamespace(
            get_playbooks_lab_config=lambda: str(manifest),
            get_provisioner_path=lambda: str(ROOT / "ansible") + os.sep,
        ),
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]),
                 "goad/provisioner/ansible/ansible.py", "exec"), scope)
    return scope["get_playbook_list"]


class Course1AnsibleManifestTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "playbooks.yml"
        self.playbooks = yaml.safe_load(self.path.read_text())

    def test_north_sequence_is_complete_kingdoms_minus_external_essos_trust(self):
        original = self.playbooks["GOAD"]
        reduced = self.playbooks["NORTH"]
        self.assertEqual(original.count("ad-trusts.yml"), 1)
        self.assertEqual(reduced, [p for p in original if p != "ad-trusts.yml"])
        self.assertIn("ad-child_domain.yml", reduced)
        self.assertIn("phase01.yml", reduced)
        self.assertIn("kingdoms-health-final.yml", reduced)
        self.assertEqual(len(reduced), 21)
        for play in reduced:
            self.assertTrue((ROOT / "ansible" / play).is_file(), play)

    def test_existing_ansible_selector_returns_north_not_default(self):
        selector = get_existing_playbook_method(self.path)
        self.assertEqual(selector(None, "NORTH"), self.playbooks["NORTH"])
        self.assertEqual(selector(None, "GOAD"), self.playbooks["GOAD"])

    def test_missing_north_manifest_never_falls_back_to_default(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "playbooks.yml"
            p.write_text(yaml.safe_dump({"default": ["build.yml"]}))
            selector = get_existing_playbook_method(p)
            with self.assertRaisesRegex(ValueError, "requires its explicit"):
                selector(None, "NORTH")
            self.assertEqual(selector(None, "default"), ["build.yml"])

    def test_missing_north_playbook_is_fatal_not_silently_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "playbooks.yml"
            p.write_text(yaml.safe_dump({"NORTH": ["missing-course1-play.yml"]}))
            selector = get_existing_playbook_method(p)
            with self.assertRaisesRegex(ValueError, "NORTH playbook is missing"):
                selector(None, "NORTH")

    def test_phase01_uses_selected_kingdoms_scenario(self):
        phase = (ROOT / "ansible/phase01.yml").read_text()
        self.assertIn("domain_name in ['GOAD', 'NORTH']", phase)
        self.assertIn('file: "../ad/{{ domain_name }}/data/config.json"', phase)


if __name__ == "__main__":
    unittest.main()
