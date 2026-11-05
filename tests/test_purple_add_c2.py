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
        self.assertIn(':hostname => "c2"', updated)
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

    def test_c2_has_no_software_installation_scripts(self):
        entry = c2.c2_definition(SOURCE.read_text())
        self.assertIn('"bento/debian-12"', entry)
        self.assertIn('configure-linux-interface.sh', entry)
        self.assertNotIn(':provision_scripts', entry)
        self.assertNotIn('wazuh-install', entry.lower())
        self.assertNotIn('sliver', entry.lower())


if __name__ == '__main__':
    unittest.main()
