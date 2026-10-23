"""Kingdoms WSLPE Windows evaluation maintenance source contract.

This is an operator-controlled installation capability only. The tests do
not invoke Ansible, Windows commands, activation or a VMware guest.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WSLPE_FOUNDATION = ROOT / "ansible/wslpe-foundation.yml"
NORTH_WS01 = ROOT / "ansible/ws01.yml"
REARM_ROLE = ROOT / "ansible/roles/settings/eval_rearm/tasks/main.yml"
STAGE2 = ROOT / "scripts/wslpe-stage2-inspect.py"
NATIVE_BOOT = ROOT / "kingdoms/wslpe_stage1.py"
NETWORK_CHECK = ROOT / "scripts/wslpe-network-acceptance.sh"


class WslpeWindowsLicenseContractTests(unittest.TestCase):
    def setUp(self):
        self.wslpe = WSLPE_FOUNDATION.read_text(encoding="utf-8")
        self.north = NORTH_WS01.read_text(encoding="utf-8")
        self.role = REARM_ROLE.read_text(encoding="utf-8")
        self.stage2 = STAGE2.read_text(encoding="utf-8")

    def test_existing_north_role_reused_without_forking(self):
        self.assertIn("role: 'settings/eval_rearm'", self.north)
        self.assertIn("name: settings/eval_rearm", self.wslpe)
        self.assertEqual(self.wslpe.count("name: settings/eval_rearm"), 1)
        self.assertIn("TIMEBASED_EVAL", self.role)
        self.assertIn("GracePeriodRemaining", self.role)
        self.assertIn("'/rearm'", self.role)
        self.assertIn("ansible.windows.win_reboot", self.role)
        self.assertIn("WINDOWS_EVAL_READY=PASS", self.role)

    def test_rearm_happens_before_standalone_learner_creation(self):
        baseline = self.wslpe.index(
            "- name: Prove Windows client and domain-free security baseline"
        )
        maintenance = self.wslpe.index(
            "- name: Maintain approved Windows evaluation grace before learner creation"
        )
        licensing_gate = self.wslpe.index(
            "- name: Require enough Windows evaluation grace for a training session"
        )
        learner = self.wslpe.index(
            "- name: Create standard local WSLPE learner"
        )
        self.assertLess(baseline, maintenance)
        self.assertLess(maintenance, licensing_gate)
        self.assertLess(licensing_gate, learner)

    def test_future_learner_install_requires_24h_eval_grace_or_licensed_sku(self):
        self.assertIn("$grace -lt 1440", self.wslpe)
        self.assertIn("TIMEBASED_EVAL", self.wslpe)
        self.assertIn("LicenseStatus", self.wslpe)
        self.assertIn("WSLPE_LICENSE_READY=PASS", self.wslpe)
        self.assertIn("throw 'WSLPE Windows licensing is unverified", self.wslpe)

    def test_stage2_license_check_is_read_only(self):
        self.assertIn("SoftwareLicensingProduct", self.stage2)
        self.assertIn("LicenseShutdownEvidence", self.stage2)
        self.assertIn("Get-WinEvent", self.stage2)
        self.assertIn("def evaluate_license(", self.stage2)
        self.assertNotIn("slmgr.vbs", self.stage2)
        self.assertNotIn("'/rearm'", self.stage2)
        self.assertNotIn("Restart-Computer", self.stage2)

    def test_native_stage1_uses_existing_license_role_via_guarded_adapter(self):
        source = NATIVE_BOOT.read_text(encoding="utf-8")
        repair = (ROOT / "kingdoms/wslpe_stage1_repair.py").read_text()
        adapter = (ROOT / "kingdoms/wslpe_license_maintenance.py").read_text()
        for target in (source, repair):
            self.assertIn("maintain_native_wslpe_license(manager, confirmed=True)", target)
            self.assertLess(target.index("maintain_native_wslpe_license(manager, confirmed=True)"),
                            target.index("instance.set_status(PROVIDED)"))
            self.assertNotIn("slmgr.vbs", target)
            self.assertNotIn("win_reboot", target)
        self.assertIn('"--tags", LICENSE_TAG', adapter)
        self.assertIn('"--limit", "ws01"', adapter)
        self.assertIn("WSLPE_LICENSE_READY=PASS", adapter)
        self.assertNotIn("New-LocalUser", adapter)

    def test_license_tag_selects_existing_role_and_gate_not_learner(self):
        self.assertEqual(self.wslpe.count("name: settings/eval_rearm"), 1)
        before_learner = self.wslpe.split(
            "- name: Create standard local WSLPE learner"
        )[0]
        self.assertEqual(before_learner.count("- wslpe_license"), 2)
        after_learner = self.wslpe.split(
            "- name: Create standard local WSLPE learner"
        )[1]
        self.assertNotIn("wslpe_license", after_learner)

    def test_rearm_role_does_not_disable_defensive_controls(self):
        for content in (self.role, self.wslpe):
            for banned in (
                "Set-NetFirewallProfile -Enabled False",
                "Set-MpPreference -DisableRealtimeMonitoring",
                "EnableLUA = 0",
                "Stop-Service WLMS",
                "Disable-Service WLMS",
                "SkipRearm",
            ):
                self.assertNotIn(banned.casefold(), content.casefold())

    def test_source_only_validator_still_scopes_north_to_ws01(self):
        self.assertIn("hosts: ws01", self.north)
        self.assertIn("hosts: wslpe", self.wslpe)
        self.assertNotIn("hosts: dc", self.wslpe)
        self.assertNotIn("hosts: dc", self.role)


if __name__ == "__main__":
    unittest.main()
