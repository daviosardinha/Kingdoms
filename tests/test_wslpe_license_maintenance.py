"""Mock-only native WSLPE licensing tests: no Ansible or Windows mutations."""
from contextlib import ExitStack
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from kingdoms import wslpe_license_maintenance as license_fix


class NativeWslpeLicenseAutomationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "kingdoms"
        self.instance_dir = self.root / "workspace/bf5369-wslpe-vmware"
        self.provider_dir = self.instance_dir / "provider"
        self.provider_dir.mkdir(parents=True)
        self.home = Path(temp.name) / "home"
        binaries = self.home / ".goad/.venv/bin"
        binaries.mkdir(parents=True)
        for name in ("ansible-playbook", "ansible-inventory"):
            path = binaries / name
            path.write_text("#!/bin/sh\n", encoding="utf-8")
            path.chmod(0o700)
        (self.root / "ansible").mkdir()
        (self.root / "ansible/wslpe-foundation.yml").write_text(
            "existing foundation\n", encoding="utf-8",
        )
        (self.instance_dir / "inventory").write_text(
            "ws01 ansible_host=172.28.232.31\n", encoding="utf-8",
        )
        (self.root / "ad/WSLPE/data").mkdir(parents=True)
        (self.root / "ad/WSLPE/data/inventory").write_text(
            "original WSLPE bootstrap inventory\n", encoding="utf-8",
        )
        self.instance = SimpleNamespace(
            instance_id="bf5369-wslpe-vmware",
            lab_name="WSLPE", provider_name="vmware", provisioner_name="local",
            extensions=[], ip_range="172.28.232", status="ready for provisioning",
            instance_path=str(self.instance_dir),
            instance_provider_path=str(self.provider_dir),
        )
        self.instance.get_status = lambda: self.instance.status
        self.provider = SimpleNamespace(
            lab_name="WSLPE", path=str(self.provider_dir),
            _winrm_forwarded_port=Mock(return_value=2200),
            _winrm_session=Mock(return_value=SimpleNamespace(
                run_ps=Mock(return_value=SimpleNamespace(
                    status_code=0, std_out=b"WSLPE_LICENSE_READY=PASS\r\n"
                ))
            )),
        )
        self.manager = SimpleNamespace(
            get_current_instance=lambda: self.instance,
            get_current_instance_provider=lambda: self.provider,
            get_current_lab_name=lambda: "WSLPE",
        )

    def patches(self):
        stack = ExitStack()
        stack.enter_context(patch.object(
            license_fix, "_exact_instance",
            return_value=(self.instance, self.provider, self.root, self.instance_dir),
        ))
        stack.enter_context(patch.object(
            license_fix, "inspect_vmware_guest", return_value=True,
        ))
        stack.enter_context(patch.object(
            license_fix, "_guest_proof", return_value=True,
        ))
        stack.enter_context(patch.object(
            license_fix, "_approved_inventory",
            return_value=(
                self.instance_dir / "inventory",
                self.root / "ad/WSLPE/data/inventory",
            ),
        ))
        stack.enter_context(patch.object(license_fix.Path, "home", return_value=self.home))
        run = stack.enter_context(patch.object(
            license_fix.subprocess, "run",
            return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
        ))
        return stack, run

    def test_existing_role_only_runs_against_exact_registered_wslpe_forward(self):
        stack, run = self.patches()
        with stack:
            self.assertTrue(license_fix.maintain_native_wslpe_license(
                self.manager, confirmed=True,
            ))
        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertEqual(command[0], str(self.home / ".goad/.venv/bin/ansible-playbook"))
        self.assertEqual(command[command.index("--limit") + 1], "ws01")
        self.assertEqual(command[command.index("--tags") + 1], "wslpe_license")
        self.assertEqual(
            command[command.index("-e") + 1],
            json.dumps({
                "ansible_host": "127.0.0.1",
                "ansible_port": 2200,
                "ansible_connection": "winrm",
                "ansible_winrm_scheme": "http",
                "ansible_winrm_transport": "ntlm",
            }, separators=(",", ":")),
        )
        self.assertIn(str(self.root / "ansible/wslpe-foundation.yml"), command)
        self.assertNotIn("vagrant", " ".join(command))
        self.assertNotIn("lpe.trainee", " ".join(command))
        self.assertEqual(run.call_args.kwargs["timeout"], license_fix.TIMEOUT_SECONDS)
        self.assertIsNotNone(run.call_args.kwargs["stdin"])
        self.provider._winrm_session.return_value.run_ps.assert_called_once_with(
            license_fix.READ_ONLY_LICENSE_PROOF,
        )

    def test_approval_missing_does_not_run_any_role_or_windows_probe(self):
        stack, run = self.patches()
        with stack:
            self.assertFalse(license_fix.maintain_native_wslpe_license(
                self.manager, confirmed=False,
            ))
        run.assert_not_called()
        self.provider._winrm_session.assert_not_called()

    def test_bad_native_identity_or_drift_blocks_before_mutation(self):
        stack, run = self.patches()
        with stack, patch.object(
            license_fix, "_exact_instance", side_effect=ValueError("wrong lab")
        ):
            self.assertFalse(license_fix.maintain_native_wslpe_license(
                self.manager, confirmed=True,
            ))
        run.assert_not_called()

    def test_guest_mac_or_management_preflight_blocks_role(self):
        stack, run = self.patches()
        with stack, patch.object(license_fix, "_guest_proof", return_value=False):
            self.assertFalse(license_fix.maintain_native_wslpe_license(
                self.manager, confirmed=True,
            ))
        run.assert_not_called()

    def test_failed_role_is_not_retried_or_accepted(self):
        stack, run = self.patches()
        with stack:
            run.return_value.returncode = 2
            self.assertFalse(license_fix.maintain_native_wslpe_license(
                self.manager, confirmed=True,
            ))
        run.assert_called_once()
        self.provider._winrm_session.assert_not_called()

    def test_successful_role_without_real_post_reboot_license_proof_blocks(self):
        stack, run = self.patches()
        self.provider._winrm_session.return_value.run_ps.return_value = SimpleNamespace(
            status_code=1, std_out=b"",
        )
        with stack:
            self.assertFalse(license_fix.maintain_native_wslpe_license(
                self.manager, confirmed=True,
            ))
        run.assert_called_once()

    def test_does_not_power_on_create_disable_license_service_or_install_learner(self):
        source = Path(license_fix.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "vmrun start", "vagrant up", "vagrant destroy", "Disable-Service WLMS",
            "Stop-Service WLMS", "SkipRearm", "New-LocalUser", "win_user",
            "ansible/wslpe-lpe-test.yml",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("/rearm", license_fix.READ_ONLY_LICENSE_PROOF)

    def test_inventory_rejects_domain_or_wrong_ip(self):
        binary = self.home / ".goad/.venv/bin/ansible-inventory"
        expected = dict(
            _meta=dict(hostvars=dict(ws01=dict(
                ansible_host="172.28.232.31", domain_name="WSLPE",
                ansible_connection="winrm", ansible_port=5985,
                ansible_winrm_scheme="http", ansible_winrm_transport="ntlm",
                ansible_user="vagrant", ansible_password="vagrant",
            ))),
            wslpe=dict(hosts=["ws01"]),
            windows_lpe_standalone=dict(hosts=["ws01"]),
        )
        with patch.object(license_fix.Path, "home", return_value=self.home), \
             patch.object(license_fix.subprocess, "run") as run:
            run.return_value = SimpleNamespace(
                returncode=0, stdout=json.dumps(expected),
            )
            self.assertEqual(
                license_fix._approved_inventory(
                    self.root, self.instance_dir, "172.28.232.31",
                )[0],
                self.instance_dir / "inventory",
            )
            self.assertEqual(run.call_args.args[0][0], str(binary))
            expected["dc"] = {"hosts": ["dc01"]}
            run.return_value.stdout = json.dumps(expected)
            with self.assertRaises(ValueError):
                license_fix._approved_inventory(
                    self.root, self.instance_dir, "172.28.232.31",
                )
            expected.pop("dc")
            expected["_meta"]["hostvars"]["ws01"]["ansible_host"] = "10.4.10.31"
            run.return_value.stdout = json.dumps(expected)
            with self.assertRaises(ValueError):
                license_fix._approved_inventory(
                    self.root, self.instance_dir, "172.28.232.31",
                )

    def test_only_exact_existing_status_and_lab_are_allowed(self):
        with patch.object(
            license_fix.GoadPath, "get_project_path", return_value=str(self.root),
        ), patch.object(
            license_fix.GoadPath, "get_workspace_path",
            return_value=str(self.root / "workspace"),
        ), patch.object(
            license_fix, "_registered_guest_vmx",
            return_value=self.provider_dir / "native.vmx",
        ):
            for value in ("GOAD", "NORTH", "WSLPE"):
                self.instance.lab_name = value
                if value != "WSLPE":
                    with self.assertRaises(ValueError):
                        license_fix._exact_instance(self.manager)
            self.instance.status = "ready"
            with self.assertRaises(ValueError):
                license_fix._exact_instance(self.manager)


if __name__ == "__main__":
    unittest.main()
