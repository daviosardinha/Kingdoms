"""Read-only VMware exercise subnet acceptance; no guest or network commands."""
from pathlib import Path
import tempfile
import unittest

from kingdoms.wslpe41_install_flow import FreshGuestIdentity, InstallBlocked
from kingdoms.wslpe41_native_vmnet import verify_native_vmnet

VMX = """
ethernet0.present = "TRUE"
ethernet0.connectionType = "nat"
ethernet0.startConnected = "TRUE"
ethernet1.present = "TRUE"
ethernet1.connectionType = "custom"
ethernet1.vnet = "vmnet3"
ethernet1.startConnected = "TRUE"
"""

NETWORKING = """answer VNET_3_HOSTONLY_SUBNET 172.28.232.0
answer VNET_3_HOSTONLY_NETMASK 255.255.255.0
answer VNET_10_HOSTONLY_SUBNET 10.4.10.0
answer VNET_10_HOSTONLY_NETMASK 255.255.255.0
"""


class NativeVmnetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vmx = self.root / "guest.vmx"
        self.vmx.write_text(VMX, encoding="utf-8")
        self.networking = self.root / "networking"
        self.networking.write_text(NETWORKING, encoding="utf-8")
        self.identity = FreshGuestIdentity(
            instance_id="fresh-wslpe", workspace=str(self.root),
            vmx=str(self.vmx), subnet="172.28.232.0/24",
            source_commit="a" * 40,
        )

    def verify(self):
        return verify_native_vmnet(
            self.identity, vmware_networking=self.networking,
        )

    def test_dedicated_vmnet_and_exact_guest_subnet_pass(self):
        self.assertEqual(self.verify(), "vmnet3")

    def test_guest_attached_to_north_vmnet_fails_closed(self):
        self.vmx.write_text(VMX.replace("vmnet3", "vmnet10"), encoding="utf-8")
        with self.assertRaises(InstallBlocked):
            self.verify()

    def test_duplicate_subnet_ownership_is_rejected(self):
        self.networking.write_text(
            NETWORKING +
            "answer VNET_4_HOSTONLY_SUBNET 172.28.232.0\n"
            "answer VNET_4_HOSTONLY_NETMASK 255.255.255.0\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(InstallBlocked, "ambiguous"):
            self.verify()

    def test_wrong_or_missing_vmnet_metadata_fails(self):
        for network_text in (
            NETWORKING.replace("172.28.232.0", "172.28.233.0"),
            NETWORKING.replace("answer VNET_3_HOSTONLY_NETMASK 255.255.255.0\n", ""),
        ):
            with self.subTest(network=network_text):
                self.networking.write_text(network_text, encoding="utf-8")
                with self.assertRaises(InstallBlocked):
                    self.verify()

    def test_extra_nic_rejected(self):
        self.vmx.write_text(
            VMX + 'ethernet2.present = "TRUE"\n', encoding="utf-8",
        )
        with self.assertRaisesRegex(InstallBlocked, "unexpected VMware adapters"):
            self.verify()

    def test_symlinked_metadata_rejected(self):
        real = self.networking
        linked = self.root / "networking-link"
        linked.symlink_to(real)
        with self.assertRaisesRegex(InstallBlocked, "metadata unavailable"):
            verify_native_vmnet(self.identity, vmware_networking=linked)


if __name__ == "__main__":
    unittest.main()
