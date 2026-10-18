"""Offline readiness checks for four *unqualified* native prototypes.

No guest calls, no installer invocation, and no source-to-candidate promotion.
"""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "ansible/files/wslpe45"


class FinalFourSourceBatchTests(unittest.TestCase):
    def test_candidate_index_still_fail_closed(self):
        doc = yaml.safe_load(
            (ROOT / "kingdoms/wslpe45_implementation_index.yml").read_text()
        )
        self.assertFalse(doc["batch_execution_authorized"])
        for number in (25, 36, 38, 40):
            with self.subTest(number=number):
                row = next(t for t in doc["techniques"] if t["number"] == number)
                self.assertEqual(row["status"], "planned")
                self.assertEqual(row["source_ci"], "pending")
                self.assertEqual(row["learner_proof"], "pending")
                self.assertEqual(row["six_stage_qualification"], "pending")
                self.assertFalse((ROOT / row["playbook"]).exists())

    def test_accepted_prototypes_are_native_and_bounded(self):
        accepted = (
            ("Kingdom25Repair.cpp", ("MsiGetPropertyW", "CustomActionData")),
            ("Kingdom36WmiProvider.cs", ("WmiConfiguration", "ManagementTask")),
            ("Kingdom40LocalRpc.idl", ("interface Kingdom40LocalRpc", "handle_t")),
        )
        for filename, expected in accepted:
            with self.subTest(filename=filename):
                body = (SRC / filename).read_text(encoding="utf-8")
                for token in expected:
                    self.assertIn(token, body)
                self.assertNotIn("GOAD-WS01", body)
        self.assertFalse((SRC / "Kingdom38DcomServer.cpp").exists())

    def test_msi_repair_package_is_per_machine_and_repair_only(self):
        src = (SRC / "Kingdom25RepairPackage.wxs").read_text(encoding="utf-8")
        root = ET.fromstring(src)
        namespace = {"w": "http://wixtoolset.org/schemas/v4/wxs"}
        pkg = root.find("w:Package", namespace)
        self.assertIsNotNone(pkg)
        self.assertEqual(pkg.attrib["Scope"], "perMachine")
        self.assertEqual(pkg.attrib["UpgradeStrategy"], "none")
        actions = {e.attrib["Id"]: e for e in pkg.findall("w:CustomAction", namespace)}
        repair = actions["Kingdom25RepairCA"].attrib
        self.assertEqual(repair["DllEntry"], "Kingdom25Repair")
        self.assertEqual(repair["Execute"], "deferred")
        self.assertEqual(repair["Impersonate"], "no")
        self.assertEqual(repair["Return"], "check")
        self.assertEqual(repair["HideTarget"], "yes")
        self.assertEqual(actions["ScheduleKingdom25Repair"].attrib["Property"],
                         "Kingdom25RepairCA")
        self.assertEqual(actions["ScheduleKingdom25Repair"].attrib["Value"],
                         "WSLPE25-REPAIR")
        seq = pkg.find("w:InstallExecuteSequence", namespace)
        events = {e.attrib["Action"]: e for e in seq.findall("w:Custom", namespace)}
        self.assertEqual(set(events), {"ScheduleKingdom25Repair",
                                        "Kingdom25RepairCA"})
        for event in events.values():
            self.assertIn("REINSTALL", event.attrib["Condition"])
            self.assertIn("NOT REMOVE", event.attrib["Condition"])
        self.assertEqual(events["Kingdom25RepairCA"].attrib["After"], "InstallFiles")
        self.assertNotIn("AlwaysInstallElevated", src)
        self.assertNotIn("GOAD-WS01", src)
        self.assertTrue((SRC / "Kingdom25Payload.txt").is_file())

    def test_msi_native_repair_marker_refuses_existing_objects(self):
        # Static source guard only. Native CI must still compile the DLL.
        # Parent ACL/reparse ownership and live repair proof remain pending.
        source = (SRC / "Kingdom25Repair.cpp").read_text(encoding="utf-8")
        self.assertIn("MsiGetPropertyW", source)
        self.assertIn("CREATE_NEW", source)
        self.assertNotIn("CREATE_ALWAYS", source)

    def test_msi_inspection_is_owned_read_only_and_fail_closed(self):
        # Offline contract only: Windows PowerShell parsing and live ACLs
        # require separate native/lab checks.
        src = (SRC / "Wslpe25RepairInspection.psm1").read_text(encoding="utf-8")
        for token in (
            "Assert-Wslpe45Identity",
            "Assert-Wslpe45OwnedFixture -Number 25",
            "Assert-Wslpe45NoReparsePoints",
            "Get-LocalGroupMember",
            "GetAccessRules",
            "AreAccessRulesProtected",
            "BeforeRepair",
            "AfterRepair",
            "Get-ChildItem",
            "WSLPE25_FIXTURE_INSPECT",
        ):
            self.assertIn(token, src)
        for forbidden in (
            "New-Wslpe45OwnedFixture",
            "Remove-Wslpe45OwnedFixture",
            "Set-Acl",
            "New-Item",
            "Remove-Item",
            "msiexec",
            "Start-Process",
        ):
            self.assertNotIn(forbidden, src)

    def test_msi_fixture_preparation_reuses_owned_standalone_contract(self):
        # Static contract: no guest/module execution in Python tests.
        src = (SRC / "Wslpe25RepairPreparation.psm1").read_text(encoding="utf-8")
        for token in (
            "Invoke-Wslpe25FixturePreparation",
            "Assert-Wslpe45Identity",
            "New-Wslpe45OwnedFixture -Number 25 -Id $id",
            "Assert-Wslpe45NoReparsePoints",
            "Assert-Wslpe25ProtectedParent",
            "AreAccessRulesProtected",
            "GetAccessRules",
            "Get-ChildItem",
            "WindowsBuiltInRole]::Administrator",
            "Assert-Wslpe25RepairFixture -Stage BeforeRepair",
            "WSLPE25_FIXTURE_PREPARED=PASS",
        ):
            self.assertIn(token, src)
        for forbidden in (
            "msiexec",
            "Start-Process",
            "Remove-Wslpe45OwnedFixture",
            "Remove-Item",
            "Set-Acl",
            "Register-PSSessionConfiguration",
            "GOAD-WS01",
        ):
            self.assertNotIn(forbidden, src)
        self.assertIn("ValidateSet('Inspect','Prepare')", src)
        self.assertNotIn("ValidateSet('Inspect','Prepare','Reset')", src)

    def test_msi_native_build_records_product_identity_before_any_runtime(self):
        # The Windows runner reads MSI database metadata without invoking it.
        workflow = (ROOT / ".github/workflows/wslpe-45-batch-source.yml").read_text(
            encoding="utf-8"
        )
        for required in (
            "Read-Wslpe25MsiProperty 'ProductCode'",
            "Read-Wslpe25MsiProperty 'ProductName'",
            "Read-Wslpe25MsiProperty 'Manufacturer'",
            "Read-Wslpe25MsiProperty 'ProductVersion'",
            "Read-Wslpe25MsiProperty 'ALLUSERS'",
            "$null = $propertyView.Execute()",
            "$null = $propertyView.Close()",
            "Get-FileHash -Algorithm SHA256",
            "WSLPE25_PRODUCT_CODE=",
            "WSLPE25_MSI_SHA256=",
            "state=unqualified-not-deployable",
            "installation_executed=false",
        ):
            self.assertIn(required, workflow)

    def test_gate_document_preserves_native_mechanisms(self):
        text = (ROOT / "docs/WSLPE45_FINAL_FOUR_SOURCE_BATCH.md").read_text()
        for string in ("#25", "#36", "#38", "#40", "NOT DEPLOYABLE",
                       "21/25", "ncalrpc", "MSI", "DCOM", "WMI"):
            self.assertIn(string, text)


if __name__ == "__main__":
    unittest.main()
