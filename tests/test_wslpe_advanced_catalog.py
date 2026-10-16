"""Advanced-only WSLPE 21–35 planning contract; source tests cannot prove live attacks."""
from pathlib import Path
import re
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "kingdoms/wslpe_advanced_catalog.yml"
PROBE = ROOT / "ansible/wslpe-advanced21-probe.yml"
SHARED = ROOT / "ansible/roles/windows_lpe/defaults/main.yml"
EXPECTED = (
    "scheduled_task_definition_acl",
    "scm_create_service_acl",
    "privileged_service_config_injection",
    "privileged_updater_hijack",
    "msi_repair_custom_action",
    "ifeo_debugger_acl_hijack",
    "com_clsid_registration_hijack",
    "app_paths_registry_hijack",
    "named_pipe_authorization",
    "jea_role_capability_misconfig",
    "setakeownership_privilege",
    "serestore_privilege",
    "sedebug_privilege",
    "ntfs_link_redirection",
    "privileged_path_traversal_write",
)

def validate_planning_catalog(data: object, existing: set[str]) -> None:
    if not isinstance(data, dict):
        raise ValueError("Advanced catalog must be a YAML mapping")
    for key, value in (
        ("schema", "kingdoms.wslpe.advanced.v1"),
        ("scope", "standalone-wslpe-only"),
        ("platform", "windows-10-workgroup"),
        ("foundation_count", 20),
        ("advanced_count", 15),
        ("target_total", 45),
        ("status", "planned"),
        ("shared_north_role_frozen", True),
    ):
        if data.get(key) != value or type(data.get(key)) is not type(value):
            raise ValueError(f"Unexpected advanced catalog scope: {key}")
    if data.get("learner") != r"WSLPE-WS01\lpe.trainee":
        raise ValueError("Standalone must use the exact local learner")
    techniques = data.get("techniques")
    if not isinstance(techniques, list) or len(techniques) != 15:
        raise ValueError("Expected 15 advanced candidate entries")
    if [entry.get("number") for entry in techniques] != list(range(21, 36)):
        raise ValueError("Advanced numbering must remain exactly 21–35")
    ids = [entry.get("id") for entry in techniques]
    if ids != list(EXPECTED) or len(set(ids)) != 15:
        raise ValueError("Unknown or repeated advanced candidate")
    if set(ids) & existing:
        raise ValueError("Advanced technique collides with NORTH's original twenty")
    for entry in techniques:
        if entry.get("status") != "planned":
            raise ValueError("Unvalidated candidate must not be marked implemented")
        for field in ("name", "category", "mechanic", "prerequisite", "fixture", "feasibility_gate"):
            minimum = 3 if field == "category" else 12
            if not isinstance(entry.get(field), str) or len(entry[field]) < minimum:
                raise ValueError(f"Missing specific advanced {field}")
        overlap = entry.get("distinct_from")
        if not isinstance(overlap, list) or not overlap:
            raise ValueError("Advanced candidates need explicit overlap comparisons")
        if any(not isinstance(v, str) for v in overlap):
            raise ValueError("Invalid overlap comparison entry")


class WslpeAdvancedCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
        cls.north = yaml.safe_load(SHARED.read_text(encoding="utf-8"))
        cls.plays = yaml.safe_load(PROBE.read_text(encoding="utf-8"))

    def test_frozen_north_twenty_and_planned_standalone_fifteen(self):
        original = self.north["windows_lpe_catalog"]
        self.assertEqual(len(original), 20)
        self.assertEqual(len(set(original)), 20)
        self.assertEqual(self.north["windows_lpe_candidate_techniques"], [])
        self.assertEqual(self.north["windows_lpe_implemented_techniques"], original)
        validate_planning_catalog(self.data, set(original))

    def test_catalog_cannot_accidentally_promote_or_repeat_candidates(self):
        from copy import deepcopy
        original = set(self.north["windows_lpe_catalog"])
        for key, value in (
            ("target_total", 35),
            ("shared_north_role_frozen", False),
            ("scope", "north"),
            ("status", "implemented"),
            ("advanced_count", 14),
        ):
            corrupt = deepcopy(self.data)
            corrupt[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_planning_catalog(corrupt, original)
        for damaged in ("duplicate", "promoted", "overlap"):
            corrupt = deepcopy(self.data)
            if damaged == "duplicate":
                corrupt["techniques"][14]["id"] = corrupt["techniques"][0]["id"]
            if damaged == "promoted":
                corrupt["techniques"][0]["status"] = "implemented"
            if damaged == "overlap":
                corrupt["techniques"][0]["id"] = next(iter(original))
            with self.subTest(damaged=damaged), self.assertRaises(ValueError):
                validate_planning_catalog(corrupt, original)

    def test_21_probe_is_domain_free_exact_identity_and_read_only(self):
        self.assertEqual(len(self.plays), 2)
        local, guest = self.plays
        self.assertEqual(local["hosts"], "localhost")
        self.assertEqual(guest["hosts"], "wslpe")
        guard = "\n".join(local["tasks"][0]["ansible.builtin.assert"]["that"])
        self.assertIn("['ws01']", guard)
        self.assertIn("windows_lpe_standalone", guard)
        self.assertIn("groups.get('dc'", guard)
        self.assertIn("groups.get('domain'", guard)
        task = guest["tasks"][0]
        self.assertEqual(task["changed_when"], False)
        script = task["ansible.windows.win_powershell"]["script"]
        for expected in (
            "WSLPE-WS01", "Windows 10", "PartOfDomain",
            "Get-LocalUser -Name 'lpe.trainee'",
            "KingdomTaskBinary", "GetSecurityDescriptor(4)",
            "RawSecurityDescriptor", "WSLPE_ADV21_PROBE_READ_ONLY=TRUE",
        ):
            self.assertIn(expected, script)
        commands = "\n".join(
            line for line in script.splitlines() if not line.lstrip().startswith("#")
        )
        for mutator in (
            "SetSecurityDescriptor(", "RegisterTaskDefinition(",
            "Set-ScheduledTask ", "Register-ScheduledTask ",
            "Unregister-ScheduledTask ", "Set-Acl ", "Remove-Item ",
        ):
            self.assertNotIn(mutator, commands)

    def test_source_probe_does_not_wire_advanced_into_north_or_20_runner(self):
        shared_tasks = (ROOT / "ansible/roles/windows_lpe/tasks/main.yml").read_text()
        runner = (ROOT / "scripts/wslpe-fast-track-20.py").read_text()
        self.assertNotIn("wslpe_advanced", shared_tasks)
        self.assertNotIn("scheduled_task_definition_acl", shared_tasks)
        self.assertNotIn("wslpe-advanced21-probe", runner)
        self.assertNotIn("scheduled_task_definition_acl", runner)


if __name__ == "__main__":
    unittest.main()
