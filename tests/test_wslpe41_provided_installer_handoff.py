"""Source-only provided-instance WSLPE41 live handoff contract.

No Windows guest, VMware, or credential access from tests. The real --provided-plan
performs one live read-only operator verification on the operator's Kali host.
"""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "wslpe41_existing_install_cli", ROOT / "scripts/wslpe41-install.py")
assert SPEC and SPEC.loader
INSTALL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALL)

from kingdoms import wslpe41_operator_management as management


class ProvidedInstallerHandoffTests(unittest.TestCase):
    def test_live_plan_reuses_exact_operator_and_canonical_83_steps(self):
        target = SimpleNamespace(
            instance=Path("/home/fake/kingdoms-wslpe41-fresh/workspace/bf5369-wslpe-vmware"))
        with (patch.object(management, "exact_target", return_value=target),
              patch.object(management, "run", side_effect=lambda **kw:
                           kw["report"]("[PASS] WSLPE_OPERATOR_MANAGEMENT=PASS test")),
              patch.object(INSTALL.Path, "home", return_value=Path("/home/fake")),
              patch("builtins.print") as printed):
            code = INSTALL.main(["--provided-plan"])
        self.assertEqual(code, 0)
        output = "\n".join(str(c.args[0]) for c in printed.call_args_list if c.args)
        self.assertIn("WSLPE41_PROVIDED_STAGE_MAP=41 scenarios / 83 stages", output)
        self.assertIn("172.28.233.31:5986", output)
        self.assertIn("172.28.232.31", output)
        self.assertIn("[NOT EXECUTED]", output)
        self.assertIn("--execute is still blocked", output)

    def test_operator_verify_missing_blocks_plan_without_scenario_execution(self):
        target = SimpleNamespace(
            instance=Path("/home/fake/kingdoms-wslpe41-fresh/workspace/bf5369-wslpe-vmware"))
        with (patch.object(management, "exact_target", return_value=target),
              patch.object(management, "run", side_effect=lambda **kw: None),
              patch("builtins.print") as printed):
            result = INSTALL.main(["--provided-plan"])
        self.assertEqual(result, 2)
        output = "\n".join(str(c.args[0]) for c in printed.call_args_list if c.args)
        self.assertIn("[BLOCKED]", output)
        self.assertIn("[NO CHANGES]", output)

    def test_default_execute_still_blocks_and_does_not_verify_or_mutate(self):
        with patch.object(management, "run") as auth:
            self.assertEqual(INSTALL.main(["--execute"]), 2)
        auth.assert_not_called()

    def test_canonical_provided_plan_cannot_include_old_or_north_vmx(self):
        bad = SimpleNamespace(
            instance=Path("/home/fake/kingdoms-wslpe41-fresh/workspace/d986ad-wslpe-vmware"))
        with (patch.object(management, "exact_target", return_value=bad),
              patch.object(management, "run") as auth,
              patch("builtins.print")):
            self.assertEqual(INSTALL.main(["--provided-plan"]), 2)
        auth.assert_not_called()


if __name__ == "__main__":
    unittest.main()
