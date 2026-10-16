"""WSLPE-only learner profile preparation and prior failed AIE apply recovery.

All tests run on Linux without Windows, domain controllers, VMware or Ansible
guest access. Live Windows CreateProfile acceptance remains a separate step.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import os
import unittest

import yaml
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "ansible/wslpe-always-install-elevated-preflight.yml"
SHARED = ROOT / "ansible/roles/windows_lpe/tasks/techniques/always_install_elevated.yml"
SPEC = importlib.util.spec_from_file_location(
    "wslpe_aie_runner_test", ROOT / "scripts/wslpe-fast-track-20.py")
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class WslpeAieProfilePreflightTests(unittest.TestCase):
    def setUp(self):
        self.plays = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))
        self.assertEqual(len(self.plays), 2)
        self.ps = self.plays[1]["tasks"][0]["ansible.windows.win_powershell"]["script"]

    def test_only_standalone_guest_and_its_local_account(self):
        self.assertEqual(self.plays[0]["hosts"], "localhost")
        self.assertEqual(self.plays[1]["hosts"], "wslpe")
        asserts = self.plays[0]["tasks"][0]["ansible.builtin.assert"]["that"]
        together = "\n".join(asserts)
        self.assertIn("['ws01']", together)
        self.assertIn("windows_lpe_standalone", together)
        self.assertIn("groups.get('dc'", together)
        self.assertIn("groups.get('domain'", together)
        self.assertIn("WSLPE-WS01", self.ps)
        self.assertIn("PartOfDomain", self.ps)
        self.assertIn("Get-LocalUser -Name 'lpe.trainee'", self.ps)
        self.assertIn("S-1-5-32-544", self.ps)
        self.assertIn("must not be a local administrator", self.ps)

    def test_microsoft_profile_api_instead_of_winrm_start_process(self):
        self.assertIn('EntryPoint = "CreateProfileW"', self.ps)
        self.assertIn('DllImport("userenv.dll"', self.ps)
        self.assertIn("Add-Type -TypeDefinition $definition", self.ps)
        self.assertIn("[WslpeProfileNative]::CreateProfile(", self.ps)
        self.assertIn("Test-Path -LiteralPath $profileKey", self.ps)
        self.assertIn("'NTUSER.DAT'", self.ps)
        self.assertNotIn("Start-Process -FilePath", self.ps)
        self.assertNotIn("ConvertTo-SecureString", self.ps)

    def test_partial_cleanup_is_empty_only_with_scope_and_no_reparse_points(self):
        # The shared role creates its candidate folder before attempting
        # the failing profile Start-Process operation.
        shared = SHARED.read_text(encoding="utf-8")
        self.assertLess(shared.index("New-Item -ItemType Directory -Path $root"),
                        shared.index("Start-Process -FilePath"))
        self.assertIn("Join-Path $root 'state.json'", self.ps)
        self.assertIn("Get-ChildItem -LiteralPath $root -Force", self.ps)
        self.assertIn("ReparsePoint", self.ps)
        self.assertIn("Unexpected candidate fixture", self.ps)
        self.assertIn("contains unexpected data; refusing cleanup", self.ps)
        self.assertIn("HKLM AlwaysInstallElevated already enabled", self.ps)
        self.assertIn("Remove-Item -LiteralPath $root -Force", self.ps)
        self.assertNotIn("Remove-Item -LiteralPath $root -Recurse", self.ps)
        self.assertNotIn("NORTH\\", self.ps)

    def test_runner_prepares_before_resume_clean_check_and_initial_apply(self):
        source = (ROOT / "scripts/wslpe-fast-track-20.py").read_text()
        self.assertIn('if failed_technique == "always_install_elevated":', source)
        self.assertIn('if technique == "always_install_elevated" and not prepared_aie:', source)
        block = source.index('    prepared_aie = False')
        prepare = source.index('            if not prepare_standalone_aie(', block)
        clean = source.index('        clean_cmd = invocation(', block)
        self.assertLess(prepare, clean)
        resume_loop = source.index('    for technique in catalog[resume_index:]:')
        self.assertLess(resume_loop, source.index('        for action, state in FLOW:', resume_loop))
        self.assertIn("--limit", source)
        self.assertIn('"ws01,localhost"', source)
        self.assertNotIn('"vagrant destroy"', source)

    def test_preparation_invokes_exact_playbook_and_stops_on_failure(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / "reports"
            folder.mkdir(mode=0o700)
            args = dict(
                ansible=Path("/fake/venv/ansible-playbook"),
                inventory=Path("/fake/WSLPE/instance/inventory"),
                varsfile=Path("/fake/WSLPE/inventory_disable_vagrant"),
                env={"ANSIBLE_ROLES_PATH": "/fake/WSLPE/roles"},
                report_root=folder, timeout=300,
            )
            success = SimpleNamespace(returncode=0, stdout="ok\n", stderr="")
            with patch.object(RUNNER.subprocess, "run", return_value=success) as run:
                self.assertTrue(RUNNER.prepare_standalone_aie(**args))
                commands = run.call_args.args[0]
                self.assertEqual(commands[commands.index("--limit")+1], "ws01,localhost")
                self.assertEqual(commands[-1], str(PLAYBOOK))
                self.assertNotIn("NORTH", " ".join(commands))
            failure = SimpleNamespace(returncode=2, stdout="", stderr="access denied")
            with patch.object(RUNNER.subprocess, "run", return_value=failure):
                self.assertFalse(RUNNER.prepare_standalone_aie(**args))
                reports = list(folder.glob("wslpe-aie-profile-preflight-*.log"))
                self.assertEqual(len(reports), 1)
                self.assertEqual(reports[0].stat().st_mode & 0o777, 0o600)

if __name__ == "__main__":
    unittest.main()
