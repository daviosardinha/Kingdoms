"""Read-only teardown inventory contracts; no actual host interaction."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/course1-cleanup-audit.py"
spec = importlib.util.spec_from_file_location("course1_cleanup_audit", SOURCE)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class CleanupAuditTests(unittest.TestCase):
    def test_inventory_never_executes_destructive_host_commands(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("vagrant', 'destroy", text)
        self.assertNotIn('vagrant", "destroy', text)
        self.assertNotIn('vmware-networks", "--stop"', text)
        self.assertNotIn("shutil.rmtree", text)
        self.assertNotIn("os.unlink(", text)
        self.assertNotIn("os.remove(", text)
        self.assertNotIn("git push", text)
        self.assertNotIn("rm -rf", text)
        self.assertNotIn("systemctl disable", text)
        self.assertNotIn("systemctl stop", text)
        self.assertNotIn('delete_ref', text)

    def test_VMware_VMX_identity_proven_from_vagrant_marker(self):
        with tempfile.TemporaryDirectory() as home:
            checkout = Path(home) / "kingdoms"
            provider = checkout / "workspace/6ca91b-north-vmware/provider"
            ids = provider / ".vagrant/machines/GOAD-WS01/vmware_desktop"
            ids.mkdir(parents=True)
            vmx = Path(home) / "vm-disks/GOAD-WS01.vmx"
            vmx.parent.mkdir()
            vmx.write_text('config.version = "8"\n')
            (ids / "id").write_text(str(vmx))
            metadata = provider.parent / "instance.json"
            metadata.write_text(json.dumps({"lab": "NORTH", "provider": "vmware"}))
            found = audit.instance_candidates(checkout)
            self.assertEqual(len(found), 1)
            self.assertTrue(found[0]["candidate_for_cleanup"])
            self.assertEqual(found[0]["vagrant_identities"][0]["machine"], "GOAD-WS01")
            self.assertEqual(found[0]["vagrant_identities"][0]["vmx"], str(vmx))
            self.assertTrue(found[0]["vagrant_identities"][0]["vmx_exists"])

    def test_foreign_instance_not_auto_selected(self):
        with tempfile.TemporaryDirectory() as home:
            checkout = Path(home)
            instance = checkout / "workspace/unrelated"
            instance.mkdir(parents=True)
            (instance / "instance.json").write_text(
                json.dumps({"lab": "PRIVATE", "provider": "vmware"})
            )
            found = audit.instance_candidates(checkout)
            self.assertEqual(len(found), 1)
            self.assertFalse(found[0]["candidate_for_cleanup"])

    def test_symlink_workspace_is_not_followed(self):
        with tempfile.TemporaryDirectory() as home:
            root = Path(home)
            (root / "source").mkdir()
            (root / "checkout").mkdir()
            (root / "checkout" / "workspace").symlink_to(root / "source")
            self.assertEqual(audit.instance_candidates(root / "checkout"), [])

    def test_vmware_network_keys_scope_exact_owned_net_ids(self):
        with tempfile.TemporaryDirectory() as home:
            cfg = Path(home) / "networking"
            cfg.write_text(
                "answer VNET_10_HOSTONLY_SUBNET 10.4.10.0\n"
                "answer VNET_11_HOSTONLY_SUBNET 10.41.10.0\n"
                "answer VNET_8_HOSTONLY_SUBNET 192.168.213.0\n"
                "answer VNET_99_DHCP no\n"
            )
            original = Path
            # The network parser targets the system config. Redirect that
            # ONE lookup to an isolated file, no real /etc reads.
            def fake_path(value):
                return cfg if value == "/etc/vmware/networking" else original(value)
            with patch.object(audit, "Path", side_effect=fake_path):
                report = audit.vmware_network_config()
            self.assertIn("vmnet10", report["target_network_settings"])
            self.assertIn("vmnet11", report["target_network_settings"])
            self.assertIn("vmnet99", report["target_network_settings"])
            self.assertNotIn("vmnet8", report["target_network_settings"])

    def test_vmware_powered_off_registry_is_read_only(self):
        with tempfile.TemporaryDirectory() as home:
            root = Path(home)
            (root / ".vmware").mkdir()
            vmx = root / "machines" / "GOAD-DC01.vmx"
            registry = root / ".vmware/inventory.vmls"
            registry.write_text(
                'vmlist0.config = "' + str(vmx) + '"\n'
                'vmlist1.config = "/other/unrelated.vmx"\n'
            )
            with patch.object(audit.Path, "home", return_value=root):
                found = audit.vmware_user_registry()
            self.assertEqual(found["registered_vmx_paths"],
                             [str(vmx), "/other/unrelated.vmx"])
            self.assertTrue(found["exists"])

    def test_process_audit_never_exposes_args(self):
        fake = {"exit_code": 0, "stdout": "1234 vmware-vmx\n5678 python\n",
                "stderr": ""}
        with patch.object(audit, "run", return_value=fake) as invoke:
            found = audit.process_candidates()
        invoke.assert_called_once_with("ps", "-eo", "pid=,comm=", timeout=10)
        self.assertEqual(found["processes"],
                         [{"pid": "1234", "comm": "vmware-vmx"}])

    def test_crontab_audit_reports_lines_not_secrets(self):
        fake = {"exit_code": 0, "stdout": (
            '*/5 * * * * kingdoms-watch --password=SECRET_VALUE\n'
            '0 * * * * unrelated task\n'
        ), "stderr": ""}
        with patch.object(audit, "run", return_value=fake):
            found = audit.cron_candidates()
        self.assertEqual(found["matching_line_numbers"], [
            {"line_number": 1, "marker": "kingdoms/goad"}
        ])
        self.assertNotIn("SECRET_VALUE", json.dumps(found))


if __name__ == "__main__":
    unittest.main()
