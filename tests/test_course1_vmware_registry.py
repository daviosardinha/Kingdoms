"""Offline-only VMware Workstation registered guest inventory contract tests."""
import json
import tempfile
import unittest
from pathlib import Path

from goad import course1_vmware_registry as library
from goad.course1_host_survey import running_guest_summary


class VMwareWorkstationRegistryTests(unittest.TestCase):
    def test_registry_parses_registered_and_indexed_vmx(self):
        data = '\n'.join([
            'vmlist3.config = "/home/test/VMs/offline.vmx"',
            'vmlist1.config = ""',
            'vmlist4.config = "/home/test/VMs/offline.vmx"',
            'index0.id = "/home/test/VMs/running.vmx"',
            'vmlist3.DisplayName = "SECRET-NAME-DO-NOT-PRINT"',
            'vmlist3.UUID = "SENSITIVE"',
        ])
        paths, invalid = library.parse_library_vmx_paths(data)
        self.assertEqual(
            [p.name for p in paths],
            ["offline.vmx", "running.vmx"],
        )
        self.assertEqual(invalid, 0)
        self.assertNotIn("SECRET", str(paths))

    def test_relative_vmx_registry_pointer_is_not_claimed(self):
        paths, invalid = library.parse_library_vmx_paths(
            'vmlist0.config = "../unsafe.vmx"\n'
            'vmlist2.config = "/tmp/not-a-vmx.txt"\n'
        )
        self.assertFalse(paths)
        self.assertEqual(invalid, 2)

    def test_absent_library_reports_unverified_not_empty_certainty(self):
        with tempfile.TemporaryDirectory() as d:
            info = library.inspect_workstation_library(
                running_guest_summary, frozenset(),
                Path(d) / "missing.vmls"
            )
            self.assertEqual(info["library_status"], "NOT_FOUND")
            self.assertFalse(info["complete"])
            self.assertEqual(info["registered_vm_count"], 0)

    def test_powered_off_registered_vm_network_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            vmx = root / "offline.vmx"
            vmx.write_text(
                'ethernet1.vnet = "vmnet11"\n'
                'ethernet1.address = "00:50:56:3a:10:11"\n'
                'guestinfo.password = "DO-NOT-LEAK"\n',
                encoding="utf-8"
            )
            index = root / "inventory.vmls"
            index.write_text(f'vmlist0.config = "{vmx}"\n', encoding="utf-8")
            report = library.inspect_workstation_library(
                running_guest_summary, frozenset(), index
            )
            self.assertEqual(report["library_status"], "INSPECTED")
            self.assertTrue(report["complete"])
            self.assertEqual(report["registered_vm_count"], 1)
            self.assertEqual(
                report["registered_vms"][0]["adapters"][0]["vnet"], "vmnet11"
            )
            self.assertNotIn(str(root), json.dumps(report))
            self.assertNotIn("DO-NOT-LEAK", json.dumps(report))

    def test_unavailable_registered_vmx_is_not_marked_complete(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            index = root / "inventory.vmls"
            index.write_text(
                f'vmlist0.config = "{root / "unavailable.vmx"}"\n',
                encoding="utf-8"
            )
            output = library.inspect_workstation_library(
                running_guest_summary, frozenset(), index
            )
            self.assertEqual(output["library_status"], "INCOMPLETE")
            self.assertFalse(output["complete"])
            self.assertFalse(output["registered_vms"][0]["readable"])

    def test_symlinked_registry_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            original = root / "real.vmls"
            original.write_text('vmlist0.config = ""')
            link = root / "inventory.vmls"
            link.symlink_to(original)
            output = library.inspect_workstation_library(
                running_guest_summary, frozenset(), link
            )
            self.assertEqual(output["library_status"], "UNREADABLE")
            self.assertFalse(output["complete"])

    def test_registry_reader_does_not_mutate_vmware(self):
        source = Path(library.__file__).read_text(encoding="utf-8")
        for token in ("subprocess", "os.system", "shutil", "Path.write_text",
                      "vmrun stop", "vagrant up"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
