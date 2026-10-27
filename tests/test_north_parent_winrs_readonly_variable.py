"""Regression: PowerShell's read-only automatic $ShellId must never be assigned.

Actual NORTH evidence: VariableNotWritable item=ShellId after WinRS shell
create succeeded, before resource locator was built. Exercise isolation must
not be blamed for this isolated validator programming defect.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "ansible/files/north-parent-winrs.ps1"
EVIDENCE = ROOT / "ansible/north-parent-transport-evidence-readonly.yml"


class NorthParentWinrsReadOnlyVariableRegression(unittest.TestCase):
    def test_production_shell_guid_variable_does_not_shadow_shellid(self):
        source = PRODUCTION.read_text(encoding="utf-8")
        self.assertFalse(
            re.search(r"(?im)^\s*\$shellid\s*=", source),
            "The built-in $ShellId is read-only; use a distinct GUID variable")
        self.assertIn("$parentWinrsShellGuid = $created.SelectSingleNode", source)
        self.assertIn("$locator.AddSelector('ShellId', $parentWinrsShellGuid)", source)
        self.assertIn("[string]::IsNullOrWhiteSpace($parentWinrsShellGuid)", source)
        self.assertIn("SessionFlagUseNegotiate()", source)
        self.assertIn("https://kingslanding.sevenkingdoms.local:5986/wsman", source)
        self.assertIn("if ($locator) { $null = $session.Delete($locator, 0) }", source)

    def test_readonly_diagnostic_keeps_distinct_guid_variable(self):
        source = EVIDENCE.read_text(encoding="utf-8")
        self.assertFalse(
            re.search(r"(?im)^\s*\$shellid\s*=", source),
            "Diagnostic must not repeat production's read-only variable bug")
        self.assertIn("$parentEvidenceShellGuid = $created.SelectSingleNode", source)
        self.assertIn("if (-not $parentEvidenceShellGuid)", source)
        self.assertIn("$locator.AddSelector('ShellId', $parentEvidenceShellGuid)", source)
        self.assertIn("Write-Output 'NORTH_PARENT_WINRS_CREATE=PASS'", source)
        self.assertIn("$Ansible.Changed = $false", source)
        self.assertIn("changed_when: false", source)


if __name__ == "__main__":
    unittest.main()
