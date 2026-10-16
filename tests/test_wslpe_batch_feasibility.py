"""The 25 native probes are WSLPE-only, read-only and fail-closed."""
import base64
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from kingdoms import wslpe_batch_feasibility as probe
from kingdoms.wslpe_batch_catalog import catalog

ROOT = Path(__file__).resolve().parents[1]


class WslpeBatchFeasibilityTests(unittest.TestCase):
    @staticmethod
    def valid_payload():
        return {
            "schema": "kingdoms.wslpe.feasibility.v1",
            "hostname": "WSLPE-WS01",
            "domain_joined": False,
            "os": "Windows 10",
            "readonly": True,
            "results": [
                {"id": row["id"], "native_api": "native_api_available",
                 "fixture": "not_implemented", "learner_exploitation": "not_tested"}
                for row in catalog()[20:]
            ],
        }

    @staticmethod
    def marker(data):
        encoded = base64.b64encode(json.dumps(data).encode()).decode("ascii")
        return "ok: [ws01] => WSLPE_45_FEASIBILITY_B64=" + encoded

    def test_default_plan_never_contacts_ansible_or_vmware(self):
        with patch.object(probe, "base_module") as load, patch.object(
                probe.subprocess, "run") as call:
            args = probe.build_parser().parse_args([])
            self.assertFalse(args.execute)
            self.assertEqual(probe.run(args), 0)
            load.assert_not_called()
            call.assert_not_called()

    def test_complete_exact_guest_and_25_markers_required(self):
        expected = [row["id"] for row in catalog()[20:]]
        result = probe.interpret(self.marker(self.valid_payload()), expected)
        self.assertEqual(len(result["results"]), 25)
        for invalid in ("hostname", "domain_joined", "readonly", "results",
                        "native_api", "fixture", "learner_exploitation"):
            bad = deepcopy(self.valid_payload())
            if invalid == "hostname":
                bad["hostname"] = "GOAD-WS01"
            elif invalid == "domain_joined":
                bad["domain_joined"] = True
            elif invalid == "readonly":
                bad["readonly"] = False
            elif invalid == "results":
                bad["results"] = bad["results"][:-1]
            else:
                bad["results"][0][invalid] = "implemented"
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                probe.interpret(self.marker(bad), expected)

    def test_malformed_or_duplicate_marker_rejected(self):
        expected = [row["id"] for row in catalog()[20:]]
        marker = self.marker(self.valid_payload())
        for body in ("missing", "WSLPE_45_FEASIBILITY_B64=%%%",
                     marker + "\n" + marker):
            with self.subTest(body=body[:40]), self.assertRaises(ValueError):
                probe.interpret(body, expected)

    def test_inventory_mismatch_refuses_before_guest_invocation(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".goad/.venv/bin").mkdir(parents=True)
            for name in ("ansible-playbook", "ansible-inventory"):
                (root / ".goad/.venv/bin" / name).touch()
            base = SimpleNamespace(
                exact_standalone=lambda: (
                    root / "WSLPE/inventory", root / "WSLPE/vars", "172.28.231.31"),
                resolved_inventory_command=lambda exe, inv, var: [
                    str(exe), "-i", str(inv), "-i", str(var), "--list"],
                check_inventory=lambda data, expected: (
                    (_ for _ in ()).throw(ValueError("Wrong inventory"))
                    if data["_meta"]["hostvars"]["ws01"]["ansible_host"] != expected else None
                ),
            )
            bad = SimpleNamespace(returncode=0, stderr="",
                                  stdout=json.dumps({"_meta": {"hostvars": {
                                      "ws01": {"ansible_host": "10.4.10.31"}}}}))
            with patch.object(probe.Path, "home", return_value=root), patch.object(
                    probe, "base_module", return_value=base), patch.object(
                    probe.subprocess, "run", return_value=bad) as invoke:
                with self.assertRaisesRegex(ValueError, "Wrong inventory"):
                    probe.run(probe.build_parser().parse_args(["--execute"]))
                self.assertEqual(invoke.call_count, 1)

    def test_playbook_has_no_windows_mutation_or_north_role_execution(self):
        import yaml
        source = (ROOT / "ansible/wslpe-45-feasibility.yml").read_text()
        plays = yaml.safe_load(source)
        self.assertEqual(len(plays), 2)
        self.assertEqual(plays[0]["hosts"], "localhost")
        self.assertEqual(plays[1]["hosts"], "wslpe")
        remote = plays[1]["tasks"][0]
        self.assertIs(remote["changed_when"], False)
        script = remote["ansible.windows.win_powershell"]["script"]
        for required in ("WSLPE-WS01", "PartOfDomain", "lpe.trainee",
                         "Get-LocalGroupMember", "WSLPE_45_FEASIBILITY_B64=",
                         "GetSecurityDescriptor(4)", "native_api_blocked"):
            self.assertIn(required, script)
        # Prohibit all sensitive APIs or Windows mutators; read-only task is critical.
        for unsafe in ("SetSecurityDescriptor(", "RegisterTaskDefinition(",
                       "Set-ScheduledTask", "New-Service ", "Set-Acl ",
                       "Remove-Item ", "New-Item ", "Start-Service ",
                       "Stop-Service ", "Restart-Service ", "Set-ItemProperty ",
                       "New-ScheduledTask", "Set-LocalGroup", "Set-LocalUser",
                       "icacls.exe /grant", "secedit /configure"):
            self.assertNotIn(unsafe, script)
        self.assertNotIn("roles:", source)
        self.assertNotIn("hosts: domain", source)
        self.assertNotIn("hosts: dc", source)


if __name__ == "__main__":
    unittest.main()
