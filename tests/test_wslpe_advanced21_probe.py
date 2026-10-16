"""Read-only standalone #21 CLI probe negative paths; never contact Windows."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import importlib.util
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/wslpe-advanced21-probe.py"
SPEC = importlib.util.spec_from_file_location("wslpe_advanced21_probe_test", SOURCE)
assert SPEC is not None and SPEC.loader is not None
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class WslpeAdvanced21ProbeTests(unittest.TestCase):
    def make_base(self, directory, seen):
        def check_inventory(data, expected):
            seen.append(("check_inventory", expected))
            if data.get("_meta", {}).get("hostvars", {}).get("ws01", {}).get("ansible_host") != expected:
                raise ValueError("Wrong WinRM target")
        def make_report(location):
            return directory
        def log_private(root, label, data):
            path = directory / f"wslpe-{label}.log"
            path.write_text(data, encoding="utf-8")
            path.chmod(0o600)
            return path
        return SimpleNamespace(
            exact_standalone=lambda: (
                directory / "inventory", directory / "vars", "172.28.231.31"),
            resolved_inventory_command=lambda exe, inv, vars: [
                str(exe), "-i", str(inv), "-i", str(vars), "--list"],
            check_inventory=check_inventory,
            private_report_dir=make_report,
            private_failure_log=log_private,
        )

    def test_default_plan_never_invokes_winrm_or_ansible(self):
        with TemporaryDirectory() as tmp:
            seen = []
            base = self.make_base(Path(tmp), seen)
            with patch.object(PROBE, "baseline", return_value=base), \
                 patch.object(PROBE.subprocess, "run") as invoke:
                args = PROBE.build_parser().parse_args([])
                self.assertFalse(args.execute)
                self.assertEqual(PROBE.run(args), 0)
                invoke.assert_not_called()
                self.assertEqual(seen, [])

    def test_exact_guest_and_complete_windows_markers_required(self):
        markers = (
            "WSLPE_ADV21_GUEST=EXACT",
            "WSLPE_ADV21_LOCAL_LEARNER=NONADMIN",
            "WSLPE_ADV21_TASK_COM_DACL_READ=PASS",
            "WSLPE_ADV21_PROBE_READ_ONLY=TRUE",
        )
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            tools = directory / ".goad/.venv/bin"
            tools.mkdir(parents=True)
            for name in ("ansible-playbook", "ansible-inventory"):
                (tools / name).touch()
            base = self.make_base(directory, [])
            args = PROBE.build_parser().parse_args(["--execute"])
            inventory = SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({
                "_meta": {"hostvars": {"ws01": {"ansible_host": "172.28.231.31"}}}}))
            healthy = SimpleNamespace(returncode=0, stderr="", stdout="\n".join(markers))
            incomplete = SimpleNamespace(returncode=0, stderr="", stdout="\n".join(markers[:-1]))
            denied = SimpleNamespace(returncode=2, stderr="denied", stdout="")
            with patch.object(PROBE.Path, "home", return_value=directory), \
                 patch.object(PROBE, "baseline", return_value=base), \
                 patch.object(PROBE.subprocess, "run",
                              side_effect=[inventory, healthy]) as call:
                self.assertEqual(PROBE.run(args), 0)
                guest_cmd = call.call_args_list[1].args[0]
                self.assertEqual(guest_cmd[guest_cmd.index("--limit")+1], "ws01,localhost")
                self.assertEqual(guest_cmd[-1], str(PROBE.PROBE))
                self.assertNotIn("GOAD-WS01", " ".join(guest_cmd))
            with patch.object(PROBE.Path, "home", return_value=directory), \
                 patch.object(PROBE, "baseline", return_value=base), \
                 patch.object(PROBE.subprocess, "run", side_effect=[inventory, incomplete]):
                self.assertEqual(PROBE.run(args), 2)
                self.assertTrue((directory / "wslpe-adv21-probe-marker.log").is_file())
            with patch.object(PROBE.Path, "home", return_value=directory), \
                 patch.object(PROBE, "baseline", return_value=base), \
                 patch.object(PROBE.subprocess, "run", side_effect=[inventory, denied]):
                self.assertEqual(PROBE.run(args), 2)
                self.assertTrue((directory / "wslpe-adv21-probe.log").is_file())

    def test_wrong_inventory_is_rejected_before_guest_call(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            tools = directory / ".goad/.venv/bin"
            tools.mkdir(parents=True)
            for name in ("ansible-playbook", "ansible-inventory"):
                (tools / name).touch()
            base = self.make_base(directory, [])
            mismatched = SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({
                "_meta": {"hostvars": {"ws01": {"ansible_host": "10.4.10.31"}}}}))
            with patch.object(PROBE.Path, "home", return_value=directory), \
                 patch.object(PROBE, "baseline", return_value=base), \
                 patch.object(PROBE.subprocess, "run", return_value=mismatched) as call:
                with self.assertRaisesRegex(ValueError, "Wrong WinRM target"):
                    PROBE.run(PROBE.build_parser().parse_args(["--execute"]))
                self.assertEqual(call.call_count, 1)

    def test_source_has_no_guest_mutation_and_no_shared_role_catalog_changes(self):
        script = SOURCE.read_text(encoding="utf-8")
        self.assertIn("base.exact_standalone()", script)
        self.assertIn("base.check_inventory(", script)
        self.assertIn('str(PROBE)', script)
        self.assertIn('if any(marker not in diagnostic', script)
        self.assertNotIn("subprocess.Popen", script)
        self.assertNotIn("vmrun", script)
        self.assertNotIn("vagrant destroy", script)


if __name__ == "__main__":
    unittest.main()
