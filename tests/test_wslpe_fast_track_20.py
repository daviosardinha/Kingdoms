"""WSLPE 20-tech fast-track must stay exact-instance and refuse NORTH imports."""
from pathlib import Path
import importlib.util
import json
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/wslpe-fast-track-20.py"
SPEC = importlib.util.spec_from_file_location("wslpe_fast_track_20", SOURCE)
assert SPEC and SPEC.loader
FAST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FAST)


class WslpeFastTrackTests(unittest.TestCase):
    def test_catalog_is_entire_reused_north_implemented_set(self):
        actual = FAST.load_catalog()
        self.assertEqual(len(actual), 20)
        self.assertEqual(len(set(actual)), 20)
        self.assertIn("stored_runas_credentials", actual)
        self.assertIn("seimpersonate_privilege", actual)

    def test_exact_existing_reversible_technique_cycle(self):
        self.assertEqual(FAST.FLOW, (
            ("apply", None), ("validate", "vulnerable"),
            ("reset", None), ("validate", "clean"),
            ("apply", None), ("validate", "vulnerable"),
        ))

    def test_only_ws01_standalone_inventory_is_accepted(self):
        inventory = {
            "wslpe": {"hosts": ["ws01"]},
            "windows_lpe_standalone": {"hosts": ["ws01"]},
            "_meta": {"hostvars": {"ws01": {
                "ansible_host": "172.28.231.31",
                "ansible_connection": "winrm",
                "ansible_user": "vagrant",
                "domain_name": "WSLPE",
            }}},
        }
        FAST.check_inventory(inventory, "172.28.231.31")
        for name in ("wslpe", "windows_lpe_standalone"):
            changed = json.loads(json.dumps(inventory))
            changed[name]["hosts"].append("GOAD-WS01")
            with self.assertRaises(ValueError):
                FAST.check_inventory(changed, "172.28.231.31")
        for bad in ("10.4.10.31", "172.28.231.32"):
            with self.assertRaises(ValueError):
                FAST.check_inventory(inventory, bad)
        changed = json.loads(json.dumps(inventory))
        changed["dc"] = {"hosts": ["GOAD-DC01"]}
        with self.assertRaises(ValueError):
            FAST.check_inventory(changed, "172.28.231.31")

    def test_invocation_never_selects_north_and_has_correct_validation_state(self):
        binpath = Path("/opt/venv/bin/ansible-playbook")
        inv = Path("/tmp/WSLPE/inventory")
        varsfile = Path("/tmp/WSLPE/inventory_disable_vagrant")
        arg = FAST.invocation(binpath, inv, varsfile,
                              "unquoted_service_path", "validate", "clean")
        self.assertEqual(arg[arg.index("--limit")+1], "ws01")
        self.assertEqual(arg[arg.index("-e")+1], '{"wslpe_action":"validate","wslpe_techniques":["unquoted_service_path"],"windows_lpe_validate_state":"clean"}')
        self.assertIn("wslpe-lpe-test.yml", " ".join(arg))
        self.assertNotIn("ws01-lpe-install.yml", " ".join(arg))
        with self.assertRaises(ValueError):
            FAST.invocation(binpath, inv, varsfile, "nonexisting", "apply", None)
        with self.assertRaises(ValueError):
            FAST.invocation(binpath, inv, varsfile, "unquoted_service_path", "apply", "clean")

    def test_default_mode_does_not_invoke_ansible_or_modify_vm(self):
        from types import SimpleNamespace
        with patch.object(FAST, "exact_standalone", return_value=(
                Path("/tmp/ws/inventory"), Path("/tmp/ws/vars"), "172.28.231.31"
                )), patch.object(FAST.subprocess, "run") as call:
            args = SimpleNamespace(execute=False)
            self.assertEqual(FAST.run(args), 0)
            call.assert_not_called()

    def test_source_contains_only_existing_wslpe_harness_and_no_north_lifecycle(self):
        s = SOURCE.read_text(encoding="utf-8")
        self.assertIn('ansible/wslpe-lpe-test.yml', s)
        self.assertIn('meta.get("lab") != "WSLPE"', s)
        self.assertIn('confirmation != "QUALIFY WSLPE 20"', s)
        for unsafe in ("lab-mode.sh", "GOAD-WS01.vmx", "vmrun stop",
                       "nft flush", "vagrant up", "ansible/ws01-lpe-install.yml"):
            self.assertNotIn(unsafe, s)


if __name__ == "__main__":
    unittest.main()
