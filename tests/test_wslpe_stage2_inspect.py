"""Mock/fixture-only tests for WSLPE Stage 2 guest inspection.

No VMware, Vagrant, WinRM or Windows commands are executed by these tests.
"""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/wslpe-stage2-inspect.py"
SPEC = importlib.util.spec_from_file_location("wslpe_stage2_inspector", SOURCE)
assert SPEC and SPEC.loader
STAGE2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STAGE2)


def guest_data():
    return {
        "Name": "WSLPE-WS01", "ProductType": 1,
        "OSCaption": "Microsoft Windows 10 Pro",
        "WindowsVersion": "10.0.19045", "WindowsBuild": "19045",
        "DomainJoined": False, "UAC": 1,
        "Firewall": [
            {"Name": "Domain", "Enabled": True},
            {"Name": "Private", "Enabled": True},
            {"Name": "Public", "Enabled": True},
        ],
        "DefenderService": True, "DefenderAntivirus": True,
        "IPv4": [
            {"IPAddress": "192.168.213.104", "InterfaceIndex": 11, "PrefixLength": 24},
            {"IPAddress": "172.28.231.31", "InterfaceIndex": 12, "PrefixLength": 24},
        ],
        "Interfaces": [
            {"Name": "Ethernet0", "InterfaceIndex": 11, "Status": "Up"},
            {"Name": "Ethernet1", "InterfaceIndex": 12, "Status": "Up"},
        ],
        "DefaultRoutes": [
            {"InterfaceIndex": 11, "NextHop": "192.168.213.2"}
        ],
        "LearnerExists": False,
        "LicenseProducts": [{
            "Name": "Windows(R), Professional edition",
            "Description": "Windows(R) Operating System, RETAIL channel",
            "LicenseStatus": 1,
            "GracePeriodRemaining": 0,
        }],
        "LicenseShutdownEvidence": [],
    }


def manifest(name):
    return {
        "id": name, "lab": "WSLPE", "provider": "vmware",
        "provisioner": "local", "status": "ready for provisioning",
        "ip_range": "172.28.231", "extensions": [], "is_default": False,
    }


class WslpeStage2InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.instance = self.workspace / "wslpe-fixture"
        self.instance.mkdir()
        (self.instance / "instance.json").write_text(
            json.dumps(manifest(self.instance.name)), encoding="utf-8"
        )

    def test_exact_native_provided_instance(self):
        found, info = STAGE2.find_instance(self.workspace)
        self.assertEqual(found, self.instance)
        self.assertEqual(info["status"], "ready for provisioning")
        self.assertEqual(info["ip_range"], "172.28.231")

    def test_rejects_duplicate_instance_or_wrong_lab_status(self):
        other = self.workspace / "wslpe-other"
        other.mkdir()
        (other / "instance.json").write_text(
            json.dumps(manifest(other.name)), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "Exactly one"):
            STAGE2.find_instance(self.workspace)
        (other / "instance.json").unlink()
        original = manifest(self.instance.name)
        original["status"] = "installed"
        (self.instance / "instance.json").write_text(json.dumps(original))
        with self.assertRaisesRegex(ValueError, "status"):
            STAGE2.find_instance(self.workspace)

    def test_refuses_symlinked_workspace(self):
        other = self.root / "other"
        other.mkdir()
        link = self.root / "linked"
        link.symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            STAGE2.find_instance(link)

    def test_parse_actual_vmware_adapter_types(self):
        vmx_text = '''
ethernet0.present = "TRUE"
ethernet0.connectionType = "nat"
ethernet0.generatedAddress = "00:0c:29:00:11:22"
ethernet1.present = "TRUE"
ethernet1.connectionType = "custom"
ethernet1.vnet = "vmnet2"
ethernet2.present = "FALSE"
ethernet2.connectionType = "nat"
'''
        adapters = STAGE2.vmx_network_adapters(vmx_text)
        self.assertEqual(len(adapters), 2)
        self.assertEqual(adapters[0]["type"], "nat")
        self.assertEqual(adapters[1]["vnet"], "vmnet2")

    def test_exact_vm_registration_checked_against_vmrun(self):
        state = (self.instance / "provider/.vagrant/machines/WSLPE-WS01"
                 "/vmware_desktop")
        state.mkdir(parents=True)
        vmx = self.root / "windows_10.vmx"
        vmx.write_text("displayName = WSLPE")
        (state / "id").write_text(str(vmx))
        with patch.object(STAGE2, "read_command", return_value=(
            f"Total running VMs: 1\n{vmx}\n"
        )) as command:
            self.assertEqual(STAGE2.locate_registered_vm(self.instance), vmx)
        command.assert_called_once_with(["vmrun", "-T", "ws", "list"])

    def test_north_vmx_registration_blocked_without_vmrun(self):
        state = (self.instance / "provider/.vagrant/machines/WSLPE-WS01"
                 "/vmware_desktop")
        state.mkdir(parents=True)
        vmx = self.root / "GOAD-WS01.vmx"
        vmx.write_text("NORTH fixture")
        (state / "id").write_text(str(vmx))
        with patch.object(STAGE2, "read_command",
                          side_effect=AssertionError("do not inspect vmrun")):
            with self.assertRaisesRegex(ValueError, "NORTH"):
                STAGE2.locate_registered_vm(self.instance)

    def test_vagrant_port_inspection_is_read_only(self):
        port_output = "5985 (guest) => 55985 (host)\n"
        with patch.object(STAGE2.os, "geteuid", return_value=1000), \
             patch.object(STAGE2, "read_command",
                          return_value=port_output) as command:
            self.assertEqual(STAGE2.forwarded_winrm_port(self.instance), 55985)
        self.assertEqual(
            command.call_args.args[0],
            ["vagrant", "port", "WSLPE-WS01"],
        )

    def test_root_port_lookup_uses_sudo_operator_vagrant_context(self):
        import pwd
        from types import SimpleNamespace
        owner = self.instance.stat().st_uid
        # Owner fixture is the actual temp dir's owner. The username is
        # looked up from pwd, never interpolated from a shell string.
        with patch.object(STAGE2.os, "geteuid", return_value=0), \
             patch.dict(STAGE2.os.environ, {"SUDO_UID": str(owner)}), \
             patch.object(pwd, "getpwuid",
                          return_value=SimpleNamespace(pw_name="operator")):
            if owner == 0:
                with self.assertRaisesRegex(ValueError, "owner"):
                    STAGE2.vagrant_port_command(self.instance)
            else:
                self.assertEqual(
                    STAGE2.vagrant_port_command(self.instance),
                    ["sudo", "-H", "-u", "operator", "--",
                     "vagrant", "port", "WSLPE-WS01"],
                )

    def test_root_port_lookup_rejects_wrong_or_missing_sudo_identity(self):
        owner = self.instance.stat().st_uid
        for claimed_uid in ("", "not-an-id", str(owner + 1)):
            with self.subTest(uid=claimed_uid), \
                 patch.object(STAGE2.os, "geteuid", return_value=0), \
                 patch.dict(STAGE2.os.environ,
                            {"SUDO_UID": claimed_uid}):
                with self.assertRaisesRegex(ValueError, "owner"):
                    STAGE2.vagrant_port_command(self.instance)

    def test_root_port_lookup_delegates_only_port_read_not_firewall(self):
        import pwd
        from types import SimpleNamespace
        owner = self.instance.stat().st_uid
        if owner == 0:
            self.skipTest("unprivileged temp directory ownership required")
        with patch.object(STAGE2.os, "geteuid", return_value=0), \
             patch.dict(STAGE2.os.environ, {"SUDO_UID": str(owner)}), \
             patch.object(pwd, "getpwuid",
                          return_value=SimpleNamespace(pw_name="operator")), \
             patch.object(STAGE2, "read_command",
                          return_value="5985 (guest) => 2210 (host)") as query:
            self.assertEqual(STAGE2.forwarded_winrm_port(self.instance), 2210)
        query.assert_called_once_with(
            ["sudo", "-H", "-u", "operator", "--", "vagrant",
             "port", "WSLPE-WS01"],
            cwd=self.instance / "provider",
        )

    def test_winrm_forwarding_bound_only_to_loopback(self):
        listeners = (
            "LISTEN 0 128 127.0.0.1:55985 0.0.0.0:*\n"
            "LISTEN 0 128 [::1]:55985 [::]:*\n"
        )
        with patch.object(STAGE2, "read_command",
                          return_value=listeners) as command:
            scope = STAGE2.inspect_management_port_binding(55985)
            self.assertIn("127.0.0.1", scope)
            self.assertIn("::1", scope)
            command.assert_called_once_with(["ss", "-H", "-ltn"])

    def test_winrm_wildcard_binding_fails_closed(self):
        for host in ("0.0.0.0", "*", "[::]", "192.168.76.160"):
            with self.subTest(host=host), patch.object(
                STAGE2, "read_command",
                return_value=f"LISTEN 0 128 {host}:55985 0.0.0.0:*\n",
            ):
                with self.assertRaisesRegex(ValueError, "exposed"):
                    STAGE2.inspect_management_port_binding(55985)

    def test_unproven_winrm_port_bind_fails_closed(self):
        with patch.object(STAGE2, "read_command",
                          return_value="LISTEN 0 128 127.0.0.1:44000 0.0.0.0:*"):
            with self.assertRaisesRegex(ValueError, "Cannot establish"):
                STAGE2.inspect_management_port_binding(55985)

    def test_guarded_vmnet_nat_wildcard_accepted_only_with_verified_live_evidence(self):
        from test_wslpe_winrm_guard import nft_fixture
        listener = ('LISTEN 0 20 0.0.0.0:2210 0.0.0.0:* '
                    'users:(("vmnet-nat",pid=2162896,fd=9))')
        # First read_command: unprivileged ss listing used by the strict
        # loopback check; then privileged nft JSON and privileged ss owner.
        with patch.object(STAGE2, "read_command",
                          side_effect=[listener, nft_fixture(), listener]) as call, \
             patch.object(STAGE2.os, "geteuid", return_value=0):
            result = STAGE2.inspect_management_access(2210)
        self.assertIn("non-loopback TCP/2210 drop verified", result)
        self.assertEqual(call.call_count, 3)

    def test_wildcard_listener_without_exact_firewall_rule_stays_blocked(self):
        from test_wslpe_winrm_guard import nft_fixture
        listener = ('LISTEN 0 20 0.0.0.0:2210 0.0.0.0:* '
                    'users:(("vmnet-nat",pid=2162896,fd=9))')
        with patch.object(
            STAGE2, "read_command",
            side_effect=[listener, nft_fixture(2211), listener],
        ), patch.object(STAGE2.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(ValueError, "lacks the exact"):
                STAGE2.inspect_management_access(2210)

    def test_wildcard_rule_not_accepted_if_owner_is_unknown(self):
        from test_wslpe_winrm_guard import nft_fixture
        listener = "LISTEN 0 20 0.0.0.0:2210 0.0.0.0:*"
        with patch.object(
            STAGE2, "read_command",
            side_effect=[listener, nft_fixture(), listener],
        ), patch.object(STAGE2.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(ValueError, "ownership"):
                STAGE2.inspect_management_access(2210)

    def test_guest_baseline_and_distinct_nat_exercise_ips_pass(self):
        ok, failed = STAGE2.evaluate_windows(guest_data(), "172.28.231")
        self.assertEqual(failed, [])
        self.assertGreaterEqual(len(ok), 7)

    def test_non_evaluation_licensed_windows_product_passes(self):
        guest = guest_data()
        ok, details = STAGE2.evaluate_license(guest)
        self.assertTrue(ok)
        self.assertTrue(any("non-evaluation" in x for x in details))
        self.assertEqual(STAGE2.evaluate_windows(guest, "172.28.231")[1], [])

    def test_valid_time_based_evaluation_with_training_grace_passes(self):
        guest = guest_data()
        guest["LicenseProducts"] = [{
            "Name": "Windows(R), Enterprise Evaluation edition",
            "Description": "Windows(R) Operating System, TIMEBASED_EVAL channel",
            "LicenseStatus": 2,
            "GracePeriodRemaining": 43200,
        }]
        self.assertTrue(STAGE2.evaluate_license(guest)[0])
        self.assertEqual(STAGE2.evaluate_windows(guest, "172.28.231")[1], [])

    def test_expired_or_nearly_expired_eval_blocks_course(self):
        for grace in (0, -1, 30, 1439, None, "180"):
            with self.subTest(grace=grace):
                guest = guest_data()
                guest["LicenseProducts"] = [{
                    "Name": "Windows(R), Enterprise Evaluation edition",
                    "Description": "TIMEBASED_EVAL channel",
                    "LicenseStatus": 0,
                    "GracePeriodRemaining": grace,
                }]
                self.assertFalse(STAGE2.evaluate_license(guest)[0])
                self.assertTrue(any("Windows licensing" in x
                                    for x in STAGE2.evaluate_windows(
                                        guest, "172.28.231")[1]))

    def test_unknown_or_unlicensed_windows_fails_closed(self):
        for products in (
            [], None, "UNKNOWN",
            [{"Name": "Windows(R), Professional edition",
              "Description": "RETAIL channel",
              "LicenseStatus": 0, "GracePeriodRemaining": 0}],
            [{"Name": "Office", "Description": "TIMEBASED_EVAL",
              "LicenseStatus": 1, "GracePeriodRemaining": 8000}],
        ):
            with self.subTest(products=products):
                guest = guest_data()
                guest["LicenseProducts"] = products
                self.assertFalse(STAGE2.evaluate_license(guest)[0])

    def test_historical_wlms_shutdown_is_evidence_not_permanent_failure(self):
        guest = guest_data()
        guest["LicenseShutdownEvidence"] = [
            {"Id": 1074, "ProviderName": "User32",
             "TimeCreated": "2026-10-14"}
        ]
        ok, details = STAGE2.evaluate_license(guest)
        self.assertTrue(ok)
        self.assertTrue(any("Historical" in x for x in details))
        self.assertTrue(any("current license" in x for x in details))

    def test_licensing_probe_only_reads_cim_and_shutdown_event_log(self):
        script = STAGE2.WINDOWS_READ_ONLY
        self.assertIn("SoftwareLicensingProduct", script)
        self.assertIn("Get-WinEvent", script)
        self.assertIn("LicenseShutdownEvidence", script)
        for forbidden in ("slmgr.vbs", "/rearm", "Restart-Computer",
                          "Set-Service", "Stop-Service"):
            self.assertNotIn(forbidden, script)

    def test_firewall_cim_enum_true_strings_are_accepted(self):
        """A Windows CIM GpoBoolean value can serialize as JSON text."""
        guest = guest_data()
        for profile in guest["Firewall"]:
            profile["Enabled"] = "True"
        guest["NetworkProfiles"] = [{
            "InterfaceAlias": "Ethernet1", "NetworkCategory": "Public"
        }]
        ok, evidence = STAGE2.firewall_profile_evidence(guest)
        self.assertTrue(ok)
        self.assertEqual(len([x for x in evidence if "Firewall " in x]), 3)
        self.assertTrue(any("category=Public" in x for x in evidence))
        _, failed = STAGE2.evaluate_windows(guest, "172.28.231")
        self.assertEqual(failed, [])

    def test_firewall_false_strings_do_not_pass_through_python_truthiness(self):
        guest = guest_data()
        guest["Firewall"][2]["Enabled"] = "False"
        ok, details = STAGE2.firewall_profile_evidence(guest)
        self.assertFalse(ok)
        self.assertTrue(any("Public: Enabled=False" in x for x in details))
        _, failed = STAGE2.evaluate_windows(guest, "172.28.231")
        self.assertIn("All Windows firewall profiles enabled", failed)

    def test_firewall_notconfigured_missing_and_duplicate_profiles_fail_closed(self):
        for value in ("NotConfigured", "", None, 1, 0):
            with self.subTest(value=value):
                guest = guest_data()
                guest["Firewall"][0]["Enabled"] = value
                self.assertFalse(STAGE2.firewall_profile_evidence(guest)[0])
        for replacement in (
            [guest_data()["Firewall"][0]] * 3,
            guest_data()["Firewall"][:2],
            None,
        ):
            with self.subTest(replacement=replacement):
                guest = guest_data()
                guest["Firewall"] = replacement
                self.assertFalse(STAGE2.firewall_profile_evidence(guest)[0])

    def test_firewall_details_are_read_only_and_include_each_profile(self):
        raw = STAGE2.WINDOWS_READ_ONLY
        self.assertIn("Get-NetFirewallProfile", raw)
        self.assertIn("Get-NetConnectionProfile", raw)
        self.assertIn("DefaultInboundAction", raw)
        self.assertNotIn("Set-NetFirewallProfile", raw)
        self.assertNotIn("Enable-NetFirewallRule", raw)

    def test_guest_domain_join_firewall_and_exercise_default_route_block(self):
        guest = guest_data()
        guest["DomainJoined"] = True
        guest["Firewall"][1]["Enabled"] = False
        guest["DefaultRoutes"] = [{"InterfaceIndex": 12, "NextHop": "172.28.231.1"}]
        passed, failed = STAGE2.evaluate_windows(guest, "172.28.231")
        self.assertTrue(any("Active Directory" in text for text in failed))
        self.assertTrue(any("firewall" in text.lower() for text in failed))
        self.assertTrue(any("default" in text.lower() for text in failed))
        self.assertTrue(passed)

    def test_other_windows_versions_cannot_masquerade_as_win10(self):
        guest = guest_data()
        guest["OSCaption"] = "Microsoft Windows 11 Pro"
        _, failed = STAGE2.evaluate_windows(guest, "172.28.231")
        self.assertTrue(any("Windows 10" in x for x in failed))

    def test_guest_wrong_ip_and_disabled_defender_block(self):
        guest = guest_data()
        guest["IPv4"] = [{"IPAddress": "172.28.230.31",
                          "InterfaceIndex": 12, "PrefixLength": 24}]
        guest["DefenderAntivirus"] = False
        _, failed = STAGE2.evaluate_windows(guest, "172.28.231")
        self.assertTrue(any("172.28.231.31" in x for x in failed))
        self.assertTrue(any("Defender" in x for x in failed))

    def test_windows_probe_uses_direct_instance_ip_not_nat_forward(self):
        data = guest_data()
        response = SimpleNamespace(
            status_code=0,
            std_out=("WSLPE_AUDIT_JSON=" + json.dumps(data)).encode("utf-8"),
        )
        session = SimpleNamespace(run_ps=Mock(return_value=response))
        fake_winrm = SimpleNamespace(Session=Mock(return_value=session))
        with patch.dict(sys.modules, {"winrm": fake_winrm}):
            observed = STAGE2.windows_probe("172.28.231.31")
        self.assertEqual(observed, data)
        fake_winrm.Session.assert_called_once()
        self.assertEqual(
            fake_winrm.Session.call_args.args[0],
            "http://172.28.231.31:5985/wsman",
        )
        self.assertEqual(fake_winrm.Session.call_args.kwargs["transport"], "ntlm")
        session.run_ps.assert_called_once_with(STAGE2.WINDOWS_READ_ONLY)

    def test_windows_probe_rejects_public_loopback_north_and_invalid_ips(self):
        for target in ("127.0.0.1", "8.8.8.8", "10.4.10.31",
                       "not-an-ip", "::1", None):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    STAGE2.windows_probe(target)

    def test_windows_probe_script_contains_only_read_operations(self):
        powershell = STAGE2.WINDOWS_READ_ONLY.lower()
        for forbidden in (
            "set-net", "new-net", "remove-net", "new-localuser",
            "set-itemproperty", "new-item", "invoke-expression",
            "restart-computer", "stop-service", "start-process",
        ):
            self.assertNotIn(forbidden, powershell)
        self.assertIn("convertto-json", powershell)
        self.assertIn("get-mpcomputerstatus", powershell)


if __name__ == "__main__":
    unittest.main()
