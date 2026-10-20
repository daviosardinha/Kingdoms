"""Public KINGDOMS alias regression tests - no VMware or installed VMs required."""
import argparse
import ast
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch

from goad.lab_names import canonical_lab_name, public_lab_name

ROOT = Path(__file__).resolve().parents[1]


def source_function(relative_path, function_name, parent_class=None):
    """Load the real function from source without importing VMware/WinRM."""
    path = ROOT / relative_path
    nodes = ast.parse(path.read_text(encoding='utf-8')).body
    if parent_class:
        parent = next(n for n in nodes if isinstance(n, ast.ClassDef) and n.name == parent_class)
        nodes = parent.body
    node = next(n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == function_name)
    namespace = {
        'argparse': argparse,
        'canonical_lab_name': canonical_lab_name,
        'public_lab_name': public_lab_name,
        'VMWARE': 'vmware',
        'LUDUS': 'ludus',
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[function_name]


class KingdomsLabAliasTests(unittest.TestCase):
    def test_public_alias_resolves_to_original_internal_lab(self):
        self.assertEqual(canonical_lab_name('KINGDOMS'), 'GOAD')
        self.assertEqual(canonical_lab_name('GOAD'), 'GOAD')
        self.assertEqual(public_lab_name('GOAD'), 'KINGDOMS')
        self.assertEqual(public_lab_name('KINGDOMS'), 'KINGDOMS')

    def test_other_lab_names_remain_unchanged(self):
        for lab in ('NORTH', 'GOAD-Light', 'GOAD-Mini', 'MINILAB', 'WSLPE', '', None):
            with self.subTest(lab=lab):
                self.assertEqual(canonical_lab_name(lab), lab)
                self.assertEqual(public_lab_name(lab), lab)

    def test_noninteractive_install_normalizes_before_config(self):
        parse_args = source_function('goad_nomad.py', 'parse_args')
        for selection in ('KINGDOMS', 'GOAD'):
            with self.subTest(selection=selection), patch.object(
                sys, 'argv', ['goad_nomad.py', '-t', 'install', '-l', selection, '-p', 'vmware']
            ):
                args = parse_args()
                self.assertEqual(args.lab, 'GOAD')
                self.assertEqual(args.task, 'install')
                self.assertEqual(args.provider, 'vmware')

    def test_default_and_other_cli_labs(self):
        parse_args = source_function('goad_nomad.py', 'parse_args')
        with patch.object(sys, 'argv', ['goad_nomad.py', '-t', 'check']):
            self.assertEqual(parse_args().lab, 'GOAD')
        with patch.object(sys, 'argv', ['goad_nomad.py', '-t', 'check', '-l', 'NORTH']):
            self.assertEqual(parse_args().lab, 'NORTH')

    def test_interactive_set_lab_keeps_internal_identity(self):
        set_lab_name = source_function('goad/settings.py', 'set_lab_name', 'Settings')
        manager = SimpleNamespace(is_lab_exist=lambda lab: lab == 'GOAD')
        settings = SimpleNamespace(lab_manager=manager, lab_name=None)
        self.assertEqual(set_lab_name(settings, 'KINGDOMS', refresh=False), 'GOAD')
        self.assertEqual(settings.lab_name, 'GOAD')
        self.assertEqual(set_lab_name(settings, 'GOAD', refresh=False), 'GOAD')

    def test_existing_instance_label_is_display_only(self):
        inline = source_function('goad/settings.py', 'inline', 'Settings')
        settings = SimpleNamespace(
            lab_name='GOAD', provider_name='vmware', provisioner_name='local',
            ip_range='10.4.0', is_goad_nomad_segmented=lambda: True,
        )
        self.assertEqual(
            inline(settings), 'KINGDOMS/vmware/local/10.4.0.0-16-segmented'
        )
        self.assertEqual(settings.lab_name, 'GOAD')

    def test_interactive_completion_offers_alias_and_legacy(self):
        complete = source_function('goad_nomad.py', 'complete_set_lab', 'GoadNomad')
        console = SimpleNamespace(
            lab_manager=SimpleNamespace(
                get_labs_options=lambda: ['GOAD', 'GOAD-Light', 'NORTH']
            )
        )
        choices = complete(console, '', '', 0, 0)
        self.assertIn('KINGDOMS', choices)
        self.assertIn('GOAD', choices)
        self.assertIn('GOAD-Light', choices)
        self.assertIn('NORTH', choices)
        self.assertEqual(complete(console, 'KING', '', 0, 0), ['KINGDOMS'])

    def test_provider_still_uses_original_machine_identity(self):
        path = ROOT / 'goad/provider/vagrant/vmware_nomad.py'
        source = path.read_text(encoding='utf-8')
        self.assertIn("return self.lab_name == 'GOAD'", source)
        self.assertIn("'GOAD-ROUTER'", source)
        self.assertIn("'GOAD-WS01': '10.4.10.31'", source)


if __name__ == '__main__':
    unittest.main()
