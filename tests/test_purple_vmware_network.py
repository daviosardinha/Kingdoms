"""No host changes: validate PURPLE uses one existing, unused vmnet4."""
import unittest
from goad import purple_vmware_network as purple


def config(dhcp="no", nat="no", subnet="172.28.233.0"):
    return (
        f"answer VNET_4_HOSTONLY_SUBNET {subnet}\n"
        "answer VNET_4_HOSTONLY_NETMASK 255.255.255.0\n"
        f"answer VNET_4_DHCP {dhcp}\n"
        f"answer VNET_4_NAT {nat}\n"
        "answer VNET_4_VIRTUAL_ADAPTER yes\n"
    )


class PurpleNetworkTests(unittest.TestCase):
    def test_valid_unmodified_existing_vmnet4(self):
        purple.validate_config(config())

    def test_no_vmnet4_fails(self):
        with self.assertRaises(purple.PurpleNetworkError):
            purple.validate_config("answer VNET_10_NAT no\n")

    def test_wrong_subnet_fails(self):
        with self.assertRaises(purple.PurpleNetworkError):
            purple.validate_config(config(subnet="10.4.10.0"))

    def test_nat_enabled_fails(self):
        with self.assertRaises(purple.PurpleNetworkError):
            purple.validate_config(config(nat="yes"))

    def test_dhcp_enabled_fails(self):
        with self.assertRaises(purple.PurpleNetworkError):
            purple.validate_config(config(dhcp="yes"))

    def test_duplicate_settings_fail(self):
        with self.assertRaises(purple.PurpleNetworkError):
            purple.validate_config(config() + "answer VNET_4_NAT no\n")

    def test_registered_vmnet_collision(self):
        registry='vmlist0.config = "/lab/guest.vmx"\n'
        vmx='/lab/guest.vmx'
        with self.assertRaises(purple.PurpleNetworkError):
            purple.validate_vmx(
                registry, {vmx: 'ethernet1.vnet = "vmnet4"\n'}
            )

    def test_registered_mac_collision(self):
        registry='vmlist0.config = "/lab/guest.vmx"\n'
        vmx='/lab/guest.vmx'
        with self.assertRaises(purple.PurpleNetworkError):
            purple.validate_vmx(
                registry, {vmx: 'ethernet1.address = "00:50:56:10:04:30"\n'}
            )

    def test_unreadable_registered_vm_fails(self):
        with self.assertRaises(purple.PurpleNetworkError):
            purple.validate_vmx('vmlist0.config = "/missing.vmx"\n', {})

    def test_no_host_mutation_code(self):
        import pathlib
        path = pathlib.Path(__file__).resolve().parents[1] / "goad/purple_vmware_network.py"
        source = path.read_text()
        self.assertNotIn("vmware-networks", source)
        self.assertNotIn("course1_host_network_apply", source)
        self.assertNotIn("authorized_strip", source)
        self.assertNotIn("kingdoms-course1-owner.json", source)


if __name__ == "__main__":
    unittest.main()
