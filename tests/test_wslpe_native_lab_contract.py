"""Source-only contract for the native Kingdoms WSLPE single-workstation lab.

Does not create, start, destroy or access VMs. Guest/runtime proof is separate.
"""
from pathlib import Path
import unittest

from kingdoms.course_registry import get_course


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "ad/WSLPE"
VM = LAB / "providers/vmware/Vagrantfile"
PROVIDER_INVENTORY = LAB / "providers/vmware/inventory"
INITIAL_INVENTORY = LAB / "data/inventory"
LAB_INVENTORY = LAB / "data/inventory_disable_vagrant"
ROUTING = ROOT / "playbooks.yml"
FOUNDATION = ROOT / "ansible/wslpe-foundation.yml"
LPE_HARNESS = ROOT / "ansible/wslpe-lpe-test.yml"
CONTROLLER = ROOT / "goad_nomad.py"
PROTOTYPE = ROOT / "courses/windows-lpe/standalone/Vagrantfile"


class WslpeNativeLabContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vm = VM.read_text(encoding="utf-8")
        cls.provider = PROVIDER_INVENTORY.read_text(encoding="utf-8")
        cls.initial_inventory = INITIAL_INVENTORY.read_text(encoding="utf-8")
        cls.inventory = LAB_INVENTORY.read_text(encoding="utf-8")
        cls.routes = ROUTING.read_text(encoding="utf-8")
        cls.foundation = FOUNDATION.read_text(encoding="utf-8")
        cls.harness = LPE_HARNESS.read_text(encoding="utf-8")
        cls.controller = CONTROLLER.read_text(encoding="utf-8")

    def test_first_class_lab_follows_existing_discovery_layout(self):
        self.assertTrue((LAB / "providers/vmware").is_dir())
        self.assertTrue((LAB / "data").is_dir())
        self.assertTrue(PROVIDER_INVENTORY.is_file())
        self.assertTrue(INITIAL_INVENTORY.is_file())
        self.assertTrue(LAB_INVENTORY.is_file())
        self.assertEqual(get_course("windows-lpe").legacy_lab, "WSLPE")
        self.assertFalse(get_course("windows-lpe").lifecycle_ready)

    def test_single_distinct_pinned_windows_guest(self):
        self.assertEqual(self.vm.count(':name => "WSLPE-WS01"'), 1)
        self.assertIn(':hostname => "wslpe-ws01"', self.vm)
        self.assertIn(':box => "mayfly/windows10"', self.vm)
        self.assertIn(':box_version => "2024.01.06"', self.vm)
        self.assertIn(':ip => "{{ip_range}}.31"', self.vm)
        self.assertIn(':cpus => 2', self.vm)
        self.assertIn(':mem => 4096', self.vm)
        self.assertNotIn('GOAD-WS01', self.vm)

    def test_recipe_has_no_north_network_or_domain_dependencies(self):
        for source in (self.vm, self.provider, self.initial_inventory, self.inventory):
            for term in ("vmnet10", "vmnet20", "vmnet30", "vmnet99",
                         "10.4.10.", "north.sevenkingdoms.local",
                         "win_domain_membership", "GOAD-ROUTER"):
                self.assertNotIn(term, source)

    def test_inventory_contains_only_local_workstation(self):
        self.assertIn('ws01 ansible_host={{ip_range}}.31', self.provider)
        self.assertIn('ansible_connection=winrm', self.inventory)
        self.assertIn('ansible_connection=winrm', self.initial_inventory)
        self.assertIn('[wslpe]\nws01', self.initial_inventory)
        self.assertIn('[windows_lpe_standalone]\nws01', self.initial_inventory)
        self.assertIn('ansible_user=vagrant', self.inventory)
        self.assertIn('[wslpe]\nws01', self.inventory)
        self.assertIn('[windows_lpe_standalone]\nws01', self.inventory)
        self.assertNotIn('[dc]', self.inventory)
        self.assertNotIn('[domain]', self.inventory)

    def test_initial_provisioner_inventory_uses_native_source_path(self):
        # Existing Ansible._get_lab_inventory reads data/inventory during the
        # initial run, NOT data/inventory_disable_vagrant.
        from goad.goadpath import GoadPath
        self.assertEqual(
            Path(GoadPath.get_lab_inventory_file("WSLPE")).resolve(),
            INITIAL_INVENTORY.resolve(),
        )

    def test_native_playbook_routing_is_not_ad_or_full_lpe(self):
        self.assertIn('WSLPE:\n  - wslpe-foundation.yml\n', self.routes)
        self.assertNotIn('WSLPE:\n  - build.yml', self.routes)
        self.assertNotIn('WSLPE:\n  - ws01-lpe-install.yml', self.routes)
        self.assertIn('hosts: wslpe', self.foundation)
        self.assertNotIn('role: windows_lpe', self.foundation)
        self.assertNotIn('win_domain_membership', self.foundation)

    def test_foundation_guards_local_identity_and_windows_security(self):
        for marker in (
            "KINGDOMS_WSLPE_LEARNER_PASSWORD",
            "ansible.windows.win_user:",
            "groups_action: replace",
            "Get-CimInstance Win32_ComputerSystem",
            "if ($computer.PartOfDomain)",
            "EnableLUA",
            "Get-NetFirewallProfile",
            "Get-MpComputerStatus",
            "Get-LocalGroupMember",
            "WSLPE_LOCAL_LEARNER=PASS",
        ):
            self.assertIn(marker, self.foundation)
        self.assertIn("no_log: true", self.foundation)

    def test_existing_windows_lpe_role_is_reused_one_technique_at_a_time(self):
        self.assertIn('role: windows_lpe', self.harness)
        self.assertIn('windows_lpe_profile: none', self.harness)
        self.assertIn('windows_lpe_allow_candidate: false', self.harness)
        self.assertIn("wslpe_action == 'status' or (wslpe_techniques | length) == 1", self.harness)
        self.assertIn("KINGDOMS_WSLPE_LEARNER_PASSWORD", self.harness)
        self.assertIn("WSLPE-WS01", self.harness)
        self.assertIn("if ($machine.PartOfDomain)", self.harness)
        # Manual harness must never be part of normal WSLPE install.
        self.assertNotIn('wslpe-lpe-test.yml', self.routes)

    def test_operator_installer_does_not_implicitly_boot_wslpe(self):
        self.assertIn("self.lab_manager.get_current_lab_name() == 'WSLPE'", self.controller)
        self.assertIn("if getattr(args, 'lab', None) == 'WSLPE'", self.controller)
        self.assertIn("WSLPE is a registered Kingdoms lab recipe", self.controller)
        self.assertIn("bootstrap_native_wslpe(", self.controller)
        self.assertIn("select windows-lpe explicitly", self.controller.lower())

    def test_previous_parallel_bootstrap_is_not_authoritative(self):
        self.assertTrue(PROTOTYPE.exists())
        self.assertIn("Direct VM boot is retired", self.controller)
        self.assertIn("Direct Windows LPE VM bootstrap is retired", self.controller)

    def test_existing_north_scenario_role_untouched_by_new_lab_route(self):
        self.assertIn('GOAD:\n  - build.yml', self.routes)
        self.assertIn('  - ws01-lpe-install.yml', self.routes)


if __name__ == "__main__":
    unittest.main()
