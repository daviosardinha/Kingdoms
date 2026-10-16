"""Standalone AIE reset preserves NORTH's shared role and state snapshot."""
from pathlib import Path
import re
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "ansible/wslpe-lpe-test.yml"
RESET = ROOT / "ansible/wslpe-aie-reset-tasks.yml"
SHARED = ROOT / "ansible/roles/windows_lpe/tasks/techniques/always_install_elevated.yml"
ORIGINAL_SHARED_SHA256 = None  # No role modifications are needed for WSLPE.


class WslpeAieResetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = yaml.safe_load(ADAPTER.read_text(encoding="utf-8"))
        cls.tasks = yaml.safe_load(RESET.read_text(encoding="utf-8"))

    def test_only_reset_for_exact_standalone_technique_is_intercepted(self):
        play = self.adapter[1]
        self.assertEqual(play["hosts"], "wslpe")
        self.assertEqual(play["roles"][0]["role"], "windows_lpe")
        condition = play["roles"][0]["when"]
        self.assertIn("wslpe_action == 'reset'", condition)
        self.assertIn("wslpe_techniques == ['always_install_elevated']", condition)
        target = play["tasks"][0]
        self.assertEqual(target["ansible.builtin.include_tasks"],
                         "wslpe-aie-reset-tasks.yml")
        self.assertEqual(target["when"],
                         "wslpe_action == 'reset' and wslpe_techniques == ['always_install_elevated']")
        self.assertIn("Prove the exact local guest and domain-free learner identity",
                      play["pre_tasks"][0]["name"])

    def test_two_process_hive_lifecycle_with_snapshot_kept_to_last_task(self):
        self.assertEqual(len(self.tasks), 4)
        first = self.tasks[0]["ansible.windows.win_powershell"]["script"]
        second = self.tasks[2]["ansible.windows.win_command"]["argv"]
        final = self.tasks[3]["ansible.windows.win_powershell"]["script"]
        self.assertEqual(second, ["reg.exe", "unload", "HKU\\KingdomAIE"])
        self.assertNotIn("reg.exe unload", first)
        self.assertIn("registry value did not restore", first)
        self.assertIn("snapshot does not belong", first)
        self.assertIn("hivelist", first)
        self.assertIn("exact learner profile", first)
        self.assertIn("S-1-5-32-544", first)
        self.assertIn("PartOfDomain", first)
        self.assertIn("Get-LocalUser -Name 'lpe.trainee'", first)
        self.assertIn("Ansible.Result", first)
        self.assertIn("wslpe_aie_restore.result.snapshot_verified", str(self.tasks[1]))
        self.assertIn("temporary_hive", str(self.tasks[2]["when"]))
        self.assertIn("Remove-Item -LiteralPath $stateFile", final)
        self.assertIn("Remove-Item -LiteralPath $root", final)
        self.assertIn("unexpected contents", final)
        self.assertIn("HKLM value not restored", final)
        self.assertNotIn(" -Recurse", final)

    def test_no_domain_north_firewall_or_vmware_changes(self):
        for path in (ADAPTER, RESET):
            source = path.read_text(encoding="utf-8")
            for forbidden in ("vmrun ", "vagrant destroy", "GOAD-DC", "10.4.10.",
                              "nft flush", "New-ADUser", "Set-ADUser"):
                self.assertNotIn(forbidden, source)
        self.assertIn("reg.exe unload", SHARED.read_text(encoding="utf-8"))
        # Preserve shared role unchanged rather than teaching a NORTH repair
        # as a WSLPE deployment prerequisite.

    def test_reset_rejects_snapshot_mismatch_foreign_mount_and_extra_files(self):
        first = self.tasks[0]["ansible.windows.win_powershell"]["script"]
        final = self.tasks[3]["ansible.windows.win_powershell"]["script"]
        self.assertIn("$state.sid -ne $sid", first)
        self.assertIn("[string]$state.profile", first)
        self.assertIn("hiveList", first)
        self.assertIn("record.Count -ne 1", first)
        self.assertIn('EntryPoint="QueryDosDeviceW"', first)
        self.assertIn('StringComparison]::OrdinalIgnoreCase', first)
        self.assertIn('$expectedHive = $volume', first)
        self.assertIn('[string]::Equals(', first)
        self.assertIn('AIE temporary registry mount does not map to the exact learner NTUSER.DAT', first)
        self.assertNotIn('$pathTail', first)
        self.assertNotIn('.EndsWith(', first)
        self.assertIn("Get-Item -LiteralPath $path", first)
        self.assertIn("ReparsePoint", first)
        self.assertIn("$entries.Count -ne 1", final)
        self.assertIn("$entries[0].Name -ne 'state.json'", final)

if __name__ == "__main__":
    unittest.main()
