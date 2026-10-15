"""Static safety checks for the Kingdoms standalone Windows LPE VM definition.

Does not boot, provision, or connect to Windows. Runtime VMX/network inspection
is still required after the first deliberate boot.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
VAGRANTFILE = ROOT / "courses/windows-lpe/standalone/Vagrantfile"
ARCHITECTURE = ROOT / "docs/KINGDOMS_COURSE_ARCHITECTURE.md"


class KingdomsWindowsLpeVmContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.vagrant = VAGRANTFILE.read_text(encoding="utf-8")
        cls.architecture = ARCHITECTURE.read_text(encoding="utf-8")

    def test_pinned_image_and_unique_vm_identity(self) -> None:
        self.assertIn('guest.vm.box = "mayfly/windows10"', self.vagrant)
        self.assertIn('guest.vm.box_version = "2024.01.06"', self.vagrant)
        self.assertIn('config.vm.define "kingdoms-lpe-ws01"', self.vagrant)
        self.assertIn('vmware.vmx["memsize"] = "4096"', self.vagrant)
        self.assertIn('vmware.vmx["numvcpus"] = "2"', self.vagrant)

    def test_no_lab_network_and_only_initial_management_nat(self) -> None:
        self.assertIn('vmware.vmx["ethernet0.connectionType"] = "nat"', self.vagrant)
        self.assertIn('vmware.vmx["ethernet1.present"] = "FALSE"', self.vagrant)
        self.assertIn('vmware.vmx["ethernet2.present"] = "FALSE"', self.vagrant)
        for banned in ("vmnet10", "vmnet20", "vmnet30", "vmnet99", ":private_network", ":public_network"):
            self.assertNotIn(banned, self.vagrant)

    def test_no_automatic_domain_join_or_exploit_provisioning(self) -> None:
        self.assertNotIn("guest.vm.provision", self.vagrant)
        self.assertNotIn("config.vm.provision", self.vagrant)
        self.assertNotIn("win_domain_membership", self.vagrant)
        self.assertNotIn("ansible/ws01.yml", self.vagrant)
        self.assertNotIn("windows_lpe_action", self.vagrant)

    def test_windows_management_and_no_unrestricted_rdp_forward(self) -> None:
        self.assertIn("guest.vm.communicator = \"winrm\"", self.vagrant)
        self.assertIn('guest.vm.synced_folder ".", "/vagrant", disabled: true', self.vagrant)
        self.assertIn("id: \"rdp\", auto_correct: false, disabled: true", self.vagrant)

    def test_course_boundaries_are_documented(self) -> None:
        for term in (
            "The Fall of the North",
            "Title not yet confirmed",
            "Windows Local Privilege Escalation",
            "courses/windows-lpe/standalone/",
        ):
            self.assertIn(term, self.architecture)

    def test_operator_control_plane_is_not_learner_access(self) -> None:
        for boundary in (
            "operator-only control plane",
            "Learners (untrusted lab users)",
            "installer, hypervisor APIs",
            "never the operator installer directly",
            "future AWS-backed Windows LPE course",
        ):
            self.assertIn(boundary, self.architecture)



if __name__ == "__main__":
    unittest.main()
