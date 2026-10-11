"""No-VM native instance preparation through the existing Kingdoms CLI."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "goad_nomad.py").read_text(encoding="utf-8")


def functions():
    tree = ast.parse(SOURCE)
    cls = next(node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == "GoadNomad")
    prepare = next(node for node in cls.body
                   if isinstance(node, ast.FunctionDef)
                   and node.name == "do_prepare_north")
    dispatch = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "_dispatch_task")
    ns = {"Log": Mock()}
    exec(compile(ast.Module(body=[prepare, dispatch], type_ignores=[]),
                 "goad_nomad.py", "exec"), ns)
    return ns


class Course1PrepareOnlyTests(unittest.TestCase):
    def setUp(self):
        self.actions = functions()
        self.instance = SimpleNamespace(
            lab_name="NORTH", provider_name="vmware",
            instance_provider_path="/fake/workspace/north/provider",
        )
        self.manager = Mock()
        self.manager.get_current_lab_name.return_value = "NORTH"
        self.manager.get_current_provider_name.return_value = "vmware"
        self.manager.get_current_instance.side_effect = [None, self.instance]
        self.manager.create_instance.return_value = True
        self.console = SimpleNamespace(lab_manager=self.manager)
        self.args = SimpleNamespace(task="prepare-north", instance=None,
                                    run_playbook=None, ansible_only=None)

    def test_prepares_native_north_only(self):
        self.assertTrue(self.actions["do_prepare_north"](self.console))
        self.manager.create_instance.assert_called_once_with()
        self.assertEqual(self.manager.get_current_instance.call_count, 2)

    def test_cli_dispatch_prepares_only_no_install(self):
        self.console.do_prepare_north = Mock(return_value=True)
        self.console.do_install = Mock()
        self.assertEqual(self.actions["_dispatch_task"](self.console, self.args), 0)
        self.console.do_prepare_north.assert_called_once_with()
        self.console.do_install.assert_not_called()

    def test_other_lab_and_provider_blocked(self):
        for attr, bad in (("get_current_lab_name", "GOAD"),
                          ("get_current_provider_name", "virtualbox")):
            with self.subTest(attr=attr):
                self.manager.reset_mock(return_value=False, side_effect=False)
                self.manager.get_current_lab_name.return_value = "NORTH"
                self.manager.get_current_provider_name.return_value = "vmware"
                getattr(self.manager, attr).return_value = bad
                self.assertFalse(self.actions["do_prepare_north"](self.console))
                self.manager.create_instance.assert_not_called()

    def test_existing_selected_instance_is_blocked(self):
        self.manager.get_current_instance.side_effect = None
        self.manager.get_current_instance.return_value = self.instance
        self.assertFalse(self.actions["do_prepare_north"](self.console))
        self.manager.create_instance.assert_not_called()

    def test_failed_instance_generation_is_not_claimed_successful(self):
        self.manager.create_instance.return_value = False
        self.assertFalse(self.actions["do_prepare_north"](self.console))

    def test_wrong_created_instance_identity_fails(self):
        self.instance.lab_name = "GOAD"
        self.assertFalse(self.actions["do_prepare_north"](self.console))

    def test_rejects_instance_id_on_prepare(self):
        self.args.instance = "existing-id"
        self.console.do_load = Mock()
        self.console.do_prepare_north = Mock()
        self.assertEqual(self.actions["_dispatch_task"](self.console, self.args), 1)
        self.console.do_load.assert_called_once_with("existing-id")
        self.console.do_prepare_north.assert_not_called()

    def test_dispatch_and_prepare_do_not_reach_vm_or_network_operations(self):
        tree = ast.parse(SOURCE)
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                   and node.name == "GoadNomad")
        prep = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                    and node.name == "do_prepare_north")
        code = ast.get_source_segment(SOURCE, prep)
        for unexpected in ("provider.install", "do_install_instance", "do_provide",
                           "subprocess.run", "systemctl", "prepare_install",
                           "set_runtime_mode"):
            self.assertNotIn(unexpected, code)


if __name__ == "__main__":
    unittest.main()
