"""Mock-only WSLPE native Stage-1 deployment regression.

No tests execute Vagrant/VMware or write outside TemporaryDirectory.
"""
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from goad.utils import CREATED, PROVIDED
from kingdoms import wslpe_stage1 as boot


class WslpeNativeBootTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.state = {"lab": "WSLPE", "provider": "vmware", "instance": None,
                      "prefix": "192.168.56", "allow_create": True}
        self.events = []
        self.settings = SimpleNamespace(provisioner_name="local", extensions_name=[])
        self.provider = SimpleNamespace(
            lab_name="WSLPE", path=str(self.workspace / "new-wslpe" / "provider"),
            install=self.fake_provider_install,
        )
        self.manager = SimpleNamespace(
            current_settings=self.settings,
            get_current_lab_name=lambda: self.state["lab"],
            get_current_provider_name=lambda: self.state["provider"],
            get_current_instance=lambda: self.state["instance"],
            get_current_instance_provider=lambda: self.provider,
            set_ip_range=self.fake_set_ip,
            get_ip_range=lambda: self.state["prefix"],
            create_instance=self.fake_create_instance,
        )

    def fake_set_ip(self, prefix):
        self.events.append(("set_ip", prefix))
        self.state["prefix"] = prefix

    def fake_provider_install(self):
        self.events.append(("provider_install",))
        return True

    def fake_create_instance(self):
        self.events.append(("create_instance",))
        if not self.state["allow_create"]:
            return False
        target = self.workspace / "new-wslpe"
        provider = target / "provider"
        provider.mkdir(parents=True)
        (provider / "Vagrantfile").write_text(
            'boxes = [{ :name => "WSLPE-WS01" }]', encoding="utf-8"
        )
        instance = SimpleNamespace(
            lab_name="WSLPE", provider_name="vmware",
            provisioner_name="local", ip_range=self.state["prefix"],
            status=CREATED, instance_path=str(target),
            instance_provider_path=str(provider),
        )
        instance.get_status = lambda: instance.status
        def set_status(status):
            self.events.append(("set_status", status))
            instance.status = status
        instance.set_status = set_status
        self.state["instance"] = instance
        return True

    def patches(self):
        stack = ExitStack()
        stack.enter_context(patch.object(boot.GoadPath, "get_project_path",
                                         return_value=str(self.root)))
        stack.enter_context(patch.object(boot.GoadPath, "get_workspace_path",
                                         return_value=str(self.workspace)))
        stack.enter_context(patch.object(boot, "preboot_acceptance",
                                         return_value=True))
        stack.enter_context(patch.object(boot, "inspect_vmware_guest",
                                         return_value=True))
        return stack

    def run_boot(self, prefix="172.28.231", confirmed=True):
        with self.patches():
            return boot.bootstrap_native_wslpe(self.manager, prefix,
                                               confirmed=confirmed)

    def test_native_single_guest_through_existing_instance_and_provider(self):
        self.assertTrue(self.run_boot())
        self.assertEqual(self.events, [
            ("set_ip", "172.28.231"), ("create_instance",),
            ("provider_install",), ("set_status", PROVIDED),
        ])
        self.assertEqual(self.state["instance"].status, PROVIDED)

    def test_unconfirmed_install_never_mutates_workspace(self):
        self.assertFalse(self.run_boot(confirmed=False))
        self.assertEqual(self.events, [])
        self.assertFalse(self.workspace.exists())

    def test_north_public_and_malformed_prefixes_are_rejected(self):
        for prefix in ("10.4.10", "8.8.8", "127.0.0", "172.28.231.0"):
            with self.subTest(prefix=prefix):
                self.assertFalse(self.run_boot(prefix))
        self.assertFalse(self.workspace.exists())

    def test_loaded_instance_cannot_trigger_boot(self):
        self.state["instance"] = object()
        self.assertFalse(self.run_boot())
        self.assertEqual(self.events, [])

    def test_wrong_lab_provider_method_or_extensions_are_rejected(self):
        self.state["lab"] = "GOAD"
        self.assertFalse(self.run_boot())
        self.state["lab"] = "WSLPE"
        self.state["provider"] = "virtualbox"
        self.assertFalse(self.run_boot())
        self.state["provider"] = "vmware"
        self.settings.provisioner_name = "runner"
        self.assertFalse(self.run_boot())
        self.settings.provisioner_name = "local"
        self.settings.extensions_name = ["fixture"]
        self.assertFalse(self.run_boot())
        self.assertEqual(self.events, [])

    def test_symlinked_workspace_is_forbidden(self):
        other = self.root / "foreign"
        other.mkdir()
        self.workspace.symlink_to(other, target_is_directory=True)
        self.assertFalse(self.run_boot())
        self.assertEqual(self.events, [])

    def test_failed_preflight_does_not_create_instance(self):
        with self.patches(), patch.object(boot, "preboot_acceptance",
                                          return_value=False):
            self.assertFalse(boot.bootstrap_native_wslpe(
                self.manager, "172.28.231", confirmed=True
            ))
        self.assertEqual(self.events, [])

    def test_failed_provider_not_retried_and_never_marked_provided(self):
        def failure():
            self.events.append(("provider_failure",))
            return False
        self.provider.install = failure
        self.assertFalse(self.run_boot())
        self.assertEqual(self.events.count(("provider_failure",)), 1)
        self.assertEqual(self.state["instance"].status, CREATED)

    def test_unverified_guest_does_not_mark_instance_provided(self):
        with self.patches(), patch.object(boot, "inspect_vmware_guest",
                                          return_value=False):
            self.assertFalse(boot.bootstrap_native_wslpe(
                self.manager, "172.28.231", confirmed=True
            ))
        self.assertEqual(self.state["instance"].status, CREATED)
        self.assertNotIn(("set_status", PROVIDED), self.events)


if __name__ == "__main__":
    unittest.main()
