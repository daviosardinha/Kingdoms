"""NORTH WS01 -> WSLPE source-parity regression.

Source-only: does not contact guests, start providers, or change networking.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def source_lines(source: str) -> str:
    return "\n".join(line for line in source.splitlines()
                     if not line.lstrip().startswith("#"))


class WslpeWs01ParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.north = read("ad/GOAD/providers/vmware/Vagrantfile")
        cls.wslpe = read("ad/WSLPE/providers/vmware/Vagrantfile")
        cls.foundation = read("ansible/wslpe-foundation.yml")
        cls.lpe = read("ansible/wslpe-lpe-test.yml")
        cls.routes = read("playbooks.yml")

    def test_same_windows_box_distinct_host_identity(self):
        block = self.north.split(':name => "GOAD-WS01"', 1)[1].split("  },", 1)[0]
        for source in (block, self.wslpe):
            self.assertIn(':box => "mayfly/windows10"', source)
            self.assertIn(':box_version => "2024.01.06"', source)
            self.assertIn(':cpus => 2', source)
        self.assertIn(':mem => 4000', block)
        self.assertIn(':mem => 4096', self.wslpe)
        self.assertIn(':name => "WSLPE-WS01"', self.wslpe)
        self.assertIn(':hostname => "wslpe-ws01"', self.wslpe)
        self.assertNotIn("GOAD-WS01", self.wslpe)

    def test_standalone_core_has_no_domain_join_or_north_roles(self):
        for script in (self.foundation, self.lpe):
            active = source_lines(script)
            for forbidden in (
                "win_domain_membership", "commonwkstn", "member_domain:",
                "domain_password:", "north.sevenkingdoms.local",
                "hosts: dc", "hosts: GOAD", "lab-mode.sh",
                "settings/no_updates", "role: 'common'",
                "name: common", "name: commonwkstn",
            ):
                self.assertNotIn(forbidden, active)
        self.assertIn("if ($computer.PartOfDomain)", self.foundation)
        self.assertIn("if ($machine.PartOfDomain)", self.lpe)
        self.assertIn("hosts: wslpe", self.foundation)
        self.assertIn("hosts: wslpe", self.lpe)
        self.assertIn("WSLPE:\n  - wslpe-foundation.yml", self.routes)
        self.assertNotIn("WSLPE:\n  - ws01.yml", self.routes)

    def test_reuses_non_domain_windows_roles_but_does_not_enable_course(self):
        self.assertIn("name: settings/hostname", self.foundation)
        self.assertIn("hostname: WSLPE-WS01", self.foundation)
        self.assertIn("$env:COMPUTERNAME -ne 'WSLPE-WS01'", self.foundation)
        self.assertIn("name: settings/eval_rearm", self.foundation)
        self.assertIn("Create standard local WSLPE learner", self.foundation)
        self.assertIn("groups:\n          - Users", self.foundation)
        # Standalone learner RDP access is intentionally allowed through the
        # local built-in group, without granting administrative membership.
        self.assertIn("Grant standard local learner membership in Remote Desktop Users",
                      source_lines(self.foundation))
        self.assertIn("S-1-5-32-555", self.foundation)
        self.assertIn("S-1-5-32-544", self.foundation)
        self.assertIn("groups_action: replace", self.foundation)
        self.assertIn("WSLPE_LOCAL_LEARNER_RDP_GROUP=PASS", self.foundation)
        self.assertIn("WSLPE_LOCAL_ADMIN_MEMBERSHIP=DENIED", self.foundation)
        self.assertIn("windows_lpe_profile: none", self.lpe)
        self.assertIn("windows_lpe_allow_candidate: false", self.lpe)

    def test_runas_target_is_localized_without_changing_north(self):
        defaults = read("ansible/roles/windows_lpe/defaults/main.yml")
        task = read("ansible/roles/windows_lpe/tasks/techniques/stored_runas_credentials.yml")
        self.assertIn("credential_target: 'WS01\\kingdom.runas'", defaults)
        self.assertIn("windows_lpe_stored_runas_credential_target | default(", task)
        self.assertIn("windows_lpe_stored_runas_credentials.credential_target", task)
        self.assertIn(
            "windows_lpe_stored_runas_credential_target: 'WSLPE-WS01\\kingdom.runas'",
            self.lpe,
        )
        self.assertIn("windows_lpe_learner_account: 'WSLPE-WS01\\lpe.trainee'",
                      self.lpe)
        self.assertNotIn("NORTH\\rickon", self.lpe)

    def test_standalone_winrm_endpoint_scoped_per_inventory(self):
        for path in ("ad/WSLPE/data/inventory",
                     "ad/WSLPE/data/inventory_disable_vagrant"):
            data = read(path)
            self.assertIn("ansible_port=5985", data)
            self.assertIn("ansible_winrm_scheme=http", data)
            self.assertIn("ansible_winrm_transport=ntlm", data)
            self.assertIn("[wslpe]\nws01", data)

    def test_no_implicit_domain_mode_or_vulnerability_provisioning(self):
        stage1 = read("kingdoms/wslpe_stage1.py")
        resume = read("kingdoms/wslpe_resume.py")
        self.assertIn("instance.set_status(PROVIDED)", stage1)
        self.assertIn('"--no-provision"', resume)
        self.assertIn("direct_winrm_resume_file", resume)
        self.assertNotIn("win_domain_membership", source_lines(stage1))
        self.assertNotIn("windows_lpe_action: apply", self.foundation)
        self.assertIn("windows_lpe_action: \"{{ wslpe_action }}\"", self.lpe)

    def test_audits_are_nonmutating_and_release_is_not_claimed(self):
        access = read("ansible/wslpe-access-audit.yml")
        runtime = read("scripts/wslpe-network-acceptance.sh")
        self.assertIn("Get-WSManInstance", access)
        self.assertIn("UserAuthentication", access)
        self.assertIn("CertificateThumbprint", access)
        self.assertIn("NOT VERIFIED", access)
        self.assertIn("wslpe-stage2-acceptance.sh", runtime)
        self.assertIn("wslpe-exercise-network-preflight.py", runtime)
        self.assertIn("NOT VERIFIED", runtime)
        self.assertIn("PROVIDED", read("docs/WSLPE_WS01_PARITY_AUDIT.md"))


if __name__ == "__main__":
    unittest.main()
