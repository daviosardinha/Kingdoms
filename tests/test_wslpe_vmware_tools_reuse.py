"""Source-only tests. Never run VMware/Vagrant, guest MSI or PowerShell."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

from kingdoms.wslpe_vmware_tools import WSLPE_VMTOOLS_SETUP


# WSLPE source CI intentionally has no pywinrm package. Compile only this
# pure Python selector from the existing provider; never load/execute VMware.
SOURCE = Path(__file__).resolve().parents[1] / "goad/provider/vagrant/vmware.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))
PROVIDER = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == "VmwareProvider")
SELECTOR = next(n for n in PROVIDER.body if isinstance(n, ast.FunctionDef) and n.name == "_vmware_tools_setup_script")
SCOPE = {"WSLPE_VMTOOLS_SETUP": WSLPE_VMTOOLS_SETUP}
exec(compile(ast.fix_missing_locations(ast.Module(body=[SELECTOR], type_ignores=[])),
             str(SOURCE), "exec"), SCOPE)



class WslpeToolsReuseTests(unittest.TestCase):
    def test_wslpe_uses_existing_provider_install_reboot_flow_with_vgauth_guard(self):
        provider = SimpleNamespace()
        provider.lab_name = "WSLPE"
        script = SCOPE['_vmware_tools_setup_script'](provider)
        self.assertEqual(script, WSLPE_VMTOOLS_SETUP)
        for marker in (
            "WSLPE_VMTOOLS_WRONG_GUEST",
            "$computer.PartOfDomain",
            "$env:COMPUTERNAME",
            "$_.VolumeName -eq 'VMware Tools'",
            "Stop-Service -Name VGAuthService",
            "Get-Service -Name VGAuthService",
            "Start-Service -Name VGAuthService",
            "[TimeSpan]::FromSeconds(30)",
            "'/v\"/qn REBOOT=ReallySuppress\"'",
            "GOAD_VMTOOLS_INSTALL_EXIT",
            "WSLPE_VMTOOLS_INSTALL_FAILED",
            "finally {",
        ):
            self.assertIn(marker, script)
        self.assertNotIn("Uninstall-", script)
        self.assertNotIn("Remove-Item", script)
        self.assertNotIn("Set-Acl", script)
        self.assertNotIn("Get-VM", script)

    def test_goad_and_other_labs_retain_original_installer_source(self):
        for lab in ("GOAD", "NORTH", "KINGDOMS"):
            provider = SimpleNamespace()
            provider.lab_name = lab
            script = SCOPE['_vmware_tools_setup_script'](provider)
            self.assertIn("GOAD_VMTOOLS_INSTALL_EXIT", script)
            self.assertIn("Start-Process -FilePath $setup", script)
            self.assertNotIn("Stop-Service -Name VGAuthService", script)
            self.assertNotIn("WSLPE_VMTOOLS_WRONG_GUEST", script)

    def test_no_credential_or_vmware_network_operations_in_setup(self):
        script = WSLPE_VMTOOLS_SETUP
        for forbidden in (
            "vagrant/vagrant", "vmnet", "netsh", "New-NetIPAddress",
            "Disable-NetAdapter", "Set-NetIPInterface", "Set-NetFirewall",
            "invoke-expression", "Invoke-Expression", "irm ", "iex ",
        ):
            self.assertNotIn(forbidden, script)


if __name__ == "__main__":
    unittest.main()
