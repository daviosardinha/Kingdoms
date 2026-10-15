"""Fail-closed source checks for WSLPE portability beyond this VMware host.

Source tests only. VMware routes/interfaces and any VPS/cloud adapter still
need live runtime validation before installation is unlocked.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "ad/WSLPE/providers/vmware/Vagrantfile"
SHARED_VMWARE = ROOT / "template/provider/vmware/Vagrantfile"
NETWORK_CONTRACT = ROOT / "docs/WSLPE_NETWORK_PORTABILITY.md"
NATIVE_PREVIEW = ROOT / "scripts/wslpe-preview-native-instance.py"
OPERATOR_CONSOLE = ROOT / "goad_nomad.py"
LPE_ROLE = ROOT / "ansible/roles/windows_lpe/defaults/main.yml"


class WslpeNetworkPortabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recipe = RECIPE.read_text(encoding="utf-8")
        cls.template = SHARED_VMWARE.read_text(encoding="utf-8")
        cls.contract = NETWORK_CONTRACT.read_text(encoding="utf-8")
        cls.preview = NATIVE_PREVIEW.read_text(encoding="utf-8")
        cls.console = OPERATOR_CONSOLE.read_text(encoding="utf-8")
        cls.role = LPE_ROLE.read_text(encoding="utf-8")

    def test_wslpe_recipe_has_no_hardcoded_vmnet_or_host_subnet(self):
        for forbidden in (
            "vmnet8", "vmnet10", "vmnet99", "vmnet1",
            "172.28.231", "192.168.213", "192.168.76",
            "10.4.10", "10.4.99",
        ):
            self.assertNotIn(forbidden, self.recipe)
        self.assertIn(':ip => "{{ip_range}}.31"', self.recipe)

    def test_wslpe_uses_native_kingdoms_private_network_not_north_adapters(self):
        self.assertIn("target.vm.network :private_network, ip: box[:ip]", self.template)
        self.assertIn("unless box[:skip_private_network]", self.template)
        self.assertNotIn("skip_private_network", self.recipe)
        self.assertNotIn("vmware_network_adapters", self.recipe)
        self.assertNotIn(":vmware_vmx", self.recipe)

    def test_preview_uses_operator_chosen_private_prefix(self):
        self.assertIn('parser.add_argument(\n        "--ip-range"', self.preview)
        self.assertIn('instance._create_vagrantfile()', self.preview)
        self.assertIn("Live host/VMware vmnet collision validation: NOT PERFORMED", self.preview)
        self.assertNotIn("vagrant up", self.preview)

    def test_shared_lpe_role_has_no_provider_or_vmnet_dependencies(self):
        for forbidden in ("vmnet8", "vmnet10", "vmnet99", "VNET_", "ec2.amazonaws"):
            self.assertNotIn(forbidden, self.role)

    def test_unapproved_wslpe_install_remains_locked(self):
        self.assertIn("WSLPE native Kingdoms instance integration is pending", self.console)
        self.assertIn("WSLPE is a registered Kingdoms lab recipe", self.console)
        self.assertIn("legacy -l WSLPE mutation", self.console)

    def test_cloud_portability_is_not_misrepresented_as_deployed(self):
        self.assertIn("only a VMware provider definition", self.contract)
        self.assertIn("not yet implemented as a complete pre-install automated gate", self.contract)
        self.assertIn("not applicable", self.contract)
        self.assertIn("without NORTH", self.contract)


if __name__ == "__main__":
    unittest.main()
