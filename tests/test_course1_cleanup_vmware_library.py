"""Identity-based VMware inventory maintenance tests."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/course1-cleanup-vmware-library.py"
spec = importlib.util.spec_from_file_location("vmware_library", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
MACHINES = ("GOAD-DC01", "GOAD-DC02", "GOAD-DC03",
            "GOAD-SRV02", "GOAD-SRV03", "GOAD-WS01", "GOAD-ROUTER")


def fixture(home):
    parent = home / "Documents/GOAD_NOMAD/workspace/6fdd5a-goad-vmware/provider/.vagrant/machines"
    lines = ['vmlist1.config = ""', 'vmlist1.displayName = "keep"']
    for index, machine in enumerate(MACHINES, 4):
        vmx = parent / machine / "vmware_desktop" / "21391744-6229-4d18-a657-ba072ef62567" / "WindowsServer2019.vmx"
        lines.extend([f'vmlist{index}.config = "{vmx}"',
                      f'vmlist{index}.displayName = "{machine}"'])
    vmx = home / "vmware/KINGDOMS-SQL-CLONE/KINGDOMS-SQL-CLONE.vmx"
    lines.append(f'vmlist11.config = "{vmx}"')
    lines.append('vmlist12.config = "/unrelated/retain.vmx"')
    return "\n".join(lines) + "\n"


class InventoryTests(unittest.TestCase):
    def test_exact_eight_slots(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            slots = audit.target_slots(fixture(home), home)
            self.assertEqual(slots, frozenset(range(4, 12)))
            clean = audit.strip_slots(fixture(home), slots)
            self.assertIn('vmlist1.displayName = "keep"', clean)
            self.assertIn('vmlist12.config = "/unrelated/retain.vmx"', clean)
            self.assertNotIn('vmlist11.config', clean)

    def test_existing_guest_file_refuses_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            text = fixture(home)
            registered = next(line.split('"')[1] for line in text.splitlines()
                              if line.startswith("vmlist4.config"))
            guest = Path(registered)
            guest.parent.mkdir(parents=True)
            guest.write_text("version=1")
            with self.assertRaisesRegex(ValueError, "VMX still exists"):
                audit.target_slots(text, home)

    def test_missing_clone_registration_refuses_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            text = fixture(home)
            text = "\n".join(
                line for line in text.splitlines()
                if not line.startswith("vmlist11.config")
            ) + "\n"
            with self.assertRaisesRegex(ValueError, "Registration set differs"):
                audit.target_slots(text, home)

    def test_unknown_slot_refuses_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            changed = fixture(home).replace("vmlist4.config", "vmlist14.config")
            with self.assertRaisesRegex(ValueError, "Registration set differs"):
                audit.target_slots(changed, home)


if __name__ == "__main__":
    unittest.main()
