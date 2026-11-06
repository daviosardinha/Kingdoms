"""Regression checks for add-only PURPLE-C2 VMware pilot extension."""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ad/PURPLE/providers/vmware/Vagrantfile"
HELPER = ROOT / "scripts/purple-add-c2.py"
spec = importlib.util.spec_from_file_location("purple_add_c2", HELPER)
c2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2)


def existing_pilot_fixture():
    source = SOURCE.read_text(encoding="utf-8")
    entry = c2.c2_definition(source).replace("172.28.233", "{{ip_range}}")
    assert source.count(",\n" + entry) == 1
    original = source.replace(",\n" + entry, "")
    return 'Vagrant.configure("2") do |config|\n' + (
        original.replace("{{ip_range}}", "172.28.233")
    ) + '\n  boxes.each do |box|\n  end\nend\n'


class PurpleC2ExtensionTests(unittest.TestCase):
    def test_only_the_fifth_machine_is_added_to_existing_generated_file(self):
        old = existing_pilot_fixture()
        updated, changed = c2.extend_vagrantfile(SOURCE.read_text(), old)
        self.assertTrue(changed)
        self.assertEqual(updated.count(':name => "PURPLE-C2"'), 1)
        for machine in c2.ORIGINALS:
            self.assertEqual(updated.count(f':name => "{machine}"'), 1)
        self.assertIn(':ip => "172.28.233.60"', updated)
        self.assertIn(':hostname => "PURPLE-C2"', updated)
        self.assertIn('00:50:56:10:04:60', updated)
        self.assertEqual(updated.replace(",\n" + c2.c2_definition(SOURCE.read_text()), ""), old)

    def test_idempotent_and_rejects_unexpected_existing_c2(self):
        old = existing_pilot_fixture()
        updated, _ = c2.extend_vagrantfile(SOURCE.read_text(), old)
        again, changed = c2.extend_vagrantfile(SOURCE.read_text(), updated)
        self.assertFalse(changed)
        self.assertEqual(again, updated)
        with self.assertRaises(c2.UnsafeExtension):
            c2.extend_vagrantfile(SOURCE.read_text(),
                                  old.replace('"PURPLE-WAZUH"', '"OTHER"'))
        with self.assertRaises(c2.UnsafeExtension):
            c2.extend_vagrantfile(SOURCE.read_text(),
                                  old.replace('172.28.233.51', '172.28.233.60'))

    def test_legacy_installed_c2_preserves_existing_guest_hostname(self):
        old = existing_pilot_fixture()
        current, _ = c2.extend_vagrantfile(SOURCE.read_text(), old)
        legacy = current.replace(':hostname => "PURPLE-C2"', ':hostname => "c2"')
        unchanged, changed = c2.extend_vagrantfile(SOURCE.read_text(), legacy)
        self.assertFalse(changed)
        self.assertEqual(unchanged, legacy)
        self.assertEqual(unchanged.count(':name => "PURPLE-C2"'), 1)
        # Refuse unexpected names rather than silently changing installed VMs.
        with self.assertRaises(c2.UnsafeExtension):
            c2.extend_vagrantfile(SOURCE.read_text(),
                                  legacy.replace(':hostname => "c2"',
                                                 ':hostname => "OTHER-C2"'))

    def test_vmware_inventory_folder_entry_is_not_treated_as_vm(self):
        inventory = (
            'vmlist1.config = "folder6"\n'
            'vmlist2.config = "/tmp/PURPLE-DC01.vmx"\n'
            'vmlist3.config = "folder17"\n'
            'vmlist4.config = "/tmp/other.vmx"\n'
        )
        self.assertEqual(
            c2.vm_config_paths(inventory),
            ["/tmp/PURPLE-DC01.vmx", "/tmp/other.vmx"],
        )
        # Arbitrary missing/relative VMX records must still be inspected
        # and rejected by verify_existing_vmware rather than silently skipped.
        self.assertEqual(
            c2.vm_config_paths('vmlist5.config = "unexpected-vm"\n'),
            ["unexpected-vm"],
        )

    def test_c2_has_no_software_installation_scripts(self):
        entry = c2.c2_definition(SOURCE.read_text())
        self.assertIn('"bento/debian-12"', entry)
        self.assertIn('configure-linux-interface.sh', entry)
        self.assertNotIn(':provision_scripts', entry)
        self.assertNotIn('wazuh-install', entry.lower())
        self.assertNotIn('sliver', entry.lower())


if __name__ == '__main__':
    unittest.main()
