"""Architectural boundary: WSLPE41 adapters must not become a second provider.

These are source guards, not proof of native provisioning. The existing
KINGDOMS native provider retains VM lifecycle, networking and guest creation.
"""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = (
    "kingdoms/wslpe41_foundation_executor.py",
    "kingdoms/wslpe41_stage_executor.py",
    "kingdoms/wslpe41_native_stage_runner.py",
    "kingdoms/wslpe41_runtime_proof.py",
)
FORBIDDEN_IMPORTS = (
    "vagrant", "vmware", "pyvmomi", "libvirt", "paramiko",
)
FORBIDDEN_COMMANDS = (
    "vmrun start", "vmrun stop", "vmrun clone",
    "vagrant up", "vagrant destroy", "vmware-netcfg",
    "vmware-networks --stop", "vmware-networks --start",
    "New-LocalUser", "New-NetIPAddress",
)


class FrameworkBoundaryTests(unittest.TestCase):
    def test_adapters_are_not_new_providers(self):
        for relative in ADAPTERS:
            with self.subTest(path=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                tree = ast.parse(source, filename=relative)
                imports = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imports.extend(alias.name for alias in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        imports.append(node.module)
                for name in imports:
                    self.assertFalse(
                        any(name == blocked or name.startswith(blocked + ".")
                            for blocked in FORBIDDEN_IMPORTS),
                        f"{relative} introduced a separate infrastructure provider: {name}",
                    )
                for command in FORBIDDEN_COMMANDS:
                    self.assertNotIn(command.casefold(), source.casefold(),
                                     f"{relative} introduced provider mutation: {command}")

    def test_existing_foundation_playbooks_remain_the_source(self):
        source = (ROOT / "kingdoms/wslpe41_foundation_executor.py").read_text()
        self.assertIn('ansible/wslpe-foundation.yml', source)
        self.assertIn('ansible/wslpe-operator-foundation.yml', source)

    def test_production_entrypoint_remains_locked_without_provider_proof(self):
        source = (ROOT / "scripts/wslpe41-install.py").read_text()
        self.assertIn('if args.execute:', source)
        self.assertIn('return 2', source)


if __name__ == "__main__":
    unittest.main()
