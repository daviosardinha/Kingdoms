"""Static regression guard for Kingdoms-specific and standalone-capable LPE roles.

These tests do not validate Windows runtime or independent VM provisioning.
"""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = ROOT / "ansible/roles/windows_lpe/defaults/main.yml"
TASKS = ROOT / "ansible/roles/windows_lpe/tasks/main.yml"
KINGDOMS_WRAPPERS = [
    ROOT / "ansible/windows-lpe.yml",
    ROOT / "ansible/ws01-lpe-install.yml",
]


class WindowsLpeLearnerAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.defaults = DEFAULTS.read_text(encoding="utf-8")
        cls.tasks = TASKS.read_text(encoding="utf-8")
        cls.wrappers = [file.read_text(encoding="utf-8") for file in KINGDOMS_WRAPPERS]

    def test_shared_role_has_no_north_or_rickon_identity(self) -> None:
        self.assertNotIn(r"NORTH\rickon.stark", self.defaults)
        self.assertNotIn("Winter2022", self.defaults)
        self.assertIn("windows_lpe_learner_account: ''", self.defaults)
        self.assertIn("windows_lpe_learner_password: ''", self.defaults)

    def test_five_techniques_use_same_learner_identity(self) -> None:
        self.assertEqual(
            self.defaults.count('target_account: "{{ windows_lpe_learner_account }}"'),
            4,
        )
        self.assertEqual(
            self.defaults.count('owner_account: "{{ windows_lpe_learner_account }}"'),
            1,
        )
        self.assertEqual(
            self.defaults.count('target_password: "{{ windows_lpe_learner_password }}"'),
            1,
        )
        self.assertEqual(
            self.defaults.count('owner_password: "{{ windows_lpe_learner_password }}"'),
            1,
        )

    def test_kingdoms_wrappers_preserve_existing_values(self) -> None:
        for text in self.wrappers:
            self.assertIn("windows_lpe_learner_account: 'NORTH\\rickon.stark'", text)
            self.assertIn("windows_lpe_learner_password: 'Winter2022'", text)
            self.assertIn("role: windows_lpe", text)

    def test_identity_and_secret_guards_precede_scenario_mutations(self) -> None:
        identity_guard = self.tasks.index(
            "- name: Require a configured learner for identity-dependent scenarios"
        )
        credential_guard = self.tasks.index(
            "- name: Require an explicit learner credential for profile/RunAs seeding"
        )
        first_technique = self.tasks.index("- name: Manage unquoted service path technique")
        self.assertLess(identity_guard, credential_guard)
        self.assertLess(credential_guard, first_technique)
        self.assertIn("windows_lpe_action == 'apply'", self.tasks)


if __name__ == "__main__":
    unittest.main()
