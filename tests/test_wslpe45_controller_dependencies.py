"""Controller-only source provenance checks; never contact Windows or VMware."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import yaml

from kingdoms import wslpe45_batch_operator as batch


class ControllerDependencyTests(unittest.TestCase):
    def test_all_21_candidate_sources_and_lockdown_imports_resolve(self):
        seen = []
        for row in batch.index_rows():
            if row["status"] != "candidate":
                continue
            playbook = batch.ROOT / row["playbook"]
            plays = yaml.safe_load(playbook.read_text(encoding="utf-8"))
            self.assertEqual(
                batch.controller_source_blockers(playbook, plays),
                [], f"#{row['number']} {row['id']}",
            )
            seen.append(row["id"])
        self.assertEqual(len(seen), 21)

    def test_rejects_traversal_style_wrong_relative_source(self):
        path = batch.ROOT / "ansible/wslpe45/traversal.yml"
        plays = deepcopy(yaml.safe_load(path.read_text(encoding="utf-8")))
        copy_task = next(
            t for t in plays[1]["tasks"] if "ansible.windows.win_copy" in t
        )
        copy_task["ansible.windows.win_copy"]["src"] = (
            "files/wslpe45/WslpeFixture.psm1"
        )
        self.assertTrue(any(
            "noncanonical controller copy source" in issue
            for issue in batch.controller_source_blockers(path, plays)
        ))

    def test_missing_source_is_rejected_before_any_guest_access(self):
        path = batch.ROOT / "ansible/wslpe45/traversal.yml"
        plays = deepcopy(yaml.safe_load(path.read_text(encoding="utf-8")))
        copy_task = next(
            t for t in plays[1]["tasks"] if "ansible.windows.win_copy" in t
        )
        copy_task["ansible.windows.win_copy"]["src"] = (
            "../files/wslpe45/NonexistentSource.cs"
        )
        self.assertTrue(any(
            "missing or unsafe controller copy source" in issue
            for issue in batch.controller_source_blockers(path, plays)
        ))

    def test_import_must_be_exact_existing_lockdown_task(self):
        path = batch.ROOT / "ansible/wslpe45/traversal.yml"
        plays = deepcopy(yaml.safe_load(path.read_text(encoding="utf-8")))
        imported = next(
            t for t in plays[1]["tasks"]
            if "ansible.builtin.import_tasks" in t
        )
        imported["ansible.builtin.import_tasks"] = "other.yml"
        self.assertIn(
            "unsafe or missing WSLPE library lockdown import",
            batch.controller_source_blockers(path, plays),
        )

    def test_rejects_source_symlink_even_if_target_is_a_regular_file(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            playbook_dir = root / "ansible/wslpe45"
            source_dir = root / "ansible/files/wslpe45"
            playbook_dir.mkdir(parents=True)
            source_dir.mkdir(parents=True)
            (playbook_dir / "lockdown-library.yml").write_text("[]\n")
            (source_dir / "WslpeFixture.psm1").write_text("module")
            (source_dir / "Other.psm1").symlink_to(
                source_dir / "WslpeFixture.psm1"
            )
            plays = [{"tasks": [
                {"ansible.builtin.import_tasks": "lockdown-library.yml"},
                {"ansible.windows.win_copy": {
                    "src": "../files/wslpe45/WslpeFixture.psm1"
                }},
                {"ansible.windows.win_copy": {
                    "src": "../files/wslpe45/Other.psm1"
                }},
            ]}]
            from unittest.mock import patch
            with patch.object(batch, "ROOT", root):
                issues = batch.controller_source_blockers(
                    playbook_dir / "example.yml", plays
                )
            self.assertTrue(any("unsafe controller copy" in x for x in issues))


if __name__ == "__main__":
    unittest.main()
