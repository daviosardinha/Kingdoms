"""Regression contract for AD-aware Kingdoms mode transitions."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAB_MODE = ROOT / "scripts" / "lab-mode.sh"


class LabModeAdReadinessTests(unittest.TestCase):
    def setUp(self):
        self.text = LAB_MODE.read_text(encoding="utf-8")

    def test_provisioning_restarts_dcs_before_members_and_waits_for_identity(self):
        text = self.text

        self.assertIn("configure_windows_nat_provisioning()", text)
        self.assertIn('for vm in "${DOMAIN_CONTROLLERS[@]}"', text)
        self.assertIn('wait_domain_controller_ready "${vm}"', text)
        self.assertIn('for vm in "${DOMAIN_MEMBERS[@]}"', text)
        self.assertIn('wait_domain_member_ready "${vm}"', text)

        fn = text[text.index("configure_windows_nat_provisioning()"):
                  text.index("configure_windows_nat_exercise()")]
        self.assertLess(
            fn.index('for vm in "${DOMAIN_CONTROLLERS[@]}"'),
            fn.index('for vm in "${DOMAIN_MEMBERS[@]}"'),
        )

    def test_exercise_restarts_members_before_domain_controllers(self):
        text = self.text
        fn = text[text.index("configure_windows_nat_exercise()"):
                  text.index("verify_persistent_state()")]

        self.assertLess(
            fn.index('for vm in "${DOMAIN_MEMBERS[@]}"'),
            fn.index('for vm in "${EXERCISE_DOMAIN_CONTROLLERS[@]}"'),
        )
        self.assertIn("preflight_domain_health", text)

    def test_exercise_restart_proves_authenticated_readiness_before_final_disconnect(self):
        text = self.text

        for token in (
            "prove_isolated_guest_ready()",
            'temporarily connecting runtime NAT for authenticated readiness',
            'vmrun -T ws connectNamedDevice',
            'vmrun -T ws disconnectNamedDevice',
            'authenticated post-reboot readiness proven; runtime NAT disconnected',
            'prove_isolated_guest_ready "${vm}" member',
            'prove_isolated_guest_ready "${vm}" dc',
        ):
            self.assertIn(token, text)

        fn = text[text.index("prove_isolated_guest_ready()"):
                  text.index("configure_windows_nat_exercise()")]
        self.assertIn(
            '[[ "${persistent}" == "FALSE" ]]',
            fn,
        )
        self.assertIn("trap cleanup_runtime_nat EXIT", fn)

    def test_winrm_helpers_use_explicit_nested_timeout(self):
        text = self.text
        helpers = text[text.index("vagrant_powershell_ready()"):
                       text.index("ensure_child_dc_time_ready()")]

        self.assertIn('local timeout_seconds="$3"', helpers)
        self.assertEqual(helpers.count('timeout "${timeout_seconds}" vagrant winrm'), 2)
        self.assertNotIn("timeout 90 vagrant winrm", helpers)

    def test_readiness_deadlines_cap_nested_winrm_to_remaining_budget(self):
        text = self.text

        for token in (
            "readonly AD_READINESS_TIMEOUT_SECONDS=300",
            "readonly AD_READINESS_PROBE_TIMEOUT_SECONDS=15",
            "readonly AD_READINESS_RETRY_DELAY_SECONDS=5",
            "readonly AD_REPAIR_TIMEOUT_SECONDS=90",
        ):
            self.assertIn(token, text)

        child = text[text.index("ensure_child_dc_time_ready()"):
                     text.index("wait_domain_controller_ready()")]
        dc = text[text.index("wait_domain_controller_ready()"):
                  text.index("wait_domain_member_ready()")]
        member = text[text.index("wait_domain_member_ready()"):
                      text.index("preflight_domain_health()")]

        for fn in (child, dc, member):
            self.assertIn('local started="${SECONDS}"', fn)
            self.assertIn(
                '(( remaining < probe_timeout )) && probe_timeout="${remaining}"',
                fn,
            )
            self.assertNotIn("for attempt in {1..60}", fn)

        # Original child/DC probes remain bounded by 300s.
        for fn in (child, dc):
            self.assertIn(
                "while (( SECONDS - started < AD_READINESS_TIMEOUT_SECONDS )); do",
                fn,
            )
            self.assertIn("remaining=$((AD_READINESS_TIMEOUT_SECONDS - elapsed))", fn)

        # NORTH members alone can extend the deadline for time-only convergence.
        self.assertIn('local readiness_deadline="${AD_READINESS_TIMEOUT_SECONDS}"', member)
        self.assertIn(
            "while (( SECONDS - started < readiness_deadline )); do", member
        )
        self.assertIn("remaining=$((readiness_deadline - elapsed))", member)
        self.assertIn("readonly AD_MEMBER_TIME_CONVERGENCE_TIMEOUT_SECONDS=600", text)
        reason = member.index('if [[ "${last_state}" == reason=time\\|* ]]; then')
        extension = member.index('readiness_deadline="${AD_MEMBER_TIME_CONVERGENCE_TIMEOUT_SECONDS}"')
        self.assertLess(reason, extension)
        self.assertIn(
            'if [[ "${GOAD_LAB_PROFILE}" == NORTH ]]; then',
            member[reason:extension],
        )

        self.assertIn(
            'vagrant_powershell_capture "${vm}" "${probe_script}" "${probe_timeout}"',
            child,
        )
        self.assertIn(
            'vagrant_powershell_ready "${vm}" "${script}" "${probe_timeout}"',
            dc,
        )
        self.assertIn(
            'vagrant_powershell_capture "${vm}" "${script}" "${probe_timeout}"',
            member,
        )

        # A repair is allowed a larger inner timeout, but never more than the
        # parent readiness window still has left.
        for fn in (child, member):
            self.assertIn('repair_timeout="${AD_REPAIR_TIMEOUT_SECONDS}"', fn)
            self.assertIn(
                '(( remaining < repair_timeout )) && repair_timeout="${remaining}"',
                fn,
            )
            self.assertIn('"${repair_script}" "${repair_timeout}"', fn)

    def test_declared_300s_readiness_budget_is_not_attempt_math(self):
        text = self.text
        relevant = text[text.index("ensure_child_dc_time_ready()"):
                        text.index("preflight_domain_health()")]

        self.assertNotIn("$((attempt * 5))", relevant)
        self.assertNotIn("for attempt in {1..60}", relevant)
        self.assertGreaterEqual(
            relevant.count("AD_READINESS_TIMEOUT_SECONDS - elapsed"),
            2,
        )

        member = relevant[relevant.index("wait_domain_member_ready()"):]
        self.assertGreaterEqual(member.count("readiness_deadline - elapsed"), 3)

    def test_dc_readiness_is_ad_aware_not_merely_winrm(self):
        text = self.text

        for token in (
            "ADPS_LoadDefaultDrive",
            "Get-ADRootDSE",
            "SYSVOL",
            "NETLOGON",
            "nltest.exe '/dsgetdc:",
            "KINGDOMS_DC_RUNTIME_READY",
        ):
            self.assertIn(token, text)

    def test_child_dc_time_hierarchy_is_explicit_and_repaired_before_members(self):
        text = self.text

        for token in (
            'DC_TIME_PARENT_DOMAIN',
            '[GOAD-DC02]="sevenkingdoms.local"',
            'DC_TIME_PARENT_SERVER',
            '[GOAD-DC02]="kingslanding.sevenkingdoms.local"',
            'ensure_child_dc_time_ready()',
            "nltest.exe '/dsgetdc:${parent_domain}' /timeserv /force",
            "w32tm.exe /stripchart /computer:${parent_server}",
            "w32tm.exe /config /syncfromflags:domhier /update",
            "w32tm.exe /resync /rediscover /nowait",
            "KINGDOMS_DC_TIME_REPAIRED",
            "KINGDOMS_DC_TIME_REPAIR_FAILED",
        ):
            self.assertIn(token, text)

        fn = text[text.index("wait_domain_controller_ready()"):
                  text.index("wait_domain_member_ready()")]
        self.assertIn('ensure_child_dc_time_ready "${vm}"', fn)

    def test_recorded_exercise_preflights_child_time_before_member_isolation(self):
        text = self.text
        fn = text[text.index("enter_exercise_mode()"):
                  text.index("enter_provisioning_mode()")]

        self.assertIn("preflight_exercise_time_dependencies", fn)
        self.assertLess(
            fn.index("preflight_exercise_time_dependencies"),
            fn.index("configure_windows_nat_exercise"),
        )

        dep = text[text.index("preflight_exercise_time_dependencies()"):
                   text.index("configure_windows_nat_provisioning()")]
        self.assertIn('prove_isolated_guest_ready "${vm}" dc', dep)
        self.assertIn('DC_TIME_PARENT_DOMAIN', dep)

    def test_child_dc_time_repair_is_bounded_and_never_rewrites_trust(self):
        text = self.text
        fn = text[text.index("ensure_child_dc_time_ready()"):
                  text.index("wait_domain_controller_ready()")]

        self.assertIn("repair_attempted == 0", fn)
        self.assertIn("consecutive_source_failures >= 6", fn)
        self.assertIn("syncAttempt -le 12", fn)

        for forbidden in (
            "Reset-ComputerMachinePassword",
            "/sc_reset:",
            "netdom resetpwd",
        ):
            self.assertNotIn(forbidden, fn)

    def test_member_readiness_proves_trust_account_lookup_and_domain_time(self):
        text = self.text

        for token in (
            "Test-ComputerSecureChannel -Server",
            "System.Security.Principal.NTAccount",
            "Translate([System.Security.Principal.SecurityIdentifier])",
            "w32tm.exe /query /source",
            "expected=${dc}",
            "KINGDOMS_MEMBER_RUNTIME_READY",
        ):
            self.assertIn(token, text)

    def test_member_readiness_emits_exact_failure_class(self):
        text = self.text
        fn = text[text.index("wait_domain_member_ready()"):
                  text.index("preflight_domain_health()")]

        for marker in (
            "KINGDOMS_MEMBER_NOT_READY|reason=dns",
            "KINGDOMS_MEMBER_NOT_READY|reason=secure_channel",
            "KINGDOMS_MEMBER_NOT_READY|reason=account_translation",
            "KINGDOMS_MEMBER_NOT_READY|reason=netlogon_session",
            "KINGDOMS_MEMBER_NOT_READY|reason=time|source=",
            "reason=transport",
        ):
            self.assertIn(marker, fn)

        self.assertIn(
            'did not regain domain identity readiness for ${domain} within ${readiness_deadline}s; ${last_state}; time_repair_attempted=${time_repair_attempted}',
            fn,
        )

    def test_member_lifecycle_uses_one_bounded_time_only_repair(self):
        text = self.text
        fn = text[text.index("wait_domain_member_ready()"):
                  text.index("preflight_domain_health()")]

        for token in (
            "consecutive_time_failures >= time_repair_threshold",
            "time_repair_attempted == 0",
            "w32tm.exe /config /syncfromflags:domhier /update",
            "nltest.exe '/dsgetdc:${domain}' /timeserv /force",
            "w32tm.exe /stripchart /computer:${dc}",
            "nltest.exe '/sc_query:${domain}'",
            "Restart-Service W32Time -Force",
            "w32tm.exe /resync /rediscover /nowait",
            "KINGDOMS_MEMBER_TIME_REPAIRED",
            "KINGDOMS_MEMBER_TIME_REPAIR_FAILED",
        ):
            self.assertIn(token, fn)

        self.assertIn("local time_repair_threshold=6", fn)
        self.assertIn('[[ "${GOAD_LAB_PROFILE}" == NORTH ]] && time_repair_threshold=18', fn)
        self.assertIn("time_repair_attempted=1", fn)

        # Normal lifecycle may recover W32Time only. Directory trust repair
        # remains an explicit maintenance/provisioning operation.
        for forbidden in (
            "Reset-ComputerMachinePassword",
            "/sc_reset:",
            "netdom resetpwd",
        ):
            self.assertNotIn(forbidden, fn)

    def test_time_repair_requires_identity_probe_to_reach_time_stage(self):
        text = self.text
        fn = text[text.index("wait_domain_member_ready()"):
                  text.index("preflight_domain_health()")]

        self.assertLess(
            fn.index("Resolve-DnsName '${dc}'"),
            fn.index("Test-ComputerSecureChannel -Server '${dc}'"),
        )
        self.assertLess(
            fn.index("Test-ComputerSecureChannel -Server '${dc}'"),
            fn.index("System.Security.Principal.NTAccount"),
        )
        self.assertLess(
            fn.index("System.Security.Principal.NTAccount"),
            fn.index("nltest.exe '/sc_query:${domain}'"),
        )
        self.assertLess(
            fn.index("nltest.exe '/sc_query:${domain}'"),
            fn.index("w32tm.exe /query /source"),
        )
        self.assertIn(
            'if [[ "${last_state}" == reason=time\\|* ]]; then',
            fn,
        )

    def test_member_time_recovery_requires_live_netlogon_session(self):
        text = self.text
        fn = text[text.index("wait_domain_member_ready()"):
                  text.index("preflight_domain_health()")]

        for token in (
            "KINGDOMS_MEMBER_NOT_READY|reason=netlogon_session",
            "KINGDOMS_MEMBER_TIME_REPAIR_FAILED|stage=netlogon_session",
            "KINGDOMS_MEMBER_TIME_REPAIR_FAILED|stage=netlogon_session_lost",
            "netlogon_session=ready",
        ):
            self.assertIn(token, fn)

    def test_time_repair_failure_marker_is_not_hidden(self):
        text = self.text
        fn = text[text.index("wait_domain_member_ready()"):
                  text.index("preflight_domain_health()")]

        self.assertIn(
            "KINGDOMS_MEMBER_TIME_(REPAIRED|REPAIR_FAILED)",
            fn,
        )
        self.assertIn(
            'elif [[ "${marker}" == KINGDOMS_MEMBER_TIME_REPAIR_FAILED\\|* ]]; then',
            fn,
        )
        self.assertIn(
            'bounded domain-time recovery failed: ${marker}',
            fn,
        )
        self.assertNotIn(
            "time-recovery command returned without a success marker",
            fn,
        )


if __name__ == "__main__":
    unittest.main()