"""Fail-closed NORTH-derived WSLPE NIC lifecycle, without touching guests."""
import unittest
from kingdoms import wslpe_nic_contract as nic


VMX = '''
ethernet0.present = "TRUE"
ethernet0.connectionType = "nat"
ethernet0.startConnected = "TRUE"
ethernet1.present = "TRUE"
ethernet1.connectionType = "custom"
ethernet1.vnet = "vmnet2"
ethernet1.startConnected = "TRUE"
'''
SUBNETS = {"vmnet2": "172.28.231.0/24", "vmnet8": "192.168.213.0/24"}


class WslpeNicContractTests(unittest.TestCase):
    def test_two_nic_provisioning_passes_for_dedicated_vmnet(self):
        self.assertEqual(nic.check_provisioning_layout(VMX), [])
        self.assertEqual(nic.check_exercise_mapping(VMX, SUBNETS, "172.28.231"), [])

    def test_reject_missing_or_wrong_management_nat(self):
        invalid = VMX.replace('ethernet0.connectionType = "nat"',
                              'ethernet0.connectionType = "bridged"')
        self.assertTrue(nic.check_provisioning_layout(invalid))
        invalid = VMX.replace('ethernet0.startConnected = "TRUE"',
                              'ethernet0.startConnected = "FALSE"')
        self.assertTrue(nic.check_provisioning_layout(invalid))

    def test_refuse_north_and_shared_nat_vmnet_for_exercise(self):
        for vnet in ("vmnet1", "vmnet8", "vmnet10", "vmnet20", "vmnet30", "vmnet99"):
            with self.subTest(vnet=vnet):
                vmx = VMX.replace("vmnet2", vnet)
                messages = nic.check_exercise_mapping(vmx, SUBNETS, "172.28.231")
                self.assertTrue(any("NORTH or a shared default VMware network" in x for x in messages))

    def test_unproven_vmnet_assignment_is_not_guessed(self):
        vmx = VMX.replace('ethernet1.vnet = "vmnet2"', "")
        messages = nic.check_exercise_mapping(vmx, SUBNETS, "172.28.231")
        self.assertTrue(any("explicit vnet assignment" in x for x in messages))

    def test_actual_vmnet_subnet_must_match_native_instance(self):
        wrong = {"vmnet2": "172.16.195.0/24"}
        messages = nic.check_exercise_mapping(VMX, wrong, "172.28.231")
        self.assertTrue(any("not native WSLPE" in x for x in messages))
        self.assertTrue(nic.check_exercise_mapping(VMX, {}, "172.28.231"))

    def test_north_persistent_exercise_state_is_independent(self):
        self.assertTrue(nic.check_exercise_persistent_state(VMX))
        offline = VMX.replace('ethernet0.startConnected = "TRUE"',
                              'ethernet0.startConnected = "FALSE"')
        self.assertEqual(nic.check_exercise_persistent_state(offline), [])
        self.assertTrue(nic.check_provisioning_layout(offline))


if __name__ == "__main__":
    unittest.main()
